"""Low-latency real-time audio playback engine for SoundMaster.

Uses continuous WASAPI / PortAudio output streams in the background to eliminate
device-initialization delay. Audio buffers are pre-decoded into RAM for near-zero
latency (sub-millisecond trigger time on click).
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from threading import RLock, Thread
from typing import Any

import numpy as np

try:
    import sounddevice as sd
    import soundfile as sf

    SOUNDDEVICE_AVAILABLE = True
except Exception:  # noqa: BLE001
    sd = None
    sf = None
    SOUNDDEVICE_AVAILABLE = False

logger = logging.getLogger(__name__)


def load_audio_pcm(path: Path | str, target_sr: int = 44100) -> tuple[np.ndarray, int]:
    """Pre-decode audio file into a 2-channel float32 PCM numpy array."""

    if not SOUNDDEVICE_AVAILABLE or sf is None:
        raise RuntimeError("soundfile library missing")

    data, sr = sf.read(str(path), dtype="float32")
    if data.ndim == 1:
        data = np.column_stack((data, data))
    elif data.ndim == 2 and data.shape[1] == 1:
        data = np.column_stack((data[:, 0], data[:, 0]))
    elif data.ndim == 2 and data.shape[1] > 2:
        data = data[:, :2]

    if sr != target_sr:
        num_samples = round(len(data) * target_sr / sr)
        indices = np.linspace(0, len(data) - 1, num_samples)
        data = np.array(
            [np.interp(indices, np.arange(len(data)), data[:, c]) for c in range(2)]
        ).T.astype(np.float32)

    return data.astype(np.float32), target_sr


class ContinuousAudioOutput:
    """A background stream that stays open to feed WASAPI with zero startup latency."""

    def __init__(self, device_name_or_index: Any = None, samplerate: int = 44100) -> None:
        self.samplerate = samplerate
        self.device = device_name_or_index
        self._closed = False
        self._lock = RLock()
        self._playing_buffers: list[dict[str, Any]] = []
        self._stream: Any = None
        self._retry_pending = False
        self._retry_thread: Thread | None = None
        # Called (from the audio thread) when the last queued buffer finishes
        # playing. The UI uses this to release the "Stop" button state.
        self._completion_callback: Any = None
        self._start_stream()

    def _audio_callback(
        self, outdata: np.ndarray, frames: int, time_info: Any, status: Any
    ) -> None:
        outdata.fill(0)
        if getattr(self, "_closed", False):
            return

        acquired = self._lock.acquire(blocking=False)
        if not acquired:
            return

        try:
            if not self._playing_buffers:
                return

            was_playing = bool(self._playing_buffers)
            active: list[dict[str, Any]] = []
            mix_buffer = np.zeros_like(outdata)

            for item in self._playing_buffers:
                pcm = item["pcm"]
                idx = item["idx"]
                end = idx + frames

                if end <= len(pcm):
                    mix_buffer += pcm[idx:end]
                    item["idx"] = end
                    active.append(item)
                else:
                    remaining = len(pcm) - idx
                    if remaining > 0:
                        mix_buffer[:remaining] += pcm[idx:]

            np.clip(mix_buffer, -1.0, 1.0, out=outdata)
            self._playing_buffers = active
            finished = was_playing and not active
        finally:
            self._lock.release()

        if finished:
            callback = self._completion_callback
            if callback is not None:
                callback()

    def _start_stream(self) -> None:
        if not SOUNDDEVICE_AVAILABLE or sd is None or self._closed:
            return
        try:
            device_idx = self._resolve_device_index(self.device)
            # latency="low" halves the WASAPI shared-mode buffer (~180 ms down
            # to ~90 ms on a typical device), which is the dominant audible
            # delay between the click and the sound leaving the speakers. The
            # 512-sample callback is unaffected and keeps CPU usage low.
            self._stream = sd.OutputStream(
                device=device_idx,
                channels=2,
                samplerate=self.samplerate,
                blocksize=512,
                latency="low",
                callback=self._audio_callback,
            )
            self._stream.start()
            self._retry_pending = False
        except Exception as err:  # noqa: BLE001 - audio backend boundary.
            logger.warning(f"ContinuousAudioOutput stream start error: {err}")
            self._stream = None
            self._start_retry_loop()

    def _start_retry_loop(self) -> None:
        """Re-open the stream in the background after a failure.

        A WASAPI open takes ~0.5-1 s. Repeating it synchronously on every click
        would freeze the UI; instead the failed open is retried off-thread so
        the stream self-heals (device re-plugged, driver busy, etc.) and the
        next click finds it warm.
        """

        if self._closed or self._retry_pending or not SOUNDDEVICE_AVAILABLE or sd is None:
            return
        self._retry_pending = True

        def _retry() -> None:
            try:
                while not self._closed:
                    time.sleep(1.0)
                    with self._lock:
                        if self._closed:
                            return
                        if self._stream is not None and getattr(self._stream, "active", False):
                            self._retry_pending = False
                            return
                        self._start_stream()
                        if self._stream is not None and getattr(self._stream, "active", False):
                            self._retry_pending = False
                            return
            finally:
                self._retry_pending = False

        self._retry_thread = Thread(target=_retry, daemon=True, name="soundmaster-audio-retry")
        self._retry_thread.start()

    def _resolve_device_index(self, name_or_idx: Any) -> Any:
        if name_or_idx is None or isinstance(name_or_idx, int):
            return name_or_idx
        name_str = str(name_or_idx).strip().lower()
        if not name_str or not sd:
            return None
        try:
            for i, dev in enumerate(sd.query_devices()):
                if dev["max_output_channels"] > 0 and name_str in dev["name"].lower():
                    return i
        except Exception:  # noqa: BLE001, S110 - probing devices must never raise.
            pass
        return None

    def set_device(self, device_name_or_index: Any) -> None:
        stream_to_close = None
        with self._lock:
            self.stop_all()
            stream_to_close = self._stream
            self._stream = None
            self.device = device_name_or_index

        if stream_to_close is not None:
            try:
                stream_to_close.stop()
                stream_to_close.close()
            except Exception:  # noqa: BLE001, S110 - probing devices must never raise.
                pass

        with self._lock:
            if not self._closed:
                self._start_stream()

    def play(self, pcm: np.ndarray) -> bool:
        with self._lock:
            if self._closed:
                return False
            if self._stream is None or not getattr(self._stream, "active", False):
                if self._retry_pending:
                    # A background open is already in flight: give it a short
                    # window instead of blocking the UI for a full WASAPI open.
                    deadline = time.monotonic() + 0.15
                    while self._retry_pending and time.monotonic() < deadline:
                        time.sleep(0.01)
                else:
                    # First failure after a healthy stream: one synchronous
                    # attempt (handed over to the retry loop if it fails).
                    self._start_stream()
            if self._stream is None or not getattr(self._stream, "active", False):
                # No live stream means the audio would silently never be heard;
                # report failure so the caller can fall back to QMediaPlayer
                # instead of freezing the UI.
                return False
            self._playing_buffers.append({"pcm": pcm, "idx": 0})
            return True

    def set_completion_callback(self, callback: Any) -> None:
        """Register a callable invoked (audio thread) when playback drains."""

        self._completion_callback = callback

    def stop_all(self) -> None:
        with self._lock:
            self._playing_buffers.clear()

    def is_playing(self) -> bool:
        with self._lock:
            return len(self._playing_buffers) > 0

    def is_active(self) -> bool:
        with self._lock:
            return self._stream is not None and getattr(self._stream, "active", False)

    def close(self) -> None:
        stream_to_close = None
        with self._lock:
            self._closed = True
            self._retry_pending = False
            self.stop_all()
            stream_to_close = self._stream
            self._stream = None

        if stream_to_close is not None:
            try:
                stream_to_close.stop()
                stream_to_close.close()
            except Exception:  # noqa: BLE001, S110 - probing devices must never raise.
                pass
        if self._retry_thread is not None:
            self._retry_thread.join(timeout=2.0)
            self._retry_thread = None


class FastAudioEngine:
    """Master engine handling zero-latency playback for local and virtual outputs."""

    def __init__(self, headset_device: Any = None, virtual_device: Any = None) -> None:
        self._pcm_cache: dict[str, np.ndarray] = {}
        self.headset_output = ContinuousAudioOutput(headset_device)
        self.virtual_output = ContinuousAudioOutput(virtual_device)

    def preload_sound(self, path: Path | str) -> bool:
        key = str(Path(path).resolve())
        if key in self._pcm_cache:
            return True
        try:
            pcm, _ = load_audio_pcm(key)
            self._pcm_cache[key] = pcm
            return True
        except Exception as err:  # noqa: BLE001 - audio backend boundary.
            logger.warning(f"Preload audio failed for {path}: {err}")
            return False

    def set_devices(self, headset_device: Any = None, virtual_device: Any = None) -> None:
        """Re-point both output streams after the user changes the audio settings."""

        self.headset_output.set_device(headset_device)
        self.virtual_output.set_device(virtual_device)

    def set_completion_callback(self, callback: Any) -> None:
        """Register a callable fired (audio thread) when headset playback ends.

        The virtual output intentionally shares the same callback: the UI only
        tracks one active preview at a time, and the headset stream is the one
        whose "Stop" button state must be released when the sound ends.
        """

        self.headset_output.set_completion_callback(callback)

    def play(self, path: Path | str, virtual: bool = False) -> bool:
        key = str(Path(path).resolve())
        pcm = self._pcm_cache.get(key)
        if pcm is None:
            try:
                pcm, _ = load_audio_pcm(key)
                self._pcm_cache[key] = pcm
            except Exception as err:  # noqa: BLE001 - audio backend boundary.
                logger.error(f"Play failed for {path}: {err}")
                return False

        output = self.virtual_output if virtual else self.headset_output
        return output.play(pcm)

    def stop(self, virtual: bool = False) -> None:
        output = self.virtual_output if virtual else self.headset_output
        output.stop_all()

    def is_playing(self, virtual: bool = False) -> bool:
        output = self.virtual_output if virtual else self.headset_output
        return output.is_playing()

    def is_active(self, virtual: bool = False) -> bool:
        output = self.virtual_output if virtual else self.headset_output
        return output.is_active()

    def close(self) -> None:
        self.headset_output.close()
        self.virtual_output.close()

"""Optional Windows audio capture helpers for voice-reference recording."""

from __future__ import annotations

import os
import queue
import wave
from contextlib import suppress
from pathlib import Path
from threading import Event
from typing import Any


def _wasapi_output_candidates(sounddevice: Any) -> list[tuple[int, dict[str, Any]]]:
    """Return output endpoints exposed by PortAudio's Windows WASAPI backend."""

    devices = sounddevice.query_devices()
    hostapis = sounddevice.query_hostapis()
    wasapi_hostapis = {
        index
        for index, hostapi in enumerate(hostapis)
        if "wasapi" in str(hostapi.get("name", "")).lower()
    }
    if not wasapi_hostapis:
        return []
    return [
        (index, device)
        for index, device in enumerate(devices)
        if int(device.get("max_output_channels", 0)) > 0
        and int(device.get("hostapi", -1)) in wasapi_hostapis
    ]


def wasapi_output_devices(sounddevice: Any) -> list[tuple[str, int]]:
    """Return stable display names and PortAudio indexes for WASAPI outputs."""

    return [
        (str(device.get("name", "Sortie Windows")), index)
        for index, device in _wasapi_output_candidates(sounddevice)
    ]


def resolve_wasapi_output_device(
    sounddevice: Any, requested: int | str | None = None
) -> int:
    """Resolve a UI output description to a validated WASAPI output index."""

    candidates = _wasapi_output_candidates(sounddevice)
    if isinstance(requested, int):
        if any(index == requested for index, _device in candidates):
            return requested
        raise RuntimeError("Le périphérique sélectionné n’est pas une sortie WASAPI valide.")

    if requested:
        requested_lower = requested.strip().lower()
        for index, device in candidates:
            if str(device.get("name", "")).strip().lower() == requested_lower:
                return index
        raise RuntimeError(f"Sortie WASAPI introuvable : {requested}")

    if candidates:
        default_device = getattr(sounddevice, "default", None)
        default_pair = getattr(default_device, "device", None)
        default_output = default_pair[1] if isinstance(default_pair, (tuple, list)) else None
        for index, _device in candidates:
            if index == default_output:
                return index
        return candidates[0][0]

    raise RuntimeError("Aucune sortie Windows WASAPI compatible n’a été détectée.")


class SystemAudioRecorder:
    """Capture a Windows output endpoint through WASAPI loopback when available."""

    def __init__(self, output_path: Path, device: int | str | None = None) -> None:
        self.output_path = output_path
        self.device = device
        self._stop_event = Event()
        self._stream: Any = None

    @staticmethod
    def capability_error() -> str | None:
        """Return a user-facing reason when WASAPI loopback is unavailable."""

        if os.name != "nt":
            return "La capture de sortie est disponible uniquement sous Windows."
        try:
            import sounddevice as sd
        except ImportError:
            return (
                "Le module sounddevice manque. Relancez setup_env.bat pour installer "
                "la capture audio Windows."
            )
        required = ("RawInputStream", "WasapiSettings", "query_devices", "query_hostapis")
        missing = [attribute for attribute in required if not hasattr(sd, attribute)]
        if missing:
            return f"Le backend audio est incomplet (API manquante : {', '.join(missing)})."
        try:
            if not _wasapi_output_candidates(sd):
                return (
                    "Aucune sortie WASAPI détectée. Sélectionnez un casque ou haut-parleur "
                    "Windows, puis relancez SoundMaster."
                )
        except Exception as error:  # noqa: BLE001 - capability probing must not break the UI.
            return f"Impossible d’interroger les sorties WASAPI : {error}"
        return None

    @staticmethod
    def available() -> bool:
        """Return whether sounddevice exposes at least one WASAPI output endpoint."""

        return SystemAudioRecorder.capability_error() is None

    def start(self) -> None:
        try:
            import sounddevice as sd
        except ImportError as error:
            raise RuntimeError(
                "La capture de sortie nécessite sounddevice. "
                "Relancez setup_env.bat ou installez soundmaster[audio]."
            ) from error

        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        # A recorder instance is single-use. The stop event is intentionally not
        # cleared here: the UI creates the recorder and starts its thread only after
        # the event is in the clear state, avoiding an immediate-stop race.
        try:
            device = resolve_wasapi_output_device(sd, self.device)
            device_info = sd.query_devices(device)
            # Loopback exposes the playback mix through the output endpoint. Use
            # its native rate and at most stereo to avoid opening an unsupported
            # channel layout on virtual cables.
            channels = min(2, max(1, int(device_info.get("max_output_channels", 2))))
            samplerate = int(device_info.get("default_samplerate", 48_000))
            extra_settings = sd.WasapiSettings(loopback=True)
            audio_queue: queue.Queue[bytes] = queue.Queue(maxsize=128)
            with wave.open(str(self.output_path), "wb") as output:
                output.setnchannels(channels)
                output.setsampwidth(2)
                output.setframerate(samplerate)

                def callback(indata, _frames, _time_info, _status) -> None:
                    if self._stop_event.is_set():
                        return
                    try:
                        audio_queue.put_nowait(bytes(indata))
                    except queue.Full:
                        # Never block PortAudio's real-time callback. A rare dropped
                        # block is preferable to breaking capture or causing glitches.
                        return

                self._stream = sd.RawInputStream(
                    device=device,
                    channels=channels,
                    samplerate=samplerate,
                    dtype="int16",
                    blocksize=1024,
                    callback=callback,
                    extra_settings=extra_settings,
                )
                self._stream.start()
                while not self._stop_event.is_set() or not audio_queue.empty():
                    try:
                        output.writeframes(audio_queue.get(timeout=0.1))
                    except queue.Empty:
                        continue
        except Exception as error:
            if isinstance(error, RuntimeError) and str(error).startswith(
                "Capture de la sortie Windows impossible:"
            ):
                raise
            raise RuntimeError(
                f"Capture de la sortie Windows impossible: {error}"
            ) from error
        finally:
            self.stop()

    def stop(self) -> None:
        self._stop_event.set()
        stream, self._stream = self._stream, None
        if stream is None:
            return
        with suppress(Exception):
            stream.stop()
        with suppress(Exception):
            stream.close()

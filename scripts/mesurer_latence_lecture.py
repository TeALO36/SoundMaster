"""Mesure la latence réelle du chemin de lecture des soundboards.

Décompose le pipeline en étapes mesurables :
  1. décodage PCM (froid, sans cache) ;
  2. ouverture d'un flux de sortie (froid) ;
  3. clic « Tester » → premier mixage audio (flux déjà ouvert) ;
  4. latence audible estimée = callback + tampon WASAPI (latence basse).

Usage :
    .venv\\Scripts\\python scripts/mesurer_latence_lecture.py [fichier.wav|mp3|ogg]

Sans argument, un clip WAV 3 s synthétique est généré temporairement.
Le script joue brièvement du son sur la sortie par défaut (volontairement).
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np

from soundmaster.core.fast_audio import ContinuousAudioOutput, load_audio_pcm


class MeasuredOutput(ContinuousAudioOutput):
    """ContinuousAudioOutput qui enregistre l'instant du premier mixage."""

    def __init__(self, *args, **kwargs) -> None:
        self.first_mix: float | None = None
        self.played_at: float | None = None
        super().__init__(*args, **kwargs)

    def _audio_callback(self, outdata, frames, time_info, status) -> None:
        super()._audio_callback(outdata, frames, time_info, status)
        if self.played_at is not None and self.first_mix is None and self._playing_buffers:
            self.first_mix = time.perf_counter()


def _make_clip() -> Path:
    path = Path("mesure-latence-tmp.wav")
    sr = 44100
    t = np.linspace(0, 3.0, int(sr * 3.0), endpoint=False)
    audio = (0.2 * np.sin(2 * np.pi * (220 + 80 * np.sin(2 * np.pi * 1.3 * t)) * t)).astype(np.float32)
    import soundfile as sf

    sf.write(str(path), np.column_stack((audio, audio)), sr)
    return path


def main() -> int:
    clip = Path(sys.argv[1]) if len(sys.argv) > 1 else _make_clip()
    cold_output: ContinuousAudioOutput | None = None
    measured: MeasuredOutput | None = None
    try:
        print(f"Fichier : {clip.name} ({clip.stat().st_size} octets)\n")

        # 1) Décodage à froid
        start = time.perf_counter()
        pcm, _ = load_audio_pcm(clip)
        decode_ms = (time.perf_counter() - start) * 1000
        print(f"1. Décodage PCM (froid)         : {decode_ms:6.1f} ms")

        # 2) Ouverture du flux à froid
        start = time.perf_counter()
        cold_output = ContinuousAudioOutput(None)
        open_ms = (time.perf_counter() - start) * 1000
        print(f"2. Ouverture du flux (froid)    : {open_ms:6.1f} ms")

        # 3) Clic -> premier mixage (flux déjà ouvert)
        time.sleep(0.15)  # laisser le flux se stabiliser
        measured = MeasuredOutput(None)
        time.sleep(0.15)
        measured.played_at = time.perf_counter()
        measured.play(pcm)
        for _ in range(500):
            if measured.first_mix is not None:
                break
            time.sleep(0.0005)
        callback_ms = (measured.first_mix - measured.played_at) * 1000 if measured.first_mix else None
        print(f"3. Clic -> 1er mixage (flux chaud) : {callback_ms if callback_ms is not None else float('nan'):6.1f} ms")

        # 4) Latence audible estimée : callback + tampon WASAPI basse latence
        import sounddevice as sd

        device = sd.query_devices(kind="output")
        buffer_ms = device.get("default_low_output_latency", 0.09) * 1000
        audible = (callback_ms or 0) + buffer_ms
        print(f"4. Latence audible estimée (callback + tampon ~{buffer_ms:.0f} ms) : {audible:6.1f} ms")

        print("\nVerdict :")
        if callback_ms is not None and callback_ms < 20:
            print("  Le pipeline rapide répond en < 20 ms : la latence perçue vient")
            print("  du tampon matériel WASAPI, pas de l'application.")
        else:
            print("  Le pipeline rapide est lent : vérifiez le préchargement et le flux.")
        return 0
    finally:
        if cold_output is not None:
            cold_output.close()
        if measured is not None:
            measured.close()
        if clip.name == "mesure-latence-tmp.wav":
            clip.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())

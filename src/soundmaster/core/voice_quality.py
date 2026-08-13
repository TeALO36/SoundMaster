"""Measurable guards on cloned takes: pitch collapse and speaking rate.

Two defects were characterised on the VoiceClone project by measuring 72 cloned
takes against their reference rather than listening to them, using the same
engines this application ships:

* **Octave collapse.** The Pocket sampler occasionally locks onto half the
  reference pitch, turning a female reference into a male-sounding take. The
  result is fluent and intelligible, so neither a generation error nor a
  truncation check notices it. Median pitch catches it in one number: a
  collapsed take measured 99.7 Hz against the reference's 205 Hz.
* **Speaking rate.** Every take spoke faster than the voice it imitated — the
  median by 59%, none ever slower. The engines reproduce timbre and pitch but
  not tempo, and delivery is part of recognising a voice.

Pocket TTS exposes no tempo control, so the correction is applied to the audio
after generation, and it must not move the pitch: a plain resample would slow
the speech by dropping it an octave, trading one defect for another.
"""

from __future__ import annotations

import math
from typing import Any

# Normal take-to-take pitch variation measured ~1 semitone, worst case 3, while
# an octave collapse is 12. Six separates them without false alarms.
OCTAVE_COLLAPSE_SEMITONES = 6.0
# Speech pitch lives here; searching outside it invites octave errors in the
# estimator itself.
MIN_F0_HZ = 60.0
MAX_F0_HZ = 400.0


def _as_mono(samples: Any) -> Any:
    import numpy as np

    audio = np.asarray(samples, dtype=np.float64)
    if audio.ndim > 1:
        audio = audio.mean(axis=tuple(range(audio.ndim - 1)))
    return audio.reshape(-1)


def estimate_f0_median(samples: Any, sample_rate: int) -> float | None:
    """Median fundamental frequency in hertz, or ``None`` if there is no voice.

    Autocorrelation over short windows, keeping only windows with enough energy
    to be speech. One number is enough to catch an octave collapse, and it is
    cheap: a few milliseconds for a clip of several seconds.
    """

    import numpy as np

    audio = _as_mono(samples)
    if sample_rate <= 0 or audio.size < sample_rate // 20:
        return None
    peak = float(np.max(np.abs(audio))) or 1.0
    audio = audio / peak

    window = int(sample_rate * 0.04)
    hop = max(1, window // 2)
    min_lag = max(2, int(sample_rate / MAX_F0_HZ))
    max_lag = min(window - 1, int(sample_rate / MIN_F0_HZ))
    if max_lag <= min_lag:
        return None

    estimates: list[float] = []
    for start in range(0, audio.size - window, hop):
        frame = audio[start : start + window]
        if float(np.sqrt(np.mean(frame**2))) < 0.05:
            continue  # silence or breath: no pitch to measure
        frame = frame - frame.mean()
        correlation = np.correlate(frame, frame, mode="full")[window - 1 :]
        if correlation[0] <= 0:
            continue
        segment = correlation[min_lag : max_lag + 1]
        if segment.size == 0:
            continue
        lag = int(np.argmax(segment)) + min_lag
        # Require a real periodic peak, not just the tail of the envelope.
        if correlation[lag] < 0.3 * correlation[0]:
            continue
        estimates.append(sample_rate / lag)
    if not estimates:
        return None
    return float(np.median(estimates))


def semitones_between(first: float | None, second: float | None) -> float | None:
    """Absolute distance in semitones between two frequencies."""

    if not first or not second or first <= 0 or second <= 0:
        return None
    return abs(12.0 * math.log2(first / second))


def is_octave_collapsed(
    take: Any,
    reference: Any,
    sample_rate: int,
    reference_rate: int | None = None,
    threshold: float = OCTAVE_COLLAPSE_SEMITONES,
) -> bool:
    """Whether a take drifted far enough from the reference pitch to be wrong.

    Unmeasurable audio answers ``False``: a missing measurement must never
    discard a take that may be perfectly good.
    """

    distance = semitones_between(
        estimate_f0_median(take, sample_rate),
        estimate_f0_median(reference, reference_rate or sample_rate),
    )
    return distance is not None and distance > threshold


def time_stretch(samples: Any, rate: float) -> Any:
    """Change duration by ``rate`` without moving the pitch.

    ``rate`` below 1 slows the speech down. Overlap-add on pitch-independent
    grains: resampling instead would drop the pitch by exactly the amount it
    slowed, which is the defect this is meant to avoid.
    """

    import numpy as np

    audio = _as_mono(samples)
    if audio.size == 0 or rate <= 0 or abs(rate - 1.0) < 1e-3:
        return audio

    frame = 1024
    overlap = frame // 4
    hop_in = frame - overlap
    hop_out = max(1, round(hop_in / rate))
    window = np.hanning(frame)

    frames = max(1, 1 + (audio.size - frame) // hop_in) if audio.size >= frame else 1
    output = np.zeros(hop_out * frames + frame, dtype=np.float64)
    weights = np.zeros_like(output)
    for index in range(frames):
        start = index * hop_in
        chunk = audio[start : start + frame]
        if chunk.size < frame:
            chunk = np.pad(chunk, (0, frame - chunk.size))
        target = index * hop_out
        output[target : target + frame] += chunk * window
        weights[target : target + frame] += window
    # Where the windows overlap the sum is not 1; normalise so the amplitude
    # envelope of the original speech is preserved.
    busy = weights > 1e-6
    output[busy] /= weights[busy]
    trimmed = output[: max(1, round(audio.size / rate))]
    return trimmed.astype(np.float32)

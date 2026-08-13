"""Tests for the measurable guards on cloned takes."""

from __future__ import annotations

import numpy as np
import pytest

from soundmaster.core.voice_quality import (
    OCTAVE_COLLAPSE_SEMITONES,
    estimate_f0_median,
    is_octave_collapsed,
    semitones_between,
    time_stretch,
)

RATE = 24_000


def voiced(frequency: float, seconds: float = 2.0, rate: int = RATE) -> np.ndarray:
    """A harmonic-rich tone, closer to speech than a bare sine."""

    t = np.arange(int(rate * seconds)) / rate
    signal = np.zeros_like(t)
    for harmonic, gain in enumerate((1.0, 0.5, 0.25, 0.12), start=1):
        signal += gain * np.sin(2 * np.pi * frequency * harmonic * t)
    return (signal / np.max(np.abs(signal))).astype(np.float32)


@pytest.mark.parametrize("frequency", [98.0, 147.0, 205.0, 262.0])
def test_pitch_is_measured_accurately(frequency: float) -> None:
    measured = estimate_f0_median(voiced(frequency), RATE)
    assert measured is not None
    # Within a semitone of the truth is ample to separate an octave error.
    assert abs(12 * np.log2(measured / frequency)) < 1.0, f"{measured} Hz vs {frequency} Hz"


def test_silence_and_noise_report_no_pitch() -> None:
    assert estimate_f0_median(np.zeros(RATE), RATE) is None
    assert estimate_f0_median(np.zeros(10), RATE) is None
    assert estimate_f0_median(voiced(200.0), 0) is None


def test_octave_collapse_is_detected_but_normal_variation_is_not() -> None:
    """The real case: a 205 Hz reference cloned at 99.7 Hz sounds male."""

    reference = voiced(205.0)
    collapsed = voiced(99.7)
    assert is_octave_collapsed(collapsed, reference, RATE) is True

    # Take-to-take variation measured ~1 semitone, worst case 3: never flagged.
    for cents in (1, 2, 3):
        near = voiced(205.0 * 2 ** (cents / 12))
        assert is_octave_collapsed(near, reference, RATE) is False, f"{cents} demi-tons"

    # And a faithful take is obviously kept.
    assert is_octave_collapsed(voiced(205.0), reference, RATE) is False


def test_unmeasurable_audio_never_discards_a_take() -> None:
    """A missing measurement must not throw away a possibly good take."""

    assert is_octave_collapsed(np.zeros(RATE), voiced(200.0), RATE) is False
    assert is_octave_collapsed(voiced(200.0), np.zeros(RATE), RATE) is False
    assert semitones_between(None, 200.0) is None
    assert semitones_between(0.0, 200.0) is None


def test_reference_may_have_its_own_sample_rate() -> None:
    reference = voiced(205.0, rate=48_000)
    assert is_octave_collapsed(voiced(205.0), reference, RATE, reference_rate=48_000) is False
    assert is_octave_collapsed(voiced(102.5), reference, RATE, reference_rate=48_000) is True


@pytest.mark.parametrize("rate", [0.7, 0.85, 1.25])
def test_stretching_changes_duration_without_moving_pitch(rate: float) -> None:
    """A plain resample would slow speech by dropping its pitch; this must not."""

    source = voiced(180.0, seconds=2.0)
    stretched = time_stretch(source, rate)

    expected = source.size / rate
    assert abs(stretched.size - expected) / expected < 0.05

    before = estimate_f0_median(source, RATE)
    after = estimate_f0_median(stretched, RATE)
    assert after is not None
    assert abs(12 * np.log2(after / before)) < 1.0, f"{before} Hz -> {after} Hz"


def test_stretching_is_a_no_op_at_unit_rate() -> None:
    source = voiced(180.0, seconds=0.5)
    assert np.asarray(time_stretch(source, 1.0)).size == source.size
    assert time_stretch(np.zeros(0), 0.7).size == 0
    # A nonsensical rate must not raise.
    assert np.asarray(time_stretch(source, 0.0)).size == source.size


def test_the_collapse_threshold_sits_between_variation_and_an_octave() -> None:
    assert 3.0 < OCTAVE_COLLAPSE_SEMITONES < 12.0

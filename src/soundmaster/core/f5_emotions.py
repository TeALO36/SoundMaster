"""Emotion metadata and text conversion for the F5-TTS editor.

The official F5-TTS demo exposes six emotion styles. The editor keeps those
styles as formatting metadata and only emits bracket markers immediately before
calling the F5-TTS backend, so the visible text remains natural to edit and copy.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class F5Emotion:
    key: str
    label: str
    tag: str
    background: str
    foreground: str
    description: str


# These names mirror the styles demonstrated by the upstream F5-TTS project:
# Calm, Angry, Disgust, Happy, Sad, and Fearful.
F5_EMOTIONS: tuple[F5Emotion, ...] = (
    F5Emotion("calm", "Calme", "calm", "#64748b", "#f8fafc", "Voix posée et maîtrisée"),
    F5Emotion("angry", "Colère", "angry", "#dc2626", "#fff7ed", "Voix tendue et agressive"),
    F5Emotion("disgust", "Dégoût", "disgust", "#15803d", "#f0fdf4", "Voix de rejet ou de répulsion"),
    F5Emotion("happy", "Joie", "happy", "#ca8a04", "#1c1917", "Voix lumineuse et enthousiaste"),
    F5Emotion("sad", "Tristesse", "sad", "#2563eb", "#eff6ff", "Voix douce et mélancolique"),
    F5Emotion("fearful", "Peur", "fearful", "#7c3aed", "#f5f3ff", "Voix inquiète ou tremblante"),
)

F5_EMOTION_BY_KEY = {emotion.key: emotion for emotion in F5_EMOTIONS}
# QTextFormat user properties start at 0x1000; keep this key private to the editor.
EMOTION_FORMAT_PROPERTY = 0x1001


@dataclass(frozen=True, slots=True)
class EmotionSpan:
    """A half-open character range carrying one F5 emotion."""

    start: int
    end: int
    emotion: str


def render_emotion_tags(text: str, spans: tuple[EmotionSpan, ...] | list[EmotionSpan]) -> str:
    """Insert F5 bracket markers before valid, non-overlapping emotion spans.

    Uncoloured text is left untouched. When two coloured ranges meet, the later
    marker changes the active style, which is the syntax used by the F5 emotion
    checkpoints supported by SoundMaster.
    """

    if not text or not spans:
        return text

    output: list[str] = []
    cursor = 0
    for span in sorted(spans, key=lambda item: (item.start, item.end)):
        emotion = F5_EMOTION_BY_KEY.get(span.emotion)
        start = max(cursor, min(len(text), span.start))
        end = max(start, min(len(text), span.end))
        if emotion is None or end <= start:
            continue
        if start > cursor:
            output.append(text[cursor:start])
        output.append(f"[{emotion.tag}]")
        output.append(text[start:end])
        cursor = end
    output.append(text[cursor:])
    return "".join(output)

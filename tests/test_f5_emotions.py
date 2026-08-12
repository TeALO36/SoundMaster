from soundmaster.core.f5_emotions import (
    F5_EMOTIONS,
    EmotionSpan,
    render_emotion_tags,
)


def test_palette_matches_the_supported_f5_styles() -> None:
    assert [emotion.key for emotion in F5_EMOTIONS] == [
        "calm",
        "angry",
        "disgust",
        "happy",
        "sad",
        "fearful",
    ]
    assert F5_EMOTIONS[1].background == "#dc2626"
    assert F5_EMOTIONS[4].background == "#2563eb"


def test_render_emotion_tags_keeps_plain_text_and_switches_styles() -> None:
    text = "Bonjour, tout va bien. Mais je suis triste."
    spans = [
        EmotionSpan(0, 8, "happy"),
        EmotionSpan(23, len(text), "sad"),
    ]

    assert render_emotion_tags(text, spans) == (
        "[happy]Bonjour, tout va bien. [sad]Mais je suis triste."
    )


def test_render_emotion_tags_ignores_unknown_and_empty_ranges() -> None:
    text = "Bonjour"
    spans = [
        EmotionSpan(-4, 0, "happy"),
        EmotionSpan(0, 0, "sad"),
        EmotionSpan(1, 4, "unknown"),
        EmotionSpan(2, 5, "angry"),
    ]

    assert render_emotion_tags(text, spans) == "Bo[angry]njour"

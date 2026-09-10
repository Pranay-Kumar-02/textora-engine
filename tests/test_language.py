"""
Tests for universal language detection and validation.
"""

from textora_engine.language.validator import UniversalLanguageValidator
from textora_engine.models import RawTranscript, TranscriptSegment, TranscriptSource


def test_auto_language_accepts_any_valid_language():
    validator = UniversalLanguageValidator(target_language="auto")

    # Spanish text in auto mode
    spanish_transcript = RawTranscript(
        source_id="v_es",
        transcript_source=TranscriptSource.MANUAL_CAPTIONS,
        language_code="es",
        is_generated=False,
        segments=[TranscriptSegment(text="Hola a todos, bienvenidos a este tutorial de programacion.", start=0.0, duration=3.0)],
        raw_text="Hola a todos, bienvenidos a este tutorial de programacion.",
    )
    decision = validator.validate(spanish_transcript)
    assert decision.is_acceptable is True
    assert decision.detected_language == "es"


def test_english_validation_accepts_clean_english():
    validator = UniversalLanguageValidator(target_language="en")

    english_transcript = RawTranscript(
        source_id="v_en",
        transcript_source=TranscriptSource.MANUAL_CAPTIONS,
        language_code="en",
        is_generated=False,
        segments=[TranscriptSegment(
            text="In this lecture we will explore the fundamental theorems of linear algebra and matrix calculus. This is a crucial topic for machine learning.",
            start=0.0,
            duration=6.0,
        )],
        raw_text="In this lecture we will explore the fundamental theorems of linear algebra and matrix calculus. This is a crucial topic for machine learning.",
    )
    decision = validator.validate(english_transcript)
    assert decision.is_acceptable is True
    assert decision.detected_language == "en"


def test_english_validation_rejects_non_latin_scripts():
    validator = UniversalLanguageValidator(target_language="en")

    # Hindi in Devanagari script
    devanagari_transcript = RawTranscript(
        source_id="v_hi",
        transcript_source=TranscriptSource.MANUAL_CAPTIONS,
        language_code="hi",
        is_generated=False,
        segments=[TranscriptSegment(text="à¤¨à¤®à¤¸à¥à¤¤à¥‡ à¤¦à¥‹à¤¸à¥à¤¤à¥‹à¤‚, à¤†à¤œ à¤¹à¤® à¤­à¥Œà¤¤à¤¿à¤• à¤µà¤¿à¤œà¥à¤žà¤¾à¤¨ à¤•à¥‡ à¤®à¤¹à¤¤à¥à¤µà¤ªà¥‚à¤°à¥à¤£ à¤¨à¤¿à¤¯à¤®à¥‹à¤‚ à¤•à¥‹ à¤¸à¤®à¤à¥‡à¤‚à¤—à¥‡à¥¤", start=0.0, duration=4.0)],
        raw_text="à¤¨à¤®à¤¸à¥à¤¤à¥‡ à¤¦à¥‹à¤¸à¥à¤¤à¥‹à¤‚, à¤†à¤œ à¤¹à¤® à¤­à¥Œà¤¤à¤¿à¤• à¤µà¤¿à¤œà¥à¤žà¤¾à¤¨ à¤•à¥‡ à¤®à¤¹à¤¤à¥à¤µà¤ªà¥‚à¤°à¥à¤£ à¤¨à¤¿à¤¯à¤®à¥‹à¤‚ à¤•à¥‹ à¤¸à¤®à¤à¥‡à¤‚à¤—à¥‡à¥¤",
    )
    decision = validator.validate(devanagari_transcript)
    assert decision.is_acceptable is False
    assert "non_latin" in decision.detected_language or "hi" in decision.detected_language


def test_english_validation_rejects_transliterated_hinglish():
    validator = UniversalLanguageValidator(target_language="en")

    # Hinglish written in Latin script
    hinglish_transcript = RawTranscript(
        source_id="v_hinglish",
        transcript_source=TranscriptSource.AUTO_CAPTIONS,
        language_code="en",
        is_generated=True,
        segments=[TranscriptSegment(
            text="dekho bhai bacho ab hum yahan par yeh formula kaise lagana hai yeh samjhenge kyunki yeh sabse important hai aur aapko padhai karna chahiye.",
            start=0.0,
            duration=6.0,
        )],
        raw_text="dekho bhai bacho ab hum yahan par yeh formula kaise lagana hai yeh samjhenge kyunki yeh sabse important hai aur aapko padhai karna chahiye.",
    )
    decision = validator.validate(hinglish_transcript)
    assert decision.is_acceptable is False
    assert decision.detected_language == "hinglish"


def test_scientific_vocabulary_is_not_falsely_penalized():
    validator = UniversalLanguageValidator(target_language="en")

    technical_transcript = RawTranscript(
        source_id="v_tech",
        transcript_source=TranscriptSource.MANUAL_CAPTIONS,
        language_code="en",
        is_generated=False,
        segments=[TranscriptSegment(
            text="The Hamiltonian of the quantum system is defined by the Schrodinger differential equation, where the kinetic and potential energy operators commute.",
            start=0.0,
            duration=5.0,
        )],
        raw_text="The Hamiltonian of the quantum system is defined by the Schrodinger differential equation, where the kinetic and potential energy operators commute.",
    )
    decision = validator.validate(technical_transcript)
    assert decision.is_acceptable is True
    assert decision.detected_language == "en"

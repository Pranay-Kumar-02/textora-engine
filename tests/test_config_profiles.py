"""
Unit tests for configuration profiles and enhanced TOML loading.
"""

from pathlib import Path
import pytest

from textora_engine.config import TextoraConfig


def test_config_profiles():
    fast = TextoraConfig.from_profile("fast")
    assert fast.stt_model == "tiny"
    assert fast.frame_interval_seconds == 15.0

    balanced = TextoraConfig.from_profile("balanced")
    assert balanced.stt_model == "base"
    assert balanced.frame_interval_seconds == 10.0

    hq = TextoraConfig.from_profile("high-quality")
    assert hq.stt_model == "medium"
    assert hq.frame_interval_seconds == 5.0

    with pytest.raises(ValueError, match="Unknown configuration profile"):
        TextoraConfig.from_profile("ultra-turbo-9000")


def test_config_profile_overrides():
    custom = TextoraConfig.from_profile("fast", workers=4, language="es")
    assert custom.workers == 4
    assert custom.language == "es"
    assert custom.stt_model == "tiny"


def test_config_toml_loading_nested(tmp_path: Path):
    toml_content = """
[textora]
output_dir = "./custom_out"
language = "hi"
stt_model = "small"
workers = 2
multimodal = true
frame_interval_seconds = 8.0
"""
    toml_path = tmp_path / "textora.toml"
    toml_path.write_text(toml_content, encoding="utf-8")

    cfg = TextoraConfig.load_from_toml(toml_path)
    assert str(cfg.output_dir) == "custom_out"
    assert cfg.language == "hi"
    assert cfg.stt_model == "small"
    assert cfg.workers == 2
    assert cfg.multimodal is True
    assert cfg.frame_interval_seconds == 8.0

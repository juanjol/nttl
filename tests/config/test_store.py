import pytest

from nttl.config.models import AppConfig
from nttl.config.store import ConfigError, default_config_path, load_config, save_config


def test_missing_file_returns_defaults(tmp_path):
    config = load_config(tmp_path / "nope.toml")
    assert isinstance(config, AppConfig)
    assert config.capture.session_name == "session"


def test_roundtrip_preserves_nested_values(tmp_path):
    path = tmp_path / "config.toml"
    config = AppConfig()
    config.capture.session_name = "aralar"
    config.capture.auto_exposure.enabled = True
    config.capture.auto_exposure.target_level = 0.31
    config.schedule.latitude = 42.99
    config.video.fps = 30
    save_config(path, config)
    loaded = load_config(path)
    assert loaded.capture.session_name == "aralar"
    assert loaded.capture.auto_exposure.enabled is True
    assert loaded.capture.auto_exposure.target_level == pytest.approx(0.31)
    assert loaded.schedule.latitude == pytest.approx(42.99)
    assert loaded.video.fps == 30


def test_saved_file_is_readable_toml(tmp_path):
    path = tmp_path / "config.toml"
    save_config(path, AppConfig())
    text = path.read_text(encoding="utf-8")
    assert "[capture]" in text
    assert "None" not in text


def test_partial_file_is_merged_with_defaults(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text("[video]\nfps = 48\n", encoding="utf-8")
    config = load_config(path)
    assert config.video.fps == 48
    assert config.capture.session_name == "session"


def test_invalid_toml_raises(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text("this is not = = toml", encoding="utf-8")
    with pytest.raises(ConfigError):
        load_config(path)


def test_invalid_values_raise(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text("[video]\nfps = 0\n", encoding="utf-8")
    with pytest.raises(ConfigError):
        load_config(path)


def test_default_path_follows_xdg(monkeypatch, tmp_path):
    monkeypatch.setattr("sys.platform", "linux")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert default_config_path() == tmp_path / "nttl" / "config.toml"


def test_default_path_on_windows(monkeypatch, tmp_path):
    monkeypatch.setattr("sys.platform", "win32")
    monkeypatch.setenv("APPDATA", str(tmp_path))
    assert default_config_path() == tmp_path / "nttl" / "config.toml"


def test_save_creates_parent_directories(tmp_path):
    path = tmp_path / "deep" / "nested" / "config.toml"
    save_config(path, AppConfig())
    assert path.exists()

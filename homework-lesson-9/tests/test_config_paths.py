"""Regression tests for config path normalisation.

The Settings model must return absolute filesystem paths anchored at the
hw9 project root, regardless of the process cwd. Otherwise launching
SearchMCP from ``/tmp`` (or pm2/tmux) would silently read and write
files relative to the wrong directory.
"""

import os
from pathlib import Path

from config import PROJECT_ROOT, Settings


def _fresh_settings(monkeypatch, **overrides):
    """Build a Settings() isolated from stray env-vars + any .env file."""
    for key in (
        "DATA_DIR", "INDEX_DIR", "OUTPUT_DIR",
        "API_BASE", "API_KEY", "EMBEDDING_BASE_URL",
    ):
        monkeypatch.delenv(key, raising=False)
    for key, value in overrides.items():
        monkeypatch.setenv(key, value)
    # Disable .env file lookup for this test so we only see our overrides.
    monkeypatch.setattr(Settings, "model_config", {"env_file": None})
    return Settings()


def test_default_paths_are_absolute(monkeypatch):
    settings = _fresh_settings(monkeypatch)
    for attr in ("data_dir", "index_dir", "output_dir"):
        value = getattr(settings, attr)
        assert os.path.isabs(value), f"{attr} must be absolute, got {value!r}"


def test_relative_path_anchored_at_project_root(monkeypatch):
    settings = _fresh_settings(monkeypatch, OUTPUT_DIR="output")
    expected = str((PROJECT_ROOT / "output").resolve())
    assert settings.output_dir == expected


def test_absolute_path_preserved(monkeypatch, tmp_path):
    target = tmp_path / "custom-output"
    settings = _fresh_settings(monkeypatch, OUTPUT_DIR=str(target))
    assert settings.output_dir == str(target)


def test_paths_stable_regardless_of_cwd(monkeypatch, tmp_path):
    """Launching from a different cwd must produce the same paths."""
    cwd_before = os.getcwd()
    try:
        os.chdir(tmp_path)
        settings = _fresh_settings(monkeypatch, OUTPUT_DIR="output")
        assert settings.output_dir == str((PROJECT_ROOT / "output").resolve())
        assert Path(settings.output_dir).is_absolute()
    finally:
        os.chdir(cwd_before)


def test_env_file_is_anchored_at_project_root():
    """Settings.model_config['env_file'] must be an absolute path under
    PROJECT_ROOT, otherwise Pydantic would resolve it against the
    process cwd and silently skip the real .env file when the server
    is launched from another directory."""
    env_file = Settings.model_config.get("env_file")
    assert env_file is not None
    assert os.path.isabs(env_file), f"env_file must be absolute, got {env_file!r}"
    assert Path(env_file).parent == PROJECT_ROOT

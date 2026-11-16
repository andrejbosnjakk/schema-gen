"""Tests never touch the developer's real settings, projects or log (the app's per-user folder)."""
import pytest


@pytest.fixture(autouse=True)
def _schemagen_home(tmp_path_factory, monkeypatch):
    monkeypatch.setenv("SCHEMAGEN_HOME", str(tmp_path_factory.mktemp("schemagen-home")))

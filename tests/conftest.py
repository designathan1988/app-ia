"""Every test starts from the untaught system: what the user taught and the preferences learned from their undos live
in data/ and must not change what a test measures (nor be changed by it)."""

from __future__ import annotations

import pytest

from nucleo.lang import learned, preferences


@pytest.fixture(autouse=True)
def _isolated_user_data(tmp_path, monkeypatch):
    monkeypatch.setattr(learned, "STORE", tmp_path / "vocabulario.json")
    monkeypatch.setattr(preferences, "STORE", tmp_path / "preferencias.json")

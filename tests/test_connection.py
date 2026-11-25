"""T66 — fail-fast DATABASE_URL (không reload module — chỉ gọi hàm)."""

import pytest

from app.database import connection


def test_connection_requires_database_url(monkeypatch):
    monkeypatch.setattr(connection.settings, "database_url", "")
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        connection._require_database_url()


def test_connection_returns_configured_url(monkeypatch):
    monkeypatch.setattr(connection.settings, "database_url", "postgresql+asyncpg://u:p@h:5432/db")
    assert connection._require_database_url() == "postgresql+asyncpg://u:p@h:5432/db"

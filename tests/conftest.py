import hashlib
import hmac
import json
from unittest.mock import MagicMock

import pytest


class FakeRequest:
    """Request giả để gọi thẳng endpoint webhook (không cần TestClient/DB)."""

    def __init__(self, body: bytes, headers: dict | None = None) -> None:
        self._body = body
        self.headers = headers or {}

    async def body(self) -> bytes:
        return self._body

    async def json(self) -> dict:
        return json.loads(self._body)


def make_sig(body: bytes, secret: str) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


@pytest.fixture
def fake_session() -> MagicMock:
    return MagicMock()

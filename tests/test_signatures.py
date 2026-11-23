import hashlib
import hmac

from app.channels.base import verify_hmac_signature, verify_secret_token


def test_hmac_valid_signature():
    secret = "s3cret"
    body = b'{"event_name":"user_send_text"}'
    sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    assert verify_hmac_signature(body, sig, secret) is True


def test_hmac_wrong_signature():
    body = b"hello"
    assert verify_hmac_signature(body, "sha256=" + "0" * 64, "s3cret") is False


def test_hmac_missing_header_with_secret():
    assert verify_hmac_signature(b"hello", None, "s3cret") is False


def test_hmac_empty_secret_dev_mode():
    assert verify_hmac_signature(b"hello", None, "") is True
    assert verify_hmac_signature(b"hello", "sha256=bad", "") is True


def test_hmac_accepts_bare_hex_without_prefix():
    secret = "s3cret"
    body = b"payload"
    bare = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    assert verify_hmac_signature(body, bare, secret) is True


def test_secret_token_match():
    assert verify_secret_token("abc123", "abc123") is True


def test_secret_token_mismatch():
    assert verify_secret_token("abc123", "xyz") is False


def test_secret_token_missing_with_secret():
    assert verify_secret_token(None, "abc123") is False


def test_secret_token_empty_secret_dev_mode():
    assert verify_secret_token(None, "") is True
    assert verify_secret_token("anything", "") is True

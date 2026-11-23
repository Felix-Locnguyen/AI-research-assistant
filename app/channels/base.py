import hashlib
import hmac
from dataclasses import dataclass

@dataclass(frozen=True)
class IncomingMessage:
    channel: str       # telegram / zalo / messenger
    user_id: str
    username: str | None
    text: str


def verify_hmac_signature(raw_body: bytes, header_signature: str | None, secret: str) -> bool:
    """Kiểm tra chữ ký HMAC-SHA256 (định dạng 'sha256=' + hex). Secret rỗng = dev mode, bỏ qua."""
    if not secret:
        return True
    if not header_signature:
        return False
    provided = header_signature.removeprefix("sha256=")
    expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(provided, expected)


def verify_secret_token(header_token: str | None, secret: str) -> bool:
    """Kiểm tra secret-token kiểu Telegram (so sánh nguyên văn, hằng thời gian). Secret rỗng = dev mode."""
    if not secret:
        return True
    return bool(header_token) and hmac.compare_digest(header_token, secret)


async def send_text(channel: str, user_id: str, text: str, proactive: bool = False) -> None:
    """Gửi tin nhắn tới user trên bất kỳ kênh nào (dispatcher cho notifier).

    Lazy-import để tránh circular import: các kênh import IncomingMessage từ base.
    proactive=True dành cho gửi chủ động (lời nhắc): Messenger dùng MESSAGE_TAG,
    các kênh khác bỏ qua cờ này.
    """
    if channel == "telegram":
        from app.channels import telegram
        await telegram.send_text(user_id, text)
    elif channel == "zalo":
        from app.channels import zalo
        await zalo.send_text(user_id, text)
    elif channel == "messenger":
        from app.channels import messenger
        await messenger.send_text(user_id, text, proactive=proactive)
    else:
        raise ValueError(f"Kênh không hỗ trợ: {channel}")

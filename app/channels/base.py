from dataclasses import dataclass

@dataclass(frozen=True)
class IncomingMessage:
    channel: str       # telegram / zalo / messenger
    user_id: str
    username: str | None
    text: str
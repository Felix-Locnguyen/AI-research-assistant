from pathlib import Path

from app.database.models import Memory, Message
from app.memory.manager import build_context_markdown

PROMPT_FILE = Path(__file__).resolve().parents[2] / "prompts" / "assistant.md"
HISTORY_LIMIT = 20


def load_system_prompt(preferences: dict[str, str], memories: list[Memory] | None = None) -> str:
    prompt = PROMPT_FILE.read_text(encoding="utf-8")
    return prompt + build_context_markdown(preferences, memories)

def build_contents(history: list[Message], user_text: str) -> list[dict]:
    contents = [
        {"role": "user" if msg.role == "user" else "model", "parts": [{"text": msg.content}]}
        for msg in history
    ]
    contents.append({"role": "user", "parts": [{"text": user_text}]})
    return contents

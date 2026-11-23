from pathlib import Path

from app.database.models import Message

PROMPT_FILE = Path(__file__).resolve().parents[2] / "prompts" / "assistant.md"
HISTORY_LIMIT = 20


def load_system_prompt(preferences: dict[str, str]) -> str:
    prompt = PROMPT_FILE.read_text(encoding="utf-8")
    if preferences:
        prefs = "\n".join(f"- {key}: {value}" for key, value in preferences.items())
        prompt += f"\n\n## Sở thích người dùng đã lưu\n{prefs}"
    return prompt


def build_contents(history: list[Message], user_text: str) -> list[dict]:
    contents = [
        {"role": "user" if msg.role == "user" else "model", "parts": [{"text": msg.content}]}
        for msg in history
    ]
    contents.append({"role": "user", "parts": [{"text": user_text}]})
    return contents

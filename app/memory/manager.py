"""Quản lý ký ức dài hạn: kiểm tra nội dung, CRUD và tạo context Markdown (T33/T34/T37)."""

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Memory
from app.database.repository import MemoryRepository

MAX_CONTENT_LENGTH = 500
MIN_CONTENT_LENGTH = 10


def validate_content(content: str) -> str:
    """Làm sạch và kiểm tra nội dung ký ức trước khi lưu. Trả về ValueError nếu không hợp lệ."""
    content = (content or "").strip()[:MAX_CONTENT_LENGTH]
    if not content:
        raise ValueError("Nội dung ký ức rỗng")
    if len(content) < MIN_CONTENT_LENGTH:
        raise ValueError(f"Nội dung ký ức quá ngắn (tối thiểu {MIN_CONTENT_LENGTH} ký tự)")
    if not any(char.isalpha() for char in content):
        raise ValueError("Nội dung ký ức không chứa chữ cái")
    return content


def build_context_markdown(preferences: dict[str, str], memories: list[Memory] | None = None) -> str:
    """Tạo phần context Markdown từ sở thích và ký ức đã lưu (T37)."""
    sections = []
    if preferences:
        prefs = "\n".join(f"- {key}: {value}" for key, value in preferences.items())
        sections.append(f"## Sở thích người dùng đã lưu\n{prefs}")
    if memories:
        items = "\n".join(f"- {memory.content}" for memory in memories)
        sections.append(f"## Ký ức đã lưu\n{items}")
    return "".join(f"\n\n{section}" for section in sections)


class MemoryManager:
    """Facade cho thao tác ký ức: mọi đường lưu (tool / extractor) đều đi qua đây."""

    def __init__(self, session: AsyncSession):
        self.repo = MemoryRepository(session)

    async def save(self, user_id: int, content: str, expires_at: datetime | None = None) -> Memory:
        content = validate_content(content)
        return await self.repo.add(user_id, content, expires_at)

    async def update(
        self, user_id: int, memory_id: int, content: str, expires_at: datetime | None = None
    ) -> Memory:
        content = validate_content(content)
        return await self.repo.update(user_id, memory_id, content, expires_at)

    async def delete(self, user_id: int, memory_id: int) -> bool:
        return await self.repo.delete(user_id, memory_id)

    async def list(self, user_id: int, limit: int = 20) -> list[Memory]:
        return await self.repo.list_active(user_id, limit)

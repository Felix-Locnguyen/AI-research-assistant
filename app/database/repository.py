from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Conversation, Memory, Message, User, UserPreference

class UserRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_or_create(self, channel: str, channel_user_id: str, username: str | None = None) -> User:
        stmt = select(User).where(User.channel == channel, User.channel_user_id == channel_user_id)
        user = (await self.session.execute(stmt)).scalar_one_or_none()
        if user is None:
            user = User(channel=channel, channel_user_id=channel_user_id, username=username)
            self.session.add(user)
            await self.session.commit()
        return user

    async def get_preferences(self, user_id: int) -> dict[str, str]:
        stmt = select(UserPreference).where(UserPreference.user_id == user_id)
        rows = (await self.session.execute(stmt)).scalars()
        return {row.key: row.value for row in rows}

    async def set_preference(self, user_id: int, key: str, value: str) -> None:
        stmt = select(UserPreference).where(UserPreference.user_id == user_id, UserPreference.key == key)
        pref = (await self.session.execute(stmt)).scalar_one_or_none()
        if pref is None:
            self.session.add(UserPreference(user_id=user_id, key=key, value=value))
        else:
            pref.value = value
        await self.session.commit()


class ConversationRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_or_create(self, user_id: int) -> Conversation:
        stmt = select(Conversation).where(Conversation.user_id == user_id).order_by(Conversation.id.desc())
        conversation = (await self.session.execute(stmt)).scalars().first()
        if conversation is None:
            conversation = Conversation(user_id=user_id)
            self.session.add(conversation)
            await self.session.commit()
        return conversation

    async def add_message(self, conversation_id: int, role: str, content: str) -> None:
        self.session.add(Message(conversation_id=conversation_id, role=role, content=content))
        await self.session.commit()

    async def recent_messages(self, conversation_id: int, limit: int = 20) -> list[Message]:
        stmt = (
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.id.desc())
            .limit(limit)
        )
        messages = (await self.session.execute(stmt)).scalars().all()
        return list(reversed(messages))


class MemoryRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, user_id: int, memory_id: int) -> Memory | None:
        stmt = select(Memory).where(Memory.user_id == user_id, Memory.id == memory_id)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def update(
        self, user_id: int, memory_id: int, content: str, expires_at: datetime | None = None
    ) -> Memory:
        memory = await self.get(user_id, memory_id)
        if memory is None:
            raise ValueError(f"Không tìm thấy ký ức id={memory_id}")
        memory.content = content.strip()[:500]
        memory.expires_at = expires_at
        await self.session.commit()
        return memory

    async def delete(self, user_id: int, memory_id: int) -> bool:
        memory = await self.get(user_id, memory_id)
        if memory is None:
            return False
        await self.session.delete(memory)
        await self.session.commit()
        return True

    async def add(self, user_id: int, content: str, expires_at: datetime | None = None) -> Memory:
        content = content.strip()[:500]
        if not content:
            raise ValueError("Nội dung ký ức rỗng")          # T33 validation
        stmt = select(Memory).where(Memory.user_id == user_id, Memory.content == content)
        existing = (await self.session.execute(stmt)).scalar_one_or_none()
        if existing:
            return existing                                    # trùng -> bỏ qua
        memory = Memory(user_id=user_id, content=content, expires_at=expires_at)
        self.session.add(memory)
        await self.session.commit()
        return memory

    async def list_active(self, user_id: int, limit: int = 20) -> list[Memory]:
        now = datetime.now(UTC).replace(tzinfo=None)           # khớp func.now() của Postgres (UTC, naive)
        stmt = (
            select(Memory)
            .where(Memory.user_id == user_id)
            .where((Memory.expires_at.is_(None)) | (Memory.expires_at > now))
            .order_by(Memory.id.desc())
            .limit(limit)
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def cleanup_expired(self) -> int:                    # T36
        now = datetime.now(UTC).replace(tzinfo=None)
        result = await self.session.execute(
            delete(Memory).where(Memory.expires_at.is_not(None), Memory.expires_at <= now)
        )
        await self.session.commit()
        return result.rowcount or 0
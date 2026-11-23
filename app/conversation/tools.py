from datetime import UTC, datetime, timedelta

from google.genai import types

from app.agents.research import run_research
from app.database.repository import UserRepository
from app.memory.manager import MemoryManager
from app.reminders import service as reminder_service

SAVE_PREFERENCE = types.Tool(
    function_declarations=[
        {
            "name": "save_user_preference",
            "description": (
                "Lưu một thông tin/sở thích của người dùng vào hồ sơ "
                "để dùng lại ở các lần trò chuyện sau."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {
                        "type": "string",
                        "description": "Tên thông tin, ví dụ: ten, thanh-pho, nganh-nghe",
                    },
                    "value": {"type": "string", "description": "Nội dung thông tin"},
                },
                "required": ["key", "value"],
            },
        }
    ]
)

SAVE_MEMORY = types.Tool(
    function_declarations=[
        {
            "name": "save_memory",
            "description": (
                "Ghi nhớ lâu dài một sự kiện hoặc thông tin cá nhân quan trọng của người dùng. "
                "Tự gọi khi người dùng chia sẻ điều đáng nhớ (dự định, lịch sự kiện, thói quen...)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "Nội dung cần nhớ, 1 câu ngắn gọn"},
                    "expires_in_days": {
                        "type": "integer",
                        "description": "Số ngày hết hạn; bỏ trống nếu nhớ vô thời hạn",
                    },
                },
                "required": ["content"],
            },
        }
    ]
)

MANAGE_MEMORY = types.Tool(
    function_declarations=[
        {
            "name": "list_memories",
            "description": "Xem danh sách ký ức đang lưu của người dùng (kèm id) trước khi sửa hoặc xóa.",
            "parameters": {"type": "object", "properties": {}},
        },
        {
            "name": "update_memory",
            "description": "Sửa nội dung hoặc thời hạn của một ký ức đã lưu theo id.",
            "parameters": {
                "type": "object",
                "properties": {
                    "memory_id": {"type": "integer", "description": "Id của ký ức cần sửa"},
                    "content": {"type": "string", "description": "Nội dung mới"},
                    "expires_in_days": {
                        "type": "integer",
                        "description": "Số ngày hết hạn mới; bỏ trống nếu nhớ vô thời hạn",
                    },
                },
                "required": ["memory_id", "content"],
            },
        },
        {
            "name": "delete_memory",
            "description": "Xóa một ký ức đã lưu theo id khi người dùng yêu cầu.",
            "parameters": {
                "type": "object",
                "properties": {
                    "memory_id": {"type": "integer", "description": "Id của ký ức cần xóa"},
                },
                "required": ["memory_id"],
            },
        },
    ]
)

RESEARCH = types.Tool(
    function_declarations=[
        {
            "name": "research",
            "description": (
                "Tìm kiếm, lọc và tổng hợp thông tin trên Internet về một chủ đề. "
                "Dùng khi người dùng muốn tìm hiểu, so sánh hoặc cập nhật tin tức về chủ đề nào đó."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "topic": {
                        "type": "string",
                        "description": "Chủ đề hoặc câu hỏi cần nghiên cứu",
                    },
                    "feeds": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Tùy chọn: danh sách URL nguồn RSS cần thu thập thêm",
                    },
                },
                "required": ["topic"],
            },
        }
    ]
)

REMINDER = types.Tool(
    function_declarations=[
        {
            "name": "create_reminder",
            "description": (
                "Tạo lời nhắc cho người dùng. Tự gọi khi người dùng muốn được nhắc việc; "
                "tự đọc thời gian từ tin nhắn và chuyển thành định dạng ISO 8601."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Nội dung cần nhắc"},
                    "remind_at": {
                        "type": "string",
                        "description": "Thời gian nhắc, ISO 8601 theo giờ địa phương của người dùng, ví dụ 2026-01-01T08:00:00",
                    },
                    "repeat": {
                        "type": "string",
                        "enum": ["none", "daily", "weekly"],
                        "description": "Kiểu lặp lại; bỏ trống nếu nhắc một lần",
                    },
                },
                "required": ["text", "remind_at"],
            },
        },
        {
            "name": "list_reminders",
            "description": "Xem danh sách lời nhắc đang chờ của người dùng (kèm id) trước khi sửa hoặc xóa.",
            "parameters": {"type": "object", "properties": {}},
        },
        {
            "name": "update_reminder",
            "description": "Sửa nội dung, thời gian hoặc kiểu lặp của một lời nhắc theo id.",
            "parameters": {
                "type": "object",
                "properties": {
                    "reminder_id": {"type": "integer", "description": "Id của lời nhắc cần sửa"},
                    "text": {"type": "string", "description": "Nội dung mới"},
                    "remind_at": {"type": "string", "description": "Thời gian mới, ISO 8601"},
                    "repeat": {"type": "string", "enum": ["none", "daily", "weekly"]},
                },
                "required": ["reminder_id"],
            },
        },
        {
            "name": "delete_reminder",
            "description": "Xóa một lời nhắc theo id khi người dùng yêu cầu.",
            "parameters": {
                "type": "object",
                "properties": {
                    "reminder_id": {"type": "integer", "description": "Id của lời nhắc cần xóa"},
                },
                "required": ["reminder_id"],
            },
        },
    ]
)


def _expires_at_from_days(days) -> datetime | None:
    if days is None:
        return None
    return datetime.now(UTC).replace(tzinfo=None) + timedelta(days=int(days))


async def execute(
    call,
    user_id: int,
    session,
) -> str:
    user_repo = UserRepository(session)
    memory_manager = MemoryManager(session)
    if call.name == "save_user_preference":
        await user_repo.set_preference(user_id, call.args.get("key", ""), call.args.get("value", ""))
        return "Đã lưu vào hồ sơ người dùng."
    if call.name == "save_memory":
        memory = await memory_manager.save(
            user_id,
            call.args.get("content", ""),
            _expires_at_from_days(call.args.get("expires_in_days")),
        )
        return f"Đã ghi nhớ (id={memory.id})."
    if call.name == "list_memories":
        memories = await memory_manager.list(user_id)
        if not memories:
            return "Chưa có ký ức nào được lưu."
        lines = [
            f"- id={memory.id}: {memory.content}"
            + (f" (hết hạn {memory.expires_at})" if memory.expires_at else "")
            for memory in memories
        ]
        return "\n".join(lines)
    if call.name == "update_memory":
        memory_id = int(call.args.get("memory_id", 0))
        try:
            memory = await memory_manager.update(
                user_id,
                memory_id,
                call.args.get("content", ""),
                _expires_at_from_days(call.args.get("expires_in_days")),
            )
        except ValueError:
            return f"Không tìm thấy ký ức id={memory_id}."
        return f"Đã cập nhật ký ức id={memory.id}."
    if call.name == "delete_memory":
        memory_id = int(call.args.get("memory_id", 0))
        deleted = await memory_manager.delete(user_id, memory_id)
        return f"Đã xóa ký ức id={memory_id}." if deleted else f"Không tìm thấy ký ức id={memory_id}."
    if call.name == "research":
        preferences = await user_repo.get_preferences(user_id)
        outcome = await run_research(
            call.args.get("topic", ""),
            preferences,
            user_id,
            session,
            feeds=call.args.get("feeds"),
        )
        return outcome.formatted
    if call.name == "create_reminder":
        try:
            reminder = await reminder_service.create_reminder(
                session,
                user_id,
                call.args.get("text", ""),
                call.args.get("remind_at", ""),
                call.args.get("repeat", "none"),
            )
        except ValueError as exc:
            return str(exc)
        tz = await reminder_service.user_tz(session, user_id)
        return f"Đã tạo lời nhắc ({reminder_service.format_reminder(reminder, tz)})."
    if call.name == "list_reminders":
        reminders = await reminder_service.list_reminders(session, user_id)
        if not reminders:
            return "Chưa có lời nhắc nào."
        tz = await reminder_service.user_tz(session, user_id)
        return "\n".join(f"- {reminder_service.format_reminder(r, tz)}" for r in reminders)
    if call.name == "update_reminder":
        reminder_id = int(call.args.get("reminder_id", 0))
        try:
            reminder = await reminder_service.update_reminder(
                session,
                user_id,
                reminder_id,
                text=call.args.get("text"),
                remind_at_raw=call.args.get("remind_at"),
                repeat=call.args.get("repeat"),
            )
        except ValueError as exc:
            return str(exc)
        tz = await reminder_service.user_tz(session, user_id)
        return f"Đã cập nhật lời nhắc ({reminder_service.format_reminder(reminder, tz)})."
    if call.name == "delete_reminder":
        reminder_id = int(call.args.get("reminder_id", 0))
        deleted = await reminder_service.delete_reminder(session, user_id, reminder_id)
        return f"Đã xóa lời nhắc id={reminder_id}." if deleted else f"Không tìm thấy lời nhắc id={reminder_id}."
    return f"Không tồn tại tool: {call.name}"

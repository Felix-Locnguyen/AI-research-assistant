from datetime import UTC, datetime, timedelta

from google.genai import types

from app.memory.manager import MemoryManager

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


def _expires_at_from_days(days) -> datetime | None:
    if days is None:
        return None
    return datetime.now(UTC).replace(tzinfo=None) + timedelta(days=int(days))


async def execute(
    call,
    user_id: int,
    user_repo,
    memory_manager: MemoryManager,
) -> str:
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
    return f"Không tồn tại tool: {call.name}"

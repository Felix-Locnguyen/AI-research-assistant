from google.genai import types

from app.database.repository import UserRepository

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


async def execute(call, user_id: int, user_repo: UserRepository) -> str:
    if call.name == "save_user_preference":
        await user_repo.set_preference(user_id, call.args.get("key", ""), call.args.get("value", ""))
        return "Đã lưu vào hồ sơ người dùng."
    return f"Không tồn tại tool: {call.name}"

from google.genai import types

from app.channels.base import IncomingMessage
from app.conversation import tools
from app.conversation.context_builder import HISTORY_LIMIT, build_contents, load_system_prompt
from app.core import llm
from app.database.repository import ConversationRepository, UserRepository
from app.memory import extractor, retriever
from app.memory.manager import MemoryManager

MAX_TOOL_ROUNDS = 3

async def handle_message(message: IncomingMessage, session) -> str:
    user_repo = UserRepository(session)
    user = await user_repo.get_or_create(message.channel, message.user_id, message.username)
    preferences = await user_repo.get_preferences(user.id)

    memory_manager = MemoryManager(session)
    memories = await retriever.retrieve(session, user.id, message.text)

    conversation_repo = ConversationRepository(session)
    conversation = await conversation_repo.get_or_create(user.id)
    history = await conversation_repo.recent_messages(conversation.id, HISTORY_LIMIT)  # T31: bộ nhớ ngắn hạn

    contents = build_contents(history, message.text)
    system_prompt = load_system_prompt(preferences, memories)
    reply = await _reply(system_prompt, contents, user.id, session)

    await conversation_repo.add_message(conversation.id, "user", message.text)
    await conversation_repo.add_message(conversation.id, "assistant", reply)

    extractor.spawn(user.id, message.text, reply)  # T32: trích xuất ký ức nền, không chặn phản hồi
    return reply


async def _reply(
    system_prompt: str,
    contents: list[dict],
    user_id: int,
    session,
) -> str:
    for _ in range(MAX_TOOL_ROUNDS):
        response = await llm.generate(
            system_prompt,
            contents,
            tools=[tools.SAVE_PREFERENCE, tools.SAVE_MEMORY, tools.MANAGE_MEMORY, tools.RESEARCH, tools.REMINDER],
        )
        if not response.function_calls:
            return response.text or ""
        # gửi kết quả tool ngược lại cho model để nó ra câu trả lời cuối
        contents.append(response.candidates[0].content)
        for call in response.function_calls:
            result = await tools.execute(call, user_id, session)
            contents.append(
                types.Content(
                    role="user",  # API hiện tại không nhận role 'function'
                    parts=[types.Part.from_function_response(name=call.name, response={"result": result})],
                )
            )
    return "Xin lỗi, mình chưa xử lý được yêu cầu lần này."

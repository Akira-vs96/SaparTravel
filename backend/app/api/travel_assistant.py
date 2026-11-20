"""Public, rate-limited endpoint for the Gemini travel-search assistant."""
from collections import deque
from threading import Lock
import time
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import Field, StringConstraints, model_validator
from typing import Annotated

from app.api.schemas import InputModel, Language
from app.core.config import get_settings
from app.core.security import DbSession
from app.services.travel_assistant_service import GeminiUnavailable, answer

router = APIRouter()


class ChatMessage(InputModel):
    role: Literal["user", "assistant"]
    content: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1200)]


class TravelAssistantInput(InputModel):
    lang: Language = "ru"
    messages: list[ChatMessage] = Field(min_length=1, max_length=10)

    @model_validator(mode="after")
    def valid_conversation(self):
        if self.messages[-1].role != "user" or any(
            message.role != ("user" if index % 2 == 0 else "assistant")
            for index, message in enumerate(self.messages)
        ):
            raise ValueError("Диалог должен чередовать сообщения посетителя и консультанта и завершаться вопросом посетителя.")
        if sum(len(message.content) for message in self.messages) > 5000:
            raise ValueError("Слишком длинный диалог. Начните новый поиск.")
        return self


_requests: dict[str, deque[float]] = {}
_rate_lock = Lock()
_RATE_WINDOW_SECONDS = 60
_RATE_LIMIT = 8


def _allowed(client: str) -> bool:
    now = time.monotonic()
    with _rate_lock:
        if len(_requests) >= 2048 and client not in _requests:
            expired = [key for key, events in _requests.items() if not events or now - events[-1] > _RATE_WINDOW_SECONDS]
            for key in expired:
                _requests.pop(key, None)
            if len(_requests) >= 2048:
                oldest = min(_requests, key=lambda key: _requests[key][-1] if _requests[key] else 0)
                _requests.pop(oldest, None)
        events = _requests.setdefault(client, deque())
        while events and now - events[0] > _RATE_WINDOW_SECONDS:
            events.popleft()
        if len(events) >= _RATE_LIMIT:
            return False
        events.append(now)
        return True


def _client_key(request: Request) -> str:
    forwarded = request.headers.get("x-real-ip", "").strip()
    if forwarded and len(forwarded) <= 64:
        return forwarded
    return request.client.host if request.client else "unknown"


def _detail(lang: str, kind: str) -> str:
    messages = {
        "not_configured": {
            "ru": "ИИ-консультант не настроен на сервере. Добавьте GEMINI_API_KEY в окружение API.",
            "kk": "ИИ кеңесшісі серверде бапталмаған. API ортасына GEMINI_API_KEY қосыңыз.",
            "en": "The AI assistant is not configured on the server. Add GEMINI_API_KEY to the API environment.",
        },
        "unavailable": {
            "ru": "Gemini сейчас недоступен. Повторите попытку или выберите тур через каталог.",
            "kk": "Gemini қазір қолжетімсіз. Қайталап көріңіз немесе каталогтан тур таңдаңыз.",
            "en": "Gemini is temporarily unavailable. Please retry or choose a trip from the catalog.",
        },
        "rate_limit": {
            "ru": "Слишком много сообщений. Подождите минуту и попробуйте снова.",
            "kk": "Хабарламалар саны тым көп. Бір минут күтіп, қайта көріңіз.",
            "en": "Too many messages. Wait a minute and try again.",
        },
    }
    return messages[kind][lang]


@router.post("/travel-assistant/chat")
def travel_assistant_chat(data: TravelAssistantInput, request: Request, db: DbSession):
    settings = get_settings()
    if not settings.gemini_api_key:
        raise HTTPException(503, _detail(data.lang, "not_configured"))
    if not _allowed(_client_key(request)):
        raise HTTPException(429, _detail(data.lang, "rate_limit"))
    history = [{"role": message.role, "content": message.content} for message in data.messages]
    try:
        return answer(
            db,
            api_key=settings.gemini_api_key.get_secret_value(),
            model=settings.gemini_model,
            lang=data.lang,
            history=history,
        )
    except GeminiUnavailable:
        raise HTTPException(503, _detail(data.lang, "unavailable")) from None

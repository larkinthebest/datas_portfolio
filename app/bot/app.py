from __future__ import annotations

import asyncio
import html
from typing import Any

import httpx
from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import Message

from app.core.config import Settings, get_settings

HELP = """Команды:
/whoami — показать ваш числовой Telegram user ID
/ask &lt;вопрос&gt; — вопрос по документам
/search &lt;текст&gt; — поиск доказательств
/documents — документы
/transactions — операции
/unmatched, /conflicts — сверка
/calculations — доступные расчёты
/sync — безопасный dry-run (только admin)
/sync_status — статус синхронизации
/audit — аудит (только admin)
/settings — состояние конфигурации (только admin)
/health — состояние API"""


def create_dispatcher(settings: Settings) -> Dispatcher:
    dispatcher = Dispatcher()
    router = Router()

    def allowed(message: Message) -> bool:
        return bool(
            message.from_user and message.from_user.id in settings.telegram_allowed_user_ids
        )

    def admin(message: Message) -> bool:
        return bool(message.from_user and message.from_user.id in settings.telegram_admin_user_ids)

    async def api(method: str, path: str, *, json: dict[str, object] | None = None) -> Any:
        headers = {"X-API-Key": settings.api_key.get_secret_value()}
        async with httpx.AsyncClient(base_url=settings.internal_api_url, timeout=60) as client:
            response = await client.request(method, path, json=json, headers=headers)
            response.raise_for_status()
            return response.json()

    async def require_tenant(message: Message) -> str | None:
        if settings.telegram_default_tenant_id is None:
            await message.answer(
                "Не задан TELEGRAM_DEFAULT_TENANT_ID. Настройте tenant mapping перед запросами."
            )
            return None
        return str(settings.telegram_default_tenant_id)

    async def answer_question(message: Message, query: str) -> None:
        tenant_id = await require_tenant(message)
        if tenant_id is None:
            return
        try:
            result = await api(
                "POST", "/api/v1/ask", json={"tenant_id": tenant_id, "query": query}
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code >= 500:
                await message.answer(
                    "Сервис генерации ответа временно перегружен. Попробуйте ещё раз через минуту."
                )
                return
            raise
        except httpx.RequestError:
            await message.answer("API временно недоступен. Попробуйте ещё раз через минуту.")
            return
        sources = "\n\n".join(
            f"📄 {html.escape(source['file_name'])}\n"
            f"Страница: {source.get('page') or '—'}\n"
            f"„{html.escape(source['quote'])}“"
            for source in result.get("sources", [])
        )
        body = html.escape(result.get("answer", "Недостаточно данных."))
        await message.answer(f"{body}\n\nИсточники:\n{sources or 'Не найдены'}")

    @router.message(Command("whoami"))
    async def whoami_handler(message: Message) -> None:
        if message.from_user is None:
            await message.answer("Не удалось определить Telegram user ID.")
            return
        await message.answer(f"Ваш Telegram user ID: {message.from_user.id}")

    @router.message(Command("start", "help"))
    async def help_handler(message: Message) -> None:
        await message.answer(HELP if allowed(message) else "Доступ запрещён.")

    @router.message(Command("health"))
    async def health_handler(message: Message) -> None:
        if not allowed(message):
            return
        await message.answer(f"API: {await api('GET', '/health')}")

    @router.message(Command("settings"))
    async def settings_handler(message: Message) -> None:
        if not admin(message):
            await message.answer("Команда доступна только администратору.")
            return
        await message.answer(
            "\n".join(
                (
                    f"Environment: {settings.app_env}",
                    f"Drive: {'configured' if settings.google_drive_root_folder_id else 'missing'}",
                    f"Pinecone: {'configured' if settings.pinecone_index else 'missing'}",
                    f"Gemini external processing: {settings.ai_external_processing_enabled}",
                    f"Initial dry run: {settings.initial_sync_dry_run}",
                )
            )
        )

    @router.message(Command("sync"))
    async def sync_handler(message: Message) -> None:
        if not admin(message):
            await message.answer("Команда доступна только администратору.")
            return
        tenant_id = await require_tenant(message)
        if tenant_id is None:
            return
        result = await api(
            "POST",
            "/api/v1/sync",
            json={"tenant_id": tenant_id, "dry_run": True, "limit": 20},
        )
        await message.answer(f"Dry-run поставлен в очередь: {result['job_id']}")

    @router.message(Command("ask"))
    async def ask_handler(message: Message) -> None:
        if not allowed(message):
            return
        query = (message.text or "").partition(" ")[2].strip()
        if not query:
            await message.answer("Добавьте вопрос после /ask.")
            return
        await answer_question(message, query)

    @router.message(Command("search"))
    async def search_handler(message: Message) -> None:
        if not allowed(message):
            return
        query = (message.text or "").partition(" ")[2].strip()
        tenant_id = await require_tenant(message)
        if not query or tenant_id is None:
            await message.answer("Добавьте поисковый запрос после /search.")
            return
        result = await api("POST", "/api/v1/search", json={"tenant_id": tenant_id, "query": query})
        lines = [
            f"{index}. {html.escape(hit['metadata'].get('file_name', hit['chunk_id']))}"
            for index, hit in enumerate(result.get("hits", []), start=1)
        ]
        await message.answer("Найдено:\n" + ("\n".join(lines) or "Ничего"))

    @router.message(Command("documents", "transactions", "audit"))
    async def list_handler(message: Message) -> None:
        if not allowed(message):
            return
        command = (message.text or "").split(maxsplit=1)[0].lstrip("/").split("@")[0]
        if command == "audit" and not admin(message):
            await message.answer("Команда доступна только администратору.")
            return
        tenant_id = await require_tenant(message)
        if tenant_id is None:
            return
        result = await api("GET", f"/api/v1/{command}?tenant_id={tenant_id}&limit=20")
        await message.answer(html.escape(str(result)[:3500]))

    @router.message(
        Command(
            "document",
            "unmatched",
            "conflicts",
            "calculations",
            "sync_status",
        )
    )
    async def command_placeholder(message: Message) -> None:
        if not allowed(message):
            return
        await message.answer(
            "Укажите параметры команды; подробности доступны через /help и API docs."
        )

    @router.message(F.text)
    async def plain_question(message: Message) -> None:
        if not allowed(message):
            return
        await answer_question(message, message.text or "")

    dispatcher.include_router(router)
    return dispatcher


async def run() -> None:
    settings = get_settings()
    token = settings.telegram_bot_token.get_secret_value()
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is required")
    bot = Bot(token=token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    await create_dispatcher(settings).start_polling(bot)


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()

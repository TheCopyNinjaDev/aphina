import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from app.config import settings
from app.database import init_db
from app.proxy_manager import proxy_manager, Proxy
from bot.handlers import auth, profile, food, progress, recipe, fallback

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def _make_bot(proxy: Proxy | None) -> Bot:
    """Create a Bot instance, optionally routing Telegram traffic through a proxy."""
    session = AiohttpSession(proxy=proxy.http_url) if proxy else AiohttpSession()
    return Bot(
        token=settings.BOT_TOKEN,
        session=session,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )


async def _init(bot: Bot) -> None:
    await init_db()
    me = await bot.get_me()
    logger.info(f"Bot connected: @{me.username}")


async def main():
    dp = Dispatcher(storage=MemoryStorage())

    dp.include_router(auth.router)
    dp.include_router(profile.router)
    dp.include_router(food.router)
    dp.include_router(progress.router)
    dp.include_router(recipe.router)
    dp.include_router(fallback.router)

    tried: set[Proxy] = set()
    last_exc: Exception | None = None

    # Try each proxy in turn; fall back to direct on full exhaustion
    max_attempts = min(len(proxy_manager._all) + 1, 6)  # proxies + 1 direct fallback

    for attempt in range(1, max_attempts + 1):
        proxy = proxy_manager._pick(tried)
        if proxy:
            tried.add(proxy)

        label = str(proxy) if proxy else "direct"
        logger.info(f"Connecting to Telegram via {label} (attempt {attempt})")

        bot = _make_bot(proxy)
        try:
            await _init(bot)
        except Exception as exc:
            last_exc = exc
            logger.warning(f"Connection via {label} failed: {exc}")
            if proxy:
                proxy_manager.mark_failed(proxy)
            await bot.session.close()
            await asyncio.sleep(2)
            continue

        # Connected — start polling
        logger.info("Starting polling...")
        try:
            await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
        except Exception as exc:
            logger.error(f"Polling crashed: {exc}")
        finally:
            await bot.session.close()
        return  # normal exit

    raise RuntimeError(
        f"Could not connect to Telegram after {max_attempts} attempts"
    ) from last_exc


if __name__ == "__main__":
    asyncio.run(main())

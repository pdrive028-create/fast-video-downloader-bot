import os
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart

TOKEN = os.getenv("BOT_TOKEN")

if not TOKEN:
    raise RuntimeError("BOT_TOKEN is not set")

bot = Bot(TOKEN)
dp = Dispatcher()


@dp.message(CommandStart())
async def start(message: types.Message):
    await message.answer(
        "🎬 Fast Video Downloader\n\n"
        "Send me any video link from YouTube, Facebook, Instagram, "
        "Terabox & supported websites.\n\n"
        "⚡ HD • Full HD • 4K"
    )


@dp.message()
async def handle_message(message: types.Message):
    text = message.text or ""

    if text.startswith("http://") or text.startswith("https://"):
        await message.answer(
            "🔍 Link received!\n\n"
            "Downloader system is being prepared. ⚡"
        )
    else:
        await message.answer(
            "📎 Please send a video link."
        )


async def main():
    print("Bot started...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

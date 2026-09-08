import os
import asyncio
import tempfile
from pathlib import Path

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile

import yt_dlp
import imageio_ffmpeg


TOKEN = os.getenv("BOT_TOKEN")

if not TOKEN:
    raise RuntimeError("BOT_TOKEN is not set")

FFMPEG_PATH = imageio_ffmpeg.get_ffmpeg_exe()

bot = Bot(TOKEN)
dp = Dispatcher()

# Temporary format storage
user_formats = {}


@dp.message(CommandStart())
async def start(message: types.Message):
    await message.answer(
        "🎬 Fast Video Downloader\n\n"
        "Send me any video link from YouTube, Facebook, Instagram, "
        "Terabox & supported websites.\n\n"
        "⚡ HD • Full HD • 4K"
    )


def get_video_info(url: str):
    options = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "ffmpeg_location": FFMPEG_PATH,
    }

    with yt_dlp.YoutubeDL(options) as ydl:
        return ydl.extract_info(url, download=False)


def build_quality_options(info):
    formats = info.get("formats", [])

    heights = [2160, 1440, 1080, 720, 480]

    result = []

    for target_height in heights:
        candidates = []

        for f in formats:
            height = f.get("height")
            if not height:
                continue

            if height <= target_height:
                vcodec = f.get("vcodec")
                acodec = f.get("acodec")

                if vcodec and vcodec != "none":
                    size = f.get("filesize") or f.get("filesize_approx") or 0

                    candidates.append({
                        "format_id": f["format_id"],
                        "height": height,
                        "size": size,
                        "has_audio": bool(acodec and acodec != "none"),
                    })

        if candidates:
            best = max(candidates, key=lambda x: x["height"])

            if not any(x["height"] == best["height"] for x in result):
                result.append(best)

    return result


def size_text(size):
    if not size:
        return "Size unknown"

    mb = size / (1024 * 1024)

    if mb >= 1024:
        return f"{mb / 1024:.2f} GB"

    return f"{mb:.1f} MB"


@dp.message(F.text)
async def handle_message(message: types.Message):
    text = message.text.strip()

    if not (text.startswith("http://") or text.startswith("https://")):
        await message.answer("📎 Please send a video link.")
        return

    status = await message.answer("🔍 Analyzing video...\n\nPlease wait ⚡")

    try:
        info = await asyncio.to_thread(get_video_info, text)

        title = info.get("title", "Video")
        formats = build_quality_options(info)

        if not formats:
            await status.edit_text(
                "❌ No downloadable video qualities were found."
            )
            return

        user_formats[message.from_user.id] = {}

        buttons = []

        for index, fmt in enumerate(formats):
            key = str(index)

            user_formats[message.from_user.id][key] = {
                "url": text,
                "format_id": fmt["format_id"],
                "height": fmt["height"],
            }

            label = f"{fmt['height']}p • {size_text(fmt['size'])}"

            buttons.append(
                [
                    InlineKeyboardButton(
                        text=label,
                        callback_data=f"quality:{key}"
                    )
                ]
            )

        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

        await status.edit_text(
            f"🎬 {title}\n\n"
            "📥 Select video quality:",
            reply_markup=keyboard
        )

    except Exception as e:
        print("INFO ERROR:", repr(e))

        await status.edit_text(
            "❌ Could not analyze this link.\n\n"
            "Please check the URL and try again."
        )


@dp.callback_query(F.data.startswith("quality:"))
async def quality_selected(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    key = callback.data.split(":", 1)[1]

    if user_id not in user_formats:
        await callback.answer("This selection expired. Send the link again.", show_alert=True)
        return

    selected = user_formats[user_id].get(key)

    if not selected:
        await callback.answer("Selection expired. Send the link again.", show_alert=True)
        return

    await callback.answer()

    await callback.message.edit_text(
        f"⏳ Preparing {selected['height']}p video...\n\n"
        "⚡ Downloading..."
    )

    url = selected["url"]
    format_id = selected["format_id"]
    height = selected["height"]

    temp_dir = Path(tempfile.mkdtemp(prefix="video_dl_"))
    output_template = str(temp_dir / "%(title).80s.%(ext)s")

    try:
        # Prefer selected video + best audio.
        format_selector = (
            f"{format_id}+bestaudio/best[height<={height}]"
        )

        options = {
            "format": format_selector,
            "outtmpl": output_template,
            "merge_output_format": "mp4",
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "ffmpeg_location": FFMPEG_PATH,
        }

        await asyncio.to_thread(
            download_video,
            url,
            options
        )

        files = list(temp_dir.glob("*"))

        video_file = None

        for file in files:
            if file.is_file() and file.suffix.lower() in {
                ".mp4",
                ".mkv",
                ".webm",
                ".mov"
            }:
                video_file = file
                break

        if not video_file:
            raise RuntimeError("Downloaded video file not found")

        await callback.message.edit_text(
            f"✅ {height}p download complete!\n\n"
            "📤 Uploading to Telegram..."
        )

        await callback.message.answer_document(
            FSInputFile(video_file),
            caption=f"🎬 {height}p • Fast Video Downloader"
        )

        await callback.message.delete()

    except Exception as e:
        print("DOWNLOAD ERROR:", repr(e))

        await callback.message.edit_text(
            "❌ Download failed.\n\n"
            "Try another quality or another video link."
        )

    finally:
        for file in temp_dir.glob("*"):
            try:
                file.unlink()
            except Exception:
                pass

        try:
            temp_dir.rmdir()
        except Exception:
            pass

        user_formats.pop(user_id, None)


def download_video(url, options):
    with yt_dlp.YoutubeDL(options) as ydl:
        ydl.download([url])


async def main():
    print("Bot started...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

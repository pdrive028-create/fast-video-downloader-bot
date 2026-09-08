import os
import asyncio
import tempfile
from pathlib import Path

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    FSInputFile,
)

import yt_dlp
import imageio_ffmpeg


# =========================================================
# CONFIG
# =========================================================

TOKEN = os.getenv("BOT_TOKEN")

if not TOKEN:
    raise RuntimeError("BOT_TOKEN is not set")

# Railway private connection to bgutil provider
POT_PROVIDER_URL = os.getenv(
    "POT_PROVIDER_URL",
    "http://bgutil-ytdlp-pot-provider:4416"
)

FFMPEG_PATH = imageio_ffmpeg.get_ffmpeg_exe()

bot = Bot(TOKEN)
dp = Dispatcher()

# Temporary format storage
user_formats = {}


# =========================================================
# YOUTUBE SETTINGS
# =========================================================

# mweb is the recommended client when using
# a PO Token Provider.
#
# Fallback clients are included in case one client
# does not work for a specific video.
YOUTUBE_CLIENTS = [
    ["mweb"],
    ["android_vr"],
    ["tv"],
    ["web_embedded"],
]


# =========================================================
# YOUTUBE EXTRACTOR OPTIONS
# =========================================================

def youtube_extractor_args(clients):
    return {
        "youtube": {
            "player_client": clients
        },
        "youtubepot-bgutilhttp": {
            "base_url": POT_PROVIDER_URL
        }
    }


# =========================================================
# START
# =========================================================

@dp.message(CommandStart())
async def start(message: types.Message):

    await message.answer(
        "🎬 Fast Video Downloader\n\n"
        "Send me any video link from YouTube, Facebook, Instagram, "
        "Terabox & supported websites.\n\n"
        "⚡ HD • Full HD • 4K"
    )


# =========================================================
# GET VIDEO INFO
# =========================================================

def get_video_info(url: str):

    last_error = None

    for clients in YOUTUBE_CLIENTS:

        options = {
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "ffmpeg_location": FFMPEG_PATH,

            "extractor_args": youtube_extractor_args(
                clients
            ),

            "retries": 2,
            "fragment_retries": 2,
        }

        try:

            print(
                f"Trying YouTube client: {clients}"
            )

            with yt_dlp.YoutubeDL(options) as ydl:

                info = ydl.extract_info(
                    url,
                    download=False
                )

            if info:
                print(
                    f"Successfully extracted using {clients}"
                )

                return info

        except Exception as e:

            last_error = e

            print(
                f"INFO ERROR with client {clients}: "
                f"{repr(e)}"
            )

    if last_error:
        raise last_error

    raise RuntimeError(
        "Unable to extract video information"
    )


# =========================================================
# QUALITY OPTIONS
# =========================================================

def build_quality_options(info):

    formats = info.get(
        "formats",
        []
    )

    heights = [
        2160,
        1440,
        1080,
        720,
        480,
        360,
    ]

    result = []

    for target_height in heights:

        candidates = []

        for f in formats:

            height = f.get(
                "height"
            )

            if not height:
                continue

            if height <= target_height:

                vcodec = f.get(
                    "vcodec"
                )

                if (
                    vcodec
                    and vcodec != "none"
                ):

                    size = (
                        f.get("filesize")
                        or f.get("filesize_approx")
                        or 0
                    )

                    candidates.append(
                        {
                            "format_id": f.get(
                                "format_id"
                            ),
                            "height": height,
                            "size": size,
                            "vcodec": vcodec,
                            "acodec": f.get(
                                "acodec"
                            ),
                        }
                    )

        if not candidates:
            continue

        # Highest resolution available
        best = max(
            candidates,
            key=lambda x: (
                x["height"],
                x["size"]
            )
        )

        # Don't duplicate resolutions
        if not any(
            x["height"] == best["height"]
            for x in result
        ):

            result.append(
                best
            )

    return result


# =========================================================
# SIZE FORMAT
# =========================================================

def size_text(size):

    if not size:
        return "Size unknown"

    mb = size / (
        1024 * 1024
    )

    if mb >= 1024:

        return (
            f"{mb / 1024:.2f} GB"
        )

    return (
        f"{mb:.1f} MB"
    )


# =========================================================
# LINK RECEIVED
# =========================================================

@dp.message(F.text)
async def handle_message(
    message: types.Message
):

    text = message.text.strip()

    if not (
        text.startswith("http://")
        or text.startswith("https://")
    ):

        await message.answer(
            "📎 Please send a video link."
        )

        return

    status = await message.answer(
        "🔍 Analyzing video...\n\n"
        "Please wait ⚡"
    )

    try:

        info = await asyncio.to_thread(
            get_video_info,
            text
        )

        title = info.get(
            "title",
            "Video"
        )

        formats = build_quality_options(
            info
        )

        if not formats:

            await status.edit_text(
                "❌ No downloadable video qualities were found."
            )

            return

        user_id = message.from_user.id

        user_formats[user_id] = {}

        buttons = []

        for index, fmt in enumerate(
            formats
        ):

            key = str(index)

            user_formats[user_id][key] = {
                "url": text,
                "format_id": fmt[
                    "format_id"
                ],
                "height": fmt[
                    "height"
                ],
            }

            label = (
                f"{fmt['height']}p"
                f" • "
                f"{size_text(fmt['size'])}"
            )

            buttons.append(
                [
                    InlineKeyboardButton(
                        text=label,
                        callback_data=(
                            f"quality:{key}"
                        )
                    )
                ]
            )

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=buttons
        )

        await status.edit_text(
            f"🎬 {title}\n\n"
            "📥 Select video quality:",
            reply_markup=keyboard
        )

    except Exception as e:

        print(
            "INFO ERROR:",
            repr(e)
        )

        await status.edit_text(
            "❌ Could not analyze this link.\n\n"
            "YouTube may be temporarily blocking the request.\n"
            "Please try again."
        )


# =========================================================
# QUALITY BUTTON
# =========================================================

@dp.callback_query(
    F.data.startswith("quality:")
)
async def quality_selected(
    callback: types.CallbackQuery
):

    user_id = callback.from_user.id

    key = callback.data.split(
        ":",
        1
    )[1]

    if user_id not in user_formats:

        await callback.answer(
            "This selection expired. "
            "Send the link again.",
            show_alert=True
        )

        return

    selected = user_formats[
        user_id
    ].get(key)

    if not selected:

        await callback.answer(
            "Selection expired. "
            "Send the link again.",
            show_alert=True
        )

        return

    await callback.answer()

    height = selected[
        "height"
    ]

    await callback.message.edit_text(
        f"⏳ Preparing {height}p video...\n\n"
        "⚡ Downloading..."
    )

    url = selected[
        "url"
    ]

    temp_dir = Path(
        tempfile.mkdtemp(
            prefix="video_dl_"
        )
    )

    output_template = str(
        temp_dir
        / "%(title).80s.%(ext)s"
    )

    try:

        # =================================================
        # DOWNLOAD
        # =================================================

        format_selector = (
            f"bestvideo[height<={height}]"
            "+bestaudio/"
            f"best[height<={height}]"
        )

        # First try mweb with PO Token Provider
        # Then fallback clients if needed.
        download_success = False
        last_download_error = None

        for clients in YOUTUBE_CLIENTS:

            options = {
                "format": format_selector,

                "outtmpl": output_template,

                "merge_output_format": "mp4",

                "noplaylist": True,

                "quiet": True,

                "no_warnings": True,

                "ffmpeg_location": FFMPEG_PATH,

                "retries": 3,

                "fragment_retries": 3,

                "continuedl": True,

                "concurrent_fragment_downloads": 4,

                "extractor_args": youtube_extractor_args(
                    clients
                ),
            }

            try:

                print(
                    f"Trying download client: {clients}"
                )

                await asyncio.to_thread(
                    download_video,
                    url,
                    options
                )

                download_success = True

                print(
                    f"Download successful using {clients}"
                )

                break

            except Exception as e:

                last_download_error = e

                print(
                    f"DOWNLOAD ERROR with client "
                    f"{clients}: {repr(e)}"
                )

        if not download_success:

            if last_download_error:
                raise last_download_error

            raise RuntimeError(
                "All YouTube download clients failed"
            )

        # =================================================
        # FIND DOWNLOADED FILE
        # =================================================

        files = list(
            temp_dir.glob("*")
        )

        video_file = None

        for file in files:

            if (
                file.is_file()
                and file.suffix.lower()
                in {
                    ".mp4",
                    ".mkv",
                    ".webm",
                    ".mov"
                }
            ):

                video_file = file

                break

        if not video_file:

            raise RuntimeError(
                "Downloaded video file not found"
            )

        # =================================================
        # UPLOAD
        # =================================================

        await callback.message.edit_text(
            f"✅ {height}p download complete!\n\n"
            "📤 Uploading to Telegram..."
        )

        await callback.message.answer_document(
            FSInputFile(
                video_file
            ),
            caption=(
                f"🎬 {height}p\n"
                "⚡ Fast Video Downloader"
            )
        )

        await callback.message.delete()

    except Exception as e:

        print(
            "DOWNLOAD ERROR:",
            repr(e)
        )

        await callback.message.edit_text(
            "❌ Download failed.\n\n"
            "Try another quality or another video link."
        )

    finally:

        # =================================================
        # DELETE TEMP FILES
        # =================================================

        for file in temp_dir.glob("*"):

            try:
                file.unlink()

            except Exception:
                pass

        try:

            temp_dir.rmdir()

        except Exception:
            pass

        user_formats.pop(
            user_id,
            None
        )


# =========================================================
# DOWNLOAD FUNCTION
# =========================================================

def download_video(
    url,
    options
):

    with yt_dlp.YoutubeDL(
        options
    ) as ydl:

        ydl.download(
            [url]
        )


# =========================================================
# MAIN
# =========================================================

async def main():

    print(
        "Bot started..."
    )

    print(
        "PO Token Provider:",
        POT_PROVIDER_URL
    )

    await dp.start_polling(
        bot
    )


# =========================================================
# RUN
# =========================================================

if __name__ == "__main__":

    asyncio.run(
        main()
    )

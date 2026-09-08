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
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer

import yt_dlp
import imageio_ffmpeg


# =========================================================
# CONFIG
# =========================================================

TOKEN = os.getenv("BOT_TOKEN")

if not TOKEN:
    raise RuntimeError("BOT_TOKEN is not set")


# =========================================================
# BGUTIL PO TOKEN PROVIDER
# =========================================================

POT_PROVIDER_URL = os.getenv(
    "POT_PROVIDER_URL",
    "http://bgutil-ytdlp-pot-provider:4416"
)


# =========================================================
# TELEGRAM LOCAL BOT API
# =========================================================

LOCAL_BOT_API_URL = os.getenv(
    "LOCAL_BOT_API_URL",
    ""
)


# =========================================================
# FFMPEG
# =========================================================

FFMPEG_PATH = imageio_ffmpeg.get_ffmpeg_exe()


# =========================================================
# TELEGRAM BOT SETUP
# =========================================================

if LOCAL_BOT_API_URL:

    print(
        "========================================"
    )

    print(
        "Using Telegram Local Bot API"
    )

    print(
        "Local API:",
        LOCAL_BOT_API_URL
    )

    print(
        "========================================"
    )

    session = AiohttpSession(
        api=TelegramAPIServer.from_base(
            LOCAL_BOT_API_URL,
            is_local=True
        )
    )

    bot = Bot(
        TOKEN,
        session=session
    )

else:

    print(
        "========================================"
    )

    print(
        "Using Telegram Cloud Bot API"
    )

    print(
        "========================================"
    )

    bot = Bot(TOKEN)


dp = Dispatcher()


# =========================================================
# USER FORMAT STORAGE
# =========================================================

user_formats = {}


# =========================================================
# YOUTUBE CLIENTS
# =========================================================
#
# mweb is used with the bgutil PO Token provider.
#
# This is important because YouTube may require
# PO Tokens for some player clients.
# =========================================================

YOUTUBE_CLIENTS = [
    ["mweb"],
]


# =========================================================
# YOUTUBE EXTRACTOR ARGS
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
# START COMMAND
# =========================================================

@dp.message(CommandStart())
async def start(message: types.Message):

    await message.answer(
        "🎬 Fast Video Downloader\n\n"
        "Send me a video link.\n\n"
        "⚡ HD • Full HD • 4K"
    )


# =========================================================
# GET VIDEO INFORMATION
# =========================================================

def get_video_info(url: str):

    last_error = None

    for clients in YOUTUBE_CLIENTS:

        options = {
            "quiet": True,

            "no_warnings": True,

            "noplaylist": True,

            "skip_download": True,

            "ffmpeg_location": FFMPEG_PATH,

            "extractor_args": youtube_extractor_args(
                clients
            ),

            "retries": 3,

            "fragment_retries": 3,

            "socket_timeout": 30,
        }

        try:

            print(
                "========================================"
            )

            print(
                f"Trying info client: {clients}"
            )

            print(
                f"URL: {url}"
            )

            with yt_dlp.YoutubeDL(
                options
            ) as ydl:

                info = ydl.extract_info(
                    url,
                    download=False
                )

            if info:

                print(
                    f"INFO SUCCESS: {clients}"
                )

                print(
                    "Title:",
                    info.get(
                        "title",
                        "Unknown"
                    )
                )

                return info

        except Exception as e:

            last_error = e

            print(
                "----------------------------------------"
            )

            print(
                f"INFO ERROR: {clients}"
            )

            print(
                repr(e)
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

    target_heights = [
        2160,
        1440,
        1080,
        720,
        480,
        360,
    ]

    result = []

    available_formats = []

    for f in formats:

        height = f.get("height")

        if not height:
            continue

        if height <= 0:
            continue

        vcodec = f.get("vcodec")

        if not vcodec:
            continue

        if vcodec == "none":
            continue

        acodec = f.get("acodec")

        filesize = (
            f.get("filesize")
            or f.get("filesize_approx")
            or 0
        )

        available_formats.append(
            {
                "format_id": f.get(
                    "format_id"
                ),

                "height": height,

                "size": filesize,

                "vcodec": vcodec,

                "acodec": acodec,

                "ext": f.get(
                    "ext"
                ),
            }
        )


    # =====================================================
    # BUILD QUALITY BUTTONS
    # =====================================================

    for target in target_heights:

        candidates = [
            f
            for f in available_formats
            if f["height"] <= target
        ]

        if not candidates:
            continue

        candidates.sort(
            key=lambda x: (
                x["height"],

                1 if (
                    x["acodec"]
                    and x["acodec"] != "none"
                ) else 0,

                x["size"],
            ),

            reverse=True
        )

        best = candidates[0]

        if any(
            x["height"] == best["height"]
            for x in result
        ):
            continue

        result.append(
            best
        )

    return result


# =========================================================
# SIZE TEXT
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
# USER SENDS VIDEO LINK
# =========================================================

@dp.message(F.text)
async def handle_message(
    message: types.Message
):

    text = message.text.strip()

    if not (
        text.startswith(
            "http://"
        )
        or
        text.startswith(
            "https://"
        )
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
                "❌ No downloadable video "
                "qualities were found."
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

                "height": fmt[
                    "height"
                ],

                "format_id": fmt[
                    "format_id"
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
            "========================================"
        )

        print(
            "INFO FINAL ERROR:"
        )

        print(
            repr(e)
        )

        print(
            "========================================"
        )


        await status.edit_text(
            "❌ Could not analyze this link.\n\n"
            "Please try another video link."
        )


# =========================================================
# QUALITY SELECTED
# =========================================================

@dp.callback_query(
    F.data.startswith(
        "quality:"
    )
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
            "Selection expired. "
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


    url = selected[
        "url"
    ]

    height = selected[
        "height"
    ]


    await callback.message.edit_text(
        f"⏳ Preparing {height}p video...\n\n"
        "⚡ Downloading..."
    )


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
        # FORMAT FALLBACKS
        # =================================================

        format_selectors = [

            # Best MP4 under selected height
            f"best[height<={height}][ext=mp4]",

            # Best combined format
            f"best[height<={height}]",

            # Best video + audio
            f"bestvideo[height<={height}]+bestaudio",

            # Video + audio fallback
            f"bestvideo[height<={height}]+bestaudio/best",

            # Final fallback
            "best",
        ]


        download_success = False

        last_download_error = None


        # =================================================
        # TRY YOUTUBE CLIENTS
        # =================================================

        for clients in YOUTUBE_CLIENTS:

            for format_selector in format_selectors:

                options = {

                    "format":
                        format_selector,

                    "outtmpl":
                        output_template,

                    "merge_output_format":
                        "mp4",

                    "noplaylist":
                        True,

                    "quiet":
                        True,

                    "no_warnings":
                        True,

                    "ffmpeg_location":
                        FFMPEG_PATH,

                    "retries":
                        3,

                    "fragment_retries":
                        3,

                    "continuedl":
                        True,

                    "concurrent_fragment_downloads":
                        4,

                    "socket_timeout":
                        30,

                    "extractor_args":
                        youtube_extractor_args(
                            clients
                        ),
                }


                try:

                    print(
                        "----------------------------------------"
                    )

                    print(
                        f"DOWNLOAD CLIENT: "
                        f"{clients}"
                    )

                    print(
                        f"FORMAT: "
                        f"{format_selector}"
                    )


                    await asyncio.to_thread(
                        download_video,

                        url,

                        options
                    )


                    files = [
                        f
                        for f in temp_dir.glob("*")
                        if f.is_file()
                    ]


                    valid_files = [
                        f
                        for f in files
                        if f.suffix.lower()
                        in {
                            ".mp4",
                            ".mkv",
                            ".webm",
                            ".mov",
                        }
                    ]


                    if valid_files:

                        download_success = True


                        print(
                            "DOWNLOAD SUCCESS"
                        )

                        print(
                            f"Client: {clients}"
                        )

                        print(
                            f"Format: "
                            f"{format_selector}"
                        )

                        break


                except Exception as e:

                    last_download_error = e


                    print(
                        "DOWNLOAD ATTEMPT FAILED"
                    )

                    print(
                        f"Client: {clients}"
                    )

                    print(
                        f"Format: "
                        f"{format_selector}"
                    )

                    print(
                        repr(e)
                    )


                    # Remove partial files
                    for partial in temp_dir.glob("*"):

                        try:

                            if partial.is_file():

                                partial.unlink()

                        except Exception:

                            pass


            if download_success:

                break


        # =================================================
        # DOWNLOAD FAILED
        # =================================================

        if not download_success:

            if last_download_error:

                raise last_download_error

            raise RuntimeError(
                "All download attempts failed"
            )


        # =================================================
        # FIND FINAL VIDEO
        # =================================================

        files = [
            f
            for f in temp_dir.glob("*")
            if f.is_file()
        ]


        video_files = [
            f
            for f in files
            if f.suffix.lower()
            in {
                ".mp4",
                ".mkv",
                ".webm",
                ".mov",
            }
        ]


        if not video_files:

            raise RuntimeError(
                "Downloaded video file "
                "not found"
            )


        # =================================================
        # PREFER MP4
        # =================================================

        mp4_files = [
            f
            for f in video_files
            if f.suffix.lower()
            == ".mp4"
        ]


        if mp4_files:

            video_file = max(
                mp4_files,

                key=lambda f:
                f.stat().st_size
            )

        else:

            video_file = max(
                video_files,

                key=lambda f:
                f.stat().st_size
            )


        # =================================================
        # TELEGRAM UPLOAD
        # =================================================

        await callback.message.edit_text(
            f"✅ {height}p download complete!\n\n"
            "📤 Uploading to Telegram..."
        )


        file_size_mb = (
            video_file.stat().st_size
            / (1024 * 1024)
        )


        print(
            "========================================"
        )

        print(
            "TELEGRAM UPLOAD"
        )

        print(
            "File:",
            video_file
        )

        print(
            f"Size: {file_size_mb:.2f} MB"
        )

        print(
            "========================================"
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
            "========================================"
        )

        print(
            "DOWNLOAD FINAL ERROR:"
        )

        print(
            repr(e)
        )

        print(
            "========================================"
        )


        await callback.message.edit_text(
            "❌ Download failed.\n\n"
            "Try another quality or another "
            "video link."
        )


    finally:

        # =================================================
        # CLEAN TEMP FILES
        # =================================================

        for file in temp_dir.glob("*"):

            try:

                if file.is_file():

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
        "========================================"

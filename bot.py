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

    print("========================================")
    print("Using Telegram Local Bot API")
    print("Local API:", LOCAL_BOT_API_URL)
    print("========================================")

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

    print("========================================")
    print("Using Telegram Cloud Bot API")
    print("========================================")

    bot = Bot(TOKEN)


dp = Dispatcher()


# =========================================================
# USER FORMAT STORAGE
# =========================================================

user_formats = {}


# =========================================================
# YOUTUBE CLIENTS
# =========================================================

YOUTUBE_CLIENTS = [
    ["mweb"],
    ["android_vr"],
    ["tv"],
    ["web_embedded"],
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

    successful_infos = []
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

            # Help yt-dlp expose formats instead of
            # stopping at one combined/progressive format.
            "allow_unplayable_formats": False,
        }

        try:

            print("========================================")
            print(f"Trying info client: {clients}")
            print(f"URL: {url}")

            with yt_dlp.YoutubeDL(options) as ydl:

                info = ydl.extract_info(
                    url,
                    download=False
                )

            if not info:
                continue

            formats = info.get("formats", [])

            heights = sorted({
                f.get("height")
                for f in formats
                if f.get("height")
            })

            max_height = max(
                heights,
                default=0
            )

            video_format_count = sum(
                1
                for f in formats
                if (
                    f.get("height")
                    and f.get("height") > 0
                    and f.get("vcodec")
                    and f.get("vcodec") != "none"
                )
            )

            print(
                f"INFO SUCCESS: {clients}"
            )

            print(
                "Title:",
                info.get("title", "Unknown")
            )

            print(
                "Available heights:",
                heights
            )

            print(
                "Maximum height:",
                max_height
            )

            print(
                "Video format count:",
                video_format_count
            )

            successful_infos.append({
                "info": info,
                "max_height": max_height,
                "video_format_count": video_format_count,
                "client": clients,
            })

        except Exception as e:

            last_error = e

            print("----------------------------------------")
            print(f"INFO ERROR: {clients}")
            print(repr(e))

    # =====================================================
    # NO CLIENT WORKED
    # =====================================================

    if not successful_infos:

        if last_error:
            raise last_error

        raise RuntimeError(
            "Unable to extract video information"
        )

    # =====================================================
    # CHOOSE THE RICHEST BASE INFO
    # =====================================================

    successful_infos.sort(
        key=lambda item: (
            item["max_height"],
            item["video_format_count"]
        ),
        reverse=True
    )

    best_info = successful_infos[0]["info"]

    # =====================================================
    # MERGE FORMATS FROM ALL SUCCESSFUL CLIENTS
    # =====================================================

    merged_formats = []
    seen = set()

    for item in successful_infos:

        info = item["info"]

        for f in info.get("formats", []):

            format_id = f.get("format_id")

            # Create a signature that remains useful
            # even when different clients expose different
            # format IDs.
            signature = (
                format_id,
                f.get("height"),
                f.get("width"),
                f.get("vcodec"),
                f.get("acodec"),
                f.get("ext"),
                f.get("protocol"),
            )

            if signature in seen:
                continue

            seen.add(signature)
            merged_formats.append(f)

    best_info["formats"] = merged_formats

    # =====================================================
    # FINAL MERGED FORMAT LOG
    # =====================================================

    final_heights = sorted({
        f.get("height")
        for f in merged_formats
        if f.get("height")
    })

    print("========================================")
    print("FINAL MERGED VIDEO INFO")
    print(
        "Selected base client:",
        successful_infos[0]["client"]
    )
    print(
        "FINAL AVAILABLE HEIGHTS:",
        final_heights
    )
    print(
        "FINAL FORMAT COUNT:",
        len(merged_formats)
    )
    print("========================================")

    # =====================================================
    # DETAILED FORMAT LOG
    # =====================================================

    for f in sorted(
        merged_formats,
        key=lambda x: (
            x.get("height") or 0,
            x.get("tbr") or 0
        )
    ):

        height = f.get("height")

        if not height:
            continue

        print(
            "FORMAT:",
            f.get("format_id"),
            "|",
            f.get("height"),
            "p |",
            f.get("ext"),
            "|",
            "vcodec=" + str(f.get("vcodec")),
            "|",
            "acodec=" + str(f.get("acodec")),
            "|",
            "protocol=" + str(f.get("protocol"))
        )

    return best_info


# =========================================================
# QUALITY OPTIONS
# =========================================================

def build_quality_options(info):

    formats = info.get("formats", [])

    target_heights = [
        2160,
        1440,
        1080,
        720,
        480,
        360
    ]

    video_formats = []
    audio_formats = []

    # =====================================================
    # COLLECT VIDEO + AUDIO
    # =====================================================

    for f in formats:

        height = f.get("height")
        width = f.get("width")

        vcodec = f.get("vcodec")
        acodec = f.get("acodec")

        filesize = (
            f.get("filesize")
            or f.get("filesize_approx")
            or 0
        )

        tbr = f.get("tbr") or 0
        fps = f.get("fps") or 0
        ext = f.get("ext")

        # -------------------------------------------------
        # VIDEO
        # -------------------------------------------------

        if (
            height
            and height > 0
            and vcodec
            and vcodec != "none"
        ):

            video_formats.append({
                "format_id": f.get("format_id"),
                "height": height,
                "width": width or 0,
                "size": filesize,
                "vcodec": vcodec,
                "acodec": acodec,
                "ext": ext,
                "tbr": tbr,
                "fps": fps,
            })

        # -------------------------------------------------
        # AUDIO ONLY
        # -------------------------------------------------

        if (
            acodec
            and acodec != "none"
            and (
                not vcodec
                or vcodec == "none"
            )
        ):

            audio_formats.append({
                "format_id": f.get("format_id"),
                "size": filesize,
                "abr": f.get("abr") or 0,
                "ext": ext,
            })

    # =====================================================
    # BEST AUDIO FOR SIZE ESTIMATION
    # =====================================================

    best_audio_size = 0

    if audio_formats:

        audio_formats.sort(
            key=lambda x: (
                x["abr"],
                x["size"]
            ),
            reverse=True
        )

        best_audio_size = (
            audio_formats[0]["size"]
        )

    # =====================================================
    # BUILD ONE OPTION PER RESOLUTION
    # =====================================================

    result = []

    for target in target_heights:

        candidates = [
            f
            for f in video_formats
            if f["height"] <= target
        ]

        if not candidates:
            continue

        # Highest actual resolution first.
        # Then highest bitrate.
        # Then MP4.
        # Then filesize.
        candidates.sort(
            key=lambda x: (
                x["height"],
                x["tbr"],
                1 if x["ext"] == "mp4" else 0,
                x["size"]
            ),
            reverse=True
        )

        best = candidates[0]

        # Prevent duplicate resolutions.
        if any(
            x["height"] == best["height"]
            for x in result
        ):
            continue

        total_size = (
            best["size"]
            + best_audio_size
        )

        result.append({
            "format_id": best["format_id"],
            "height": best["height"],
            "size": total_size,
            "vcodec": best["vcodec"],
            "acodec": best["acodec"],
            "ext": best["ext"],
            "tbr": best["tbr"],
            "fps": best["fps"],
        })

    # Highest quality first.
    result.sort(
        key=lambda x: x["height"],
        reverse=True
    )

    print("========================================")
    print("QUALITY BUTTONS")

    for item in result:
        print(
            item["height"],
            "p |",
            size_text(item["size"]),
            "|",
            item["format_id"]
        )

    print("========================================")

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
                "height": fmt["height"],
                "format_id": fmt["format_id"],
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

    url = selected["url"]
    height = selected["height"]

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
        # FORMAT SELECTORS
        # =================================================

        format_selectors = [

            # Best MP4 combined format
            f"best[height<={height}][ext=mp4]",

            # Best combined format
            f"best[height<={height}]",

            # Best video + best audio
            f"bestvideo[height<={height}]+bestaudio",

            # Video + audio fallback
            f"bestvideo[height<={height}]+bestaudio/best[height<={height}]",

            # Final fallback
            "best",
        ]

        download_success = False
        last_download_error = None

        # =================================================
        # TRY ALL YOUTUBE CLIENTS
        # =================================================

        
        for clients in YOUTUBE_CLIENTS:

            if download_success:
                break

            for format_selector in format_selectors:

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

                    "socket_timeout": 30,

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
                        f"DOWNLOAD CLIENT: {clients}"
                    )

                    print(
                        f"DOWNLOAD HEIGHT: {height}p"
                    )

                    print(
                        f"FORMAT: {format_selector}"
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
                            f"Format: {format_selector}"
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
                        f"Format: {format_selector}"
                    )

                    print(
                        repr(e)
                    )

                    # Remove partial files.
                    for partial in temp_dir.glob("*"):

                        try:

                            if partial.is_file():

                                partial.unlink()

                        except Exception:

                            pass

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
            if f.suffix.lower() == ".mp4"
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
    )

    print(
        "Video Downloader 4K"
    )

    print(
        "Bot started..."
    )

    print(
        "Telegram Local API:",
        LOCAL_BOT_API_URL
        if LOCAL_BOT_API_URL
        else "DISABLED"
    )

    print(
        "PO Token Provider:",
        POT_PROVIDER_URL
    )

    print(
        "FFmpeg:",
        FFMPEG_PATH
    )

    print(
        "YouTube Clients:",
        YOUTUBE_CLIENTS
    )

    print(
        "========================================"
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

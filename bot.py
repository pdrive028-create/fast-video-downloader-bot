import os
import asyncio
import tempfile
import subprocess
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

    # -----------------------------------------------------
    # TRY EVERY CLIENT
    # -----------------------------------------------------

    for clients in YOUTUBE_CLIENTS:

        options = {
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "skip_download": True,
            "ffmpeg_location": FFMPEG_PATH,

            "extractor_args":
                youtube_extractor_args(
                    clients
                ),

            "retries": 3,
            "fragment_retries": 3,
            "socket_timeout": 30,
        }

        try:

            print("========================================")
            print("Trying info client:", clients)
            print("URL:", url)

            with yt_dlp.YoutubeDL(
                options
            ) as ydl:

                info = ydl.extract_info(
                    url,
                    download=False
                )

            if not info:
                continue

            formats = info.get(
                "formats",
                []
            )

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
                "INFO SUCCESS:",
                clients
            )

            print(
                "Title:",
                info.get(
                    "title",
                    "Unknown"
                )
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
            print(
                "INFO ERROR:",
                clients
            )

            print(
                repr(e)
            )

    # -----------------------------------------------------
    # ALL CLIENTS FAILED
    # -----------------------------------------------------

    if not successful_infos:

        if last_error:

            raise last_error

        raise RuntimeError(
            "Unable to extract video information"
        )

    # -----------------------------------------------------
    # BEST BASE INFO
    # -----------------------------------------------------

    successful_infos.sort(
        key=lambda item: (
            item["max_height"],
            item["video_format_count"]
        ),
        reverse=True
    )

    best_info = successful_infos[0]["info"]

    # -----------------------------------------------------
    # MERGE FORMATS
    #
    # IMPORTANT:
    # Store the client which originally provided
    # each format. This prevents a format_id from one
    # client being incorrectly requested from another.
    # -----------------------------------------------------

    merged_formats = []
    seen = set()

    for item in successful_infos:

        info = item["info"]
        source_client = item["client"]

        for f in info.get(
            "formats",
            []
        ):

            signature = (
                f.get("format_id"),
                f.get("height"),
                f.get("width"),
                f.get("vcodec"),
                f.get("acodec"),
                f.get("ext"),
                f.get("protocol"),
                tuple(source_client),
            )

            if signature in seen:
                continue

            seen.add(signature)

            format_copy = dict(f)

            # Internal field.
            # Used only by our downloader.
            format_copy["_source_client"] = (
                source_client
            )

            merged_formats.append(
                format_copy
            )

    best_info["formats"] = merged_formats

    # -----------------------------------------------------
    # FINAL FORMAT LOG
    # -----------------------------------------------------

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

    # -----------------------------------------------------
    # DETAILED FORMAT LOG
    # -----------------------------------------------------

    for f in sorted(
        merged_formats,
        key=lambda x: (
            x.get("height") or 0,
            x.get("tbr") or 0
        )
    ):

        if not f.get("height"):
            continue

        print(
            "FORMAT:",
            f.get("format_id"),
            "|",
            f.get("height"),
            "p |",
            f.get("ext"),
            "|",
            "vcodec=" + str(
                f.get("vcodec")
            ),
            "|",
            "acodec=" + str(
                f.get("acodec")
            ),
            "|",
            "client=" + str(
                f.get("_source_client")
            )
        )

    return best_info


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

    video_formats = []

    audio_formats = []

    # -----------------------------------------------------
    # COLLECT FORMATS
    # -----------------------------------------------------

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

        source_client = f.get(
            "_source_client"
        )

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

                "format_id":
                    f.get("format_id"),

                "height":
                    height,

                "width":
                    width or 0,

                "size":
                    filesize,

                "vcodec":
                    vcodec,

                "acodec":
                    acodec,

                "ext":
                    ext,

                "tbr":
                    tbr,

                "fps":
                    fps,

                "source_client":
                    source_client,
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

                "format_id":
                    f.get("format_id"),

                "size":
                    filesize,

                "abr":
                    f.get("abr") or 0,

                "source_client":
                    source_client,
            })

    # -----------------------------------------------------
    # BEST AUDIO SIZE
    # -----------------------------------------------------

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

    # -----------------------------------------------------
    # BUILD QUALITY OPTIONS
    # -----------------------------------------------------

    result = []

    for target in target_heights:

        candidates = [
            f
            for f in video_formats
            if f["height"] <= target
        ]

        if not candidates:
            continue

        # Highest actual resolution.
        # Highest bitrate.
        # Prefer MP4 where possible.
        # Then larger known file.
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

            "format_id":
                best["format_id"],

            "height":
                best["height"],

            "size":
                total_size,

            "vcodec":
                best["vcodec"],

            "acodec":
                best["acodec"],

            "ext":
                best["ext"],

            "tbr":
                best["tbr"],

            "fps":
                best["fps"],

            "source_client":
                best["source_client"],
        })

    # -----------------------------------------------------
    # HIGHEST FIRST
    # -----------------------------------------------------

    result.sort(
        key=lambda x:
        x["height"],
        reverse=True
    )

    print("========================================")
    print("QUALITY BUTTONS")

    for item in result:

        print(
            item["height"],
            "p |",
            size_text(
                item["size"]
            ),
            "| format=",
            item["format_id"],
            "| client=",
            item["source_client"]
        )

    print("========================================")

    return result


# =========================================================
# SIZE TEXT
# =========================================================

def size_text(size):

    if not size:

        return "Size unknown"

    mb = (
        size
        / (1024 * 1024)
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

        # -------------------------------------------------
        # CREATE BUTTONS
        # -------------------------------------------------

        for index, fmt in enumerate(
            formats
        ):

            key = str(index)

            user_formats[user_id][key] = {

                "url":
                    text,

                "height":
                    fmt["height"],

                "format_id":
                    fmt["format_id"],

                "source_client":
                    fmt["source_client"],

                "ext":
                    fmt["ext"],

                "vcodec":
                    fmt["vcodec"],

                "acodec":
                    fmt["acodec"],
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

    # -----------------------------------------------------
    # CHECK USER DATA
    # -----------------------------------------------------

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
    format_id = selected["format_id"]
    source_client = selected["source_client"]

    await callback.message.edit_text(
        f"⏳ Preparing {height}p video...\n\n"
        "⚡ Downloading..."
    )

    # -----------------------------------------------------
    # TEMP DIRECTORY
    # -----------------------------------------------------

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
        # IMPORTANT:
        # DOWNLOAD THE EXACT FORMAT SELECTED
        #
        # Do NOT use generic "best" first.
        # The selected format_id belongs to the client
        # that originally returned it.
        # =================================================

        exact_format_selectors = [

            # Selected video + best audio
            f"{format_id}+bestaudio",

            # Selected format alone
            f"{format_id}",
        ]

        download_success = False
        last_download_error = None

        # =================================================
        # FIRST: TRY THE ORIGINAL FORMAT'S CLIENT
        # =================================================

        download_clients = []

        if source_client:

            download_clients.append(
                source_client
            )

        # Then try remaining clients as fallback.
        for client in YOUTUBE_CLIENTS:

            if client not in download_clients:

                download_clients.append(
                    client
                )

        # =================================================
        # DOWNLOAD LOOP
        # =================================================

        for clients in download_clients:

            if download_success:
                break

            for format_selector in exact_format_selectors:

                # Clean temp folder before every attempt.
                for partial in temp_dir.glob("*"):

                    try:

                        if partial.is_file():

                            partial.unlink()

                    except Exception:

                        pass

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
                        "DOWNLOAD ATTEMPT"
                    )

                    print(
                        "Requested height:",
                        f"{height}p"
                    )

                    print(
                        "Selected format ID:",
                        format_id
                    )

                    print(
                        "Source client:",
                        source_client
                    )

                    print(
                        "Using client:",
                        clients
                    )

                    print(
                        "Format selector:",
                        format_selector
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

                    if not valid_files:

                        raise RuntimeError(
                            "yt-dlp completed but "
                            "no video file was created"
                        )

                    # -------------------------------------------------
                    # VERIFY ACTUAL VIDEO RESOLUTION
                    # -------------------------------------------------

                    video_file_candidate = max(
                        valid_files,
                        key=lambda f:
                        f.stat().st_size
                    )

                    actual_height = get_video_height(
                        video_file_candidate
                    )

                    print(
                        "Requested resolution:",
                        f"{height}p"
                    )

                    print(
                        "Actual downloaded resolution:",
                        (
                            f"{actual_height}p"
                            if actual_height
                            else "Unknown"
                        )
                    )

                    # -------------------------------------------------
                    # NEVER ACCEPT A LOWER QUALITY
                    # -------------------------------------------------

                    if (
                        actual_height
                        and actual_height < height
                    ):

                        raise RuntimeError(
                            f"Wrong quality downloaded: "
                            f"requested {height}p, "
                            f"got {actual_height}p"
                        )

                    download_success = True

                    print(
                        "DOWNLOAD SUCCESS"
                    )

                    print(
                        "Final file:",
                        video_file_candidate
                    )

                    break

                except Exception as e:

                    last_download_error = e

                    print(
                        "DOWNLOAD ATTEMPT FAILED"
                    )

                    print(
                        "Requested:",
                        f"{height}p"
                    )

                    print(
                        "Format:",
                        format_selector
                    )

                    print(
                        "Client:",
                        clients
                    )

                    print(
                        repr(e)
                    )

        # =================================================
        # DOWNLOAD FAILED
        # =================================================

        if not download_success:

            if last_download_error:

                raise last_download_error

            raise RuntimeError(
                "All exact-format download "
                "attempts failed"
            )

        # =================================================
        # FIND FINAL FILE
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
                "Downloaded video file not found"
            )

        # -------------------------------------------------
        # PREFER MP4
        # -------------------------------------------------

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

        # -------------------------------------------------
        # FINAL RESOLUTION CHECK
        # -------------------------------------------------

        actual_height = get_video_height(
            video_file
        )

        print(
            "========================================"
        )

        print(
            "FINAL VIDEO CHECK"
        )

        print(
            "Requested:",
            f"{height}p"
        )

        print(
            "Actual:",
            (
                f"{actual_height}p"
                if actual_height
                else "Unknown"
            )
        )

        print(
            "File size:",
            f"{video_file.stat().st_size / (1024 * 1024):.2f} MB"
        )

        print(
            "File:",
            video_file
        )

        print(
            "========================================"
        )

        # =================================================
        # DO NOT UPLOAD LOWER QUALITY
        # =================================================

        if (
            actual_height
            and actual_height < height
        ):

            raise RuntimeError(
                f"Final quality verification failed: "
                f"requested {height}p but file is "
                f"{actual_height}p"
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
            "Resolution:",
            (
                f"{actual_height}p"
                if actual_height
                else "Unknown"
            )
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
            "The selected quality could not "
            "be downloaded correctly.\n\n"
            "Please try again."
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
# VIDEO RESOLUTION CHECK
# =========================================================

def get_video_height(
    video_file: Path
):

    try:

        command = [
            FFMPEG_PATH,
            "-i",
            str(video_file),
        ]

        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=30,
        )

        output = (
            result.stdout
            + "\n"
            + result.stderr
        )

        import re

        matches = re.findall(
            r"Video:.*?(\d{2,5})x(\d{2,5})",
            output
        )

        if not matches:
            return None

        heights = [
            int(height)
            for width, height in matches
        ]

        if not heights:
            return None

        return max(heights)

    except Exception as e:

        print(
            "Resolution probe error:",
            repr(e)
        )

        return None


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

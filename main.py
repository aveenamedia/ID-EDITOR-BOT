
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
import os
import logging
import subprocess
import uuid
from pathlib import Path

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

TOKEN = os.getenv("BOT_TOKEN")
WORKDIR = Path("/tmp/id_editor")
WORKDIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)


# ERROR HANDLER
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error("Bot error:", exc_info=context.error)


# FFMPEG
def run_ffmpeg(args):
    return subprocess.run(
        ["ffmpeg", "-y"] + args,
        capture_output=True,
        text=True,
        timeout=900
    )


# START
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("✂️ Trim Video", callback_data="trim")],
        [InlineKeyboardButton("🎵 Add Music", callback_data="music")],
        [InlineKeyboardButton("💬 Add Subtitles", callback_data="subs")],
    ]

    await update.message.reply_text(
        "🎬 ID EDITOR BOT\n\n"
        "Ku soo dhowow Video Editing Bot!\n\n"
        "1. Ii soo dir video.\n"
        "2. Dooro editing-ka aad rabto.",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# RECEIVE VIDEO
async def receive_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message

    await message.reply_text("⏳ Video-ga waan helay, waan diyaarinayaa...")

    file = await message.video.get_file()
    path = WORKDIR / f"{uuid.uuid4().hex}.mp4"
    await file.download_to_drive(str(path))

    context.user_data["video"] = str(path)

    keyboard = [
        [InlineKeyboardButton("✂️ Trim", callback_data="trim")],
        [InlineKeyboardButton("🎵 Music", callback_data="music")],
        [InlineKeyboardButton("💬 Subtitles", callback_data="subs")],
    ]

    await message.reply_text(
        "✅ Video-ga waa la helay!\nDooro editing-ka:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# EDITING MENU
async def edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    action = query.data

    if not context.user_data.get("video"):
        await query.message.reply_text("❗ Marka hore ii soo dir video.")
        return

    if action == "trim":
        context.user_data["action"] = "trim"
        await query.message.reply_text(
            "Geli waqtiga bilowga iyo dhammaadka.\n"
            "Tusaale: 00:00:10 00:00:30"
        )

    elif action == "music":
        context.user_data["action"] = "music"
        await query.message.reply_text("🎵 Ii soo dir music MP3.")

    elif action == "subs":
        context.user_data["action"] = "subs"
        await query.message.reply_text("💬 Ii soo dir SRT file.")


# TRIM VIDEO
async def receive_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    action = context.user_data.get("action")
    video = context.user_data.get("video")

    if action != "trim" or not video:
        return

    try:
        start_time, end_time = update.message.text.split()

        output = WORKDIR / f"{uuid.uuid4().hex}_trim.mp4"

        result = run_ffmpeg([
            "-ss", start_time,
            "-to", end_time,
            "-i", video,
            "-c", "copy",
            str(output)
        ])

        if result.returncode != 0:
            logger.error(result.stderr)
            await update.message.reply_text("❌ Video jaristu way fashilantay.")
            return

        with output.open("rb") as f:
            await update.message.reply_video(
                f,
                caption="✅ Video waa la jaray!\n🎬 ID EDITOR BOT"
            )

    except Exception:
        logger.exception("Trim error")
        await update.message.reply_text(
            "❌ Waqtiga si sax ah u qor.\n"
            "Tusaale: 00:00:10 00:00:30"
        )

    finally:
        context.user_data["action"] = None


# PROCESS MUSIC AND SUBTITLES
async def process_files(update: Update, context: ContextTypes.DEFAULT_TYPE):
    action = context.user_data.get("action")
    video = context.user_data.get("video")

    if not video or action not in ["music", "subs"]:
        return

    extra = context.user_data.get(
        "music" if action == "music" else "subtitle"
    )

    if not extra or not os.path.exists(extra):
        await update.message.reply_text("❗ File-ka lama helin.")
        return

    await update.message.reply_text("⏳ Editing ayaa socda...")

    output = WORKDIR / f"{uuid.uuid4().hex}_edited.mp4"

    if action == "music":
        args = [
            "-i", video,
            "-i", extra,
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-c:v", "copy",
            "-c:a", "aac",
            "-shortest",
            str(output)
        ]

    else:
        subtitle_filter = (
            "subtitles=" +
            extra.replace("\\", "/").replace(":", "\\:")
        )

        args = [
            "-i", video,
            "-vf", subtitle_filter,
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-c:a", "copy",
            str(output)
        ]

    try:
        result = run_ffmpeg(args)

        if result.returncode != 0:
            logger.error(result.stderr)
            await update.message.reply_text(
                "❌ Editing wuu fashilmay. Hubi file-ka."
            )
            return

        with output.open("rb") as f:
            await update.message.reply_video(
                f,
                caption="✅ ID EDITOR BOT\nEditing waa dhammaaday!"
            )

    except Exception:
        logger.exception("Editing error")
        await update.message.reply_text("❌ Cilad ayaa dhacday.")

    finally:
        context.user_data["action"] = None


# RECEIVE FILES
async def receive_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    document = update.message.document

    if not document:
        return

    ext = Path(document.file_name or "file.srt").suffix.lower()

    if ext not in [".srt", ".mp3", ".m4a", ".wav", ".aac"]:
        await update.message.reply_text("❌ File-kan lama taageero.")
        return

    path = WORKDIR / f"{uuid.uuid4().hex}{ext}"

    file = await document.get_file()
    await file.download_to_drive(str(path))

    if ext == ".srt":
        context.user_data["subtitle"] = str(path)
        await update.message.reply_text("✅ SRT waa la helay.")
        if context.user_data.get("action") == "subs":
            await process_files(update, context)

    else:
        context.user_data["music"] = str(path)
        await update.message.reply_text("✅ Music waa la helay.")
        if context.user_data.get("action") == "music":
            await process_files(update, context)


# RECEIVE AUDIO
async def receive_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    audio = update.message.audio

    if not audio:
        return

    path = WORKDIR / f"{uuid.uuid4().hex}.mp3"

    file = await audio.get_file()
    await file.download_to_drive(str(path))

    context.user_data["music"] = str(path)

    await update.message.reply_text("✅ Music waa diyaar.")

    if context.user_data.get("action") == "music":
        await process_files(update, context)


# CANCEL
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text(
        "Hawsha waa la joojiyay.\n/start ku bilow."
    )


# RENDER HEALTH SERVER
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ID EDITOR BOT is running")

    def log_message(self, format, *args):
        pass


def run_health_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    server.serve_forever()


# MAIN
def main():
    if not TOKEN:
        raise RuntimeError("BOT_TOKEN lama dejin.")

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("cancel", cancel))

    app.add_handler(CallbackQueryHandler(edit))

    app.add_handler(MessageHandler(filters.VIDEO, receive_video))
    app.add_handler(MessageHandler(filters.Document.ALL, receive_file))
    app.add_handler(MessageHandler(filters.AUDIO, receive_audio))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, receive_text))

    app.add_error_handler(error_handler)

    threading.Thread(
        target=run_health_server,
        daemon=True
    ).start()

    logger.info("ID EDITOR BOT is starting...")
    app.run_polling()


if __name__ == "__main__":
    main()

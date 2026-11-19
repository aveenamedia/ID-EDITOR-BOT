
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
WORKDIR.mkdir(exist_ok=True)

logging.basicConfig(level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)

def run_ffmpeg(args):
    return subprocess.run(
        ["ffmpeg", "-y"] + args,
        capture_output=True,
        text=True,
        timeout=900
    )

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("✂️ Trim Video", callback_data="trim")],
        [InlineKeyboardButton("🎵 Add Music", callback_data="music")],
        [InlineKeyboardButton("💬 Add Subtitles", callback_data="subs")],
    ]
    await update.message.reply_text(
        "🎬 ID EDITOR BOT\n\n"
        "Ku soo dhowow Video Editing Bot!\n"
        "1. Ii soo dir video.\n"
        "2. Dooro editing-ka aad rabto.",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def receive_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message.video:
        return

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
        "✅ Video-ga waa la helay!\nDooro waxa aad rabto:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

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
    else:
        context.user_data["music"] = str(path)
        await update.message.reply_text("✅ Music waa la helay.")

async def receive_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    audio = update.message.audio
    if not audio:
        return
    path = WORKDIR / f"{uuid.uuid4().hex}.mp3"
    file = await audio.get_file()
    await file.download_to_drive(str(path))
    context.user_data["music"] = str(path)
    await update.message.reply_text("✅ Music waa diyaar.")

async def edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    action = query.data
    video = context.user_data.get("video")

    if action in ["trim", "music", "subs"] and not video:
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
        await query.message.reply_text("Ii soo dir music MP3.")
    elif action == "subs":
        context.user_data["action"] = "subs"
        await query.message.reply_text("Ii soo dir SRT file.")

async def receive_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    action = context.user_data.get("action")
    video = context.user_data.get("video")

    if action != "trim" or not video:
        return

    try:
        start, end = update.message.text.split()
        output = WORKDIR / f"{uuid.uuid4().hex}_trim.mp4"

        result = run_ffmpeg([
            "-ss", start, "-to", end,
            "-i", video, "-c", "copy", str(output)
        ])

        if result.returncode != 0:
            raise ValueError("FFmpeg error")

        with output.open("rb") as f:
            await update.message.reply_video(f, caption="✅ Video waa la jaray!")

    except Exception:
        await update.message.reply_text(
            "❌ Waqtiga si sax ah u qor.\nTusaale: 00:00:10 00:00:30"
        )
    finally:
        context.user_data["action"] = None

async def process_files(update: Update, context: ContextTypes.DEFAULT_TYPE):
    action = context.user_data.get("action")
    video = context.user_data.get("video")

    if not video:
        return

    if action not in ["music", "subs"]:
        return

    extra = context.user_data.get(
        "music" if action == "music" else "subtitle"
    )

    if not extra or not os.path.exists(extra):
        await update.message.reply_text("❗ Marka hore soo dir file-ka loo baahan yahay.")
        return

    output = WORKDIR / f"{uuid.uuid4().hex}_edited.mp4"

    if action == "music":
        result = run_ffmpeg([
            "-i", video, "-i", extra,
            "-map", "0:v:0", "-map", "1:a:0",
            "-c:v", "copy", "-c:a", "aac",
            "-shortest", str(output)
        ])
    else:
        subtitle_filter = "subtitles=" + extra.replace("\\", "/").replace(":", "\\:")
        result = run_ffmpeg([
            "-i", video, "-vf", subtitle_filter,
            "-c:v", "libx264", "-preset", "ultrafast",
            "-c:a", "copy", str(output)
        ])

    if result.returncode != 0:
        await update.message.reply_text("❌ Editing wuu fashilmay. Hubi file-ka.")
        return

    with output.open("rb") as f:
        await update.message.reply_video(f, caption="✅ ID EDITOR BOT")

    context.user_data["action"] = None

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("Hawsha waa la joojiyay. /start ku bilow.")

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
    app.add_handler(MessageHandler(filters.VIDEO, process_files))

    app.run_polling()

if __name__ == "__main__":
    main()
    

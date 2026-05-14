import aiohttp

from pyrogram import filters

from AloneRobot import pbot as alone


API_BASE = "https://nexacoders-nexa-api.hf.space"

# simple in-memory toggle system (NO DATABASE REQUIRED)
NSFW_CHAT = set()


async def get_file_bytes(client, message):
    file_id = None

    if message.document:
        if int(message.document.file_size) > 3145728:
            return None
        if message.document.mime_type not in ("image/png", "image/jpeg"):
            return None
        file_id = message.document.file_id

    elif message.photo:
        file_id = message.photo.file_id

    elif message.sticker:
        file_id = message.sticker.file_id

    elif message.animation:
        file_id = message.animation.file_id

    elif message.video:
        file_id = message.video.file_id

    if not file_id:
        return None

    return await client.download_media(file_id, in_memory=True)


async def scan_api(file_bytes: bytes):
    async with aiohttp.ClientSession() as session:
        data = aiohttp.FormData()
        data.add_field("file", file_bytes, filename="file.jpg")

        async with session.post(f"{API_BASE}/nsfw", data=data) as r:
            return await r.json()


# ================= AUTO DETECT =================

@alone.on_message(
    (filters.photo | filters.video | filters.document | filters.sticker | filters.animation)
)
async def auto_nsfw(client, message):
    chat_id = message.chat.id

    if chat_id not in NSFW_CHAT:
        return

    file_bytes = await get_file_bytes(client, message)
    if not file_bytes:
        return

    try:
        res = await scan_api(file_bytes)
    except:
        return

    if not res.get("ok"):
        return

    result = res["result"]

    if not result.get("is_nsfw"):
        return

    try:
        await message.delete()
    except:
        return

    await message.reply_text(
        f"🔞 NSFW DETECTED\n\n"
        f"User: {message.from_user.mention if message.from_user else 'Unknown'}\n"
        f"Porn: {result.get('porn', 0)}%\n"
        f"Hentai: {result.get('hentai', 0)}%\n"
        f"Sexy: {result.get('sexy', 0)}%"
    )


# ================= SCAN COMMAND =================

@alone.on_message(filters.command("nsfwscan"))
async def nsfwscan(client, message):
    if not message.reply_to_message:
        return await message.reply_text("Reply to media")

    file_bytes = await get_file_bytes(client, message.reply_to_message)
    if not file_bytes:
        return await message.reply_text("Unsupported media")

    msg = await message.reply_text("Scanning...")

    try:
        res = await scan_api(file_bytes)
    except:
        return await msg.edit("API error")

    if not res.get("ok"):
        return await msg.edit("Failed")

    r = res["result"]

    await msg.edit(
        f"🔍 NSFW RESULT\n\n"
        f"Neutral: {r.get('neutral', 0)}%\n"
        f"Porn: {r.get('porn', 0)}%\n"
        f"Hentai: {r.get('hentai', 0)}%\n"
        f"Sexy: {r.get('sexy', 0)}%\n"
        f"NSFW: {r.get('is_nsfw')}"
    )


# ================= TOGGLE =================

@alone.on_message(filters.command("antinsfw"))
async def antinsfw(_, message):
    chat_id = message.chat.id

    if len(message.command) != 2:
        return await message.reply_text("Use /antinsfw on or off")

    state = message.command[1].lower()

    if state == "on":
        NSFW_CHAT.add(chat_id)
        return await message.reply_text("✅ AntiNSFW Enabled")

    elif state == "off":
        NSFW_CHAT.discard(chat_id)
        return await message.reply_text("❌ AntiNSFW Disabled")

    else:
        return await message.reply_text("Use /antinsfw on or off")

"""
Streams audio in Telegram voice chats using the user-account session
defined as STRING_SESSION in AloneRobot/config.py. The bot (Pyrogram
Client) handles commands; the assistant (user client built from
STRING_SESSION) joins the VC and pipes audio via PyTgCalls.
Run with:
    python -m AloneRobot          # or however your project boots
    # ensure AloneRobot/config.py exposes:
    #   API_ID, API_HASH, BOT_TOKEN, STRING_SESSION
    # and optionally LOG_GROUP_ID
Requirements:
    pip install pyrogram tgcrypto py-tgcalls yt-dlp aiohttp
    apt install ffmpeg
"""
from __future__ import annotations
import asyncio
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Deque, Optional
from pyrogram import Client, filters, idle
from pyrogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
try:
    from pytgcalls import PyTgCalls
    from pytgcalls.types import MediaStream, Update
    from pytgcalls.types.stream import StreamAudioEnded
except ImportError as e:  # pragma: no cover
    raise SystemExit(
        "py-tgcalls is required. Install with: pip install py-tgcalls"
    ) from e
from youtube import yt, YouTubeAPIError
from AloneRobot import pbot as alone
import logging 

from AloneRobot.config import (
    API_ID,
    API_HASH,
    BOT_TOKEN,
    STRING_SESSION,
)
try:
    from AloneRobot.config import LOG_GROUP_ID  # optional
except Exception:
    LOG_GROUP_ID = 0

from AloneRobot.config import (
    API_ID,
    API_HASH,
    TOKEN,
    STRING_SESSION,
)
try:
    from AloneRobot.config import LOG_GROUP_ID  # optional
except Exception:
    LOG_GROUP_ID = 

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
log = logging.getLogger("AloneRobot.play")
# ── pyrogram clients ──────────────────────────────────────────────
app = Client(
    "AloneRobotBot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    in_memory=True,
)
assistant = Client(
    "AloneRobotAssistant",
    api_id=API_ID,
    api_hash=API_HASH,
    session_string=STRING_SESSION,
    in_memory=True,
)
calls = PyTgCalls(assistant)
# ───────────────────── queue ─────────────────────
@dataclass
class Track:
    title: str
    artist: str
    duration: int
    thumbnail: str
    video_id: str
    stream_url: str
    webpage_url: str
    requester: str
    chat_id: int
_queues: dict[int, Deque[Track]] = defaultdict(deque)
_current: dict[int, Track] = {}
def _fmt(s: int) -> str:
    s = max(0, int(s))
    return f"{s // 60}:{s % 60:02d}"
def _markup(chat_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("⏸ Pause", callback_data=f"pp:pause:{chat_id}"),
                InlineKeyboardButton("▶️ Resume", callback_data=f"pp:resume:{chat_id}"),
                InlineKeyboardButton("⏭ Skip", callback_data=f"pp:skip:{chat_id}"),
            ],
            [
                InlineKeyboardButton("⏹ Stop", callback_data=f"pp:stop:{chat_id}"),
                InlineKeyboardButton("✖️ Close", callback_data=f"pp:close:{chat_id}"),
            ],
        ]
    )
async def _resolve(query: str, requester: str, chat_id: int) -> Track:
    meta = await yt.top_match(query)
    url = meta.get("youtube_url") or meta.get("webpage_url") or (
        f"https://youtu.be/{meta['video_id']}" if meta.get("video_id") else None
    )
    if not url:
        raise YouTubeAPIError("Could not resolve YouTube URL for query.")
    stream = await yt.extract_stream(url)
    return Track(
        title=meta.get("title") or stream["title"],
        artist=meta.get("artist") or meta.get("channel") or "",
        duration=int(meta.get("duration") or stream.get("duration") or 0),
        thumbnail=meta.get("thumbnail") or stream.get("thumbnail", ""),
        video_id=meta.get("video_id") or meta.get("videoId", ""),
        stream_url=stream["url"],
        webpage_url=stream.get("webpage_url", url),
        requester=requester,
        chat_id=chat_id,
    )
async def _ensure_assistant_in_chat(chat_id: int) -> None:
    """Make sure the assistant userbot is a member of the group."""
    try:
        await assistant.get_chat(chat_id)
    except Exception:
        try:
            invite = await app.export_chat_invite_link(chat_id)
            await assistant.join_chat(invite)
        except Exception as e:
            raise RuntimeError(
                "Assistant could not join chat. Add the assistant account "
                f"to the group first. ({e})"
            )
async def _play_track(t: Track) -> None:
    await _ensure_assistant_in_chat(t.chat_id)
    await calls.play(
        t.chat_id,
        MediaStream(t.stream_url, video_flags=MediaStream.Flags.IGNORE),
    )
    _current[t.chat_id] = t
    await yt.update_now_playing(
        title=t.title, artist=t.artist, cover=t.thumbnail,
        video_id=t.video_id, duration=t.duration, position=0, is_playing=True,
    )
    caption = (
        f"🎵 <b>Now Playing</b>\n\n"
        f"<b>{t.title}</b>\n"
        f"👤 {t.artist or 'Unknown'}\n"
        f"⏱ {_fmt(t.duration)}\n"
        f"🙋 Requested by: {t.requester}"
    )
    try:
        if t.thumbnail:
            await app.send_photo(
                t.chat_id, t.thumbnail, caption=caption,
                reply_markup=_markup(t.chat_id),
            )
        else:
            await app.send_message(
                t.chat_id, caption, reply_markup=_markup(t.chat_id),
            )
    except Exception as e:
        log.warning("send now-playing card failed: %s", e)
        await app.send_message(t.chat_id, caption)
        try:
            t = await _resolve(query, m.from_user.mention if m.from_user else "Anonymous", m.chat.id)
        except (YouTubeAPIError, Exception) as e:
            dit(f"❌ {e}")
        if m.chat.id in _current:
            _queues[m.chat.id].append(t)
            pos = len(_queues[m.chat.id])
            return await msg.edit(f"➕ Queued at <b>#{pos}</b>: {t.title}")
        await msg.delete()
    if LOG_GROUP_ID:
        try:
                await app.send_message(
                LOG_GROUP_ID,
                f"▶️ <b>{t.title}</b> playing in <code>{t.chat_id}</code> "
                f"(req: {t.requester})",
            )
        except Exception:
            pass
async def _advance(chat_id: int, notice: Optional[Message] = None) -> None:
    q = _queues[chat_id]
    if not q:
        _current.pop(chat_id, None)
        try:
            await calls.leave_call(chat_id)
        except Exception:
            pass
        if notice:
            await notice.reply("⏹ Queue finished.")
        return
    nxt = q.popleft()
    try:
        await _play_track(nxt)
        if notice:
            await notice.reply(f"⏭ Now playing: <b>{nxt.title}</b>")
    except Exception as e:
        log.exception("advance failed")
        if notice:
            await notice.reply(f"❌ {e}")
        await _advance(chat_id, notice) 

# ── command handlers ──────────────────────────────────────────────
@alone.on_message(filters.command("start") & filters.private)
async def _start(_, m: Message):
    await m.reply(
        "👋 <b>AloneRobot Music</b>\n\n"
        "Add me to a group, start a voice chat, then send "
        "<code>/play song name</code>."
    )
@alone.on_message(filters.command(["play", "p"]) & ~filters.private)
async def _play(_, m: Message):
    if len(m.command) < 2 and not (m.reply_to_message and m.reply_to_message.text):
        return await m.reply("Usage: <code>/play song name or YouTube URL</code>")
    query = (
        m.text.split(None, 1)[1]
        if len(m.command) >= 2
        else m.reply_to_message.text
    )
    msg = await m.reply(f"🔎 Searching <b>{query}</b>…")
    try:
        requester = m.from_user.mention if m.from_user else "Anonymous"
        track = await _resolve(query, requester, m.chat.id)
    except Exception as e:
        return await msg.edit(f"❌ {e}")
    if m.chat.id in _current:
        _queues[m.chat.id].append(track)
        return await msg.edit(
            f"➕ Queued at <b>#{len(_queues[m.chat.id])}</b>: {track.title}"
        )

    await msg.delete()
    try:
        await _play_track(track)
    except Exception as e:
        log.exception("play failed")
        await m.reply(f"❌ Failed to start stream: {e}")
@alone.on_message(filters.command("pause") & ~filters.private)
async def _pause(_, m: Message):
    try:
        await calls.pause_stream(m.chat.id)
        await m.reply("⏸ Paused")
    except Exception as e:
        await m.reply(f"❌ {e}")
@alone.on_message(filters.command("resume") & ~filters.private)
async def _resume(_, m: Message):
    try:
        await calls.resume_stream(m.chat.id)
        await m.reply("▶️ Resumed")
    except Exception as e:
        await m.reply(f"❌ {e}")
@alone.on_message(filters.command(["skip", "next"]) & ~filters.private)
async def _skip(_, m: Message):
    await _advance(m.chat.id, notice=m)
@alone.on_message(filters.command(["stop", "end", "leave"]) & ~filters.private)
async def _stop(_, m: Message):
    _queues[m.chat.id].clear()
    _current.pop(m.chat.id, None)
    try:
        await calls.leave_call(m.chat.id)
    except Exception:
        pass
    await m.reply("⏹ Stopped & cleared queue.")

@alone.on_message(filters.command("queue") & ~filters.private)
async def _queue(_, m: Message):
    q = _queues[m.chat.id]
    cur = _current.get(m.chat.id)
    if not cur and not q:
        return await m.reply("📭 Queue is empty.")
    lines = []
    if cur:
        lines.append(f"▶️ <b>Now:</b> {cur.title}")
    for i, t in enumerate(q, 1):
        lines.append(f"{i}. {t.title} — {_fmt(t.duration)}")
    await m.reply("\n".join(lines))

@alone.on_callback_query(filters.regex(r"^pp:(pause|resume|skip|stop|close):(-?\d+)$"))
async def _btn(_, cq: CallbackQuery):
    action = cq.matches[0].group(1)
    chat_id = int(cq.matches[0].group(2))
    try:
        if action == "pause":
            await calls.pause_stream(chat_id)
            await cq.answer("Paused")
        elif action == "resume":
            await calls.resume_stream(chat_id)
            await cq.answer("Resumed")
        elif action == "skip":
            await _advance(chat_id)
            await cq.answer("Skipped")
        elif action == "stop":
            _queues[chat_id].clear()
            _current.pop(chat_id, None)
            try:
                await calls.leave_call(chat_id)
            except Exception:
                pass
            await cq.answer("Stopped")
        elif action == "close":
            try:
                await cq.message.delete()
            except Exception:
                pass
            await cq.answer()
    except Exception as e:
        await cq.answer(f"❌ {e}", show_alert=True)

# ── auto-advance when track ends ──────────────────────────────────
@calls.on_update()
async def _on_update(_, update: Update):
    if isinstance(update, StreamAudioEnded):
        await _advance(update.chat_id)
# ── entry point ───────────────────────────────────────────────────
async def main() -> None:
    await assistant.start()
    await app.start()
    await calls.start()
    me_bot = await app.get_me()
    me_asst = await assistant.get_me()
    log.info("Bot started as @%s", me_bot.username)
    log.info("Assistant started as %s (id=%s)", me_asst.first_name, me_asst.id)
    if LOG_GROUP_ID:
        try:
            await app.send_message(
                LOG_GROUP_ID,
                f"✅ <b>AloneRobot online</b>\n"
                f"Bot: @{me_bot.username}\n"
                f"Assistant: <code>{me_asst.id}</code>",
            )
        except Exception as e:
            log.warning("log group notify failed: %s", e)
    await idle()
    await app.stop()
    await assistant.stop()
if __name__ == "__main__":
    asyncio.get_event_loop().run_until_complete(main())
        
                  

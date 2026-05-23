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
def _fmt_time(s: int) -> str:
    s = max(0, int(s))
    return f"{s // 60}:{s % 60:02d}"
def _now_playing_markup(chat_id: int) -> InlineKeyboardMarkup:
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
    stream = await yt.extract_stream(meta.get("youtube_url") or meta["webpage_url"])
    return Track(
        title=meta.get("title") or stream["title"],
        artist=meta.get("artist") or meta.get("channel", ""),
        duration=int(meta.get("duration") or stream.get("duration") or 0),
        thumbnail=meta.get("thumbnail") or stream.get("thumbnail", ""),
        video_id=meta.get("video_id") or meta.get("videoId", ""),
        stream_url=stream["url"],
        webpage_url=stream.get("webpage_url", ""),
        requester=requester,
        chat_id=chat_id,
    )
async def _play_track(calls: PyTgCalls, app: Client, t: Track) -> None:
    await calls.play(t.chat_id, MediaStream(t.stream_url, video_flags=MediaStream.Flags.IGNORE))
    _current[t.chat_id] = t
    await yt.update_now_playing(
        title=t.title, artist=t.artist, cover=t.thumbnail,
        video_id=t.video_id, duration=t.duration, position=0, is_playing=True,
    )
    caption = (
        f"🎵 <b>Now Playing</b>\n\n"
        f"<b>{t.title}</b>\n"
        f"👤 {t.artist or 'Unknown'}\n"
        f"⏱ {_fmt_time(t.duration)}\n"
        f"🙋 Requested by: {t.requester}"
    )
    try:
        if t.thumbnail:
            await app.send_photo(
                t.chat_id, t.thumbnail, caption=caption,
                reply_markup=_now_playing_markup(t.chat_id),
            )
        else:
            await app.send_message(
                t.chat_id, caption, reply_markup=_now_playing_markup(t.chat_id),
            )
    except Exception:
        await app.send_message(t.chat_id, caption)
# ───────────────────── registration ─────────────────────
def register(app: Client, assistant: Client, calls: PyTgCalls) -> None:
    """Attach /play, /pause, /resume, /skip, /stop, /queue + buttons."""
    @app.on_message(filters.command(["play", "p"]) & ~filters.private)
    async def _play(_, m: Message):
        if len(m.command) < 2 and not m.reply_to_message:
            return await m.reply("Usage: <code>/play song name or YouTube URL</code>")
        query = m.text.split(None, 1)[1] if len(m.command) >= 2 else m.reply_to_message.text
        msg = await m.reply(f"🔎 Searching <b>{query}</b>…")
        try:
            t = await _resolve(query, m.from_user.mention if m.from_user else "Anonymous", m.chat.id)
        except (YouTubeAPIError, Exception) as e:
            return await msg.edit(f"❌ {e}")
        if m.chat.id in _current:
            _queues[m.chat.id].append(t)
            pos = len(_queues[m.chat.id])
            return await msg.edit(f"➕ Queued at <b>#{pos}</b>: {t.title}")
        await msg.delete()
        try:
            await _play_track(calls, app, t)
        except Exception as e:
            await m.reply(f"❌ Failed to start stream: {e}")
    @alone.on_message(filters.command("pause") & ~filters.private)
    async def _pause(_, m: Message):
        try: await calls.pause_stream(m.chat.id); await m.reply("⏸ Paused")
        except Exception as e: await m.reply(f"❌ {e}")
    @alone.on_message(filters.command("resume") & ~filters.private)
    async def _resume(_, m: Message):
        try: await calls.resume_stream(m.chat.id); await m.reply("▶️ Resumed")
        except Exception as e: await m.reply(f"❌ {e}")
    @alone.on_message(filters.command(["skip", "next"]) & ~filters.private)
    async def _skip(_, m: Message):
        await _advance(app, calls, m.chat.id, notice_to=m)
    @alone.on_message(filters.command(["stop", "end", "leave"]) & ~filters.private)
    async def _stop(_, m: Message):
        _queues[m.chat.id].clear()
        _current.pop(m.chat.id, None)
        try: await calls.leave_call(m.chat.id)
        except Exception: pass
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
            lines.append(f"{i}. {t.title} — {_fmt_time(t.duration)}")
        await m.reply("\n".join(lines))
    @alone.on_callback_query(filters.regex(r"^pp:(pause|resume|skip|stop|close):(-?\d+)$"))
    async def _btn(_, cq: CallbackQuery):
        action, chat_id = cq.matches[0].group(1), int(cq.matches[0].group(2))
        try:
            if action == "pause":   await calls.pause_stream(chat_id);  await cq.answer("Paused")
            elif action == "resume":await calls.resume_stream(chat_id); await cq.answer("Resumed")
            elif action == "skip":  await _advance(app, calls, chat_id); await cq.answer("Skipped")
            elif action == "stop":
                _queues[chat_id].clear(); _current.pop(chat_id, None)
                try: await calls.leave_call(chat_id)
                except Exception: pass
                await cq.answer("Stopped")
            elif action == "close":
                try: await cq.message.delete()
                except Exception: pass
                await cq.answer()
        except Exception as e:
            await cq.answer(f"❌ {e}", show_alert=True)
    # auto-advance when track ends
    @calls.on_update()
    async def _ended(_, update: Update):
        if isinstance(update, StreamAudioEnded):
            await _advance(app, calls, update.chat_id)

async def _advance(app: Client, calls: PyTgCalls, chat_id: int, notice_to: Optional[Message] = None):
    q = _queues[chat_id]
    if not q:
        _current.pop(chat_id, None)
        try: await calls.leave_call(chat_id)
        except Exception: pass
        if notice_to: await notice_to.reply("⏹ Queue finished.")
        return
    nxt = q.popleft()
    try:
        await _play_track(calls, app, nxt)
        if notice_to: await notice_to.reply(f"⏭ Now playing: <b>{nxt.title}</b>")
    except Exception as e:
        if notice_to: await notice_to.reply(f"❌ {e}")
        await _advance(app, calls, chat_id, notice_to)
        

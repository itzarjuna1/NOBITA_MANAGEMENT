"""
youtube.py — UpperMoon Tunes API client + YouTube stream extractor.
Edit API_KEY and BASE_URL below with the values from your website's
Developer Portal (https://<your-site>/developer).
Exposes a single `YouTubeAPI` class used by play.py.
"""
from __future__ import annotations
import asyncio
import os
import re
from typing import Any, Optional
import aiohttp
import yt_dlp
# ─────────────────────────────────────────────────────────────
# 🔑  CONFIGURE THESE TWO VALUES
# ─────────────────────────────────────────────────────────────
API_KEY: str = os.getenv("UPPERMOON_API_KEY", "umowner_REPLACE_ME")
BASE_URL: str = os.getenv(
    "UPPERMOON_BASE_URL",
    "https://ydvaruzgftvizgymwalw.supabase.co/functions/v1/bot-api",
).rstrip("/")
# ─────────────────────────────────────────────────────────────
YT_URL_RE = re.compile(
    r"(?:youtube\.com/(?:watch\?v=|shorts/|embed/)|youtu\.be/)([A-Za-z0-9_-]{11})"
)
def _is_youtube_url(text: str) -> Optional[str]:
    m = YT_URL_RE.search(text or "")
    return m.group(1) if m else None
class YouTubeAPIError(Exception):
    pass
class YouTubeAPI:
    """Thin wrapper around the website's /bot-api endpoints + yt-dlp."""
    def __init__(self, api_key: str = API_KEY, base_url: str = BASE_URL):
        if not api_key or api_key.startswith("umowner_REPLACE"):
            raise YouTubeAPIError(
                "Set API_KEY in youtube.py (get it from the website's Developer Portal)."
            )
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self._session: Optional[aiohttp.ClientSession] = None
    # ---------- internals ----------
    async def _sess(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers={"X-API-Key": self.api_key},
                timeout=aiohttp.ClientTimeout(total=30),
            )
        return self._session
    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
    async def _get(self, path: str, **params: Any) -> dict:
        sess = await self._sess()
        url = f"{self.base_url}/{path.lstrip('/')}"
        async with sess.get(url, params=params) as r:
            data = await r.json(content_type=None)
            if r.status >= 400:
                raise YouTubeAPIError(data.get("error") or f"HTTP {r.status}")
            return data
    async def _post(self, path: str, payload: dict) -> dict:
        sess = await self._sess()
        url = f"{self.base_url}/{path.lstrip('/')}"
        async with sess.post(url, json=payload) as r:
            data = await r.json(content_type=None)
            if r.status >= 400:
                raise YouTubeAPIError(data.get("error") or f"HTTP {r.status}")
            return data
    # ---------- public API ----------
    async def search(self, query: str, limit: int = 10) -> list[dict]:
        vid = _is_youtube_url(query)
        if vid:
            # Skip search, hit /play to grab metadata for the exact video.
            res = await self._get("play", q=f"https://youtu.be/{vid}")
            return [res["track"]]
        res = await self._get("search", q=query, limit=limit)
        return res.get("results", [])
    async def shorts(self, query: str, limit: int = 10) -> list[dict]:
        res = await self._get("shorts", q=query, limit=limit)
        return res.get("results", [])
    async def top_match(self, query: str) -> dict:
        """First search hit — what /play uses."""
        if _is_youtube_url(query):
            results = await self.search(query, 1)
        else:
            res = await self._get("play", q=query)
            results = [res["track"]]
        if not results:
            raise YouTubeAPIError(f"No results for '{query}'")
        return results[0]
    async def update_now_playing(
        self,
        title: str,
        artist: str = "",
        cover: str = "",
        video_id: str = "",
        duration: int = 0,
        position: int = 0,
        is_playing: bool = True,
    ) -> None:
        try:
            await self._post(
                "nowplaying",
                {
                    "title": title,
                    "artist": artist,
                    "cover": cover,
                    "video_id": video_id,
                    "duration": int(duration),
                    "position": int(position),
                    "is_playing": is_playing,
                },
            )
        except YouTubeAPIError:
            pass  # never break playback over a logging failure
    # ---------- yt-dlp stream extraction ----------
    async def extract_stream(self, video_url: str) -> dict:
        """Returns {'url', 'title', 'duration', 'thumbnail', 'webpage_url'}."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._extract_sync, video_url)
    @staticmethod
    def _extract_sync(video_url: str) -> dict:
        ydl_opts = {
            "format": "bestaudio/best",
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "geo_bypass": True,
            "nocheckcertificate": True,
            "source_address": "0.0.0.0",
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=False)
            if "entries" in info:
                info = info["entries"][0]
            return {
                "url": info["url"],
                "title": info.get("title", ""),
                "duration": info.get("duration", 0),
                "thumbnail": info.get("thumbnail", ""),
                "webpage_url": info.get("webpage_url", video_url),
      }
# Singleton importable as: from youtube import yt
yt = YouTubeAPI()

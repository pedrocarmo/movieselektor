"""Lazy poster fetching from TMDB, cached to the local filesystem.

Called when a film becomes the active pick. The first draw of a given film hits the
TMDB API; every draw after that is served from the local cache. If no API key is
configured, or TMDB has no match, the film simply shows without a poster.
"""
from __future__ import annotations

from typing import Optional

import httpx

from . import config

SEARCH_URL = "https://api.themoviedb.org/3/search/movie"
IMAGE_BASE = "https://image.tmdb.org/t/p"


async def fetch_poster(title: str, year: Optional[int]) -> tuple[Optional[int], Optional[str]]:
    """Resolve a film to (tmdb_id, local_poster_filename).

    Returns (None, None) on any failure or when no key is set. Never raises — a missing
    poster must never break a draw.
    """
    if not config.TMDB_API_KEY:
        return None, None

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            params = {"api_key": config.TMDB_API_KEY, "query": title}
            if year:
                params["year"] = year
            resp = await client.get(SEARCH_URL, params=params)
            resp.raise_for_status()
            results = resp.json().get("results", [])
            if not results:
                return None, None

            top = results[0]
            tmdb_id = top.get("id")
            poster_path = top.get("poster_path")
            if not poster_path:
                return tmdb_id, None  # remember the id even without a poster

            filename = f"{tmdb_id}.jpg"
            config.POSTER_DIR.mkdir(parents=True, exist_ok=True)
            dest = config.POSTER_DIR / filename
            if not dest.exists():
                img = await client.get(f"{IMAGE_BASE}/{config.TMDB_POSTER_SIZE}{poster_path}")
                img.raise_for_status()
                dest.write_bytes(img.content)
            return tmdb_id, filename
    except (httpx.HTTPError, OSError):
        return None, None

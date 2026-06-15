"""SQLite access: connection helper, schema bootstrap, and all queries.

Queries live here so route handlers stay thin and readable. The whole app is one
shared club state, so there is no notion of a user anywhere.
"""
from __future__ import annotations

from typing import Any, Optional

import aiosqlite

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS films (
    id                    INTEGER PRIMARY KEY,
    rank                  INTEGER NOT NULL UNIQUE,
    title                 TEXT    NOT NULL,
    year                  INTEGER,
    director              TEXT,
    letterboxd_search_url TEXT,
    tmdb_id               INTEGER,
    poster_path           TEXT
);

CREATE TABLE IF NOT EXISTS picks (
    id         INTEGER PRIMARY KEY,
    film_id    INTEGER NOT NULL REFERENCES films(id),
    drawn_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    watched_at TIMESTAMP,
    status     TEXT NOT NULL DEFAULT 'active'
               CHECK (status IN ('active', 'watched'))
);

CREATE INDEX IF NOT EXISTS picks_status ON picks(status);
CREATE INDEX IF NOT EXISTS picks_drawn_at ON picks(drawn_at DESC);
"""


async def connect() -> aiosqlite.Connection:
    """Open a connection with WAL + foreign keys and dict-like row access."""
    config.DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = await aiosqlite.connect(config.DATABASE_PATH)
    conn.row_factory = aiosqlite.Row
    await conn.execute("PRAGMA journal_mode=WAL")
    await conn.execute("PRAGMA foreign_keys=ON")
    return conn


async def init_schema() -> None:
    conn = await connect()
    try:
        await conn.executescript(SCHEMA)
        await conn.commit()
    finally:
        await conn.close()


# --- Films -----------------------------------------------------------------

async def film_count(conn: aiosqlite.Connection) -> int:
    row = await (await conn.execute("SELECT COUNT(*) AS n FROM films")).fetchone()
    return row["n"]


async def get_film(conn: aiosqlite.Connection, film_id: int) -> Optional[aiosqlite.Row]:
    cur = await conn.execute("SELECT * FROM films WHERE id = ?", (film_id,))
    return await cur.fetchone()


async def set_film_poster(
    conn: aiosqlite.Connection, film_id: int, tmdb_id: Optional[int], poster_path: Optional[str]
) -> None:
    await conn.execute(
        "UPDATE films SET tmdb_id = ?, poster_path = ? WHERE id = ?",
        (tmdb_id, poster_path, film_id),
    )
    await conn.commit()


# --- Picks -----------------------------------------------------------------

async def current_pick(conn: aiosqlite.Connection) -> Optional[aiosqlite.Row]:
    """The active pick joined with its film, or None if nothing is drawn."""
    cur = await conn.execute(
        """
        SELECT p.id AS pick_id, p.status, p.drawn_at, p.watched_at, f.*
        FROM picks p JOIN films f ON f.id = p.film_id
        WHERE p.status = 'active'
        ORDER BY p.id DESC LIMIT 1
        """
    )
    return await cur.fetchone()


async def draw_new(conn: aiosqlite.Connection) -> Optional[aiosqlite.Row]:
    """Retire any active pick as skipped, then draw a random unwatched film.

    Returns the newly drawn film row, or None if the draw pool is empty.
    """
    watched_ids = await _watched_film_ids(conn)
    active = await current_pick(conn)
    exclude = set(watched_ids)
    if active is not None:
        exclude.add(active["id"])

    placeholders = ",".join("?" * len(exclude)) if exclude else ""
    where = f"WHERE id NOT IN ({placeholders})" if exclude else ""
    cur = await conn.execute(
        f"SELECT * FROM films {where} ORDER BY RANDOM() LIMIT 1", tuple(exclude)
    )
    film = await cur.fetchone()
    if film is None:
        return None  # everything watched (or pool exhausted)

    await conn.execute("DELETE FROM picks WHERE status = 'active'")
    await conn.execute(
        "INSERT INTO picks (film_id, status) VALUES (?, 'active')", (film["id"],)
    )
    await conn.commit()
    return film


async def mark_watched(conn: aiosqlite.Connection) -> Optional[int]:
    """Mark the active pick as watched. Returns the pick id (for undo), or None."""
    active = await current_pick(conn)
    if active is None:
        return None
    await conn.execute(
        "UPDATE picks SET status = 'watched', watched_at = CURRENT_TIMESTAMP WHERE id = ?",
        (active["pick_id"],),
    )
    await conn.commit()
    return active["pick_id"]


async def undo_watch(conn: aiosqlite.Connection, pick_id: int) -> None:
    """Revert a just-watched pick back to active."""
    await conn.execute(
        "UPDATE picks SET status = 'active', watched_at = NULL WHERE id = ?", (pick_id,)
    )
    await conn.commit()


async def history(conn: aiosqlite.Connection) -> list[aiosqlite.Row]:
    cur = await conn.execute(
        """
        SELECT p.id AS pick_id, p.watched_at, f.*
        FROM picks p JOIN films f ON f.id = p.film_id
        WHERE p.status = 'watched'
        ORDER BY p.watched_at DESC, p.id DESC
        """
    )
    return list(await cur.fetchall())


async def watched_count(conn: aiosqlite.Connection) -> int:
    row = await (
        await conn.execute("SELECT COUNT(*) AS n FROM picks WHERE status = 'watched'")
    ).fetchone()
    return row["n"]


async def reset_picks(conn: aiosqlite.Connection) -> None:
    """Clear all picks — drops history and the active pick. Films are untouched."""
    await conn.execute("DELETE FROM picks")
    await conn.commit()


async def _watched_film_ids(conn: aiosqlite.Connection) -> list[int]:
    cur = await conn.execute("SELECT DISTINCT film_id FROM picks WHERE status = 'watched'")
    return [r["film_id"] for r in await cur.fetchall()]

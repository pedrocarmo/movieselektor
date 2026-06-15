"""Load the TSPDT seed dataset into the films table (idempotent)."""
import json

from . import config, db


async def load_seed() -> int:
    """Insert any films from the seed file that aren't already present.

    Idempotent: matches on rank, so re-running does nothing on an already-seeded DB.
    Returns the number of films inserted this run.
    """
    with open(config.SEED_PATH, encoding="utf-8") as fh:
        films = json.load(fh)

    conn = await db.connect()
    inserted = 0
    try:
        for film in films:
            cur = await conn.execute(
                """
                INSERT INTO films (rank, title, year, director, letterboxd_search_url)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(rank) DO NOTHING
                """,
                (
                    film["rank"],
                    film["name"],
                    film.get("year"),
                    film.get("director"),
                    film.get("letterboxd_link"),
                ),
            )
            inserted += cur.rowcount if cur.rowcount > 0 else 0
        await conn.commit()
    finally:
        await conn.close()
    return inserted

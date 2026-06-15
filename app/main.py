"""Movieselektor — a 'movie of the week' club tool for the TSPDT 1000.

Single shared club state, no users, no auth. Local network only.
"""
import logging
from contextlib import asynccontextmanager
from urllib.parse import quote_plus

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import config, db, seed, signal_notify, tmdb

templates = Jinja2Templates(directory="app/templates")
templates.env.filters["urlencode"] = quote_plus
templates.env.globals["overseerr_url"] = config.OVERSEERR_URL
templates.env.globals["signal_enabled"] = bool(
    config.SIGNAL_API_URL and config.SIGNAL_SENDER_NUMBER and config.SIGNAL_GROUP_ID
)


log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.init_schema()
    config.POSTER_DIR.mkdir(parents=True, exist_ok=True)
    log.info("Signal enabled: %s (API=%r, sender=%r, group=%r)",
             bool(config.SIGNAL_API_URL and config.SIGNAL_SENDER_NUMBER and config.SIGNAL_GROUP_ID),
             config.SIGNAL_API_URL, config.SIGNAL_SENDER_NUMBER, config.SIGNAL_GROUP_ID)
    # Auto-seed on first boot so the app is immediately usable with no manual step.
    conn = await db.connect()
    try:
        if await db.film_count(conn) == 0 and config.SEED_PATH.exists():
            await conn.close()
            await seed.load_seed()
        else:
            await conn.close()
    except Exception:
        await conn.close()
    yield


app = FastAPI(title="Movieselektor", lifespan=lifespan)
# StaticFiles validates the directory at construction, before lifespan runs.
config.POSTER_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/posters", StaticFiles(directory=config.POSTER_DIR), name="posters")
app.mount("/static", StaticFiles(directory="app/static"), name="static")


async def _ensure_poster(conn, film) -> None:
    """Lazily resolve and cache a poster for a freshly drawn film."""
    if film["poster_path"]:
        return
    tmdb_id, filename = await tmdb.fetch_poster(film["title"], film["year"])
    if tmdb_id or filename:
        await db.set_film_poster(conn, film["id"], tmdb_id, filename)


def _pick_response(request: Request, pick, *, undo=None, watched=None, total=None) -> HTMLResponse:
    """Render the swappable pick area. Pass watched+total to also update the counter via OOB."""
    return templates.TemplateResponse(
        request,
        "partials/pick.html",
        {"pick": pick, "undo": undo, "oob_watched": watched, "oob_total": total},
    )


# --- Pages -----------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    conn = await db.connect()
    try:
        pick = await db.current_pick(conn)
        watched = await db.watched_count(conn)
        total = await db.film_count(conn)
    finally:
        await conn.close()
    return templates.TemplateResponse(
        request,
        "index.html",
        {"pick": pick, "watched": watched, "total": total, "undo": None},
    )


@app.get("/history", response_class=HTMLResponse)
async def history_page(request: Request):
    conn = await db.connect()
    try:
        rows = await db.history(conn)
        total = await db.film_count(conn)
    finally:
        await conn.close()
    return templates.TemplateResponse(
        request, "history.html", {"rows": rows, "watched": len(rows), "total": total}
    )


@app.get("/health")
async def health():
    return {"status": "ok"}


# --- Actions (HTMX) --------------------------------------------------------

@app.post("/draw", response_class=HTMLResponse)
async def draw(request: Request):
    conn = await db.connect()
    try:
        film = await db.draw_new(conn)
        if film is not None:
            await _ensure_poster(conn, film)
        pick = await db.current_pick(conn)
        watched = await db.watched_count(conn) if pick is None else None
        total = await db.film_count(conn) if pick is None else None
    finally:
        await conn.close()
    return _pick_response(request, pick, watched=watched, total=total)


# Skip is functionally a redraw: it retires the active pick as skipped and draws another.
@app.post("/skip", response_class=HTMLResponse)
async def skip(request: Request):
    return await draw(request)


@app.post("/watch", response_class=HTMLResponse)
async def watch(request: Request):
    conn = await db.connect()
    try:
        pick = await db.current_pick(conn)
        undo = None
        if pick is not None:
            pick_id = await db.mark_watched(conn)
            undo = {"pick_id": pick_id, "title": pick["title"]}
        watched = await db.watched_count(conn)
        total = await db.film_count(conn)
    finally:
        await conn.close()
    return _pick_response(request, None, undo=undo, watched=watched, total=total)


@app.post("/undo/{pick_id}", response_class=HTMLResponse)
async def undo(request: Request, pick_id: int):
    conn = await db.connect()
    try:
        await db.undo_watch(conn, pick_id)
        pick = await db.current_pick(conn)
        watched = await db.watched_count(conn)
        total = await db.film_count(conn)
    finally:
        await conn.close()
    return _pick_response(request, pick, watched=watched, total=total)


@app.post("/signal/share", response_class=HTMLResponse)
async def signal_share(request: Request):
    conn = await db.connect()
    try:
        pick = await db.current_pick(conn)
    finally:
        await conn.close()

    if pick is None:
        return HTMLResponse('<button id="signal-share-btn" disabled>No active pick</button>')

    year = f" ({pick['year']})" if pick["year"] else ""
    text = f"🎬 New pick: #{pick['rank']}: {pick['title']}{year}"

    image_path = config.POSTER_DIR / pick["poster_path"] if pick["poster_path"] else None
    ok = await signal_notify.send(text, image_path)

    if ok:
        return HTMLResponse('<button id="signal-share-btn" disabled>✓ Sent to Signal</button>')
    return HTMLResponse('<button id="signal-share-btn" class="secondary" disabled>✗ Signal unavailable</button>')


# --- Management (open, local network only) ---------------------------------

@app.post("/manage/seed", response_class=HTMLResponse)
async def manage_seed(request: Request):
    inserted = await seed.load_seed()
    return HTMLResponse(
        f'<p>Seeded {inserted} new film(s). '
        f'<a href="/" hx-boost="false">Back to the draw</a>.</p>'
    )


@app.post("/manage/reset", response_class=HTMLResponse)
async def manage_reset_prompt(request: Request):
    # Step 1: return a confirmation partial in place of the button.
    return templates.TemplateResponse(request, "partials/reset_confirm.html", {})


@app.post("/manage/reset/confirm", response_class=HTMLResponse)
async def manage_reset_confirm(request: Request):
    # Step 2: actually clear all picks.
    conn = await db.connect()
    try:
        await db.reset_picks(conn)
    finally:
        await conn.close()
    return templates.TemplateResponse(request, "partials/reset_done.html", {})

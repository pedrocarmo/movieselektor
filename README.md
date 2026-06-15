# Movieselektor

A "movie of the week" club tool for working through the
[TSPDT 1000 Greatest Films](https://www.theyshootpictures.com/) (21st ed., 2026).
Draw a film, watch it together, mark it watched, repeat. Single shared club state —
no users, no auth, local network only.

See [PLAN.md](PLAN.md) for the full architecture and roadmap.

## Stack

FastAPI + Jinja2 + HTMX + Pico CSS, SQLite for storage, optional TMDB for posters.
No build step, no JS framework, one Docker service.

## Run with Docker (homelab)

```bash
cp .env.example .env        # optional: add your TMDB_API_KEY for posters
docker compose up -d --build
```

Then open `http://<homelab-ip>:8000` and click **Load the film list** once to seed
the 1000 films. Data persists in `./data/` (SQLite DB + cached posters).

## Run locally (dev)

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app.main:app --reload
```

## How it works

- **Draw** picks a random film not yet watched and makes it the shared active pick.
- **Skip** retires the current pick and draws another (no mark).
- **Mark as watched** records it with a timestamp; an **Undo** button appears right after.
- **History** lists every watched film with its date.
- **Clear all watched** (small link, bottom of page) wipes history — debug use, with a
  confirmation step. Films are never deleted.

Posters are fetched from TMDB the first time a film is drawn, then cached locally
forever. Without a `TMDB_API_KEY` the app works fine — films just show a placeholder.

## Backup

The whole state is one SQLite file:

```bash
sqlite3 ./data/db.sqlite3 ".backup ./backups/db-$(date +%Y%m%d).sqlite3"
```

Restore by stopping the stack, copying a backup over `./data/db.sqlite3`, and starting
again. Posters don't need backing up — they re-fetch on demand.

# Movieselektor — Architecture Plan

## Clarifying Questions — Resolved

| Question | Answer |
|---|---|
| Watched state scope | Shared across the whole club |
| Current pick | One shared active pick per week; persists until marked watched |
| Watch history | Timestamped log of past picks; no ratings or notes |
| Auth | None — local network only |
| Backend maintainer | Claude — choose whatever minimises code and maximises readability |
| Posters | High priority; user will create a free TMDB account |
| Cloud dependencies | TMDB only, opt-in; no other third-party services |
| Scale | Small private film club, 1000 rows — do not over-engineer |
| Deployment | Homelab Docker, single docker-compose stack |

---

## 1. Recommended Architecture & Stack

### Backend: Python 3.12 + FastAPI

FastAPI is the right call here: it produces the least code of any Python framework for a
CRUD+async workload, it's extremely readable, and its async support is needed for the
TMDB poster-fetching pipeline. Flask is simpler but synchronous, which makes the TMDB
enrichment step awkward. Go would be faster but far more verbose for the same feature
set.

### Frontend: Jinja2 templates + HTMX + Pico CSS

No JavaScript framework, no build step, no npm. HTMX lets the few interactive actions
(Draw, Skip, Mark Watched) update only the relevant part of the page without a full
reload — all driven by HTML attributes. Pico CSS is a classless stylesheet (one CDN
link) that makes plain HTML look good with zero design work.

### Database: SQLite (single file)

1000 rows, trivially low concurrent load, no concurrent write contention worth worrying
about. SQLite is a single file that is trivially backed up, trivially seeded, and needs
zero infrastructure. A separate Postgres container would be overkill by a factor of 100.

### Poster cache: local filesystem

TMDB poster images are fetched server-side at enrichment time and stored in a local
`/data/posters/` directory. FastAPI serves them as static files. This solves the CORS
problem from the prototype and means the app is self-contained after the first enrichment
run — no TMDB dependency at runtime.

### Stack summary

| Layer | Choice | Rationale |
|---|---|---|
| Language | Python 3.12 | Readable, rich stdlib, best async HTTP client |
| Web framework | FastAPI | Least code, async, auto-generates API docs |
| Templating | Jinja2 | Ships with FastAPI ecosystem |
| Interactivity | HTMX | No build step, zero JS complexity |
| Styling | Pico CSS | Classless, one CDN link, looks decent immediately |
| Database | SQLite via `aiosqlite` | Zero infra, one file, trivially backed up |
| HTTP client | `httpx` | Async, used for TMDB calls |
| Container | Docker (single service) | As specified |

---

## 2. Data Model

```sql
-- Seeded from JSON; enriched later by TMDB pipeline
CREATE TABLE films (
    id          INTEGER PRIMARY KEY,
    rank        INTEGER NOT NULL UNIQUE,
    title       TEXT    NOT NULL,
    year        INTEGER,
    director    TEXT,
    letterboxd_search_url TEXT,      -- from seed data (search link)
    tmdb_id     INTEGER,             -- populated by enrichment job
    poster_path TEXT                 -- relative path under /data/posters/, nullable
);

-- One row per draw event; the active pick is the latest row with status='active'
CREATE TABLE picks (
    id          INTEGER PRIMARY KEY,
    film_id     INTEGER NOT NULL REFERENCES films(id),
    drawn_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    watched_at  TIMESTAMP,           -- set when status flips to 'watched'
    status      TEXT NOT NULL DEFAULT 'active'
                CHECK (status IN ('active', 'skipped', 'watched'))
);

CREATE INDEX picks_status ON picks(status);
CREATE INDEX picks_drawn_at ON picks(drawn_at DESC);
```

### Key invariant

At most one row in `picks` with `status = 'active'` at any time. The application
enforces this: every Draw or Skip first sets the current active pick to `'skipped'`
before inserting the new one.

### Derived views (logical, not necessarily materialised)

- **Current pick**: `SELECT * FROM picks WHERE status = 'active' LIMIT 1`
- **Watched films**: `SELECT film_id FROM picks WHERE status = 'watched'`
- **Draw pool**: films whose `id` is not in watched films and not the current active pick's film
- **History**: `SELECT p.*, f.* FROM picks p JOIN films f ON f.id = p.film_id WHERE p.status = 'watched' ORDER BY p.watched_at DESC`

### Letterboxd direct URLs — decision: out of scope

Letterboxd has no public API. Their URL slugs (e.g. `/film/vertigo/`) are not derivable
from title, year, or IMDB ID without scraping, which they block. TMDB can give us IMDB
IDs but not Letterboxd slugs. Keep the search links from the seed data for MVP.
If this matters later, the cleanest path is a community-maintained mapping dataset
(Letterboxd exports from willing users) — not worth the effort for now.

---

## 3. API Surface

Since the frontend is server-rendered with HTMX, most routes return HTML fragments.
A `/health` endpoint and a `/api/` namespace are included for debuggability.

### Page routes (return full HTML or HTMX partial)

| Method | Path | Description |
|---|---|---|
| `GET` | `/` | Main page: current pick or "no pick yet" state |
| `GET` | `/history` | Watched history, reverse-chronological |
| `GET` | `/films` | Full film list with watched status (Phase 2) |
| `GET` | `/health` | Returns 200 OK — used by Docker healthcheck |

### Action routes (HTMX `hx-post`, return updated partial)

| Method | Path | Description |
|---|---|---|
| `POST` | `/draw` | Draw a random unwatched film; replaces any active pick |
| `POST` | `/skip` | Mark active pick as skipped; draw a new film immediately |
| `POST` | `/watch` | Mark active pick as watched; clears the current pick |
| `POST` | `/undo/{pick_id}` | Undo a mark-as-watched; restores the pick to active (see below) |

### Management routes (open, local network only — no auth)

| Method | Path | Description |
|---|---|---|
| `POST` | `/manage/seed` | Load films from `seed.json` (idempotent) |
| `POST` | `/manage/reset` | Delete all picks (clear watched history); requires confirmation step |

### Draw logic (pseudocode)

```
draw_pool = films WHERE id NOT IN watched_film_ids AND id != current_active_film_id
pick = random choice from draw_pool
if current active pick exists:
    UPDATE picks SET status='skipped' WHERE status='active'
INSERT INTO picks (film_id, status) VALUES (pick.id, 'active')
```

### Undo logic

Undo is transient: the undo button is returned in the HTMX partial immediately after
marking a film as watched, carrying the `pick_id`. It disappears on page refresh.
This is intentional — undo is a "oops, I just clicked that" affordance, not a full
history traveller. Skip has no undo.

**Undo a watch** (pick_id = the pick that was just marked watched):
```
UPDATE picks SET status='active', watched_at=NULL WHERE id = pick_id
```

If another draw has happened in the meantime, the undo may produce two active picks.
Acceptable for this scale — not worth adding optimistic locking.

### Reset / clear all watched (two-step confirmation)

Step 1 — `POST /manage/reset`: returns a confirmation partial replacing the button.
Step 2 — `POST /manage/reset/confirm`: deletes all rows from `picks`. The app returns
to day-zero state: no active pick, no history, nothing watched. Film data is untouched.

This is a debug/reset tool, surfaced as a small unobtrusive button away from the main
UI (e.g. bottom of the page or a separate `/manage` page).

---

## 4. TMDB Poster Fetching — Lazy, On Draw

Posters are fetched from TMDB only when a film is drawn as the current pick, then cached
locally forever. The club draws one film per week, so this is effectively one TMDB
lookup per pick — the latency is unnoticeable.

**On draw:**
1. Check `films.poster_path` — if already set, serve from local cache immediately.
2. If not cached: call `GET /search/movie?query={title}&year={year}` → get `tmdb_id`.
3. Call `GET /movie/{tmdb_id}` → get the poster path from TMDB.
4. Download the image from `image.tmdb.org/t/p/w500/{poster_path}`.
5. Save to `/data/posters/{tmdb_id}.jpg`; update `films.tmdb_id` and `films.poster_path`.

This means:
- No bulk job, no background worker, no scheduler.
- Only films the club actually draws ever hit the TMDB API.
- The history page shows posters for past picks automatically (already cached at draw time).
- The film browser (Phase 2) shows posters for drawn films and a placeholder for the rest.

**Fallback:** if TMDB returns no match (some obscure titles may be missing), the pick
displays without a poster — no error, just a placeholder image.

TMDB key is passed via environment variable; the app works without it (placeholders
shown everywhere).

---

## 5. Feature Decision Matrix

### Must-have — MVP

- [ ] Seed 1000 films from `seed.json` (idempotent on re-run)
- [ ] Display current pick: rank, title, year, director, Letterboxd search link
- [ ] Draw a random unwatched film
- [ ] Skip (draw a different film without marking anything)
- [ ] Mark as watched (records timestamp, removes from draw pool)
- [ ] Undo button shown immediately after mark-as-watched; reverts it to active pick
- [ ] Watch history: list of past picks with dates
- [ ] Poster fetched from TMDB at draw time, cached locally, shown on pick and history
- [ ] Clear all watched button (small, away from main UI) with two-step HTMX confirmation
- [ ] SQLite persistence (survives container restart)
- [ ] Docker container, single `docker-compose.yml`

### Nice-to-have — Phase 2

- [ ] Film browser: full list of 1000 films, filtered by watched/unwatched (posters shown for drawn films only)

### Out of scope / overkill for this scale

- Real-time push (WebSockets/SSE) — page refresh is fine for this group size
- Any concept of users, accounts, or identity — the app is fully anonymous
- Ratings, notes, or social features
- Direct Letterboxd film URLs — not feasible without scraping
- Postgres — SQLite handles this scale easily
- Any CI/CD pipeline

---

## 6. Phased Roadmap

### Phase 1 — MVP (prototype parity + reliable persistence) ✅ DONE

Goal: match everything the prototype did, with a real DB and shared state.

1. [x] Project scaffold: FastAPI app, Dockerfile, docker-compose.yml, SQLite setup
2. [x] Seed loader: load seed JSON → `films` table (idempotent, via `/manage/seed`)
3. [x] Core pick flow: Draw / Skip / Mark Watched (server-side logic + HTMX UI)
4. [x] Undo (mark-as-watched) and two-step Clear-all-watched
5. [x] Lazy TMDB poster fetch + local cache on draw
6. [x] Watch history page
7. [x] Health endpoint

**Deliverable**: a running Docker container that the club can use immediately. ✅
Verified locally: seed (1000, idempotent), draw, skip, watched-exclusion (30 draws),
single-active invariant, undo, history, and the two-step reset all pass.

### Phase 2 — Film browser

Goal: let the club browse the full 1000-film list.

1. Film browser page (all 1000 films, watched/unwatched filter)
2. Posters shown for any film that has been drawn (already cached); placeholder for the rest

**Deliverable**: full TSPDT list browsable with progress visible at a glance.

### Phase 3 — Maintenance tooling

Goal: make annual TSPDT edition updates painless.

1. Edition-aware seed: support loading a new `seed.json` that updates ranks and adds/removes
   films while preserving watched history (match on title+year, not rank)
2. Migration notes doc for edition update procedure
3. Backup/restore helper script

**Deliverable**: updating to the 2027 edition takes under 5 minutes.

---

## 7. Docker Compose & Persistence

### Directory layout

```
movieselektor/
├── docker-compose.yml
├── Dockerfile
├── .env                    # TMDB_API_KEY=... (gitignored)
├── seed.json               # 1000-film dataset
├── app/
│   ├── main.py
│   ├── db.py
│   ├── models.py
│   ├── routes/
│   └── templates/
└── data/                   # mounted as Docker volume
    ├── db.sqlite3
    └── posters/
```

### docker-compose.yml

```yaml
services:
  app:
    build: .
    ports:
      - "8000:8000"        # access on local network: http://<homelab-ip>:8000
    volumes:
      - ./data:/data       # SQLite DB + poster cache survive container updates
    environment:
      - DATABASE_URL=/data/db.sqlite3
      - POSTER_DIR=/data/posters
      - TMDB_API_KEY=${TMDB_API_KEY:-}   # optional; posters disabled if absent
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 5s
      retries: 3
    restart: unless-stopped
```

### Persistence

Everything that must survive a container rebuild lives in `./data/`:
- `db.sqlite3` — all film data, picks, watch history
- `posters/` — local poster cache (re-fetchable from TMDB if lost)

### Backup

Because it's a single SQLite file, backup is trivial:

```bash
# Manual backup (safe even while running — SQLite WAL mode)
cp ./data/db.sqlite3 ./backups/db-$(date +%Y%m%d).sqlite3

# Or with SQLite's online backup (zero chance of corruption)
sqlite3 ./data/db.sqlite3 ".backup ./backups/db-$(date +%Y%m%d).sqlite3"
```

For automation, add a cron job on the host that runs the above nightly. Posters don't
need backing up — they're re-fetchable from TMDB. The whole `./data/` directory can
also be included in any homelab snapshot/restic backup.

### Restore

```bash
docker compose down
cp ./backups/db-20260101.sqlite3 ./data/db.sqlite3
docker compose up -d
```

### Updating the container (zero data loss)

```bash
git pull
docker compose build
docker compose up -d   # replaces container; ./data/ volume is untouched
```

### No reverse proxy needed

The app runs on port 8000, local network only. No TLS, no Nginx/Caddy needed. If you
ever want to expose it outside the LAN, that's when you'd add Caddy in front — but
that's a future concern.

---

## Open Questions for Implementation

None blocking Phase 1. The following are deferred decisions:

- **Edition update matching**: for Phase 3, we need to decide whether films are matched
  across editions by `(title, year)` or by a stable ID. TMDB ID is the best stable
  anchor — another reason to run enrichment early.
- **Poster fallback**: if TMDB finds no match for a film (some obscure 1920s titles may
  not be in TMDB), show a placeholder. This is a UI detail, not an architecture concern.

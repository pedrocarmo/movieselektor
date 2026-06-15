"""Runtime configuration, read from environment with homelab-friendly defaults."""
import os
from pathlib import Path

# Where the SQLite database file lives. In Docker this points inside the mounted volume.
DATABASE_PATH = Path(os.environ.get("DATABASE_PATH", "data/db.sqlite3"))

# Directory where cached TMDB posters are stored.
POSTER_DIR = Path(os.environ.get("POSTER_DIR", "data/posters"))

# The seed dataset (TSPDT 1000). Loaded by the /manage/seed route.
SEED_PATH = Path(os.environ.get("SEED_PATH", "seed/tspdt-1000.seed.json"))

# Optional TMDB API key. If unset, posters are simply not fetched and placeholders show.
TMDB_API_KEY = os.environ.get("TMDB_API_KEY", "").strip()

# TMDB poster size segment (w185/w342/w500). w342 is a good balance for a card.
TMDB_POSTER_SIZE = os.environ.get("TMDB_POSTER_SIZE", "w342")

# Optional Overseerr base URL (no trailing slash). If unset, the link is hidden.
# e.g. https://seerr.example.com
OVERSEERR_URL = os.environ.get("OVERSEERR_URL", "").rstrip("/")

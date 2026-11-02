# MOODFLIX ✳ — Agentic entertainment discovery

A Gen Z-inspired, full-stack entertainment recommendation experience for movies, anime movies, TV series, anime series and books. Built with Next.js, FastAPI, LangGraph and optional live metadata enrichment.

## Run locally

**Requirements:** Node.js 20+, Python 3.10–3.13, internet for first dependency installation.

### Backend

```bash
cd backend
python -m venv .venv
# macOS / Linux:
source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp .env.example .env  # Windows: copy .env.example .env
uvicorn app.main:app --reload --port 8000
```

API docs: http://localhost:8000/docs

### Frontend (second terminal)

```bash
cd frontend
npm install
cp .env.example .env.local  # Windows: copy .env.example .env.local
npm run dev
```

Open http://localhost:3000

## Optional credentials

Everything works with **no keys**. Without credentials:

- Posters/covers/ratings come from keyless public APIs: **Wikipedia** (movie posters), **TVmaze** (series posters, ratings, original network), **AniList** (anime covers, scores, official streaming links), **Open Library** (book covers, reader ratings).
- Live discovery adds real titles from AniList (anime) and Open Library (books), plus TVmaze for series searches.
- Mood interpretation uses deterministic rules.

Optional `backend/.env` keys:

- `TMDB_API_KEY` (v3 key or v4 read token): TMDB posters/ratings, live movie + TV discovery/search, and **verified streaming providers** (JustWatch data via TMDB). `WATCH_REGION` (default `US`) picks the provider region.
- `OPENAI_API_KEY`: LLM intent extraction in the mood agent; any failure falls back to rules.
- `MOODFLIX_OFFLINE=1`: skip all network calls (used by the tests).

## Architecture

`Next.js UI -> FastAPI -> LangGraph: mood_agent -> discovery_agent -> ranking_agent -> explanation_agent`

- **Mood agent:** reads quiz answers or free text and handles refinements such as "something more romantic", "less sad, please", "I've already watched this" and "something similar". The client sends the conversation state (filters, exclusions, current pick) with each turn, so the server stays stateless.
- **Discovery agent:** a curated 93-title catalog (each title's source ID was checked against the live APIs), plus live API candidates when the curated pool is thin or the user searches.
- **Ranking agent:** 55% mood, 20% genre, 25% intensity; avoided moods and already-shown titles are penalized. Format and exclusions are hard filters. Ending, duration and genre are *preferences*: if fewer than 6 titles fit them all, they are relaxed one at a time (duration → ending → genre), and the response says which ones (`status: "relaxed"`, `relaxed: [...]`).
- **Explanation agent:** short, spoiler-free reasons built from tags and genres, plus artwork/rating enrichment (cached in memory for 6h).

API responses carry `status` = `ok` | `relaxed` | `no_match`, so the UI can tell a genuine empty result apart from a backend error. The frontend retries network errors and 5xx responses twice with backoff.

## Tests

```bash
cd backend && python -m pytest -q          # 89 tests, offline and deterministic
cd frontend && npx tsc --noEmit && npm run build
```

## Known limitations

- Streaming availability is shown only when a provider verifies it: TMDB/JustWatch (requires `TMDB_API_KEY`) or AniList's official links. Otherwise the UI says it couldn't verify availability and offers a JustWatch search link.
- Movie ratings require TMDB; without a key, movies show posters but no rating.
- Open Library covers redirect through archive.org and can take several seconds on first load. A shimmer placeholder shows while they load.
- Ratings appear only when there are enough votes (TMDB ≥50, Open Library ≥25).
- My Collection is stored in browser localStorage (no accounts).
- Mood and intensity tags on curated titles are editorial judgments. Live titles get tags derived from their genres.

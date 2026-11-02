import asyncio
import logging
from contextlib import asynccontextmanager
import os
import random
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / '.env')

from fastapi import FastAPI, Request as HTTPRequest  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402
from pydantic import BaseModel, Field, field_validator  # noqa: E402

from .agents import run_agents  # noqa: E402
from .catalog import CATALOG, MOODS  # noqa: E402
from .integrations import offline, tmdb_key, warm_cache  # noqa: E402

log = logging.getLogger('moodflix')
KINDS = {'movie', 'anime_movie', 'series', 'anime_series', 'book'}

@asynccontextmanager
async def lifespan(_app):
    task = asyncio.create_task(warm_cache(CATALOG))  # best-effort artwork warm-up
    yield
    task.cancel()


app = FastAPI(title='MOODFLIX Agent API', version='2.0.0', lifespan=lifespan)
origins = [x.strip() for x in os.getenv('FRONTEND_ORIGIN', 'http://localhost:3000').split(',') if x.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    # Any local dev port on localhost / 127.0.0.1 (Next.js may pick 3001 if 3000 is busy).
    allow_origin_regex=r'https?://(localhost|127\.0\.0\.1)(:\d+)?',
    allow_methods=['GET', 'POST', 'OPTIONS'],
    allow_headers=['*'],
)


class Request(BaseModel):
    message: str = Field(default='', max_length=1500)
    moods: list[str] = Field(default_factory=list)
    avoid_moods: list[str] = Field(default_factory=list)
    kinds: list[str] = Field(default_factory=list)
    genres: list[str] = Field(default_factory=list, max_length=12)
    intensity: int = Field(default=45, ge=0, le=100)
    ending: Literal['any', 'happy', 'bittersweet', 'twist', 'surprise'] = 'any'
    duration: Literal['any', 'short', 'medium', 'long'] = 'any'
    exclude: list[str] = Field(default_factory=list, max_length=200)
    seen: list[str] = Field(default_factory=list, max_length=200)
    shown: list[str] = Field(default_factory=list, max_length=60)
    focus_id: str | None = None
    similar_to: str | None = None
    search: str = Field(default='', max_length=120)
    browse: bool = False
    shuffle: bool = False
    limit: int = Field(default=12, ge=1, le=30)

    @field_validator('moods', 'avoid_moods')
    @classmethod
    def known_moods(cls, v):
        return [m for m in dict.fromkeys(v) if m in MOODS][:3]

    @field_validator('kinds')
    @classmethod
    def known_kinds(cls, v):
        return [k for k in dict.fromkeys(v) if k in KINDS]


PUBLIC_FILTERS = ('moods', 'avoid_moods', 'kinds', 'genres', 'intensity', 'ending', 'duration', 'exclude', 'seen', 'similar_to')


def _payload(state):
    items = state.get('results') or []
    relaxed = state.get('relaxed') or []
    status = 'no_match' if not items else ('relaxed' if relaxed else 'ok')
    f = state.get('filters') or {}
    return {
        'status': status,
        'items': items,
        'count': len(items),
        'relaxed': relaxed,
        'interpreted_moods': f.get('moods', []),
        'filters': {k: f.get(k) for k in PUBLIC_FILTERS},
        'sources': state.get('sources') or [],
        'trace': state.get('trace') or [],
    }


@app.exception_handler(Exception)
async def unhandled(request: HTTPRequest, exc: Exception):
    log.exception('Unhandled error on %s', request.url.path)
    return JSONResponse(status_code=500, content={'error': 'internal_error', 'detail': 'The recommendation service hit an unexpected error.'})


@app.get('/api/health')
def health():
    return {'status': 'ok', 'catalog_size': len(CATALOG), 'langgraph': True,
            'live_metadata': not offline(), 'tmdb': bool(tmdb_key()), 'llm': bool(os.getenv('OPENAI_API_KEY'))}


@app.get('/api/catalog')
def catalog():
    return {'items': CATALOG, 'count': len(CATALOG)}


@app.post('/api/recommend')
async def recommendation(request: Request):
    data = request.model_dump()
    msg = data.pop('message')
    state = await run_agents(msg, data)
    return _payload(state)


# "Bestie" voice for the chat. Templates only, so it works offline; the picks themselves
# still come from the LangGraph pipeline above.
MOOD_OPENERS = {
    'sad': ["Okay, we're in our feelings today. Respect. 🥲", 'Heartbreak era, I see you. Tissues ready? 🧻'],
    'romantic': ['Down bad hours, I see 👀', 'Delulu is the solulu, bestie. Romance incoming 💘'],
    'cozy': ['Blanket burrito mode: activated 🥔', 'Cozy potato hours. Snacks first, then this.'],
    'happy': ['Serotonin delivery, coming right up ☀️', 'Good vibes only, say less ✌️'],
    'chaotic': ['Villain era? Love that for you 😈', 'Unhinged picks for an unhinged mood. Perfect.'],
    'mystery': ['Putting on my detective hat 🕵️', 'Ooh, you want twists? I gotchu.'],
    'existential': ["Existential crisis o'clock, my favourite 🌀", 'Big thoughts mode. Let it get weird.'],
    'excited': ['Adrenaline, coming right up ⚡', 'Buckle up, these go hard.'],
    'relaxed': ['Low effort, high comfort. Say less 😌', 'Zero stress picks, just vibes.'],
    'main-character': ['Main character energy only 💅', 'Cue the slow-mo walk. These are for you.'],
    'motivated': ['Underdog arc? We love a comeback 💪', 'Getting you hyped, one sec.'],
}
SKIP_LINES = ["Say less, that one's gone 🫡", "Noted, we're pretending that one never happened.", 'Valid. Yeeting it off the list.']
PICK_LINES = ['Trust me on {lead}', 'My top pick: {lead}', 'You NEED to try {lead}', 'Start with {lead}']
CLOSERS = ["Not feeling it? Tell me, I won't be offended. (I will be a little.)",
           'Hate it? Say "nah" and I\'ll find something else.', '']


def _reply(state, notes, rng=random):
    items = state.get('results') or []
    f = state.get('filters') or {}
    if not items:
        return ("Okay I looked everywhere and came up empty 😭 Give me a vibe (cozy, down bad, villain era) "
                "or a format (movie, anime, book) and I'll try again.")
    lead = items[0]
    year = f" ({lead['year']})" if lead.get('year') else ''
    opener = []
    if 'skip' in notes:
        opener.append(rng.choice(SKIP_LINES))
    if 'similar' in notes and f.get('similar_to'):
        from .catalog import BY_ID
        ref = BY_ID.get(f['similar_to'])
        opener.append(f"Ooh, you liked {ref['title']}? Same energy, coming up." if ref else 'Same energy, coming up.')
    less = [n.split(' ', 1)[1] for n in notes if n.startswith('less ')]
    more = [n.split(' ', 1)[1] for n in notes if n.startswith('more ')]
    if 'sad' in less:
        opener.append("Girl, not another heartbreak movie 😭 Okay, I've got something better.")
    elif less:
        opener.append(f"Dialling down the {', '.join(less)}. You deserve a break 🫶")
    if more:
        opener.append(f"More {', '.join(more)}? Say less 😌")
    if 'shorter' in notes:
        opener.append('Short attention span? Same. Keeping it quick ⏱️')
    if 'lighter' in notes:
        opener.append('Keeping it light, no emotional damage today.')
    if 'more intense' in notes:
        opener.append('Oh, you want to be emotionally destroyed? Bet 😈')
    if 'fresh' in notes and 'skip' not in notes:
        opener.append('New batch, fresh out the oven 🍪')
    if not opener:
        moods = f.get('moods') or []
        opener.append(rng.choice(MOOD_OPENERS.get(moods[0], ['Okay bestie, here goes:'])) if moods else 'Okay bestie, here goes:')
    reply = ' '.join(opener) + ' ' + rng.choice(PICK_LINES).format(lead=f"{lead['title']}{year}")
    if len(items) > 1:
        reply += f", or if that's not it, {items[1]['title']}"
    reply += '.'
    if state.get('relaxed'):
        names = {'duration': 'time', 'ending': 'ending', 'genres': 'genre'}
        loosened = [names.get(r, r) for r in state['relaxed']]
        joined = loosened[0] if len(loosened) == 1 else ', '.join(loosened[:-1]) + ' and ' + loosened[-1]
        reply += f" Heads up: a few picks bend your {joined} rules, but they're worth it."
    closer = rng.choice(CLOSERS)
    return reply + (' ' + closer if closer else '')


@app.post('/api/chat')
async def chat(request: Request):
    data = request.model_dump()
    msg = data.pop('message')
    state = await run_agents(msg, data)
    payload = _payload(state)
    payload['reply'] = _reply(state, state.get('notes') or [])
    return payload

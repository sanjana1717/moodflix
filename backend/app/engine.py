"""Deterministic mood parsing, refinement and ranking.

Design notes
------------
* Category (kind) and explicit exclusions are hard filters: the user asked for books,
  so we never return a movie, and a title marked "already watched" never comes back.
* Ending, duration and genre are *preferences*. Titles that satisfy them rank first.
  If fewer than ``MIN_RESULTS`` titles satisfy every preference, we progressively relax
  them (duration -> ending -> genres) and report exactly what was relaxed, instead of
  returning an empty list. This was the root cause of the empty-results bug: the old
  engine applied them as hard filters on a 25-title catalog, so e.g. "any movie +
  Quick fix" matched nothing.
"""
import random
import re

from .catalog import CATALOG, MOODS

MIN_RESULTS = 6

MOOD_ALIASES = {
    'lonely': 'cozy', 'heartbroken': 'sad', 'in love': 'romantic', 'love story': 'romantic', 'lovey': 'romantic', 'romance': 'romantic', 'romcom': 'romantic',
    'swoon': 'romantic', 'cry': 'sad', 'tearjerker': 'sad', 'emotional': 'sad', 'stressed': 'relaxed',
    'tired': 'relaxed', 'chill': 'relaxed', 'calm': 'relaxed', 'bored': 'excited', 'thrill': 'excited',
    'action': 'excited', 'adrenaline': 'excited', 'hype': 'excited', 'suspense': 'mystery', 'twist': 'mystery',
    'detective': 'mystery', 'whodunit': 'mystery', 'laugh': 'happy', 'funny': 'happy', 'comedy': 'happy',
    'cheer': 'happy', 'uplifting': 'happy', 'feel-good': 'happy', 'feel good': 'happy', 'comfort': 'cozy',
    'wholesome': 'cozy', 'warm': 'cozy', 'inspired': 'motivated', 'inspiring': 'motivated',
    'motivation': 'motivated', 'weird': 'chaotic', 'unhinged': 'chaotic', 'messy': 'chaotic',
    'overthinking': 'existential', 'deep': 'existential', 'philosophical': 'existential',
    'thought-provoking': 'existential', 'confident': 'main-character', 'glamorous': 'main-character',
    # Gen Z vibes (match the mood cards in the UI)
    'heartbreak': 'sad', 'sad girl': 'sad', 'emotionally damaged': 'sad', 'emotional damage': 'sad', 'in my feelings': 'sad',
    'down bad': 'romantic', 'delulu': 'romantic', 'yearning': 'romantic', 'rizz': 'romantic', 'situationship': 'romantic',
    'villain era': 'chaotic', 'villain': 'chaotic', 'feral': 'chaotic', 'brain rot': 'chaotic',
    'cozy potato': 'cozy', 'couch potato': 'cozy', 'comfy': 'cozy', 'vibing': 'relaxed', 'vibes': 'relaxed',
    'slay': 'main-character', 'main character energy': 'main-character', 'that girl': 'main-character',
    'existential crisis': 'existential', 'serotonin': 'happy', 'glow up': 'motivated',
}

GENRES = ['romance', 'comedy', 'drama', 'mystery', 'thriller', 'sci-fi', 'fantasy', 'action', 'adventure',
          'horror', 'animation', 'family', 'music', 'slice of life', 'sports', 'crime', 'classic']

KIND_WORDS = [
    (r'\banime (movie|film)s?\b', ['anime_movie']),
    (r'\banime (series|show)s?\b', ['anime_series']),
    (r'\banime\b', ['anime_movie', 'anime_series']),
    (r'\b(movie|film)s?\b', ['movie']),
    (r'\b(tv|series|show|shows|sitcom)\b', ['series']),
    (r'\b(book|books|novel|novels|read|reading)\b', ['book']),
]


def _mood_words(text):
    text = text.lower()
    found = [m for m in MOODS if re.search(r'\b' + re.escape(m.replace('-', ' ')) + r'\b', text.replace('-', ' '))]
    found += [v for k, v in MOOD_ALIASES.items() if re.search(r'\b' + re.escape(k) + r'\b', text)]
    return list(dict.fromkeys(found))


def parse_mood(text):
    """Return the moods a free-text request asks for (fallback: cozy)."""
    return _mood_words(text) or ['cozy']


def parse_kinds(text):
    text = text.lower()
    for pattern, kinds in KIND_WORDS:
        if re.search(pattern, text):
            return kinds
    return []


def parse_refinement(message, filters, focus_id=None):
    """Turn a conversational message into updated filters.

    Understands e.g. "something more romantic", "less sad please", "I've already
    watched this", "something similar", "a shorter one", "only books".
    Returns (new_filters, notes) where notes describe what changed (for the reply).
    """
    text = (message or '').lower().strip()
    f = {**filters}
    f['moods'] = list(f.get('moods') or [])
    f['avoid_moods'] = list(f.get('avoid_moods') or [])
    f['exclude'] = list(f.get('exclude') or [])
    f['seen'] = list(f.get('seen') or [])
    notes = []
    if not text:
        return f, notes

    # Already watched / not interested in the current pick.
    if focus_id and re.search(r"(already (watched|seen|read)|seen (it|this)|watched (it|this)|read (it|this)|not (this|that) one|something else|skip (it|this)"
                              r"|\bnah\b|\bnope\b|hard pass|not feeling (it|this|that)|not the vibe|\bick\b|\bew+\b)", text):
        if focus_id not in f['exclude']:
            f['exclude'].append(focus_id)
        notes.append('skip')

    # "Similar to this"
    if focus_id and re.search(r'\b(similar|like (this|that|it)|more like)\b', text):
        f['similar_to'] = focus_id
        notes.append('similar')

    # "Less X" / "not so X" / "no X"
    for m in _mood_words(' '.join(re.findall(r'\b(?:less|not so|not too|no more|no|without|nothing)\s+([a-z\- ]{3,20})', text))):
        if m in f['moods']:
            f['moods'].remove(m)
        if m not in f['avoid_moods']:
            f['avoid_moods'].append(m)
        if m == 'sad':
            f['intensity'] = max(0, int(f.get('intensity', 45)) - 25)
        notes.append(f'less {m}')
    avoided = set(f['avoid_moods'])

    # "More X" / "something X"
    positive = [m for m in _mood_words(re.sub(r'\b(?:less|not so|not too|no more|no|without|nothing)\s+[a-z\-]+', ' ', text)) if m not in avoided]
    if positive:
        if re.search(r'\b(more|extra|even more|a bit more|also)\b', text):
            f['moods'] = list(dict.fromkeys(positive + f['moods']))[:3]
            notes.extend(f'more {m}' for m in positive)
        else:
            f['moods'] = positive[:3]
            notes.append('new mood')
    for m in positive:
        if m in f['avoid_moods']:
            f['avoid_moods'].remove(m)

    kinds = parse_kinds(re.sub(r"(already (watched|seen|read)|(read|watched|seen) (it|this|that))", ' ', text))
    if kinds:
        f['kinds'] = kinds
        notes.append('kinds')
    if re.search(r'\b(short|shorter|quick|quicker)\b', text):
        f['duration'] = 'short'
        notes.append('shorter')
    if re.search(r'\b(lighter|light|easy|gentle)\b', text):
        f['intensity'] = min(int(f.get('intensity', 45)), 25)
        notes.append('lighter')
    if re.search(r'\b(intense|heavier|dark|darker|gut[- ]?punch)\b', text):
        f['intensity'] = max(int(f.get('intensity', 45)), 75)
        notes.append('more intense')
    if 'happy ending' in text:
        f['ending'] = 'happy'
    elif 'twist' in text:
        f['ending'] = 'twist'
    if re.search(r'\b(different|another|new ones?|other options?|refresh)\b', text):
        notes.append('fresh')
    genres = [g for g in GENRES if re.search(r'\b' + re.escape(g) + r'\b', text)]
    if genres:
        f['genres'] = genres
    if not f['moods']:
        f['moods'] = [m for m in ['cozy', 'happy'] if m not in avoided][:1] or ['relaxed']
    return f, notes


def _duration_ok(item, duration):
    if duration in (None, '', 'any'):
        return True
    kind = item['kind']
    v = item.get('pages') if kind == 'book' else item.get('minutes')
    if not v:
        return False
    if kind == 'book':
        short, medium = 250, 400
    elif kind in ('movie', 'anime_movie'):
        short, medium = 100, 125
    else:
        short, medium = 25, 45
    if duration == 'short':
        return v <= short
    if duration == 'medium':
        return v <= medium
    if duration == 'long':
        return v > medium
    return True


def _norm_title(t):
    return re.sub(r'[^a-z0-9]', '', (t or '').lower())


def score_item(x, filters, reference=None):
    moods = filters.get('moods') or []
    genres = filters.get('genres') or []
    avoid = set(filters.get('avoid_moods') or [])
    intensity = int(filters.get('intensity', 45))
    mood_matches = [m for m in moods if m in x['moods']]
    genre_matches = [g for g in genres if g in x['genres']]
    mood_score = len(mood_matches) / len(moods) if moods else .6
    genre_score = len(genre_matches) / len(genres) if genres else .6
    intensity_score = max(0.0, 1 - abs(intensity - x.get('intensity', 50)) / 100)
    score = 100 * (.55 * mood_score + .20 * genre_score + .25 * intensity_score)
    avoided = [m for m in x['moods'] if m in avoid]
    score -= 25 * len(avoided)
    if reference:
        shared_g = len(set(reference['genres']) & set(x['genres'])) / max(1, len(reference['genres']))
        shared_m = len(set(reference['moods']) & set(x['moods'])) / max(1, len(reference['moods']))
        score = .5 * score + 50 * (.5 * shared_g + .5 * shared_m)
    if x['id'] in set(filters.get('seen') or []):
        score -= 30
    return max(1, min(99, round(score))), mood_matches, genre_matches


def recommend(filters, catalog=None):
    """Rank a candidate pool. Returns (results, relaxed) where relaxed lists the
    preferences that had to be loosened to reach MIN_RESULTS."""
    catalog = CATALOG if catalog is None else catalog
    kinds = filters.get('kinds') or []
    excluded = set(filters.get('exclude') or [])
    search = (filters.get('search') or '').lower().strip()
    ending = filters.get('ending') or 'any'
    duration = filters.get('duration') or 'any'
    genres = filters.get('genres') or []
    limit = min(30, max(1, int(filters.get('limit', 12))))

    pool = [x for x in catalog if (not kinds or x['kind'] in kinds) and x['id'] not in excluded]
    if search:
        st = _norm_title(search)
        pool = [x for x in pool if st in _norm_title(x['title']) or search in x.get('author', '').lower()
                or any(search == g for g in x['genres']) or x.get('source') == 'live-search']

    reference = None
    if filters.get('similar_to'):
        reference = next((x for x in catalog if x['id'] == filters['similar_to']), None)
        pool = [x for x in pool if x['id'] != filters['similar_to']]

    scored = []
    for x in pool:
        score, mood_matches, genre_matches = score_item(x, filters, reference)
        misses = []
        if not _duration_ok(x, duration):
            misses.append('duration')
        if ending not in ('any', 'surprise', '') and x.get('ending') != ending:
            misses.append('ending')
        if genres and not genre_matches:
            misses.append('genres')
        scored.append({**x, 'match': score, 'mood_matches': mood_matches, 'genre_matches': genre_matches, 'misses': misses})

    # Progressive relaxation: strict first, then loosen one preference at a time.
    seen = set(filters.get('seen') or [])
    fresh = [x for x in scored if x['id'] not in seen]  # on a refresh, count only titles not shown yet
    relaxed = []
    allowed = set()
    target = min(MIN_RESULTS, len(fresh))
    for step in ['duration', 'ending', 'genres']:
        if sum(1 for x in fresh if set(x['misses']) <= allowed) >= target:
            break
        if any(step in x['misses'] for x in scored):
            allowed.add(step)
            relaxed.append(step)
    results = [x for x in scored if set(x['misses']) <= allowed]
    # Already-shown titles go last on a refresh, so new picks actually surface.
    # A missed preference costs 15 points, so a strong mood match can outrank a weak exact fit.
    results.sort(key=lambda x: (x['id'] in seen, -(x['match'] - 15 * len(x['misses'])), x['title']))
    if search:
        st = _norm_title(search)

        def relevance(x):
            t = _norm_title(x['title'])
            if t == st:
                return 0
            if t.startswith(st):
                return 1
            if st in t:
                return 2
            if search in x.get('author', '').lower() or search in x['genres']:
                return 3
            return 4
        results.sort(key=relevance)  # stable: keeps mood ordering within each tier

    if filters.get('shuffle') and len(results) > 3:
        # Re-order within the strong matches only so a refresh never surfaces weak picks first.
        unseen = [x for x in results if x['id'] not in seen] or results
        cutoff = max(x['match'] for x in unseen) - 15
        strong = [x for x in unseen if x['match'] >= cutoff and not x['misses']]
        rest = [x for x in results if x not in strong]
        random.shuffle(strong)
        results = strong + rest
    return results[:limit], relaxed


def dedupe_against(items, existing):
    titles = {_norm_title(x['title']) for x in existing}
    out = []
    for x in items:
        t = _norm_title(x['title'])
        if t and t not in titles:
            titles.add(t)
            out.append(x)
    return out

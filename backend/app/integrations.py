"""Live metadata: poster/rating enrichment and API-based discovery.

Sources (all legitimate public APIs; nothing is invented):
  * TMDB            movies + series (needs TMDB_API_KEY; v3 key or v4 read token) incl. JustWatch
                    streaming providers via TMDB's watch/providers endpoint
  * Wikipedia       movie posters when no TMDB key (lead image of the film's article)
  * TVmaze          series posters, ratings and original network (keyless)
  * AniList         anime covers, scores and official streaming links (keyless)
  * Open Library    book covers and reader ratings (keyless)
  * Google Books    book fallback (keyless, rate-limited)

Every call has a short timeout. Failures leave the curated item intact, so the
recommendation flow always works offline. Set MOODFLIX_OFFLINE=1 to skip network.
"""
import asyncio
import html
import os
import re
import time

import httpx

HEADERS = {'User-Agent': 'MOODFLIX/1.0 (https://localhost; local prototype)', 'Accept-Encoding': 'gzip'}
TIMEOUT = httpx.Timeout(5.0, connect=3.0)
TMDB_IMG = 'https://image.tmdb.org/t/p/w500'
_CACHE: dict = {}
_CACHE_TTL = 6 * 3600

GENRE_MOODS = {
    'romance': ['romantic'], 'comedy': ['happy', 'chaotic'], 'drama': ['sad', 'existential'],
    'mystery': ['mystery'], 'thriller': ['excited', 'mystery'], 'sci-fi': ['existential', 'excited'],
    'fantasy': ['main-character', 'cozy'], 'action': ['excited'], 'adventure': ['excited', 'motivated'],
    'horror': ['chaotic', 'mystery'], 'slice of life': ['cozy', 'relaxed'], 'sports': ['motivated', 'excited'],
    'music': ['romantic', 'motivated'], 'psychological': ['existential', 'mystery'], 'family': ['cozy', 'happy'],
    'animation': ['happy'], 'crime': ['mystery'], 'supernatural': ['mystery'],
}
GENRE_INTENSITY = {'horror': 85, 'thriller': 78, 'psychological': 80, 'drama': 62, 'action': 65, 'mystery': 60,
                   'sci-fi': 55, 'romance': 40, 'adventure': 45, 'comedy': 25, 'slice of life': 15, 'family': 12}
MOOD_GENRES = {
    'happy': ['comedy'], 'romantic': ['romance'], 'sad': ['drama'], 'chaotic': ['comedy'],
    'relaxed': ['slice of life'], 'main-character': ['drama'], 'existential': ['sci-fi'],
    'excited': ['action', 'adventure'], 'cozy': ['slice of life'], 'mystery': ['mystery'], 'motivated': ['sports'],
}
ANILIST_GENRE = {'comedy': 'Comedy', 'romance': 'Romance', 'drama': 'Drama', 'slice of life': 'Slice of Life',
                 'sci-fi': 'Sci-Fi', 'action': 'Action', 'adventure': 'Adventure', 'mystery': 'Mystery',
                 'sports': 'Sports', 'fantasy': 'Fantasy', 'thriller': 'Thriller', 'horror': 'Horror',
                 'music': 'Music', 'psychological': 'Psychological'}
TMDB_MOVIE_GENRE = {'action': 28, 'adventure': 12, 'animation': 16, 'comedy': 35, 'crime': 80, 'drama': 18,
                    'family': 10751, 'fantasy': 14, 'horror': 27, 'music': 10402, 'mystery': 9648,
                    'romance': 10749, 'sci-fi': 878, 'thriller': 53, 'slice of life': 18, 'sports': 18}
TMDB_TV_GENRE = {'action': 10759, 'adventure': 10759, 'comedy': 35, 'crime': 80, 'drama': 18, 'family': 10751,
                 'mystery': 9648, 'sci-fi': 10765, 'fantasy': 10765, 'romance': 18, 'slice of life': 35,
                 'sports': 18, 'thriller': 9648, 'horror': 9648, 'music': 18, 'animation': 16}
TMDB_GENRE_NAMES = {28: 'action', 12: 'adventure', 16: 'animation', 35: 'comedy', 80: 'crime', 18: 'drama',
                    10751: 'family', 14: 'fantasy', 27: 'horror', 10402: 'music', 9648: 'mystery',
                    10749: 'romance', 878: 'sci-fi', 53: 'thriller', 10759: 'action', 10765: 'sci-fi'}
# Open Library subject keys (checked to return relevant, popular English titles).
OL_SUBJECT = {'romance': 'romance', 'comedy': 'humorous_fiction', 'drama': 'fiction', 'mystery': 'mystery_and_detective_stories',
              'thriller': 'thrillers', 'sci-fi': 'science_fiction', 'fantasy': 'fantasy', 'action': 'adventure_stories',
              'adventure': 'adventure_stories', 'horror': 'horror_tales', 'slice of life': 'friendship', 'sports': 'sports',
              'crime': 'mystery_and_detective_stories', 'family': 'families'}
ADULT_SUBJECTS = re.compile(r'smut|erotic|spicy|dark romance|bdsm|explicit', re.I)


def offline():
    return os.getenv('MOODFLIX_OFFLINE', '').lower() in ('1', 'true', 'yes')


def tmdb_key():
    return (os.getenv('TMDB_API_KEY') or '').strip()


def tmdb_region():
    return (os.getenv('WATCH_REGION') or 'US').upper()


def _norm(t):
    return re.sub(r'[^a-z0-9]', '', (t or '').lower())


def clean_text(text, sentences=2, limit=240):
    """Strip HTML/source notes and keep the opening premise sentences."""
    if not text:
        return ''
    text = html.unescape(re.sub(r'<[^>]+>', ' ', text))
    text = re.sub(r'\((Source|Written by)[^)]*\)', '', text, flags=re.I)
    text = re.sub(r'\s+', ' ', text).strip()
    parts = re.split(r'(?<=[.!?])\s+', text)
    out = ' '.join(parts[:sentences]).strip()
    if len(out) > limit:
        out = out[:limit].rsplit(' ', 1)[0].rstrip(',;:') + '…'
    return out


def _cache_get(key):
    hit = _CACHE.get(key)
    if hit and time.time() - hit[0] < _CACHE_TTL:
        return hit[1]
    return None


def _cache_set(key, value):
    _CACHE[key] = (time.time(), value)
    return value


async def _tmdb_get(client, path, **params):
    key = tmdb_key()
    headers = {}
    if key.startswith('eyJ'):
        headers['Authorization'] = f'Bearer {key}'
    else:
        params['api_key'] = key
    r = await client.get(f'https://api.themoviedb.org/3{path}', params=params, headers=headers)
    r.raise_for_status()
    return r.json()


def _tmdb_providers(data):
    region = (((data.get('watch/providers') or {}).get('results') or {}).get(tmdb_region()) or {})
    seen, providers = set(), []
    for bucket, label in (('flatrate', 'Stream'), ('free', 'Free'), ('ads', 'Free with ads'), ('rent', 'Rent'), ('buy', 'Buy')):
        for p in region.get(bucket) or []:
            if p.get('provider_name') in seen:
                continue
            seen.add(p.get('provider_name'))
            providers.append({'name': p.get('provider_name'), 'type': label, 'url': region.get('link'),
                              'logo': (TMDB_IMG.replace('w500', 'w92') + p['logo_path']) if p.get('logo_path') else None})
    return providers[:8]


async def _enrich_tmdb(client, item):
    typ = 'tv' if item['kind'] in ('series', 'anime_series') else 'movie'
    data = None
    if item.get('tmdb_id'):
        d = await _tmdb_get(client, f"/{typ}/{item['tmdb_id']}", append_to_response='watch/providers')
        if _norm(d.get('title') or d.get('name')) == _norm(item['title']):
            data = d
    if data is None:
        params = {'query': item['title']}
        params['first_air_date_year' if typ == 'tv' else 'year'] = item.get('year')
        res = (await _tmdb_get(client, f'/search/{typ}', **params)).get('results') or []
        match = next((r for r in res if _norm(r.get('title') or r.get('name')) == _norm(item['title'])), None)
        if not match:
            return {}
        data = await _tmdb_get(client, f"/{typ}/{match['id']}", append_to_response='watch/providers')
    out = {'external_url': f"https://www.themoviedb.org/{typ}/{data['id']}", 'tmdb_id': data['id']}
    if data.get('poster_path'):
        out.update(poster=TMDB_IMG + data['poster_path'], poster_source='TMDB')
    if data.get('vote_count', 0) >= 50 and data.get('vote_average'):
        out.update(rating=round(data['vote_average'], 1), rating_scale=10, rating_source='TMDB',
                   rating_count=data['vote_count'])
    providers = _tmdb_providers(data)
    out.update(providers=providers, providers_source='JustWatch via TMDB', providers_region=tmdb_region())
    return out


async def _enrich_wikipedia(client, item):
    title = item.get('wiki') or f"{item['title']} ({item['year']} film)"
    r = await client.get('https://en.wikipedia.org/w/api.php', params={
        'action': 'query', 'format': 'json', 'formatversion': 2, 'redirects': 1, 'titles': title,
        'prop': 'pageimages|description|info', 'piprop': 'thumbnail', 'pithumbsize': 600, 'pilicense': 'any',
        'inprop': 'url'})
    r.raise_for_status()
    pages = r.json().get('query', {}).get('pages') or []
    page = pages[0] if pages else {}
    desc = (page.get('description') or '').lower()
    if page.get('missing') or not any(w in desc for w in ('film', 'movie')):
        return {}
    out = {'wiki_url': page.get('fullurl')}
    if (page.get('thumbnail') or {}).get('source'):
        out.update(poster=page['thumbnail']['source'], poster_source='Wikipedia')
    return out


async def _enrich_tvmaze(client, item):
    if item.get('tvmaze_id'):
        r = await client.get(f"https://api.tvmaze.com/shows/{item['tvmaze_id']}")
    else:
        r = await client.get('https://api.tvmaze.com/singlesearch/shows', params={'q': item['title']})
    r.raise_for_status()
    d = r.json()
    year = int((d.get('premiered') or '0')[:4] or 0)
    if not item.get('tvmaze_id') and (abs(year - item.get('year', year)) > 1):
        return {}
    out = {'external_url': d.get('url')}
    img = d.get('image') or {}
    if img.get('original') or img.get('medium'):
        out.update(poster=img.get('original') or img.get('medium'), poster_source='TVmaze')
    if (d.get('rating') or {}).get('average'):
        out.update(rating=d['rating']['average'], rating_scale=10, rating_source='TVmaze')
    network = (d.get('webChannel') or {}).get('name') or (d.get('network') or {}).get('name')
    if network:
        out['network'] = network
    return out


ANILIST_FIELDS = ('id title{english romaji} seasonYear startDate{year} format genres duration episodes '
                  'description(asHtml:false) averageScore popularity siteUrl coverImage{extraLarge large} '
                  'externalLinks{site type url}')


def _anilist_streaming(media):
    out, seen = [], set()
    for l in media.get('externalLinks') or []:
        if l.get('type') == 'STREAMING' and l.get('site') not in seen:
            seen.add(l['site'])
            out.append({'name': l['site'], 'type': 'Stream', 'url': l['url']})
    return out[:6]


async def _enrich_anilist(client, item):
    if item.get('anilist_id'):
        q = 'query($id:Int){Media(id:$id,type:ANIME){%s}}' % ANILIST_FIELDS
        variables = {'id': item['anilist_id']}
    else:
        q = 'query($s:String){Media(search:$s,type:ANIME){%s}}' % ANILIST_FIELDS
        variables = {'s': item['title']}
    r = await client.post('https://graphql.anilist.co', json={'query': q, 'variables': variables})
    r.raise_for_status()
    m = (r.json().get('data') or {}).get('Media') or {}
    return _anilist_found(m) if m else {}


async def _enrich_openlibrary(client, item):
    out = {}
    if item.get('ol_work'):
        out['external_url'] = f"https://openlibrary.org/works/{item['ol_work']}"
        r = await client.get(f"https://openlibrary.org/works/{item['ol_work']}/ratings.json")
        r.raise_for_status()
        summary = r.json().get('summary') or {}
        if (summary.get('count') or 0) >= 25 and summary.get('average'):
            out.update(rating=round(summary['average'], 1), rating_scale=5, rating_source='Open Library',
                       rating_count=summary['count'])
        return out
    r = await client.get('https://openlibrary.org/search.json', params={
        'title': item['title'], 'author': item.get('author', ''), 'limit': 1,
        'fields': 'key,cover_i,ratings_average,ratings_count'})
    r.raise_for_status()
    docs = r.json().get('docs') or []
    if docs:
        d = docs[0]
        out['external_url'] = 'https://openlibrary.org' + d['key']
        if d.get('cover_i'):
            out.update(poster=f"https://covers.openlibrary.org/b/id/{d['cover_i']}-L.jpg", poster_source='Open Library')
        if (d.get('ratings_count') or 0) >= 25:
            out.update(rating=round(d['ratings_average'], 1), rating_scale=5, rating_source='Open Library')
    return out


async def _enrich_google_books(client, item):
    r = await client.get('https://www.googleapis.com/books/v1/volumes',
                         params={'q': f"intitle:{item['title']}" + (f" inauthor:{item['author']}" if item.get('author') else ''), 'maxResults': 1})
    r.raise_for_status()
    items = r.json().get('items') or []
    if not items:
        return {}
    info = items[0].get('volumeInfo', {})
    out = {'external_url': info.get('infoLink')}
    image = (info.get('imageLinks') or {}).get('thumbnail')
    if image:
        out.update(poster=image.replace('http://', 'https://').replace('&edge=curl', ''), poster_source='Google Books')
    return out


def static_media(item):
    """Metadata derivable without a network call (stable CDN URLs)."""
    out = {}
    if item['kind'] == 'book' and item.get('ol_cover'):
        out.update(poster=f"https://covers.openlibrary.org/b/id/{item['ol_cover']}-L.jpg", poster_source='Open Library')
        out['external_url'] = f"https://openlibrary.org/works/{item['ol_work']}"
    return out


async def enrich(client, item):
    item = {**item, **static_media(item)}
    if item.get('enriched') or offline():
        return item
    key = ('enrich', item['id'], bool(tmdb_key()))
    cached = _cache_get(key)
    if cached is not None:
        return {**item, **cached}
    found = {}
    kind = item['kind']
    steps = []
    if kind in ('movie', 'series') and tmdb_key():
        steps.append(_enrich_tmdb)
    if kind == 'movie':
        steps.append(_enrich_wikipedia)
    elif kind == 'series':
        steps.append(_enrich_tvmaze)
    elif kind.startswith('anime'):
        steps.append(_enrich_anilist)
    elif kind == 'book':
        steps.append(_enrich_openlibrary)
        steps.append(_enrich_google_books)
    ok = True
    for step in steps:
        if found.get('poster') and (found.get('rating') or kind in ('movie', 'book')):
            break
        try:
            got = await step(client, {**item, **found})
            found.update({k: v for k, v in got.items() if v and not found.get(k)})
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            ok = False
            continue
    if ok or found:
        _cache_set(key, found)
    return {**item, **found}


def _anilist_found(m):
    out = {'external_url': m.get('siteUrl')}
    cover = m.get('coverImage') or {}
    if cover.get('extraLarge') or cover.get('large'):
        out.update(poster=cover.get('extraLarge') or cover.get('large'), poster_source='AniList')
    if m.get('averageScore'):
        out.update(rating=round(m['averageScore'] / 10, 1), rating_scale=10, rating_source='AniList')
    streaming = _anilist_streaming(m)
    if streaming:
        out.update(providers=streaming, providers_source='AniList official links')
    return out


async def _prefetch_anilist(client, items):
    """AniList rate-limits bursts, so look up every anime in a single batched query."""
    ids = [x['anilist_id'] for x in items if x['kind'].startswith('anime') and x.get('anilist_id') and not x.get('enriched')
           and _cache_get(('enrich', x['id'], bool(tmdb_key()))) is None]
    if not ids:
        return
    q = 'query($ids:[Int]){Page(perPage:50){media(id_in:$ids,type:ANIME){%s}}}' % ANILIST_FIELDS
    try:
        r = await client.post('https://graphql.anilist.co', json={'query': q, 'variables': {'ids': ids[:50]}})
        r.raise_for_status()
        media = ((r.json().get('data') or {}).get('Page') or {}).get('media') or []
    except (httpx.HTTPError, ValueError):
        return
    by_id = {m['id']: m for m in media}
    for x in items:
        m = by_id.get(x.get('anilist_id'))
        if m and x['kind'].startswith('anime'):
            _cache_set(('enrich', x['id'], bool(tmdb_key())), _anilist_found(m))


async def _resolve_cover(client, url):
    """Open Library cover URLs bounce through two redirects to archive.org (~3s in the
    browser). Resolve the final image URL once server-side and cache it."""
    key = ('cover', url)
    hit = _cache_get(key)
    if hit:
        return hit
    try:
        async with client.stream('GET', url) as r:  # headers only; body is never read
            if r.status_code == 200 and r.headers.get('content-type', '').startswith('image/'):
                return _cache_set(key, str(r.url))
    except httpx.HTTPError:
        pass
    return url


async def resolve_covers(client, items):
    targets = [x for x in items if (x.get('poster') or '').startswith('https://covers.openlibrary.org/')]
    resolved = await asyncio.gather(*(_resolve_cover(client, x['poster']) for x in targets))
    for x, url in zip(targets, resolved):
        x['poster'] = url


async def enrich_many(items):
    async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True, headers=HEADERS) as client:
        if not offline():
            await _prefetch_anilist(client, items)
        out = list(await asyncio.gather(*(enrich(client, x) for x in items)))
        if not offline():
            await resolve_covers(client, out)
        return out


async def warm_cache(items):
    """Background warm-up at startup so the first visitor gets fast artwork."""
    if offline():
        return
    try:
        for i in range(0, len(items), 25):
            await enrich_many(items[i:i + 25])
    except Exception:  # warm-up is best effort
        pass


# --------------------------------------------------------------------------- discovery

def _derive(genres):
    moods = []
    for g in genres:
        moods += GENRE_MOODS.get(g, [])
    moods = list(dict.fromkeys(moods)) or ['relaxed']
    intensity = round(sum(GENRE_INTENSITY.get(g, 50) for g in genres) / max(1, len(genres))) if genres else 50
    return moods, intensity


def _query_genres(filters):
    genres = list(filters.get('genres') or [])
    for m in filters.get('moods') or []:
        genres += MOOD_GENRES.get(m, [])
    return list(dict.fromkeys(genres))[:2]


def _anilist_item(m, kind, source):
    title = (m.get('title') or {}).get('english') or (m.get('title') or {}).get('romaji')
    genres = [g.lower() for g in m.get('genres') or []]
    moods, intensity = _derive(genres)
    cover = m.get('coverImage') or {}
    item = {'id': f"live-anilist-{m['id']}", 'title': title, 'year': m.get('seasonYear') or (m.get('startDate') or {}).get('year'),
            'kind': kind, 'genres': genres[:4], 'moods': moods, 'intensity': intensity, 'ending': 'unknown',
            'minutes': m.get('duration'), 'description': clean_text(m.get('description')), 'tags': genres[:3],
            'anilist_id': m['id'], 'external_url': m.get('siteUrl'), 'poster': cover.get('extraLarge') or cover.get('large'),
            'poster_source': 'AniList', 'source': source, 'enriched': True,
            'description_source': 'AniList'}
    if m.get('averageScore'):
        item.update(rating=round(m['averageScore'] / 10, 1), rating_scale=10, rating_source='AniList')
    streaming = _anilist_streaming(m)
    if streaming:
        item.update(providers=streaming, providers_source='AniList official links')
    return item


async def _discover_anilist(client, kind, filters, search):
    fmt = 'MOVIE' if kind == 'anime_movie' else 'TV'
    variables = {'f': fmt, 'n': 12}
    args = 'type:ANIME,format:$f,isAdult:false,genre_not_in:["Ecchi","Hentai"]'
    decl = '$f:MediaFormat,$n:Int'
    if search:
        args += ',search:$s,sort:SEARCH_MATCH'
        decl += ',$s:String'
        variables['s'] = search
    else:
        genres = [ANILIST_GENRE[g] for g in _query_genres(filters) if g in ANILIST_GENRE]
        args += ',sort:POPULARITY_DESC,averageScore_greater:72'
        if genres:
            args += ',genre_in:$g'
            decl += ',$g:[String]'
            variables['g'] = genres
    q = 'query(%s){Page(perPage:$n){media(%s){%s}}}' % (decl, args, ANILIST_FIELDS)
    r = await client.post('https://graphql.anilist.co', json={'query': q, 'variables': variables})
    r.raise_for_status()
    media = ((r.json().get('data') or {}).get('Page') or {}).get('media') or []
    source = 'live-search' if search else 'live'
    return [_anilist_item(m, kind, source) for m in media if (m.get('title') or {}).get('english') or (m.get('title') or {}).get('romaji')]


async def _discover_openlibrary(client, filters, search):
    fields = 'key,title,author_name,cover_i,first_publish_year,ratings_average,ratings_count,number_of_pages_median,subject'
    if search:
        params = {'q': search, 'limit': 12, 'fields': fields}
        genres = []
    else:
        genres = _query_genres(filters)[:1] or ['fantasy']
        subject = OL_SUBJECT.get(genres[0], genres[0])
        params = {'q': f'subject_key:{subject} language:eng', 'sort': 'readinglog', 'limit': 20, 'fields': fields}
    r = await client.get('https://openlibrary.org/search.json', params=params)
    r.raise_for_status()
    out = []
    for d in r.json().get('docs') or []:
        subjects = ' '.join(d.get('subject') or [])
        if not d.get('cover_i') or ADULT_SUBJECTS.search(subjects):
            continue
        low = subjects.lower()
        g = genres or [k for k in ('romance', 'mystery', 'fantasy', 'thriller', 'horror', 'adventure') if k in low][:3] or ['fiction']
        moods, intensity = _derive(g)
        author = (d.get('author_name') or ['Unknown author'])[0]
        year = d.get('first_publish_year')
        item = {'id': 'live-ol-' + d['key'].split('/')[-1], 'title': d['title'], 'year': year, 'kind': 'book',
                'author': author, 'genres': g[:3], 'moods': moods, 'intensity': intensity, 'ending': 'unknown',
                'pages': d.get('number_of_pages_median'),
                'description': f"A {g[0]} book by {author}" + (f", first published in {year}." if year else '.'),
                'tags': g[:3], 'poster': f"https://covers.openlibrary.org/b/id/{d['cover_i']}-L.jpg",
                'poster_source': 'Open Library', 'external_url': 'https://openlibrary.org' + d['key'],
                'source': 'live-search' if search else 'live', 'enriched': True, 'description_source': 'Open Library'}
        if (d.get('ratings_count') or 0) >= 25:
            item.update(rating=round(d['ratings_average'], 1), rating_scale=5, rating_source='Open Library')
        out.append(item)
        if len(out) >= 10:
            break
    return out


async def _discover_tmdb(client, kind, filters, search):
    typ = 'tv' if kind == 'series' else 'movie'
    if search:
        data = await _tmdb_get(client, f'/search/{typ}', query=search)
    else:
        table = TMDB_TV_GENRE if typ == 'tv' else TMDB_MOVIE_GENRE
        ids = list(dict.fromkeys(table[g] for g in _query_genres(filters) if g in table))
        params = {'sort_by': 'popularity.desc', 'vote_count.gte': 800, 'with_original_language': 'en'}
        if ids:
            params['with_genres'] = '|'.join(map(str, ids))
        if typ == 'tv':
            params['without_genres'] = '16'
        data = await _tmdb_get(client, f'/discover/{typ}', **params)
    out = []
    for d in (data.get('results') or [])[:12]:
        if not d.get('poster_path') or not d.get('overview'):
            continue
        genres = list(dict.fromkeys(TMDB_GENRE_NAMES[g] for g in d.get('genre_ids') or [] if g in TMDB_GENRE_NAMES))
        moods, intensity = _derive(genres)
        date = d.get('release_date') or d.get('first_air_date') or ''
        item = {'id': f"live-tmdb-{typ}-{d['id']}", 'title': d.get('title') or d.get('name'), 'year': int(date[:4]) if date[:4].isdigit() else None,
                'kind': kind, 'genres': genres[:4], 'moods': moods, 'intensity': intensity, 'ending': 'unknown',
                'description': clean_text(d.get('overview')), 'tags': genres[:3], 'tmdb_id': d['id'],
                'poster': TMDB_IMG + d['poster_path'], 'poster_source': 'TMDB',
                'external_url': f"https://www.themoviedb.org/{typ}/{d['id']}", 'source': 'live-search' if search else 'live',
                'description_source': 'TMDB'}
        if d.get('vote_count', 0) >= 50:
            item.update(rating=round(d['vote_average'], 1), rating_scale=10, rating_source='TMDB')
        out.append(item)
    return out


async def _discover_tvmaze(client, search):
    r = await client.get('https://api.tvmaze.com/search/shows', params={'q': search})
    r.raise_for_status()
    out = []
    for hit in r.json()[:8]:
        d = hit.get('show') or {}
        img = d.get('image') or {}
        if not img or not d.get('summary'):
            continue
        genres = [g.lower().replace('science-fiction', 'sci-fi') for g in d.get('genres') or []]
        moods, intensity = _derive(genres)
        item = {'id': f"live-tvmaze-{d['id']}", 'title': d['name'], 'year': int((d.get('premiered') or '0')[:4] or 0) or None,
                'kind': 'series', 'genres': genres[:4], 'moods': moods, 'intensity': intensity, 'ending': 'unknown',
                'minutes': d.get('averageRuntime'), 'description': clean_text(d.get('summary')), 'tags': genres[:3],
                'tvmaze_id': d['id'], 'poster': img.get('original') or img.get('medium'), 'poster_source': 'TVmaze',
                'external_url': d.get('url'), 'source': 'live-search', 'enriched': True, 'description_source': 'TVmaze'}
        if (d.get('rating') or {}).get('average'):
            item.update(rating=d['rating']['average'], rating_scale=10, rating_source='TVmaze')
        network = (d.get('webChannel') or {}).get('name') or (d.get('network') or {}).get('name')
        if network:
            item['network'] = network
        out.append(item)
    return out


async def discover_live(filters):
    """Fetch extra real titles from public APIs. Returns (items, sources_used)."""
    if offline():
        return [], []
    kinds = filters.get('kinds') or ['movie', 'anime_movie', 'series', 'anime_series', 'book']
    search = (filters.get('search') or '').strip()
    key = ('discover', tuple(sorted(kinds)), tuple(_query_genres(filters)), search.lower(), bool(tmdb_key()))
    cached = _cache_get(key)
    if cached is not None:
        return cached
    jobs, names = [], []
    async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True, headers=HEADERS) as client:
        for kind in kinds:
            if kind in ('anime_movie', 'anime_series'):
                jobs.append(_discover_anilist(client, kind, filters, search)); names.append('AniList')
            elif kind == 'book':
                jobs.append(_discover_openlibrary(client, filters, search)); names.append('Open Library')
            elif tmdb_key():
                jobs.append(_discover_tmdb(client, kind, filters, search)); names.append('TMDB')
            elif kind == 'series' and search:
                jobs.append(_discover_tvmaze(client, search)); names.append('TVmaze')
        results = await asyncio.gather(*jobs, return_exceptions=True)
    items, used = [], []
    q = _norm(search)
    for name, res in zip(names, results):
        if isinstance(res, Exception):
            continue
        res = [x for x in res if x.get('title') and x.get('year')]
        if q:  # keep search hits that actually contain the query (plus the API's top hit)
            res = [x for i, x in enumerate(res) if i == 0 or q in _norm(x['title']) or q in _norm(x.get('author'))]
        items += res
        used.append(name)
    value = (items, sorted(set(used)))
    if used:
        _cache_set(key, value)
    return value

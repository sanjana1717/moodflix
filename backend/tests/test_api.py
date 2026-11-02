from itertools import product

import pytest
from fastapi.testclient import TestClient

from app.catalog import CATALOG
from app.engine import parse_mood, parse_refinement, recommend
from app.main import app

KINDS = ['movie', 'anime_movie', 'series', 'anime_series', 'book']
client = TestClient(app)


def test_catalog_integrity():
    assert {x['kind'] for x in CATALOG} == set(KINDS)
    ids = [x['id'] for x in CATALOG]
    assert len(ids) == len(set(ids))
    for x in CATALOG:
        assert x['title'] and x['year'] and x['description'] and x['moods'] and x['genres']
        assert x['ending'] in ('happy', 'bittersweet', 'twist')
        # Every curated title carries a verified source id for artwork lookup.
        assert x.get('wiki') or x.get('tvmaze_id') or x.get('anilist_id') or x.get('ol_cover'), x['id']
    for k in KINDS:
        assert sum(1 for x in CATALOG if x['kind'] == k) >= 12, k


@pytest.mark.parametrize('kind,ending,duration', list(product(KINDS + [None], ['any', 'happy', 'bittersweet', 'twist'], ['any', 'short', 'medium'])))
def test_no_quiz_combination_is_empty(kind, ending, duration):
    """Regression: 18 of 72 quiz combos used to return zero titles."""
    for moods in (['cozy'], ['sad', 'existential'], ['romantic', 'chaotic', 'mystery']):
        results, relaxed = recommend({'moods': moods, 'kinds': [kind] if kind else [], 'ending': ending, 'duration': duration})
        assert len(results) >= 6, (kind, ending, duration, moods)
        assert all(not kind or x['kind'] == kind for x in results)


def test_relaxed_picks_are_penalised_and_reported():
    results, relaxed = recommend({'moods': ['cozy'], 'kinds': ['movie'], 'duration': 'short', 'ending': 'twist'})
    assert relaxed  # nothing satisfies both, so something was relaxed and reported
    eff = [x['match'] - 15 * len(x['misses']) for x in results]
    assert eff == sorted(eff, reverse=True)


def test_romance_ranked():
    results, _ = recommend({'moods': ['romantic'], 'kinds': ['movie'], 'intensity': 45})
    assert results[0]['kind'] == 'movie' and 'romantic' in results[0]['moods']


def test_exclusion_is_hard():
    r, _ = recommend({'kinds': ['book'], 'ending': 'happy', 'exclude': ['book-pride-prejudice']})
    assert all(x['kind'] == 'book' and x['id'] != 'book-pride-prejudice' for x in r)


def test_unknown_kind_returns_empty():
    assert recommend({'kinds': ['not_a_kind']})[0] == []


def test_mood_parsing():
    assert 'romantic' in parse_mood('Need romance and comfort')
    assert 'cozy' in parse_mood('Need romance and comfort')


def test_refinement_more_less_skip_similar():
    base = {'moods': ['sad', 'cozy'], 'intensity': 60, 'kinds': ['movie']}
    f, notes = parse_refinement('Something more romantic', base)
    assert f['moods'][0] == 'romantic' and 'cozy' in f['moods']
    f, notes = parse_refinement('Less sad, please', base)
    assert 'sad' not in f['moods'] and 'sad' in f['avoid_moods'] and f['intensity'] < 60
    f, notes = parse_refinement("I've already watched this", base, focus_id='movie-about-time')
    assert 'movie-about-time' in f['exclude'] and f['kinds'] == ['movie']
    f, notes = parse_refinement('Recommend something similar', base, focus_id='movie-about-time')
    assert f['similar_to'] == 'movie-about-time'
    f, _ = parse_refinement('only anime please', base)
    assert set(f['kinds']) == {'anime_movie', 'anime_series'}


def test_avoided_mood_pushed_down():
    r, _ = recommend({'moods': ['cozy'], 'avoid_moods': ['sad'], 'kinds': ['anime_movie']})
    assert 'sad' not in r[0]['moods']


def test_similar_excludes_reference_and_shares_genre():
    r, _ = recommend({'moods': ['cozy'], 'similar_to': 'movie-knives-out'})
    assert r[0]['id'] != 'movie-knives-out'
    assert set(r[0]['genres']) & {'mystery', 'comedy', 'thriller'}


def test_api_recommend_shape_offline():
    r = client.post('/api/recommend', json={'moods': ['cozy'], 'kinds': ['movie'], 'duration': 'short'})
    assert r.status_code == 200
    d = r.json()
    assert d['status'] in ('ok', 'relaxed') and d['count'] >= 6
    item = d['items'][0]
    for key in ('id', 'title', 'year', 'genres', 'description', 'why', 'match'):
        assert item[key]
    assert len(d['trace']) == 4


def test_api_books_have_real_cover_urls_offline():
    d = client.post('/api/recommend', json={'kinds': ['book'], 'moods': ['cozy']}).json()
    assert all(x['poster'].startswith('https://covers.openlibrary.org/b/id/') for x in d['items'])


def test_api_no_match_status():
    d = client.post('/api/recommend', json={'search': 'zzzz-not-a-title'}).json()
    assert d['status'] == 'no_match' and d['items'] == []


def test_api_validation_rejects_bad_ending():
    assert client.post('/api/recommend', json={'ending': 'explode'}).status_code == 422


def test_chat_refinement_round_trip():
    first = client.post('/api/chat', json={'message': 'I want a cozy romance movie'}).json()
    assert first['items'] and first['reply'] and 'romantic' in first['filters']['moods']
    lead = first['items'][0]['id']
    second = client.post('/api/chat', json={**first['filters'], 'message': "I've already watched this", 'focus_id': lead}).json()
    assert lead not in [x['id'] for x in second['items']]
    assert lead in second['filters']['exclude']
    third = client.post('/api/chat', json={**second['filters'], 'message': 'less sad please'}).json()
    assert 'sad' in third['filters']['avoid_moods']
    assert lead not in [x['id'] for x in third['items']]  # rejected titles never return


def test_cors_allows_localhost_variants():
    for origin in ('http://localhost:3000', 'http://127.0.0.1:3000', 'http://localhost:3001'):
        r = client.options('/api/recommend', headers={'Origin': origin, 'Access-Control-Request-Method': 'POST'})
        assert r.headers.get('access-control-allow-origin') == origin


def test_refresh_surfaces_new_titles():
    first, _ = recommend({'moods': ['cozy', 'romantic'], 'kinds': ['movie'], 'duration': 'short', 'ending': 'happy', 'limit': 10})
    shown = [x['id'] for x in first]
    second, _ = recommend({'moods': ['cozy', 'romantic'], 'kinds': ['movie'], 'duration': 'short', 'ending': 'happy', 'limit': 10, 'seen': shown, 'shuffle': True})
    assert second[0]['id'] not in shown
    assert len([x for x in second if x['id'] not in shown]) >= 5


def test_search_ranks_title_matches_first():
    r, _ = recommend({'search': 'gone girl'})
    assert r and all(x['title'] == 'Gone Girl' for x in r[:2])


def test_gen_z_slang_and_rejection():
    f, _ = parse_refinement('I am so down bad rn', {'moods': []})
    assert f['moods'] == ['romantic']
    f, _ = parse_refinement('villain era vibes only', {'moods': []})
    assert 'chaotic' in f['moods']
    f, notes = parse_refinement('nah', {'moods': ['cozy']}, focus_id='movie-about-time')
    assert 'movie-about-time' in f['exclude'] and 'skip' in notes


def test_chat_reply_has_bestie_voice_and_ignores_ui_vibes():
    d = client.post('/api/chat', json={'message': 'less sad please', 'moods': ['sad'], 'vibes': ['heartbreak-era']}).json()
    assert d['reply'].startswith('Girl, not another heartbreak movie')

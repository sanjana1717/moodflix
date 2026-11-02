"""LangGraph orchestration: mood_agent -> discovery_agent -> ranking_agent -> explanation_agent.

Runs fully without API keys (deterministic heuristics + curated catalog). With
OPENAI_API_KEY set, the mood agent uses an LLM for nuanced free-text intent; any LLM
failure silently falls back to the deterministic parser.
"""
import json
import os
from typing import TypedDict

from .catalog import BY_ID, CATALOG, MOODS
from .engine import dedupe_against, parse_refinement, recommend
from .integrations import discover_live, enrich_many

KIND_LABEL = {'movie': 'movie', 'anime_movie': 'anime film', 'series': 'series', 'anime_series': 'anime series', 'book': 'book'}
MOOD_LABEL = {'main-character': 'main-character', 'existential': 'reflective', 'excited': 'high-energy',
              'chaotic': 'chaotic', 'motivated': 'motivating', 'relaxed': 'easygoing'}
LIVE_TARGET = 8


class AgentState(TypedDict, total=False):
    message: str
    filters: dict
    notes: list
    candidates: list
    results: list
    relaxed: list
    sources: list
    trace: list


async def _llm_intent(message, filters):
    """Optional: structured intent extraction with OpenAI. Returns a partial filter dict."""
    from openai import AsyncOpenAI
    client = AsyncOpenAI()
    system = ('You convert an entertainment request into JSON. Keys (all optional): '
              f'"moods": up to 3 of {MOODS} describing the desired feel of the title; '
              '"avoid_moods": moods the user wants less of; '
              '"kinds": subset of ["movie","anime_movie","series","anime_series","book"]; '
              '"intensity": 0-100 emotional intensity; "ending": one of any|happy|bittersweet|twist; '
              '"duration": any|short|medium; "skip_current": true if they already watched/read the current pick '
              'or reject it; "similar": true if they want something similar to the current pick. '
              'Users often write Gen Z slang: "heartbreak era"/"emotionally damaged" = sad, "down bad"/"delulu" = romantic, '
              '"villain era" = chaotic, "cozy potato" = cozy, "just vibing" = relaxed, "nah"/"hard pass" = skip_current. '
              'Only include keys the user implied. No commentary.')
    resp = await client.chat.completions.create(
        model=os.getenv('OPENAI_MODEL', 'gpt-4o-mini'), temperature=0, response_format={'type': 'json_object'},
        messages=[{'role': 'system', 'content': system},
                  {'role': 'user', 'content': f'Current filters: {json.dumps({k: filters.get(k) for k in ("moods", "kinds", "intensity", "ending")})}\nRequest: {message}'}],
        timeout=8)
    return json.loads(resp.choices[0].message.content or '{}')


async def mood_agent(state: AgentState):
    filters = dict(state.get('filters') or {})
    msg = (state.get('message') or '').strip()
    notes = []
    trace = list(state.get('trace') or [])
    if msg:
        focus = filters.get('focus_id')
        filters, notes = parse_refinement(msg, filters, focus)
        method = 'rules'
        if os.getenv('OPENAI_API_KEY'):
            try:
                intent = await _llm_intent(msg, filters)
                valid = set(MOODS)
                if [m for m in intent.get('moods') or [] if m in valid]:
                    filters['moods'] = [m for m in intent['moods'] if m in valid][:3]
                if intent.get('avoid_moods'):
                    filters['avoid_moods'] = list(dict.fromkeys((filters.get('avoid_moods') or []) + [m for m in intent['avoid_moods'] if m in valid]))
                    filters['moods'] = [m for m in filters['moods'] if m not in filters['avoid_moods']] or filters['moods']
                kinds = [k for k in intent.get('kinds') or [] if k in KIND_LABEL]
                if kinds:
                    filters['kinds'] = kinds
                if isinstance(intent.get('intensity'), (int, float)):
                    filters['intensity'] = max(0, min(100, int(intent['intensity'])))
                if intent.get('ending') in ('any', 'happy', 'bittersweet', 'twist'):
                    filters['ending'] = intent['ending']
                if intent.get('duration') in ('any', 'short', 'medium'):
                    filters['duration'] = intent['duration']
                if intent.get('skip_current') and focus and focus not in filters['exclude']:
                    filters['exclude'].append(focus)
                    notes.append('skip')
                if intent.get('similar') and focus:
                    filters['similar_to'] = focus
                    notes.append('similar')
                method = 'LLM'
            except Exception:
                pass
        if 'fresh' in notes:
            filters['seen'] = list(dict.fromkeys((filters.get('seen') or []) + (filters.get('shown') or [])))
        trace.append(f"mood_agent: read message via {method} -> moods {filters.get('moods')}"
                     + (f", avoiding {filters['avoid_moods']}" if filters.get('avoid_moods') else ''))
    else:
        if not filters.get('moods') and not filters.get('search'):
            filters['moods'] = []
        trace.append(f"mood_agent: quiz moods {filters.get('moods') or 'none (neutral ranking)'}")
    return {'filters': filters, 'notes': notes, 'trace': trace}


async def discovery_agent(state: AgentState):
    filters = state['filters']
    kinds = filters.get('kinds') or []
    curated = [x for x in CATALOG if not kinds or x['kind'] in kinds]
    trace = list(state['trace'])
    # Decide whether the curated pool is enough for this request.
    strict, _ = recommend({**filters, 'limit': 30}, curated)
    strict_count = sum(1 for x in strict if not x['misses'])
    live, sources = [], []
    if filters.get('search') or filters.get('browse') or strict_count < LIVE_TARGET:
        live, sources = await discover_live(filters)
        live = dedupe_against(live, curated)
    excluded = set(filters.get('exclude') or [])
    live = [x for x in live if x['id'] not in excluded]
    trace.append(f"discovery_agent: {len(curated)} curated + {len(live)} live candidates"
                 + (f" from {', '.join(sources)}" if sources else ' (offline catalog)'))
    return {'candidates': curated + live, 'sources': sources, 'trace': trace}


async def ranking_agent(state: AgentState):
    filters = state['filters']
    candidates = state['candidates']
    if filters.get('similar_to') and filters['similar_to'] not in {x['id'] for x in candidates}:
        ref = BY_ID.get(filters['similar_to'])
        if ref:
            candidates = candidates + [ref]
    results, relaxed = recommend(filters, candidates)
    msg = f'ranking_agent: ranked {len(results)} titles'
    if relaxed:
        msg += f" (relaxed {', '.join(relaxed)} to avoid an empty list)"
    return {'results': results, 'relaxed': relaxed, 'trace': state['trace'] + [msg]}


def _intensity_word(v):
    return 'gentle' if v < 30 else 'medium' if v < 65 else 'high'


def explain(item, filters, reference=None):
    """Short, spoiler-free, specific reason. Uses only tags/genres/moods, never plot."""
    moods = item.get('mood_matches') or []
    genres = item.get('genre_matches') or []
    parts = []
    if reference:
        shared = [g for g in item['genres'] if g in reference['genres']][:2]
        parts.append(f"Shares the {' and '.join(shared) or 'tone'} of {reference['title']}")
    elif moods:
        parts.append('Fits your ' + ' + '.join(MOOD_LABEL.get(m, m) for m in moods[:2]) + ' mood')
    elif filters.get('moods'):
        parts.append(f"A {', '.join(item.get('tags', [])[:2]) or 'well-loved'} pick that leans "
                     + ' / '.join(MOOD_LABEL.get(m, m) for m in item['moods'][:2]))
    else:
        parts.append(f"A {', '.join(item.get('tags', [])[:2]) or 'well-loved'} {KIND_LABEL[item['kind']]}")
    if genres:
        parts[-1] += f" with the {' and '.join(genres[:2])} you asked for"
    lead = parts[0] + '.'
    detail = [f"{_intensity_word(item.get('intensity', 50)).capitalize()} emotional intensity"]
    if item.get('ending') not in (None, 'unknown') and filters.get('ending') == item.get('ending'):
        detail.append(f"{item['ending']} ending, as requested")
    if item.get('tags') and (moods or reference):
        detail.append(f"expect something {', '.join(item['tags'][:2])}")
    why = lead + ' ' + '; '.join(detail) + '.'
    if item.get('misses'):
        label = {'duration': 'a bit longer than your time limit', 'ending': 'a different kind of ending',
                 'genres': 'outside your chosen genres'}
        why += ' Note: ' + ', '.join(label[m] for m in item['misses']) + '.'
    return why


async def explanation_agent(state: AgentState):
    filters = state['filters']
    reference = BY_ID.get(filters.get('similar_to') or '')
    limit = min(30, max(1, int(filters.get('limit', 12))))
    top = state['results'][:limit]
    for x in top:
        x['why'] = explain(x, filters, reference)
    enriched = await enrich_many(top)
    with_poster = sum(1 for x in enriched if x.get('poster'))
    for x in enriched:
        for k in ('mood_matches', 'genre_matches', 'enriched'):
            x.pop(k, None)
    return {'results': enriched,
            'trace': state['trace'] + [f'explanation_agent: wrote spoiler-free reasons; {with_poster}/{len(enriched)} have verified artwork']}


try:
    from langgraph.graph import END, START, StateGraph

    _graph = StateGraph(AgentState)
    for _name, _fn in [('mood_agent', mood_agent), ('discovery_agent', discovery_agent),
                       ('ranking_agent', ranking_agent), ('explanation_agent', explanation_agent)]:
        _graph.add_node(_name, _fn)
    _graph.add_edge(START, 'mood_agent')
    _graph.add_edge('mood_agent', 'discovery_agent')
    _graph.add_edge('discovery_agent', 'ranking_agent')
    _graph.add_edge('ranking_agent', 'explanation_agent')
    _graph.add_edge('explanation_agent', END)
    workflow = _graph.compile()
except ImportError:  # pragma: no cover - langgraph is in requirements
    workflow = None


async def run_agents(message, filters):
    state = {'message': message, 'filters': filters, 'trace': [], 'notes': [], 'relaxed': [], 'sources': []}
    if workflow:
        return await workflow.ainvoke(state)
    for fn in (mood_agent, discovery_agent, ranking_agent, explanation_agent):
        state.update(await fn(state))
    return state

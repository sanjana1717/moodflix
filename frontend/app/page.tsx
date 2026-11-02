'use client';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import {
  AlertCircle, ArrowRight, BookOpen, Bookmark, Clapperboard, Film, Menu, RefreshCw, Search, Shuffle, SlidersHorizontal, Tv, X,
} from 'lucide-react';
import { ApiError, recommend, type Filters, type Item, type RecommendResponse, type RequestBody } from '../lib/api';
import { DEFAULT_FILTERS, KIND_LABEL, MOOD_LABEL, VIBES, VIBE_BY_ID, loadCollection, saveCollection, vibeMoods } from '../lib/ui';
import { FeaturedCard, PosterCard } from '../components/cards';
import { Poster, SkeletonFeatured, SkeletonGrid, Sparkle } from '../components/bits';
import DetailModal from '../components/DetailModal';
import Quiz from '../components/Quiz';
import Chat from '../components/Chat';

type View = 'home' | 'discover' | 'quiz' | 'results' | 'movies' | 'anime' | 'series' | 'books' | 'collection';
type Category = 'movies' | 'anime' | 'series' | 'books';
const VIEWS: View[] = ['home', 'discover', 'quiz', 'results', 'movies', 'anime', 'series', 'books', 'collection'];
const CATEGORY: Record<Category, { kinds: string[]; title: string; blurb: string; icon: typeof Film; tone: string }> = {
  movies: { kinds: ['movie'], title: 'Movies', blurb: 'Comfort classics, unhinged thrillers and romance that ruins you.', icon: Film, tone: 'pink' },
  anime: { kinds: ['anime_movie', 'anime_series'], title: 'Anime', blurb: 'From soft slice-of-life to “wait, what just happened” mind-benders.', icon: Clapperboard, tone: 'lavender' },
  series: { kinds: ['series'], title: 'Series', blurb: 'Bingeable, rewatchable, fall-asleep-to-able. Your comfort show era.', icon: Tv, tone: 'matcha' },
  books: { kinds: ['book'], title: 'Books', blurb: 'BookTok-approved feels, with real covers and reader ratings.', icon: BookOpen, tone: 'butter' },
};
const NAV: { id: View; label: string }[] = [
  { id: 'home', label: 'Home' }, { id: 'discover', label: 'Discover' }, { id: 'quiz', label: 'Vibe Check' },
  { id: 'movies', label: 'Movies' }, { id: 'anime', label: 'Anime' }, { id: 'series', label: 'Series' }, { id: 'books', label: 'Books' },
];
const RELAX_LABEL: Record<string, string> = { duration: 'time limit', ending: 'ending', genres: 'genre' };

type Req = { phase: 'idle' | 'loading' | 'ok' | 'empty' | 'error'; data?: RecommendResponse; error?: string; body?: RequestBody };

function useRequest() {
  const [state, setState] = useState<Req>({ phase: 'idle' });
  const ctrl = useRef<AbortController | null>(null);
  const run = useCallback(async (body: RequestBody) => {
    ctrl.current?.abort();
    const c = new AbortController();
    ctrl.current = c;
    setState(prev => ({ phase: 'loading', data: prev.data, body }));
    try {
      const data = await recommend(body, c.signal);
      if (c.signal.aborted) return;
      setState({ phase: data.items.length ? 'ok' : 'empty', data, body });
      return data;
    } catch (e) {
      if (c.signal.aborted) return;
      setState({ phase: 'error', body, error: e instanceof ApiError ? e.message : 'Something broke while loading your picks.' });
    }
  }, []);
  const set = useCallback((data: RecommendResponse, body: RequestBody) => setState({ phase: data.items.length ? 'ok' : 'empty', data, body }), []);
  return [state, run, set] as const;
}

function ErrorPanel({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="statePanel error" role="alert">
      <AlertCircle size={22} />
      <div>
        <h3>Okay this is awkward 😬 the picks didn&apos;t load</h3>
        <p>{message}</p>
        <p className="muted small">Start the API with <code>uvicorn app.main:app --reload --port 8000</code> inside <code>backend/</code>, then retry.</p>
      </div>
      <button className="btn btnPrimary" onClick={onRetry}><RefreshCw size={16} /> Try again</button>
    </div>
  );
}

function EmptyPanel({ title, text, children }: { title: string; text: string; children?: React.ReactNode }) {
  return (
    <div className="statePanel empty">
      <Sparkle size={20} />
      <div><h3>{title}</h3><p>{text}</p></div>
      {children}
    </div>
  );
}

export default function Home() {
  const [view, setView] = useState<View>('home');
  const [menuOpen, setMenuOpen] = useState(false);
  const [filters, setFilters] = useState<Filters>(DEFAULT_FILTERS);
  const [collection, setCollection] = useState<Item[]>([]);
  const [modal, setModal] = useState<{ item: Item; focus?: 'watch' } | null>(null);
  const [chatOpen, setChatOpen] = useState(false);
  const [quizKey, setQuizKey] = useState(0);

  const [results, runResults, setResults] = useRequest();
  const [browse, runBrowse] = useRequest();
  const [search, runSearch] = useRequest();
  const [hero, runHero] = useRequest();
  const [browseCat, setBrowseCat] = useState<Category | null>(null);
  const [query, setQuery] = useState('');
  const [genre, setGenre] = useState('all');
  const [sort, setSort] = useState<'rating' | 'newest' | 'az'>('rating');
  const [animeType, setAnimeType] = useState<'all' | 'anime_movie' | 'anime_series'>('all');
  const [shelf, setShelf] = useState<'all' | Category>('all');

  // ---- routing (hash based so back/forward work)
  const go = useCallback((v: View) => {
    setMenuOpen(false);
    if (typeof window !== 'undefined' && window.location.hash !== `#/${v}`) window.location.hash = `/${v}`;
    setView(v);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }, []);
  useEffect(() => {
    const sync = () => {
      const v = window.location.hash.replace('#/', '') as View;
      setView(VIEWS.includes(v) ? v : 'home');
    };
    sync();
    window.addEventListener('hashchange', sync);
    return () => window.removeEventListener('hashchange', sync);
  }, []);

  useEffect(() => { setCollection(loadCollection()); runHero({ moods: ['cozy', 'romantic'], limit: 6 }); }, [runHero]);

  // ---- browse pages fetch on entry
  useEffect(() => {
    if (!(view in CATEGORY)) return;
    const cat = view as Category;
    if (browseCat === cat && browse.phase !== 'error') return;
    setBrowseCat(cat);
    setGenre('all');
    setQuery('');
    setAnimeType('all');
    runBrowse({ kinds: CATEGORY[cat].kinds, browse: true, limit: 30, moods: [] });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [view]);

  const savedIds = useMemo(() => new Set(collection.map(x => x.id)), [collection]);
  const toggleSave = useCallback((item: Item) => {
    setCollection(old => {
      const next = old.some(x => x.id === item.id) ? old.filter(x => x.id !== item.id) : [{ ...item }, ...old];
      saveCollection(next);
      return next;
    });
  }, []);

  // ---- recommendation actions
  const runQuiz = useCallback((extra: RequestBody = {}) => {
    const body = { ...filters, ...extra, limit: 12 };
    go('results');
    return runResults(body);
  }, [filters, go, runResults]);

  const quickMood = (vibe: string) => {
    const next = { ...DEFAULT_FILTERS, vibes: [vibe], moods: vibeMoods([vibe]) };
    setFilters(next);
    go('results');
    runResults({ ...next, limit: 12 });
  };

  const surprise = () => {
    const vibes = VIBES.map(v => v.id).sort(() => Math.random() - .5).slice(0, 2);
    const next = { ...DEFAULT_FILTERS, vibes, moods: vibeMoods(vibes) };
    setFilters(next);
    go('results');
    runResults({ ...next, shuffle: true, limit: 12 });
  };

  const refresh = () => {
    if (!results.body) return;
    const shown = results.data?.items.map(x => x.id) || [];
    runResults({ ...results.body, ...(results.data?.filters || {}), seen: [...new Set([...(results.body.seen || []), ...shown])], shuffle: true });
  };

  const similar = (item: Item) => {
    setModal(null);
    go('results');
    const base = results.data?.filters || filters;
    runResults({ ...base, moods: base.moods?.length ? base.moods : item.moods.slice(0, 2), kinds: [item.kind], similar_to: item.id, exclude: base.exclude || [], limit: 12 });
  };

  const skip = (item: Item) => {
    setModal(null);
    const ex = [...new Set([...(filters.exclude || []), item.id])];
    setFilters(f => ({ ...f, exclude: ex }));
    if (view === 'results' && results.body) runResults({ ...results.body, exclude: ex });
  };

  const items = results.data?.items || [];
  const featured = items[0];
  const rest = items.slice(1, 11);
  const active = results.data?.filters || filters;
  // Show the vibes the user picked, as long as the backend still ranks on the same moods
  // (a chat refinement can change the moods, then we fall back to plain mood chips).
  const activeVibes = (results.body?.vibes || []).filter(v => VIBE_BY_ID[v]);
  const vibesStillApply = activeVibes.length > 0 && vibeMoods(activeVibes).join() === (active.moods || []).join();

  // ---- browse derived list
  const browseItems = useMemo(() => {
    let list = browse.data?.items || [];
    if (browseCat === 'anime' && animeType !== 'all') list = list.filter(x => x.kind === animeType);
    if (genre !== 'all') list = list.filter(x => x.genres.includes(genre));
    const q = query.trim().toLowerCase();
    if (q) list = list.filter(x => x.title.toLowerCase().includes(q) || (x.author || '').toLowerCase().includes(q));
    const sorted = [...list];
    if (sort === 'rating') sorted.sort((a, b) => ((b.rating ?? -1) / (b.rating_scale || 10)) - ((a.rating ?? -1) / (a.rating_scale || 10)));
    if (sort === 'newest') sorted.sort((a, b) => (b.year || 0) - (a.year || 0));
    if (sort === 'az') sorted.sort((a, b) => a.title.localeCompare(b.title));
    return sorted;
  }, [browse.data, browseCat, animeType, genre, query, sort]);
  const browseGenres = useMemo(() => {
    const count: Record<string, number> = {};
    (browse.data?.items || []).forEach(x => x.genres.forEach(g => { count[g] = (count[g] || 0) + 1; }));
    return Object.entries(count).sort((a, b) => b[1] - a[1]).slice(0, 9).map(([g]) => g);
  }, [browse.data]);

  const shelfItems = shelf === 'all' ? collection : collection.filter(x => CATEGORY[shelf].kinds.includes(x.kind));
  const cardProps = { onSave: toggleSave, onOpen: (item: Item, focus?: 'watch') => setModal({ item, focus }) };

  return (
    <div className="shell">
      <header className="nav">
        <div className="navInner">
          <button className="logo" onClick={() => go('home')} aria-label="MOODFLIX home">
            <span className="logoChrome">MOODFLIX</span><Sparkle size={13} className="logoStar" />
          </button>
          <nav className={'links ' + (menuOpen ? 'open' : '')} aria-label="Main">
            {NAV.map(n => (
              <button key={n.id} className={view === n.id ? 'active' : ''} aria-current={view === n.id ? 'page' : undefined}
                onClick={() => { if (n.id === 'quiz') setQuizKey(k => k + 1); go(n.id); }}>{n.label}</button>
            ))}
            <button className={'collectionLink ' + (view === 'collection' ? 'active' : '')} onClick={() => go('collection')}>
              <Bookmark size={15} /> My Stash {collection.length > 0 && <span className="badge">{collection.length}</span>}
            </button>
          </nav>
          <button className="iconBtn menuBtn" onClick={() => setMenuOpen(o => !o)} aria-label={menuOpen ? 'Close menu' : 'Open menu'} aria-expanded={menuOpen}>
            {menuOpen ? <X size={22} /> : <Menu size={22} />}
          </button>
        </div>
      </header>

      <main>
        <AnimatePresence mode="wait">
          <motion.div key={view} initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: .18 }}>

            {view === 'home' && (
              <>
                <section className="hero">
                  <div className="heroText">
                    <span className="eyebrow"><Sparkle size={11} /> Movies · Anime · Series · Books</span>
                    <h1>What&apos;s your emotional damage <em>today?</em></h1>
                    <p className="lead">Spill the vibe and we&apos;ll find your next obsession. Four tiny AI agents read your mood, dig through real catalogs, rank the best fits and tell you why. No spoilers, pinky promise. 🤞</p>
                    <div className="heroCtas">
                      <button className="btn btnPrimary btnLg" onClick={() => { setQuizKey(k => k + 1); go('quiz'); }}>Take the vibe check <ArrowRight size={18} /></button>
                      <button className="btn btnGhost btnLg" onClick={surprise}><Shuffle size={17} /> Chaos mode 🎲</button>
                    </div>
                    <div className="quickMoods">
                      <span className="muted small">Pick your poison:</span>
                      {VIBES.slice(0, 6).map(m => <button key={m.id} className={`moodChip tone-${m.tone}`} onClick={() => quickMood(m.id)}><span aria-hidden="true">{m.emoji}</span>{m.label}</button>)}
                    </div>
                  </div>
                  <div className="heroArt" aria-hidden={hero.phase !== 'ok'}>
                    <div className="heroWindow">
                      <div className="winBar"><span className="dots"><i /><i /><i /></span><span>tonight_vibe.exe</span></div>
                      <div className="stack">
                        {(hero.data?.items || []).filter(x => x.poster).slice(0, 3).map((x, i) => (
                          <button key={x.id} className={`stackCard s${i}`} onClick={() => setModal({ item: x })} tabIndex={-1}>
                            <Poster item={x} />
                          </button>
                        ))}
                        {hero.phase !== 'ok' && [0, 1, 2].map(i => <div key={i} className={`stackCard s${i} placeholder tone-${['pink', 'lavender', 'butter'][i]}`} />)}
                      </div>
                      <div className="heroSticker"><Sparkle size={11} /> cozy potato + delulu 💘</div>
                    </div>
                    <span className="sticker st1" aria-hidden="true">🍿</span>
                    <span className="sticker st2" aria-hidden="true">💖</span>
                    <span className="sticker st3" aria-hidden="true">⭐</span>
                  </div>
                </section>

                <section className="section">
                  <div className="sectionHead"><h2>Choose your <em>fighter</em></h2></div>
                  <div className="catGrid">
                    {(Object.keys(CATEGORY) as Category[]).map(c => {
                      const C = CATEGORY[c];
                      return (
                        <button key={c} className={`catTile tone-${C.tone}`} onClick={() => go(c)}>
                          <C.icon size={22} strokeWidth={1.6} />
                          <strong>{C.title}</strong>
                          <small>{C.blurb}</small>
                          <span className="catGo">Let&apos;s go <ArrowRight size={14} /></span>
                        </button>
                      );
                    })}
                  </div>
                </section>

                <section className="section how">
                  <div className="sectionHead"><h2>How the <em>magic</em> works</h2><p className="muted">A tiny LangGraph pipeline. No gatekeeping, fully transparent.</p></div>
                  <ol className="steps">
                    {[
                      ['The vibe reader 🔮', 'Decodes your vibe check or messages like “less sad, more down bad”.'],
                      ['The digger 🕵️', 'Hunts through a curated catalog plus TMDB, AniList and Open Library.'],
                      ['The judge ⚖️', 'Scores mood, genre, intensity and time. Only bends a rule when it has to, and tells you.'],
                      ['The hype friend 📣', 'Writes a short, spoiler-free reason for every pick and adds real artwork.'],
                    ].map(([t, d], i) => (
                      <li key={t}><span className="stepNum">0{i + 1}</span><h3>{t}</h3><p>{d}</p></li>
                    ))}
                  </ol>
                </section>
              </>
            )}

            {view === 'quiz' && (
              <Quiz key={quizKey} filters={filters} setFilters={setFilters} loading={results.phase === 'loading'}
                onCancel={() => go('home')} onSubmit={() => runQuiz({ similar_to: null, seen: [] })} />
            )}

            {view === 'results' && (
              <section className="page results">
                {results.phase === 'idle' && (
                  <EmptyPanel title="No picks yet, bestie" text="Take the vibe check or tap a mood and we'll serve.">
                    <button className="btn btnPrimary" onClick={() => go('quiz')}>Take the vibe check <ArrowRight size={16} /></button>
                  </EmptyPanel>
                )}
                {results.phase === 'loading' && (
                  <>
                    <div className="resultsHead"><div><span className="eyebrow"><Sparkle size={11} /> Cooking 🍳</span><h2 className="pageTitle">Reading your aura<span className="dotsLoad" aria-hidden="true">…</span></h2></div></div>
                    <SkeletonFeatured />
                    <SkeletonGrid count={8} />
                  </>
                )}
                {results.phase === 'error' && <ErrorPanel message={results.error || ''} onRetry={() => results.body && runResults(results.body)} />}
                {results.phase === 'empty' && (
                  <EmptyPanel title="Not a single match. Iconic, honestly 💀" text="Everything here was skipped or didn’t fit. Clear your skips or open it up to every format.">
                    <div className="actions">
                      <button className="btn btnPrimary" onClick={() => runResults({ ...(results.body || {}), exclude: [], seen: [], kinds: [], search: '' })}>Show me everything</button>
                      <button className="btn btnGhost" onClick={() => go('quiz')}>Redo vibe check</button>
                    </div>
                  </EmptyPanel>
                )}
                {results.phase === 'ok' && featured && (
                  <>
                    <div className="resultsHead">
                      <div>
                        <span className="eyebrow"><Sparkle size={11} /> {items.length} picks, freshly served</span>
                        <h2 className="pageTitle">Your next <em>obsession</em> awaits.</h2>
                        <div className="summary">
                          {(active.similar_to && featured) ? <span className="chip strong">Similar to your pick</span> : null}
                          {vibesStillApply
                            ? activeVibes.map(v => <span className="chip strong" key={v}>{VIBE_BY_ID[v].emoji} {VIBE_BY_ID[v].label}</span>)
                            : (active.moods || []).map(m => <span className="chip strong" key={m}>{MOOD_LABEL[m] || m}</span>)}
                          {(active.avoid_moods || []).map(m => <span className="chip" key={m}>less {MOOD_LABEL[m]?.toLowerCase() || m}</span>)}
                          {(active.kinds || []).map(k => <span className="chip" key={k}>{KIND_LABEL[k as keyof typeof KIND_LABEL]}</span>)}
                          {!active.kinds?.length && <span className="chip">All formats</span>}
                        </div>
                      </div>
                      <div className="actions">
                        <button className="btn btnGhost" onClick={() => { setQuizKey(k => k + 1); go('quiz'); }}><SlidersHorizontal size={16} /> Change the vibe</button>
                        <button className="btn btnGhost btnWiggle" onClick={refresh}><RefreshCw size={16} /> Not the vibe? Try again</button>
                      </div>
                    </div>
                    {results.data?.status === 'relaxed' && (
                      <p className="notice">
                        Real talk: not enough titles ticked every box, so we loosened your {results.data.relaxed.map(r => RELAX_LABEL[r] || r).join(' and ')} preference. Picks that miss something will say so. 🫶
                      </p>
                    )}
                    <FeaturedCard item={featured} saved={savedIds.has(featured.id)} {...cardProps} />
                    {rest.length > 0 && (
                      <>
                        <div className="sectionHead tight"><h3>More for this vibe ✨</h3>
                          {results.data?.sources.length ? <span className="muted small">Includes live picks from {results.data.sources.join(', ')}</span> : null}
                        </div>
                        <div className="grid">
                          <AnimatePresence>{rest.map(x => <PosterCard key={x.id} item={x} saved={savedIds.has(x.id)} {...cardProps} />)}</AnimatePresence>
                        </div>
                      </>
                    )}
                  </>
                )}
              </section>
            )}

            {browseCat && view === browseCat && (
              <section className="page browse">
                <div className={`browseHero tone-${CATEGORY[browseCat].tone}`}>
                  <div>
                    <span className="eyebrow"><Sparkle size={11} /> Browse the shelf</span>
                    <h2 className="pageTitle">{CATEGORY[browseCat].title}</h2>
                    <p className="lead">{CATEGORY[browseCat].blurb}</p>
                  </div>
                  <button className="btn btnPrimary" onClick={() => { setFilters(f => ({ ...f, kinds: CATEGORY[browseCat].kinds })); setQuizKey(k => k + 1); go('quiz'); }}>
                    Match {CATEGORY[browseCat].title.toLowerCase()} to my vibe <ArrowRight size={16} />
                  </button>
                </div>
                <div className="toolbar">
                  <label className="searchBox small">
                    <Search size={16} />
                    <input value={query} onChange={e => setQuery(e.target.value)} placeholder={`Filter ${CATEGORY[browseCat].title.toLowerCase()}…`} aria-label="Filter by title" />
                  </label>
                  {browseCat === 'anime' && (
                    <div className="segmented" role="group" aria-label="Anime type">
                      {([['all', 'All'], ['anime_movie', 'Films'], ['anime_series', 'Series']] as const).map(([id, l]) => (
                        <button key={id} className={animeType === id ? 'on' : ''} onClick={() => setAnimeType(id)}>{l}</button>
                      ))}
                    </div>
                  )}
                  <select value={sort} onChange={e => setSort(e.target.value as typeof sort)} aria-label="Sort">
                    <option value="rating">Certified bangers</option><option value="newest">Fresh drops</option><option value="az">A–Z</option>
                  </select>
                </div>
                <div className="pills genreBar">
                  {['all', ...browseGenres].map(g => <button key={g} className={genre === g ? 'on' : ''} onClick={() => setGenre(g)}>{g === 'all' ? 'All genres' : g}</button>)}
                </div>
                {browse.phase === 'loading' && <SkeletonGrid count={10} />}
                {browse.phase === 'error' && <ErrorPanel message={browse.error || ''} onRetry={() => browse.body && runBrowse(browse.body)} />}
                {browse.phase !== 'loading' && browse.phase !== 'error' && (
                  browseItems.length ? (
                    <div className="grid">{browseItems.map(x => <PosterCard key={x.id} item={x} showMatch={false} saved={savedIds.has(x.id)} {...cardProps} />)}</div>
                  ) : (
                    <EmptyPanel title="Nothing here, it's giving empty 🫥" text="Try another genre or clear the title filter.">
                      <button className="btn btnGhost" onClick={() => { setGenre('all'); setQuery(''); }}>Clear filters</button>
                    </EmptyPanel>
                  )
                )}
              </section>
            )}

            {view === 'discover' && (
              <section className="page discover">
                <span className="eyebrow"><Sparkle size={11} /> Discover</span>
                <h2 className="pageTitle">Search anything, <em>or follow the vibes.</em></h2>
                <form className="searchBox big" onSubmit={e => { e.preventDefault(); if (query.trim()) runSearch({ search: query.trim(), limit: 24, moods: [] }); }}>
                  <Search size={20} />
                  <input value={query} onChange={e => setQuery(e.target.value)} placeholder="A title, an author, a genre… go off" aria-label="Search titles" />
                  <button className="btn btnPrimary" disabled={!query.trim() || search.phase === 'loading'}>Find it</button>
                </form>
                <div className="quickMoods">
                  {VIBES.map(m => <button key={m.id} className={`moodChip tone-${m.tone}`} onClick={() => quickMood(m.id)}><span aria-hidden="true">{m.emoji}</span>{m.label}</button>)}
                  <button className="moodChip dashed" onClick={surprise}><Shuffle size={14} /> Chaos mode</button>
                </div>
                {search.phase === 'loading' && <SkeletonGrid count={8} />}
                {search.phase === 'error' && <ErrorPanel message={search.error || ''} onRetry={() => search.body && runSearch(search.body)} />}
                {search.phase === 'empty' && <EmptyPanel title={`Nothing for “${search.body?.search}” 😔`} text="Check the spelling or go broader, like a genre (mystery, romance)." />}
                {search.phase === 'ok' && (
                  <>
                    <div className="sectionHead tight"><h3>Results for “{search.body?.search}”</h3>
                      {search.data?.sources.length ? <span className="muted small">Searched the curated catalog + {search.data.sources.join(', ')}</span> : <span className="muted small">Searched the curated catalog</span>}
                    </div>
                    <div className="grid">{search.data!.items.map(x => <PosterCard key={x.id} item={x} showMatch={false} saved={savedIds.has(x.id)} {...cardProps} />)}</div>
                  </>
                )}
                {search.phase === 'idle' && (
                  <div className="catGrid compact">
                    {(Object.keys(CATEGORY) as Category[]).map(c => {
                      const C = CATEGORY[c];
                      return <button key={c} className={`catTile tone-${C.tone}`} onClick={() => go(c)}><C.icon size={20} strokeWidth={1.6} /><strong>{C.title}</strong><span className="catGo">Browse <ArrowRight size={14} /></span></button>;
                    })}
                  </div>
                )}
              </section>
            )}

            {view === 'collection' && (
              <section className="page">
                <span className="eyebrow"><Sparkle size={11} /> Saved on this device</span>
                <h2 className="pageTitle">My <em>stash</em> 💾</h2>
                {collection.length > 0 && (
                  <div className="segmented" role="group" aria-label="Filter collection">
                    {(['all', 'movies', 'anime', 'series', 'books'] as const).map(s => (
                      <button key={s} className={shelf === s ? 'on' : ''} onClick={() => setShelf(s)}>{s === 'all' ? `All (${collection.length})` : CATEGORY[s].title}</button>
                    ))}
                  </div>
                )}
                {collection.length === 0 ? (
                  <EmptyPanel title="Your stash is looking a little empty" text="Tap the bookmark on anything that slaps and it lands here. It's saved in this browser.">
                    <button className="btn btnPrimary" onClick={() => go('quiz')}>Find my next obsession <ArrowRight size={16} /></button>
                  </EmptyPanel>
                ) : shelfItems.length ? (
                  <div className="grid"><AnimatePresence>{shelfItems.map(x => <PosterCard key={x.id} item={x} showMatch={false} saved {...cardProps} />)}</AnimatePresence></div>
                ) : (
                  <EmptyPanel title="This shelf is lonely" text="You haven’t saved anything in this format yet." />
                )}
              </section>
            )}
          </motion.div>
        </AnimatePresence>
      </main>

      <footer className="footer">
        <div className="footInner">
          <div>
            <span className="logoChrome">MOODFLIX</span>
            <p className="muted small">Artwork and ratings from TMDB, AniList, TVmaze, Wikipedia and Open Library. This product uses the TMDB API but is not endorsed or certified by TMDB.</p>
          </div>
          <div className="footLinks">
            {NAV.slice(1).map(n => <button key={n.id} onClick={() => go(n.id)}>{n.label}</button>)}
          </div>
        </div>
      </footer>

      <AnimatePresence>
        {modal && (
          <DetailModal key={modal.item.id} item={modal.item} focus={modal.focus} saved={savedIds.has(modal.item.id)}
            onClose={() => setModal(null)} onSave={toggleSave} onSimilar={similar} onSkip={skip} />
        )}
      </AnimatePresence>

      <Chat
        open={chatOpen}
        setOpen={setChatOpen}
        context={{ filters: results.data?.filters || filters, focusId: featured?.id, shown: items.map(x => x.id) }}
        onOpenItem={item => setModal({ item })}
        onSeeAll={res => { setResults(res, { ...res.filters, limit: 12 }); go('results'); }}
      />
    </div>
  );
}

import type { Filters, Item, Kind } from './api';

/**
 * Gen Z "vibes" shown in the UI. Each one maps onto the backend's mood ids, so the
 * LangGraph ranking logic is unchanged — a vibe is just a friendlier bundle of moods.
 */
export type Vibe = { id: string; label: string; emoji: string; hint: string; tone: string; moods: string[] };

export const VIBES: Vibe[] = [
  { id: 'heartbreak-era', label: 'Heartbreak Era', emoji: '💔', hint: 'Sad girl autumn, all year round. Tissues on standby.', tone: 'lavender', moods: ['sad', 'romantic'] },
  { id: 'down-bad', label: 'Down Bad', emoji: '🥵', hint: 'Yearning so hard it should be illegal.', tone: 'pink', moods: ['romantic'] },
  { id: 'delulu-romantic', label: 'Delulu Romantic', emoji: '💘', hint: 'Delulu is the solulu. Meet-cutes only.', tone: 'pink', moods: ['romantic', 'happy'] },
  { id: 'main-character', label: 'Main Character Energy', emoji: '💅', hint: 'Slow-mo walk, wind in hair, soundtrack on.', tone: 'butter', moods: ['main-character', 'motivated'] },
  { id: 'villain-era', label: 'Villain Era', emoji: '😈', hint: 'Chaos, schemes and zero apologies.', tone: 'lavender', moods: ['chaotic', 'excited'] },
  { id: 'emotionally-damaged', label: 'Emotionally Damaged', emoji: '🫠', hint: 'Want to feel everything at once? Say less.', tone: 'pink', moods: ['sad', 'existential'] },
  { id: 'cozy-potato', label: 'Cozy Potato', emoji: '🥔', hint: 'Blanket burrito, snacks, zero plot stress.', tone: 'butter', moods: ['cozy', 'relaxed'] },
  { id: 'existential-crisis', label: 'Existential Crisis', emoji: '🌀', hint: 'Mind-benders for when nothing is real anyway.', tone: 'matcha', moods: ['existential', 'mystery'] },
  { id: 'just-vibing', label: 'Just Vibing', emoji: '✌️', hint: 'No thoughts, head empty, good times only.', tone: 'matcha', moods: ['happy', 'relaxed'] },
];

export const VIBE_BY_ID: Record<string, Vibe> = Object.fromEntries(VIBES.map(v => [v.id, v]));

/** Backend moods for a set of vibes (the API accepts at most 3). */
export function vibeMoods(ids: string[]) {
  return [...new Set(ids.flatMap(id => VIBE_BY_ID[id]?.moods || []))].slice(0, 3);
}

/** Labels for the backend's raw mood ids (chips, "Feels:" line, chat refinements). */
export const MOOD_LABEL: Record<string, string> = {
  cozy: 'Cozy', romantic: 'Romantic', happy: 'Feel-good', sad: 'In my feelings', mystery: 'Twisty',
  excited: 'Adrenaline', relaxed: 'Chill', existential: 'Big thoughts', chaotic: 'Chaotic',
  'main-character': 'Main character', motivated: 'Hype',
};

export const KINDS: { id: Kind; label: string; hint: string }[] = [
  { id: 'movie', label: 'Movies', hint: 'Feature films, mostly English-language' },
  { id: 'anime_movie', label: 'Anime films', hint: 'Ghibli, Shinkai and more' },
  { id: 'series', label: 'TV series', hint: 'Bingeable and comfort shows' },
  { id: 'anime_series', label: 'Anime series', hint: 'Episodic, 20-ish minutes' },
  { id: 'book', label: 'Books', hint: 'Novels to get lost in' },
];

export const KIND_LABEL: Record<Kind, string> = {
  movie: 'Movie', anime_movie: 'Anime film', series: 'Series', anime_series: 'Anime series', book: 'Book',
};

export const GENRES = ['romance', 'comedy', 'drama', 'mystery', 'thriller', 'fantasy', 'sci-fi', 'action', 'adventure', 'slice of life'];

export const DEFAULT_FILTERS: Filters = {
  moods: [], avoid_moods: [], kinds: [], genres: [], intensity: 45, ending: 'any', duration: 'any', exclude: [], seen: [], similar_to: null, vibes: [],
};

export function meta(item: Item) {
  const bits: string[] = [KIND_LABEL[item.kind]];
  if (item.year) bits.push(String(item.year));
  if (item.kind === 'book' && item.pages) bits.push(`${item.pages} pages`);
  else if (item.minutes) bits.push(item.kind === 'series' || item.kind === 'anime_series' ? `${item.minutes} min episodes` : `${item.minutes} min`);
  return bits.join(' · ');
}

export function ratingText(item: Item) {
  if (item.rating == null || !item.rating_source) return null;
  return `${item.rating}/${item.rating_scale || 10}`;
}

export function infoLink(item: Item): { url: string; label: string } | null {
  const url = item.external_url || item.wiki_url;
  if (!url) return null;
  const host = url.includes('themoviedb') ? 'TMDB' : url.includes('anilist') ? 'AniList' : url.includes('openlibrary') ? 'Open Library'
    : url.includes('tvmaze') ? 'TVmaze' : url.includes('wikipedia') ? 'Wikipedia' : url.includes('google') ? 'Google Books' : 'source';
  return { url, label: `View on ${host}` };
}

export function justWatchSearch(item: Item) {
  return `https://www.justwatch.com/us/search?q=${encodeURIComponent(item.title)}`;
}

const STORE = 'moodflix-collection-v2';

export function loadCollection(): Item[] {
  try {
    const raw = localStorage.getItem(STORE) ?? localStorage.getItem('moodflix-vault-v1');
    const parsed = JSON.parse(raw || '[]');
    return Array.isArray(parsed) ? parsed.filter(x => x && x.id && x.title) : [];
  } catch {
    return [];
  }
}

export function saveCollection(items: Item[]) {
  try {
    localStorage.setItem(STORE, JSON.stringify(items));
  } catch {
    /* storage unavailable (private mode) – collection lives in memory for this visit */
  }
}

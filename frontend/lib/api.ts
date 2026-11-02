export type Kind = 'movie' | 'anime_movie' | 'series' | 'anime_series' | 'book';

export type Provider = { name: string; type?: string; url?: string | null; logo?: string | null };

export type Item = {
  id: string;
  title: string;
  year?: number | null;
  kind: Kind;
  genres: string[];
  moods: string[];
  intensity: number;
  ending: string;
  minutes?: number | null;
  pages?: number | null;
  author?: string;
  description: string;
  description_source?: string;
  tags: string[];
  match: number;
  why: string;
  misses?: string[];
  poster?: string | null;
  poster_source?: string;
  rating?: number;
  rating_scale?: number;
  rating_source?: string;
  rating_count?: number;
  external_url?: string | null;
  wiki_url?: string | null;
  providers?: Provider[];
  providers_source?: string;
  providers_region?: string;
  network?: string;
  source?: string;
  tmdb_id?: number;
  anilist_id?: number;
};

export type Filters = {
  moods: string[];
  avoid_moods?: string[];
  kinds: string[];
  genres: string[];
  intensity: number;
  ending: string;
  duration: string;
  exclude: string[];
  seen?: string[];
  similar_to?: string | null;
  /** UI-only vibe ids; the API ignores this and ranks on `moods`. */
  vibes?: string[];
};

export type RequestBody = Partial<Filters> & {
  message?: string;
  search?: string;
  browse?: boolean;
  shuffle?: boolean;
  limit?: number;
  focus_id?: string | null;
  shown?: string[];
};

export type RecommendResponse = {
  status: 'ok' | 'relaxed' | 'no_match';
  items: Item[];
  count: number;
  relaxed: string[];
  interpreted_moods: string[];
  filters: Filters;
  sources: string[];
  trace: string[];
  reply?: string;
};

export class ApiError extends Error {
  constructor(public kind: 'network' | 'server' | 'timeout' | 'invalid', message: string) {
    super(message);
  }
}

export const API_BASE = (process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000').replace(/\/$/, '');

const sleep = (ms: number) => new Promise(r => setTimeout(r, ms));

async function post<T>(path: string, body: unknown, { retries = 2, timeoutMs = 25000, signal }: { retries?: number; timeoutMs?: number; signal?: AbortSignal } = {}): Promise<T> {
  let last: ApiError = new ApiError('network', 'Request failed');
  for (let attempt = 0; attempt <= retries; attempt++) {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort('timeout'), timeoutMs);
    const onAbort = () => ctrl.abort('cancelled');
    signal?.addEventListener('abort', onAbort);
    try {
      const r = await fetch(`${API_BASE}${path}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
        signal: ctrl.signal,
      });
      if (r.status === 422) throw new ApiError('invalid', 'The request was not understood by the server.');
      if (r.status >= 500 || r.status === 429) {
        last = new ApiError('server', `The recommendation service returned an error (${r.status}).`);
      } else if (!r.ok) {
        throw new ApiError('server', `Unexpected response (${r.status}).`);
      } else {
        const data = await r.json();
        if (!data || !Array.isArray(data.items)) throw new ApiError('invalid', 'The server sent an unexpected response.');
        return data as T;
      }
    } catch (e) {
      if (signal?.aborted) throw e;
      if (e instanceof ApiError && e.kind !== 'server') throw e;
      if (e instanceof ApiError) last = e;
      else if (ctrl.signal.aborted) last = new ApiError('timeout', 'The recommendation service took too long to respond.');
      else last = new ApiError('network', `Can't reach the MOODFLIX API at ${API_BASE}. Is the backend running?`);
    } finally {
      clearTimeout(timer);
      signal?.removeEventListener('abort', onAbort);
    }
    if (attempt < retries) await sleep(500 * 2 ** attempt);
  }
  throw last;
}

export function recommend(body: RequestBody, signal?: AbortSignal) {
  return post<RecommendResponse>('/api/recommend', body, { signal });
}

export function chat(body: RequestBody, signal?: AbortSignal) {
  return post<RecommendResponse>('/api/chat', body, { signal });
}

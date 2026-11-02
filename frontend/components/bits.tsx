'use client';
import { useState } from 'react';
import { Star } from 'lucide-react';
import type { Item } from '../lib/api';
import { KIND_LABEL, ratingText } from '../lib/ui';

/** Four-point Y2K sparkle, used sparingly as an accent. */
export function Sparkle({ size = 14, className = '' }: { size?: number; className?: string }) {
  return (
    <svg className={'sparkle ' + className} width={size} height={size} viewBox="0 0 24 24" aria-hidden="true">
      <path d="M12 0c.6 6.2 5.8 11.4 12 12-6.2.6-11.4 5.8-12 12-.6-6.2-5.8-11.4-12-12C6.2 11.4 11.4 6.2 12 0z" fill="currentColor" />
    </svg>
  );
}

const TONES: Record<string, string> = {
  movie: 'pink', anime_movie: 'lavender', series: 'matcha', anime_series: 'lavender', book: 'butter',
};

/**
 * Real artwork from TMDB / AniList / TVmaze / Wikipedia / Open Library.
 * When none is available (offline or lookup failed) we show a clearly labelled
 * typographic tile – never a stock or invented image.
 */
export function Poster({ item, size = 'md', priority = false }: { item: Item; size?: 'sm' | 'md' | 'lg'; priority?: boolean }) {
  const [state, setState] = useState<'loading' | 'ok' | 'error'>(item.poster ? 'loading' : 'error');
  const showImg = item.poster && state !== 'error';
  return (
    <div className={`poster poster-${size} tone-${TONES[item.kind] || 'pink'} ${state === 'loading' ? 'is-loading' : ''}`}>
      {showImg ? (
        <img
          src={item.poster!}
          alt={`${item.kind === 'book' ? 'Cover' : 'Poster'} of ${item.title}`}
          loading={priority ? 'eager' : 'lazy'}
          decoding="async"
          referrerPolicy="no-referrer"
          onLoad={() => setState('ok')}
          onError={() => setState('error')}
        />
      ) : (
        <div className="posterFallback">
          <Sparkle size={size === 'lg' ? 22 : 14} />
          <strong>{item.title}</strong>
          <span>{KIND_LABEL[item.kind]}{item.year ? ` · ${item.year}` : ''}</span>
          <small>Artwork unavailable</small>
        </div>
      )}
    </div>
  );
}

export function Rating({ item, compact = false }: { item: Item; compact?: boolean }) {
  const text = ratingText(item);
  if (!text) return null;
  return (
    <span className="rating" title={`${item.rating_source} rating${item.rating_count ? ` from ${item.rating_count.toLocaleString()} ratings` : ''}`}>
      <Star size={13} fill="currentColor" aria-hidden="true" />
      <b>{text}</b>
      {!compact && <span>{item.rating_source}</span>}
    </span>
  );
}

export function MatchScore({ value, large = false }: { value: number; large?: boolean }) {
  const r = large ? 26 : 16;
  const c = 2 * Math.PI * r;
  const box = (r + 4) * 2;
  return (
    <div className={'match ' + (large ? 'matchLarge' : '')} aria-label={`${value}% mood match`}>
      <svg width={box} height={box} viewBox={`0 0 ${box} ${box}`} aria-hidden="true">
        <circle cx={box / 2} cy={box / 2} r={r} className="matchTrack" />
        <circle cx={box / 2} cy={box / 2} r={r} className="matchFill" strokeDasharray={c} strokeDashoffset={c * (1 - value / 100)} />
      </svg>
      <span><b>{value}</b>%</span>
    </div>
  );
}

export function SkeletonGrid({ count = 8 }: { count?: number }) {
  return (
    <div className="grid">
      {Array.from({ length: count }).map((_, i) => (
        <div className="card skeleton" key={i}>
          <div className="poster poster-md shimmer" />
          <div className="skLine w70" />
          <div className="skLine w40" />
        </div>
      ))}
    </div>
  );
}

export function SkeletonFeatured() {
  return (
    <div className="featured skeleton" aria-busy="true" aria-label="Loading recommendations">
      <div className="poster poster-lg shimmer" />
      <div className="featuredBody">
        <div className="skLine w30" />
        <div className="skLine big w70" />
        <div className="skLine w90" />
        <div className="skLine w80" />
        <div className="skLine w60" />
      </div>
    </div>
  );
}

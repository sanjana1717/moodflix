'use client';
import { useEffect, useRef } from 'react';
import { motion } from 'framer-motion';
import { Bookmark, BookmarkCheck, ExternalLink, EyeOff, Sparkles, X } from 'lucide-react';
import type { Item } from '../lib/api';
import { MOOD_LABEL, infoLink, justWatchSearch, meta } from '../lib/ui';
import { MatchScore, Poster, Rating } from './bits';

type Props = {
  item: Item;
  focus?: 'watch';
  saved: boolean;
  onClose: () => void;
  onSave: (item: Item) => void;
  onSimilar?: (item: Item) => void;
  onSkip?: (item: Item) => void;
};

export default function DetailModal({ item, focus, saved, onClose, onSave, onSimilar, onSkip }: Props) {
  const dialog = useRef<HTMLDivElement>(null);
  const watchRef = useRef<HTMLDivElement>(null);
  const isBook = item.kind === 'book';
  const link = infoLink(item);
  const providers = item.providers || [];
  const closeRef = useRef(onClose);
  closeRef.current = onClose;

  useEffect(() => {
    const prev = document.activeElement as HTMLElement | null;
    dialog.current?.focus();
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && closeRef.current();
    document.addEventListener('keydown', onKey);
    document.body.style.overflow = 'hidden';
    if (focus === 'watch') setTimeout(() => watchRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' }), 250);
    return () => {
      document.removeEventListener('keydown', onKey);
      document.body.style.overflow = '';
      prev?.focus();
    };
  }, [item.id, focus]);

  return (
    <motion.div className="overlay" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onMouseDown={e => e.target === e.currentTarget && onClose()}>
      <motion.div
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="detail-title"
        tabIndex={-1}
        ref={dialog}
        initial={{ opacity: 0, y: 24, scale: .98 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        exit={{ opacity: 0, y: 16 }}
      >
        <button className="iconBtn modalClose" onClick={onClose} aria-label="Close details"><X size={20} /></button>
        <div className="modalGrid">
          <div className="modalPoster">
            <Poster item={item} size="lg" priority />
            {item.poster && item.poster_source && <small className="credit">Artwork: {item.poster_source}</small>}
          </div>
          <div className="modalBody">
            <p className="metaLine">{meta(item)}{item.author ? ` · ${item.author}` : ''}</p>
            <h2 id="detail-title">{item.title}</h2>
            <div className="chipRow">
              {item.genres.map(g => <span className="chip" key={g}>{g}</span>)}
            </div>
            <div className="statRow">
              {item.match ? <div className="stat"><MatchScore value={item.match} /><span>Vibe match</span></div> : null}
              {item.rating != null && item.rating_source && (
                <div className="stat"><Rating item={item} /><span>{item.rating_count ? `${item.rating_count.toLocaleString()} ratings` : 'Verified rating'}</span></div>
              )}
              <div className="stat"><b className="statBig">{item.intensity < 30 ? 'Gentle' : item.intensity < 65 ? 'Medium' : 'Intense'}</b><span>Emotional damage level</span></div>
            </div>

            <h3 className="sectionLabel">Premise</h3>
            <p className="synopsis">{item.description}</p>
            {item.description_source && <small className="credit">Synopsis via {item.description_source}, trimmed to avoid spoilers.</small>}

            {item.why && (
              <div className="whyBox">
                <span>Why it&apos;s giving ✨</span>
                <p>{item.why}</p>
              </div>
            )}
            {item.moods?.length > 0 && (
              <p className="moodLine">The vibe: {item.moods.slice(0, 4).map(m => MOOD_LABEL[m] || m).join(', ')}</p>
            )}

            <div className="watchBox" ref={watchRef} id="where-to-watch">
              <h3 className="sectionLabel">{isBook ? 'Where to read' : 'Where to watch'}</h3>
              {providers.length > 0 ? (
                <>
                  <div className="providers">
                    {providers.map(p => (
                      <a key={p.name} className="provider" href={p.url || link?.url || '#'} target="_blank" rel="noreferrer">
                        {p.logo && <img src={p.logo} alt="" width={22} height={22} />}
                        <span>{p.name}</span>
                        {p.type && p.type !== 'Stream' && <small>{p.type}</small>}
                      </a>
                    ))}
                  </div>
                  <small className="credit">
                    Source: {item.providers_source}{item.providers_region ? ` (${item.providers_region})` : ''}. Availability varies by region and changes over time.
                  </small>
                </>
              ) : isBook ? (
                <p className="muted">Find editions, borrowing options and libraries on Open Library.</p>
              ) : (
                <>
                  {item.network && <p className="muted">Originally released on <b>{item.network}</b> (via TVmaze).</p>}
                  <p className="muted">We couldn&apos;t verify where it&apos;s streaming right now, and we don&apos;t do fake news.</p>
                  <a className="textLink" href={justWatchSearch(item)} target="_blank" rel="noreferrer">Search on JustWatch <ExternalLink size={13} /></a>
                </>
              )}
            </div>

            <div className="actions">
              <button className={'btn ' + (saved ? 'btnSaved' : 'btnPrimary')} onClick={() => onSave(item)} aria-pressed={saved}>
                {saved ? <BookmarkCheck size={17} /> : <Bookmark size={17} />} {saved ? 'Stashed 💾' : 'Add to my stash'}
              </button>
              {onSimilar && <button className="btn btnGhost" onClick={() => onSimilar(item)}><Sparkles size={16} /> More like this pls</button>}
              {onSkip && <button className="btn btnGhost" onClick={() => onSkip(item)}><EyeOff size={16} /> {isBook ? 'Already read' : 'Already seen'}</button>}
              {link && <a className="btn btnLink" href={link.url} target="_blank" rel="noreferrer">{link.label} <ExternalLink size={14} /></a>}
            </div>
          </div>
        </div>
      </motion.div>
    </motion.div>
  );
}

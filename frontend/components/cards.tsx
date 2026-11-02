'use client';
import { motion } from 'framer-motion';
import { Bookmark, BookmarkCheck, Info, Tv } from 'lucide-react';
import type { Item } from '../lib/api';
import { KIND_LABEL, meta } from '../lib/ui';
import { MatchScore, Poster, Rating, Sparkle } from './bits';

type CardProps = {
  item: Item;
  saved: boolean;
  onSave: (item: Item) => void;
  onOpen: (item: Item, section?: 'watch') => void;
  showMatch?: boolean;
};

export function FeaturedCard({ item, saved, onSave, onOpen }: CardProps) {
  const isBook = item.kind === 'book';
  return (
    <motion.article className="featured" initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: .4 }}>
      <button className="featuredPoster" onClick={() => onOpen(item)} aria-label={`Open details for ${item.title}`}>
        <Poster key={item.id} item={item} size="lg" priority />
      </button>
      <div className="featuredBody">
        <div className="featuredTop">
          <span className="eyebrow"><Sparkle size={11} /> Top pick 🏆</span>
          <MatchScore value={item.match} large />
        </div>
        <h3 className="featuredTitle">{item.title}</h3>
        <p className="metaLine">{meta(item)}{item.author ? ` · ${item.author}` : ''}</p>
        <div className="chipRow">
          {item.genres.slice(0, 4).map(g => <span className="chip" key={g}>{g}</span>)}
          <Rating item={item} />
        </div>
        <p className="synopsis">{item.description}</p>
        <div className="whyBox">
          <span>Why it&apos;s giving ✨</span>
          <p>{item.why}</p>
        </div>
        <div className="actions">
          <button className={'btn ' + (saved ? 'btnSaved' : 'btnPrimary')} onClick={() => onSave(item)} aria-pressed={saved}>
            {saved ? <BookmarkCheck size={17} /> : <Bookmark size={17} />} {saved ? 'Stashed 💾' : 'Save'}
          </button>
          <button className="btn btnGhost" onClick={() => onOpen(item)}><Info size={17} /> Spill the details</button>
          <button className="btn btnGhost" onClick={() => onOpen(item, 'watch')}>
            <Tv size={17} /> {isBook ? 'Where to read' : 'Where to watch'}
          </button>
        </div>
      </div>
    </motion.article>
  );
}

export function PosterCard({ item, saved, onSave, onOpen, showMatch = true }: CardProps) {
  return (
    <motion.article
      className="card"
      layout
      initial={{ opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0 }}
      transition={{ duration: .3 }}
    >
      <button className="cardHit" onClick={() => onOpen(item)} aria-label={`Open details for ${item.title}`}>
        <Poster item={item} />
        {showMatch && <span className="matchPill">{item.match}% your vibe</span>}
      </button>
      <button
        className={'saveDot ' + (saved ? 'on' : '')}
        onClick={() => onSave(item)}
        aria-label={saved ? `Remove ${item.title} from collection` : `Save ${item.title}`}
        aria-pressed={saved}
      >
        {saved ? <BookmarkCheck size={16} /> : <Bookmark size={16} />}
      </button>
      <div className="cardBody" onClick={() => onOpen(item)}>
        <h4>{item.title}</h4>
        <p className="cardMeta">
          <span>{KIND_LABEL[item.kind]}{item.year ? ` · ${item.year}` : ''}</span>
          <Rating item={item} compact />
        </p>
        <p className="cardGenre">{item.genres.slice(0, 2).join(' · ')}</p>
        <p className="cardLine">{item.description}</p>
      </div>
    </motion.article>
  );
}

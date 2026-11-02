'use client';
import { useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { ArrowLeft, ArrowRight, BookOpen, Check, Clapperboard, Film, Sparkles, Tv } from 'lucide-react';
import type { Filters } from '../lib/api';
import { GENRES, KINDS, VIBES, vibeMoods } from '../lib/ui';
import { Sparkle } from './bits';

const KIND_ICON = { movie: Film, anime_movie: Sparkles, series: Tv, anime_series: Clapperboard, book: BookOpen } as const;
const STEPS = ['Vibe check', 'Format', 'Extras'];
const MAX_VIBES = 2;

type Props = {
  filters: Filters;
  setFilters: (f: (old: Filters) => Filters) => void;
  onSubmit: () => void;
  onCancel: () => void;
  loading: boolean;
};

export default function Quiz({ filters, setFilters, onSubmit, onCancel, loading }: Props) {
  const [step, setStep] = useState(0);
  const toggle = (key: 'moods' | 'kinds' | 'genres', value: string, max = 99) =>
    setFilters(old => ({ ...old, [key]: old[key].includes(value) ? old[key].filter(x => x !== value) : [...old[key], value].slice(-max) }));
  const set = <K extends keyof Filters>(key: K, value: Filters[K]) => setFilters(old => ({ ...old, [key]: value }));
  const vibes = filters.vibes || [];
  const toggleVibe = (id: string) => setFilters(old => {
    const cur = old.vibes || [];
    const next = cur.includes(id) ? cur.filter(x => x !== id) : [...cur, id].slice(-MAX_VIBES);
    return { ...old, vibes: next, moods: vibeMoods(next) };
  });

  return (
    <section className="page quiz">
      <div className="quizHead">
        <span className="eyebrow"><Sparkle size={11} /> Vibe check ✨</span>
        <ol className="stepper" aria-label="Quiz progress">
          {STEPS.map((s, i) => (
            <li key={s} className={i === step ? 'current' : i < step ? 'done' : ''}>
              <button onClick={() => i < step && setStep(i)} disabled={i > step}>
                <span>{i < step ? <Check size={12} /> : i + 1}</span>{s}
              </button>
            </li>
          ))}
        </ol>
      </div>

      <AnimatePresence mode="wait">
        <motion.div key={step} initial={{ opacity: 0, x: 18 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -18 }} transition={{ duration: .22 }}>
          {step === 0 && (
            <>
              <h2 className="pageTitle">What&apos;s your emotional damage <em>today?</em></h2>
              <p className="lead">Pick your poison (up to two). Heartbreak Era + Cozy Potato? Valid. We don&apos;t judge.</p>
              <div className="moodGrid">
                {VIBES.map((m, i) => {
                  const on = vibes.includes(m.id);
                  return (
                    <motion.button key={m.id} className={`moodTile vibeTile tone-${m.tone} ${on ? 'on' : ''}`} onClick={() => toggleVibe(m.id)} aria-pressed={on}
                      initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * .03 }} whileTap={{ scale: .96 }}>
                      <span className="vibeEmoji" aria-hidden="true">{m.emoji}</span>
                      <strong>{m.label}</strong>
                      <small>{m.hint}</small>
                      {on && <span className="tick"><Check size={13} /></span>}
                    </motion.button>
                  );
                })}
              </div>
            </>
          )}
          {step === 1 && (
            <>
              <h2 className="pageTitle">Where are we escaping <em>to?</em></h2>
              <p className="lead">Pick one, pick five, pick none. Leaving it empty = everything's on the table.</p>
              <div className="kindGrid">
                {KINDS.map(k => {
                  const Icon = KIND_ICON[k.id];
                  const on = filters.kinds.includes(k.id);
                  return (
                    <button key={k.id} className={'kindTile ' + (on ? 'on' : '')} onClick={() => toggle('kinds', k.id)} aria-pressed={on}>
                      <Icon size={22} strokeWidth={1.6} />
                      <strong>{k.label}</strong>
                      <small>{k.hint}</small>
                      {on && <span className="tick"><Check size={13} /></span>}
                    </button>
                  );
                })}
              </div>
            </>
          )}
          {step === 2 && (
            <>
              <h2 className="pageTitle">The <em>extra</em> details</h2>
              <p className="lead">All optional, bestie. If nothing ticks every box we&apos;ll be honest about what we loosened.</p>
              <div className="prefs">
                <div className="prefBlock wide">
                  <label htmlFor="intensity">How hard should it hit?</label>
                  <input id="intensity" type="range" min={0} max={100} step={5} value={filters.intensity}
                    onChange={e => set('intensity', Number(e.target.value))}
                    style={{ ['--fill' as string]: `${filters.intensity}%` }} />
                  <div className="rangeLabels"><span>Soft hug 🧸</span><b>{filters.intensity < 30 ? 'Gentle' : filters.intensity < 65 ? 'Balanced' : 'Emotional damage'}</b><span>Ruin me 😭</span></div>
                </div>
                <div className="prefBlock">
                  <span className="label">Ending energy</span>
                  <div className="pills">
                    {[['any', 'Surprise me'], ['happy', 'Happy 🥹'], ['bittersweet', 'Bittersweet 🥲'], ['twist', 'Plot twist 🤯']].map(([id, label]) => (
                      <button key={id} className={filters.ending === id ? 'on' : ''} onClick={() => set('ending', id)} aria-pressed={filters.ending === id}>{label}</button>
                    ))}
                  </div>
                </div>
                <div className="prefBlock">
                  <span className="label">Attention span check</span>
                  <div className="pills">
                    {[['any', 'Whatever'], ['short', 'Quick fix'], ['medium', 'Medium'], ['long', 'Long haul']].map(([id, label]) => (
                      <button key={id} className={filters.duration === id ? 'on' : ''} onClick={() => set('duration', id)} aria-pressed={filters.duration === id}>{label}</button>
                    ))}
                  </div>
                </div>
                <div className="prefBlock wide">
                  <span className="label">Genres you stan</span>
                  <div className="pills">
                    {GENRES.map(g => (
                      <button key={g} className={filters.genres.includes(g) ? 'on' : ''} onClick={() => toggle('genres', g)} aria-pressed={filters.genres.includes(g)}>{g}</button>
                    ))}
                  </div>
                </div>
              </div>
            </>
          )}
        </motion.div>
      </AnimatePresence>

      <div className="quizFoot">
        <button className="btn btnGhost" onClick={() => (step === 0 ? onCancel() : setStep(s => s - 1))}><ArrowLeft size={17} /> Back</button>
        <span className="muted small">
          {step === 0 && (vibes.length ? `${vibes.length}/${MAX_VIBES} vibes locked in` : 'No vibe? We’ll keep it balanced.')}
          {step === 1 && (filters.kinds.length ? `${filters.kinds.length} selected` : 'Everything, no notes')}
        </span>
        {step < 2 ? (
          <button className="btn btnPrimary" onClick={() => setStep(s => s + 1)}>Next <ArrowRight size={17} /></button>
        ) : (
          <button className="btn btnPrimary" onClick={onSubmit} disabled={loading}>
            {loading ? 'Cooking…' : <>Find my next obsession <ArrowRight size={17} /></>}
          </button>
        )}
      </div>
    </section>
  );
}

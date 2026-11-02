'use client';
import { useEffect, useRef, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { ArrowUp, RotateCcw, X } from 'lucide-react';
import { ApiError, chat, type Filters, type Item, type RecommendResponse } from '../lib/api';
import { KIND_LABEL } from '../lib/ui';
import { Poster, Sparkle } from './bits';

type Msg = { role: 'user' | 'bot' | 'error'; text: string; items?: Item[]; response?: RecommendResponse; retry?: string };

const STARTERS = ['I’m down bad, give me a romance movie 💘', 'Cozy potato anime pls 🥔', 'Villain era thriller 😈', 'Something short, my brain is fried'];
const REFINERS = ['Nah, not feeling it', 'More romantic 💘', 'Less sad pls 😭', 'Already seen it', 'Something similar', 'Give me different ones'];

type Props = {
  open: boolean;
  setOpen: (v: boolean) => void;
  context: { filters: Filters; focusId?: string | null; shown: string[] };
  onOpenItem: (item: Item) => void;
  onSeeAll: (res: RecommendResponse) => void;
};

export default function Chat({ open, setOpen, context, onOpenItem, onSeeAll }: Props) {
  const [messages, setMessages] = useState<Msg[]>([]);
  const [text, setText] = useState('');
  const [busy, setBusy] = useState(false);
  const [state, setState] = useState<{ filters: Filters | null; focusId: string | null; shown: string[] }>({ filters: null, focusId: null, shown: [] });
  const body = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLInputElement>(null);

  useEffect(() => { body.current?.scrollTo({ top: body.current.scrollHeight, behavior: 'smooth' }); }, [messages, busy]);
  useEffect(() => { if (open) setTimeout(() => input.current?.focus(), 150); }, [open]);

  async function send(message: string) {
    const m = message.trim();
    if (!m || busy) return;
    setText('');
    setMessages(prev => [...prev, { role: 'user', text: m }]);
    setBusy(true);
    // First turn builds on what's on screen; later turns build on the conversation.
    const base = state.filters ?? context.filters;
    const focus = state.focusId ?? context.focusId ?? null;
    const shown = state.shown.length ? state.shown : context.shown;
    try {
      const res = await chat({ ...base, message: m, focus_id: focus, shown, limit: 12 });
      setState({ filters: res.filters, focusId: res.items[0]?.id ?? focus, shown: res.items.map(x => x.id) });
      setMessages(prev => [...prev, { role: 'bot', text: res.reply || '', items: res.items.slice(0, 3), response: res }]);
    } catch (e) {
      const msg = `Ugh, my brain glitched 😵‍💫 ${e instanceof ApiError ? e.message : 'Something went wrong.'}`;
      setMessages(prev => [...prev, { role: 'error', text: msg, retry: m }]);
    } finally {
      setBusy(false);
    }
  }

  function reset() {
    setMessages([]);
    setState({ filters: null, focusId: null, shown: [] });
  }

  const hasPicks = messages.some(x => x.items?.length);

  return (
    <>
      <button className={'chatLauncher ' + (open ? 'hidden' : '')} onClick={() => setOpen(true)} aria-label="Talk to your bestie">
        <span className="launcherEmoji" aria-hidden="true">💬</span> <span>Talk to Your Bestie</span>
      </button>
      <AnimatePresence>
        {open && (
          <motion.section
            className="chatWindow"
            role="dialog"
            aria-label="Talk to your bestie"
            initial={{ opacity: 0, y: 24, scale: .97 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 24, scale: .97 }}
          >
            <header className="chatBar">
              <span className="dots" aria-hidden="true"><i /><i /><i /></span>
              <strong>your_bestie 💕 <small className="online">online</small></strong>
              <div>
                {messages.length > 0 && <button className="iconBtn" onClick={reset} aria-label="Start a new conversation"><RotateCcw size={15} /></button>}
                <button className="iconBtn" onClick={() => setOpen(false)} aria-label="Close chat"><X size={17} /></button>
              </div>
            </header>
            <div className="chatBody" ref={body} aria-live="polite">
              <div className="bubble bot">
                Heyyy bestie 💕 spill. What are we feeling tonight? Heartbreak era, down bad, villain era… I don&apos;t judge. Tell me, and if my picks are mid just say &ldquo;nah&rdquo; and I&apos;ll try again.
              </div>
              {messages.length === 0 && (
                <div className="suggestions">
                  {STARTERS.map(s => <button key={s} onClick={() => send(s)}>{s}</button>)}
                </div>
              )}
              {messages.map((m, i) => (
                <div key={i} className={'msg ' + m.role}>
                  <div className={'bubble ' + m.role}>{m.text}</div>
                  {m.role === 'error' && m.retry && (
                    <button className="textLink" onClick={() => { setMessages(prev => prev.filter((_, j) => j !== i)); send(m.retry!); }}>Try again</button>
                  )}
                  {m.items && m.items.length > 0 && (
                    <div className="miniList">
                      {m.items.map(item => (
                        <button key={item.id} className="mini" onClick={() => onOpenItem(item)}>
                          <Poster item={item} size="sm" />
                          <span><b>{item.title}</b><small>{KIND_LABEL[item.kind]}{item.year ? ` · ${item.year}` : ''}</small></span>
                        </button>
                      ))}
                      {m.response && m.response.items.length > 3 && (
                        <button className="textLink" onClick={() => { onSeeAll(m.response!); setOpen(false); }}>
                          See all {m.response.items.length} picks, bestie →
                        </button>
                      )}
                    </div>
                  )}
                </div>
              ))}
              {busy && <div className="bubble bot typing" aria-label="Bestie is typing"><i /><i /><i /></div>}
            </div>
            {hasPicks && !busy && (
              <div className="suggestions refine">
                {REFINERS.map(s => <button key={s} onClick={() => send(s)}>{s}</button>)}
              </div>
            )}
            <form className="chatInput" onSubmit={e => { e.preventDefault(); send(text); }}>
              <Sparkle size={12} />
              <input ref={input} value={text} onChange={e => setText(e.target.value)} placeholder="spill the tea… e.g. cozy anime, no crying" maxLength={500} aria-label="Message" />
              <button className="sendBtn" disabled={busy || !text.trim()} aria-label="Send"><ArrowUp size={18} /></button>
            </form>
          </motion.section>
        )}
      </AnimatePresence>
    </>
  );
}

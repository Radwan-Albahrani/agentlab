import * as stylex from '@stylexjs/stylex';
import { useEffect, useMemo, useState, useSyncExternalStore, type KeyboardEvent } from 'react';
import { useNavigate } from 'react-router';
import { useNowBoard } from '../api/queries';
import { useScheme } from '../theme/mode';
import { hueTheme } from '../theme/hues';
import { colors, media, motion, radius, space, text } from '../theme/tokens.stylex';
import { Overlay } from '../ui/Dialog';
import { Icon } from '../ui/Icon';
import { Badge } from '../ui/status';
import type { Menu } from './menu';

// open/closed lives outside React so the sidebar, the phone bar and the shortcut all reach it
let open = false;
const listeners = new Set<() => void>();
const set = (v: boolean) => {
  open = v;
  listeners.forEach((l) => {
    l();
  });
};
export const openPalette = () => {
  set(true);
};
const subscribe = (l: () => void) => {
  listeners.add(l);
  return () => {
    listeners.delete(l);
  };
};

const pop = stylex.keyframes({
  from: { opacity: 0, transform: 'translateX(-50%) translateY(-8px) scale(.98)' },
  to: { opacity: 1, transform: 'translateX(-50%)' },
});
const fade = stylex.keyframes({ from: { opacity: 0 } });

const styles = stylex.create({
  backdrop: {
    position: 'fixed',
    inset: 0,
    zIndex: 50,
    backgroundColor: colors.overlay,
    backdropFilter: 'blur(6px)',
    animationName: fade,
    animationDuration: '160ms',
  },
  popup: {
    position: 'fixed',
    top: { default: '14vh', [media.phone]: space.xxl },
    left: '50%',
    transform: 'translateX(-50%)',
    zIndex: 51,
    width: 'min(640px, calc(100vw - 24px))',
    overflow: 'hidden',
    borderRadius: radius.xxl,
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: colors.line2,
    backgroundColor: `color-mix(in srgb, ${colors.panel} 88%, transparent)`,
    backdropFilter: 'saturate(180%) blur(24px)',
    boxShadow: `${colors.popShadow}, 0 0 0 1px color-mix(in srgb, ${colors.fg} 4%, transparent)`,
    outline: 'none',
    animationName: pop,
    animationDuration: '240ms',
    animationTimingFunction: motion.settle,
  },
  field: {
    display: 'flex',
    alignItems: 'center',
    gap: space.md,
    paddingBlock: space.xl,
    paddingInline: space.xxxl,
    borderBottomWidth: 1,
    borderBottomStyle: 'solid',
    borderBottomColor: colors.line,
    color: colors.faint,
  },
  input: {
    flex: '1',
    minWidth: 0,
    borderWidth: 0,
    outline: 'none',
    backgroundColor: 'transparent',
    fontSize: text.lg,
    color: colors.fg,
    '::placeholder': { color: colors.faint },
  },
  kbd: {
    fontFamily: 'inherit',
    fontSize: text.xxs,
    fontWeight: 600,
    color: colors.faint,
    paddingBlock: 2,
    paddingInline: space.xs,
    borderRadius: radius.xs,
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: colors.line2,
    backgroundColor: colors.sunk,
  },
  list: { maxHeight: 'min(60vh, 460px)', overflowY: 'auto', padding: space.sm, scrollPaddingBlock: space.sm },
  group: {
    paddingBlockStart: space.md,
    paddingBlockEnd: space.xxs,
    paddingInline: space.lg,
    fontSize: text.xxs,
    fontWeight: 650,
    letterSpacing: '.07em',
    textTransform: 'uppercase',
    color: colors.faint,
  },
  item: {
    display: 'flex',
    alignItems: 'center',
    gap: space.lg,
    width: '100%',
    paddingBlock: space.md,
    paddingInline: space.lg,
    borderRadius: radius.lg,
    borderWidth: 0,
    backgroundColor: 'transparent',
    color: colors.fg,
    textAlign: 'start',
    cursor: 'pointer',
    font: 'inherit',
  },
  active: { backgroundColor: colors.accentSoft },
  icon: {
    width: 30,
    height: 30,
    flexShrink: 0,
    display: 'grid',
    placeItems: 'center',
    borderRadius: radius.sm,
    backgroundColor: colors.sunk,
    color: colors.muted,
  },
  iconActive: { backgroundColor: colors.accent, color: colors.accentFg },
  label: { flex: '1', minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', fontWeight: 550 },
  hint: { fontSize: text.sm, color: colors.faint, whiteSpace: 'nowrap' },
  enter: { color: colors.accent, display: 'flex' },
  empty: { paddingBlock: space.huge, textAlign: 'center', color: colors.faint },
  foot: {
    display: 'flex',
    gap: space.xxl,
    paddingBlock: space.md,
    paddingInline: space.xxxl,
    borderTopWidth: 1,
    borderTopStyle: 'solid',
    borderTopColor: colors.line,
    fontSize: text.xs,
    color: colors.faint,
  },
  footItem: { display: 'flex', alignItems: 'center', gap: space.xs },
});

interface Command {
  id: string;
  group: string;
  label: string;
  hint?: string;
  icon?: string;
  agent?: string; // shows the agent's badge instead of an icon
  run: () => void;
}

/** Fuzzy: every typed character in order; earlier, tighter and word-start matches score higher. */
export function score(query: string, label: string): number {
  const q = query.toLowerCase().replace(/\s+/g, '');
  const l = label.toLowerCase();
  if (!q) return 1;
  let at = -1;
  let total = 0;
  for (const ch of q) {
    const next = l.indexOf(ch, at + 1);
    if (next < 0) return 0;
    total += next === at + 1 ? 3 : next === 0 || l[next - 1] === ' ' ? 2 : 1;
    at = next;
  }
  return total + (l.startsWith(q) ? 5 : 0) - at / 100;
}

const external = (url: string) => () => window.open(url, '_blank', 'noopener');

function useCommands(menu: Menu): Command[] {
  const navigate = useNavigate();
  const now = useNowBoard().data?.agents ?? [];
  const [scheme, toggle] = useScheme();
  {
    const out: Command[] = [];
    for (const a of now) {
      for (const w of a.waiting)
        out.push({
          id: `w-${a.name}-${w.id}`,
          group: 'Waiting on you',
          label: w.title,
          hint: a.name,
          agent: a.name,
          run: external(a.chat),
        });
      for (const r of a.running)
        out.push({
          id: `r-${a.name}-${r.id}`,
          group: 'Running now',
          label: r.title,
          hint: a.name,
          agent: a.name,
          run: external(a.chat),
        });
    }
    const go = (to: string) => () => {
      void navigate(to);
    };
    for (const i of [...menu.main, ...menu.agents, ...menu.system]) {
      const m = i.mark;
      out.push({
        id: `go-${i.to}`,
        group: 'Go to',
        label: i.short ?? i.label,
        icon: 'icon' in m ? m.icon : 'companionOf' in m ? 'bot' : undefined,
        agent: 'agent' in m ? m.agent : undefined,
        run: go(i.to),
      });
    }
    for (const a of now)
      out.push({ id: `chat-${a.name}`, group: 'Open', label: `${a.name} chat`, icon: 'chat', run: external(a.chat) });
    out.push({
      id: 'theme',
      group: 'Actions',
      label: `Switch to ${scheme === 'dark' ? 'light' : 'dark'} theme`,
      icon: scheme === 'dark' ? 'sun' : 'moon',
      run: toggle,
    });
    return out;
  }
}

const typing = (e: globalThis.KeyboardEvent) => {
  const t = e.target as HTMLElement | null;
  return !!t && (t.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(t.tagName));
};

/** Ctrl/⌘+K (or / when not typing) opens a search over every page, agent, live chat and action. */
export function Palette({ menu }: { menu: Menu }) {
  const shown = useSyncExternalStore(subscribe, () => open);
  useEffect(() => {
    const onKey = (e: globalThis.KeyboardEvent) => {
      if ((e.key === 'k' && (e.metaKey || e.ctrlKey)) || (e.key === '/' && !typing(e) && !open)) {
        e.preventDefault();
        set(!open);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => {
      window.removeEventListener('keydown', onKey);
    };
  }, []);
  return (
    <Overlay
      open={shown}
      onOpenChange={(o) => {
        set(o);
      }}
      label="Search"
      backdrop={styles.backdrop}
      popup={styles.popup}
    >
      {shown && <Search menu={menu} />}
    </Overlay>
  );
}

function Search({ menu }: { menu: Menu }) {
  const commands = useCommands(menu);
  const [query, setQuery] = useState('');
  const [at, setAt] = useState(0);
  const hits = useMemo(() => {
    if (!query.trim()) return commands;
    // letters scattered across a long title score about 1 each: keep only tighter matches
    const enough = query.replace(/\s+/g, '').length * 1.5;
    return commands
      .map((c) => ({ c, s: Math.max(score(query, c.label), score(query, `${c.hint ?? ''} ${c.label}`) - 1) }))
      .filter((x) => x.s >= enough)
      .sort((a, b) => b.s - a.s)
      .map((x) => x.c);
  }, [commands, query]);
  const pick = Math.min(at, Math.max(0, hits.length - 1));
  useEffect(() => {
    document.getElementById(`cmd-${pick}`)?.scrollIntoView({ block: 'nearest' });
  }, [pick]);
  const run = (c: Command | undefined) => {
    if (!c) return;
    set(false);
    c.run();
  };
  const onKey = (e: KeyboardEvent) => {
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault();
      const n = hits.length || 1;
      setAt((pick + (e.key === 'ArrowDown' ? 1 : n - 1)) % n);
    } else if (e.key === 'Enter') {
      e.preventDefault();
      run(hits[pick]);
    }
  };
  return (
    <>
      <div {...stylex.props(styles.field)}>
        <Icon name="search" size={20} />
        <input
          {...stylex.props(styles.input)}
          placeholder="Search pages, agents, chats…"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setAt(0);
          }}
          onKeyDown={onKey}
          aria-controls="cmd-list"
          aria-label="Search"
        />
        <kbd {...stylex.props(styles.kbd)}>Esc</kbd>
      </div>
      <div {...stylex.props(styles.list)} id="cmd-list">
        {!hits.length && <div {...stylex.props(styles.empty)}>Nothing matches “{query}”.</div>}
        {hits.map((c, i) => {
          const head = !query.trim() && hits[i - 1]?.group !== c.group ? c.group : '';
          const on = i === pick;
          return (
            <div key={c.id}>
              {head && <div {...stylex.props(styles.group)}>{head}</div>}
              <button
                type="button"
                id={`cmd-${i}`}
                aria-current={on}
                tabIndex={-1}
                {...stylex.props(styles.item, on && styles.active)}
                onMouseMove={() => {
                  if (!on) setAt(i);
                }}
                onClick={() => {
                  run(c);
                }}
              >
                <span {...stylex.props(hueTheme(c.agent), styles.icon, on && !c.agent && styles.iconActive)}>
                  {c.agent && !c.icon ? <Badge name={c.agent} size="sm" /> : <Icon name={c.icon ?? 'arrow'} size={16} />}
                </span>
                <span {...stylex.props(styles.label)}>{c.label}</span>
                {c.hint && <span {...stylex.props(styles.hint)}>{c.hint}</span>}
                {on && (
                  <span {...stylex.props(styles.enter)}>
                    <Icon name="arrow" size={16} />
                  </span>
                )}
              </button>
            </div>
          );
        })}
      </div>
      <div {...stylex.props(styles.foot)}>
        <span {...stylex.props(styles.footItem)}>
          <kbd {...stylex.props(styles.kbd)}>↑</kbd>
          <kbd {...stylex.props(styles.kbd)}>↓</kbd> move
        </span>
        <span {...stylex.props(styles.footItem)}>
          <kbd {...stylex.props(styles.kbd)}>Enter</kbd> open
        </span>
        <span {...stylex.props(styles.footItem)}>
          <kbd {...stylex.props(styles.kbd)}>Ctrl K</kbd> anywhere
        </span>
      </div>
    </>
  );
}

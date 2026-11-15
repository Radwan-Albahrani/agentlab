import { useEffect, useSyncExternalStore } from 'react';
import { useNavigate } from 'react-router';
import { useNowBoard } from '../api/queries';
import { useScheme } from '../theme/mode';
import { CommandPalette, type CommandEntry } from '../ui/Command';
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

interface Command extends CommandEntry {
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

function rank(commands: Command[], query: string): Command[] {
  if (!query.trim()) return commands;
  // letters scattered across a long title score about 1 each: keep only tighter matches
  const enough = query.replace(/\s+/g, '').length * 1.5;
  return commands
    .map((c) => ({ c, s: Math.max(score(query, c.label), score(query, `${c.hint ?? ''} ${c.label}`) - 1) }))
    .filter((x) => x.s >= enough)
    .sort((a, b) => b.s - a.s)
    .map((x) => x.c);
}

const external = (url: string) => () => window.open(url, '_blank', 'noopener');
const badge = (agent: string) => <Badge name={agent} size="sm" />;
const icon = (name: string) => <Icon name={name} size={16} />;

function useCommands(menu: Menu): Command[] {
  const navigate = useNavigate();
  const now = useNowBoard().data?.agents ?? [];
  const [scheme, toggle] = useScheme();
  const out: Command[] = [];
  const go = (to: string) => () => {
    void navigate(to);
  };
  for (const i of [...menu.main, ...menu.agents, ...menu.system]) {
    const m = i.mark;
    const agent = 'agent' in m ? m.agent : undefined;
    const name = 'icon' in m ? m.icon : 'companionOf' in m ? 'bot' : undefined;
    out.push({
      id: `go-${i.to}`,
      group: 'Go to',
      label: i.short ?? i.label,
      icon: agent && !name ? badge(agent) : icon(name ?? 'arrow'),
      hue: agent,
      run: go(i.to),
    });
  }
  for (const a of now)
    out.push({ id: `chat-${a.name}`, group: 'Open', label: `${a.name} chat`, icon: icon('chat'), run: external(a.chat) });
  out.push({
    id: 'theme',
    group: 'Actions',
    label: `Switch to ${scheme === 'dark' ? 'light' : 'dark'} theme`,
    icon: icon(scheme === 'dark' ? 'sun' : 'moon'),
    run: toggle,
  });
  return out;
}

const typing = (e: globalThis.KeyboardEvent) => {
  const t = e.target as HTMLElement | null;
  return !!t && (t.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(t.tagName));
};

// "/" belongs to a page's own search box when it has one (ui/inputs SearchInput)
const pageSearch = () => !!document.querySelector('main input[type="search"]');

/** Ctrl/⌘+K (or / when not typing) opens a search over every page, agent and action. */
export function Palette({ menu }: { menu: Menu }) {
  const shown = useSyncExternalStore(subscribe, () => open);
  const commands = useCommands(menu);
  useEffect(() => {
    const onKey = (e: globalThis.KeyboardEvent) => {
      if ((e.key === 'k' && (e.metaKey || e.ctrlKey)) || (e.key === '/' && !typing(e) && !open && !pageSearch())) {
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
    <CommandPalette
      open={shown}
      onOpenChange={set}
      label="Search"
      placeholder="Search pages, agents, chats…"
      entries={commands}
      rank={rank}
      onRun={(c) => {
        set(false);
        c.run();
      }}
    />
  );
}

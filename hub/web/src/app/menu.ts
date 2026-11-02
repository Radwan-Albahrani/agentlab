import type { Nav } from '../api/types';

/** What leads a menu entry: an icon, an agent's badge, or (for a companion) a bot in its agent's colour. */
type Mark = { icon: string } | { agent: string } | { companionOf: string };

export interface MenuItem {
  to: string;
  label: string;
  short?: string; // the phone bar's label
  mark: Mark;
  exact?: boolean;
  count?: number; // something needs you here
  dot?: boolean; // up / down
  note?: string;
}

export interface Menu {
  main: MenuItem[];
  agents: MenuItem[];
  system: MenuItem[];
}

const SYSTEM_ICONS: Record<string, string> = {
  services: 'layers',
  config: 'sliders',
  storage: 'disk',
  secrets: 'key',
  notifications: 'bell',
};

/** The menu the server allows right now: agents with their companions nested under them, then system screens. */
export function buildMenu(nav: Nav): Menu {
  const agents: MenuItem[] = [];
  if (nav.allAgents) agents.push({ to: '/agents', label: 'All agents', short: 'Agents', exact: true, mark: { icon: 'agents' } });
  for (const a of nav.agents) {
    agents.push({ to: `/agents/${a.name}`, label: a.name, exact: true, mark: { agent: a.name }, dot: a.up });
    for (const c of a.companions) {
      agents.push({
        to: `/agents/${a.name}/${c.name}`,
        label: c.display,
        short: `${a.name} › ${c.display}`,
        mark: { companionOf: a.name },
        count: c.waiting,
        dot: c.live,
      });
    }
  }
  const system: MenuItem[] = nav.system.map((s) => ({
    to: s.path,
    label: s.label,
    mark: { icon: SYSTEM_ICONS[s.key] ?? 'sliders' },
    count: s.count,
    note: s.note,
  }));
  if (nav.display) system.push({ to: '/display', label: 'Display', mark: { icon: 'eye' } });
  return { main: [{ to: '/', label: 'Overview', exact: true, mark: { icon: 'home' }, count: nav.attention }], agents, system };
}

export const isActive = (item: MenuItem, pathname: string) =>
  item.exact ? pathname === item.to : pathname === item.to || pathname.startsWith(`${item.to}/`);

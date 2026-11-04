import * as stylex from '@stylexjs/stylex';
import type { ReactElement } from 'react';
import { text } from '../theme/tokens.stylex';

// 24px stroke icons, plus the brand marks used on sign-in and connector rows.
const PATHS: Record<string, string> = {
  home: 'M3.5 10.5 12 4l8.5 6.5V19a1.5 1.5 0 0 1-1.5 1.5h-4v-6h-6v6H5A1.5 1.5 0 0 1 3.5 19z',
  more: 'M6.5 12a1 1 0 1 1-2 0 1 1 0 0 1 2 0zM13 12a1 1 0 1 1-2 0 1 1 0 0 1 2 0zM19.5 12a1 1 0 1 1-2 0 1 1 0 0 1 2 0z',
  search: 'M16.5 10.5a6 6 0 1 1-12 0 6 6 0 0 1 12 0zM15 15l5 5',
  bot: 'M4 11a3.5 3.5 0 0 1 3.5-3.5h9A3.5 3.5 0 0 1 20 11v5a3.5 3.5 0 0 1-3.5 3.5h-9A3.5 3.5 0 0 1 4 16zM12 7.5V4.5M9 13h.01M15 13h.01M9.5 16.5h5',
  disk: 'M4 6c0-1.5 3.6-2.8 8-2.8s8 1.3 8 2.8-3.6 2.8-8 2.8S4 7.5 4 6zM4 6v12c0 1.5 3.6 2.8 8 2.8s8-1.3 8-2.8V6M4 12c0 1.5 3.6 2.8 8 2.8s8-1.3 8-2.8',
  key: 'M12 15.5a4 4 0 1 1-8 0 4 4 0 0 1 8 0zM11 12.5 19.5 4M16.5 7l2.5 2.5M14.5 9l2 2',
  bell: 'M6 16.5V11a6 6 0 0 1 12 0v5.5l1.5 2h-15zM10 20.5a2.2 2.2 0 0 0 4 0',
  phone: 'M9 2.5h6a2.5 2.5 0 0 1 2.5 2.5v14a2.5 2.5 0 0 1-2.5 2.5H9A2.5 2.5 0 0 1 6.5 19V5A2.5 2.5 0 0 1 9 2.5zM10.5 18.5h3',
  chat: 'M20 12.5a7.5 7.5 0 0 1-11 6.6L4 20l1-4.4A7.5 7.5 0 1 1 20 12.5z',
  terminal:
    'M5.5 4.5h13A2.5 2.5 0 0 1 21 7v10a2.5 2.5 0 0 1-2.5 2.5h-13A2.5 2.5 0 0 1 3 17V7a2.5 2.5 0 0 1 2.5-2.5zM7.5 9.5l3 2.5-3 2.5M12.5 15h4',
  browser: 'M20.5 12a8.5 8.5 0 1 1-17 0 8.5 8.5 0 0 1 17 0zM3.5 12h17M12 3.5c2.5 2.6 2.5 14.4 0 17M12 3.5c-2.5 2.6-2.5 14.4 0 17',
  files: 'M3.5 7a2 2 0 0 1 2-2h4l2 2.5h7a2 2 0 0 1 2 2V17a2 2 0 0 1-2 2h-13a2 2 0 0 1-2-2z',
  arrow: 'M9 6l6 6-6 6',
  back: 'M15 6l-6 6 6 6',
  chevron: 'M6 9l6 6 6-6',
  poll: 'M5 20V10M12 20V4M19 20v-7',
  single: 'M20 12a8 8 0 1 1-16 0 8 8 0 0 1 16 0zM14.5 12a2.5 2.5 0 1 1-5 0 2.5 2.5 0 0 1 5 0z',
  multiple: 'M4 4.5h6v6H4zM4 13.5h6v6H4zM5.5 7.5l1.3 1.3L8.8 6.6M5.5 16.5l1.3 1.3 2-2.2M13.5 7.5h6.5M13.5 16.5h6.5',
  x: 'M6 6l12 12M18 6 6 18',
  pr: 'M8 6a2 2 0 1 1-4 0 2 2 0 0 1 4 0zM6 8v8M8 18a2 2 0 1 1-4 0 2 2 0 0 1 4 0zM20 18a2 2 0 1 1-4 0 2 2 0 0 1 4 0zM18 16V9.5A3.5 3.5 0 0 0 14.5 6H11M13 3.5 10.5 6 13 8.5',
  draft:
    'M8 6a2 2 0 1 1-4 0 2 2 0 0 1 4 0zM6 8v8M8 18a2 2 0 1 1-4 0 2 2 0 0 1 4 0zM20 18a2 2 0 1 1-4 0 2 2 0 0 1 4 0zM18 6v.01M18 11v.01',
  sort: 'M7 4v16M3.5 16.5 7 20l3.5-3.5M17 20V4M13.5 7.5 17 4l3.5 3.5',
  filter: 'M4 6.5h16M7 12h10M10 17.5h4',
  refresh: 'M20 11a8 8 0 0 0-14.6-4.5M4 4.5v4h4M4 13a8 8 0 0 0 14.6 4.5M20 19.5v-4h-4',
  broom: 'M14.5 3.5 10 12M7 12h7l2.5 8.5h-12zM9 16.5v4M12.5 16.5v4',
  eye: 'M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12zM14.8 12a2.8 2.8 0 1 1-5.6 0 2.8 2.8 0 0 1 5.6 0z',
  edit: 'M4 20h4L19 9a2.1 2.1 0 0 0-4-4L4 16zM13.5 6.5l4 4',
  trash: 'M4.5 7h15M9.5 7V4.5h5V7M6.5 7l1 12.5h9l1-12.5',
  plus: 'M12 5v14M5 12h14',
  history: 'M3.5 12a8.5 8.5 0 1 0 2.5-6M3.5 4v4h4M12 7.5V12l3 2',
  check: 'm5 12.5 4.5 4.5L19 7.5',
  alert: 'M12 4 2.8 19.5h18.4zM12 10v4.5M12 17.2h.01',
  clock: 'M20.5 12a8.5 8.5 0 1 1-17 0 8.5 8.5 0 0 1 17 0zM12 7.5V12l3 2',
  send: 'M20.5 3.5 10 14M20.5 3.5 14 20.5l-4-6.5-6.5-4z',
  power: 'M12 3.5v8M7 6.5a7 7 0 1 0 10 0',
  slack:
    'M9.5 3.5a2 2 0 1 0 0 4h2v-2a2 2 0 0 0-2-2zM9.5 9.5h-5a2 2 0 1 0 0 4h5a2 2 0 1 0 0-4zM20.5 9.5a2 2 0 1 0-4 0v2h2a2 2 0 0 0 2-2zM14.5 9.5v-5a2 2 0 1 0-4 0M14.5 20.5a2 2 0 1 0 0-4h-2v2a2 2 0 0 0 2 2zM14.5 14.5h5a2 2 0 1 0 0-4h-5a2 2 0 1 0 0 4zM3.5 14.5a2 2 0 1 0 4 0v-2h-2a2 2 0 0 0-2 2zM9.5 14.5v5a2 2 0 1 0 4 0',
  github:
    'M9 19c-4.3 1.4-4.3-2.5-6-3m12 5v-3.5c0-1 .1-1.4-.5-2 2.8-.3 5.5-1.4 5.5-6a4.6 4.6 0 0 0-1.3-3.2 4.2 4.2 0 0 0-.1-3.2s-1.1-.3-3.5 1.3a12 12 0 0 0-6.2 0C6.5 2.8 5.4 3.1 5.4 3.1a4.2 4.2 0 0 0-.1 3.2A4.6 4.6 0 0 0 4 9.5c0 4.6 2.7 5.7 5.5 6-.6.6-.6 1.2-.5 2V21',
  layers: 'M12 3.5 3 8l9 4.5L21 8zM3 12l9 4.5 9-4.5M3 16l9 4.5 9-4.5',
  sliders:
    'M4 6h10M18 6h2M4 12h4M12 12h8M4 18h12M18 6a2 2 0 1 1-4 0 2 2 0 0 1 4 0zM12 12a2 2 0 1 1-4 0 2 2 0 0 1 4 0zM20 18a2 2 0 1 1-4 0 2 2 0 0 1 4 0z',
  log: 'M6.5 3.5h11A2.5 2.5 0 0 1 20 6v12a2.5 2.5 0 0 1-2.5 2.5h-11A2.5 2.5 0 0 1 4 18V6a2.5 2.5 0 0 1 2.5-2.5zM8 8h8M8 12h8M8 16h5',
  agents:
    'M5.5 3.5h3a2 2 0 0 1 2 2v3a2 2 0 0 1-2 2h-3a2 2 0 0 1-2-2v-3a2 2 0 0 1 2-2zM15.5 3.5h3a2 2 0 0 1 2 2v3a2 2 0 0 1-2 2h-3a2 2 0 0 1-2-2v-3a2 2 0 0 1 2-2zM5.5 13.5h3a2 2 0 0 1 2 2v3a2 2 0 0 1-2 2h-3a2 2 0 0 1-2-2v-3a2 2 0 0 1 2-2zM15.5 13.5h3a2 2 0 0 1 2 2v3a2 2 0 0 1-2 2h-3a2 2 0 0 1-2-2v-3a2 2 0 0 1 2-2z',
  copy: 'M9 9h10v11H9zM5 15V4h10',
  sun: 'M16 12a4 4 0 1 1-8 0 4 4 0 0 1 8 0zM12 2.5v2M12 19.5v2M4.6 4.6 6 6M18 18l1.4 1.4M2.5 12h2M19.5 12h2M4.6 19.4 6 18M18 6l1.4-1.4',
  moon: 'M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z',
  ext: 'M14 4.5h5.5V10M19.5 4.5 11 13M18 14v4.5a1.5 1.5 0 0 1-1.5 1.5h-11A1.5 1.5 0 0 1 4 18.5v-11A1.5 1.5 0 0 1 5.5 6H10',
};

const styles = stylex.create({
  icon: (size: number) => ({ width: size, height: size, flexShrink: 0 }),
  letter: { fontSize: text.lg, fontWeight: 700 },
});

export function Icon({ name, size = 18 }: { name: string; size?: number }) {
  return (
    <svg
      {...stylex.props(styles.icon(size))}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d={PATHS[name] ?? PATHS.alert} />
    </svg>
  );
}

const BRANDS: Record<string, ReactElement> = {
  claude: (
    <path
      fill="#D97757"
      d="M12 2.5l1.6 6.2 5.5-3.3-3.3 5.5 6.2 1.6-6.2 1.6 3.3 5.5-5.5-3.3L12 21.5l-1.6-6.2-5.5 3.3 3.3-5.5-6.2-1.6 6.2-1.6-3.3-5.5 5.5 3.3z"
    />
  ),
  codex: (
    <g fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="9.5" />
      <path d="M8.5 9.5l3 2.5-3 2.5M13 15h3" />
    </g>
  ),
  github: (
    <path
      fill="currentColor"
      d="M12 2a10 10 0 0 0-3.2 19.5c.5.1.7-.2.7-.5v-1.7c-2.8.6-3.4-1.3-3.4-1.3-.5-1.2-1.1-1.5-1.1-1.5-.9-.6.1-.6.1-.6 1 .1 1.5 1 1.5 1 .9 1.5 2.4 1.1 2.9.8.1-.6.4-1.1.6-1.3-2.2-.3-4.6-1.1-4.6-5 0-1.1.4-2 1-2.7-.1-.3-.4-1.3.1-2.7 0 0 .8-.3 2.8 1a9.6 9.6 0 0 1 5 0c1.9-1.3 2.8-1 2.8-1 .5 1.4.2 2.4.1 2.7.6.7 1 1.6 1 2.7 0 3.9-2.4 4.7-4.6 5 .4.3.7.9.7 1.9v2.8c0 .3.2.6.7.5A10 10 0 0 0 12 2z"
    />
  ),
  expo: (
    <path
      fill="currentColor"
      d="M11.2 5.6c.4-.6 1.2-.6 1.6 0l8 12.4c.4.6 0 1.4-.8 1.4-.3 0-.6-.2-.8-.4L12 8.6l-7.2 10.4c-.2.3-.5.4-.8.4-.8 0-1.2-.8-.8-1.4z"
    />
  ),
  sentry: (
    <path
      fill="none"
      stroke="#7553ff"
      strokeWidth={1.9}
      strokeLinejoin="round"
      d="M12 3.5L3 19h4.2a6.5 6.5 0 0 0-3.4-5.4M12 3.5l3.4 5.9a11 11 0 0 1 5.6 9.6h-4.3a6.7 6.7 0 0 0-3.4-5.8l-1.9 3.2a3 3 0 0 1 1.6 2.6"
    />
  ),
  axiom: (
    <path
      fill="none"
      stroke="currentColor"
      strokeWidth={1.9}
      strokeLinejoin="round"
      d="M12 3.5 2.8 20h4.4L12 11.4 16.8 20h4.4zM9.4 16.2h5.2"
    />
  ),
  linear: (
    <path
      fill="#5e6ad2"
      d="M3.2 13.6l7.2 7.2A9 9 0 0 1 3.2 13.6zM3 11l10 10a9 9 0 0 0 2.2-.4L3.4 8.8A9 9 0 0 0 3 11zm1.4-4.1l12.7 12.7a9 9 0 0 0 1.6-1.2L5.6 5.3c-.5.5-.9 1-1.2 1.6zM7.3 4A9 9 0 0 1 20 16.7z"
    />
  ),
};

/** A brand mark if there is one, else the name's first letter. */
export function Brand({ name, label }: { name: string; label?: string }) {
  const mark = BRANDS[name];
  if (!mark) return <b {...stylex.props(styles.letter)}>{(label || name).charAt(0).toUpperCase()}</b>;
  return (
    <svg {...stylex.props(styles.icon(18))} viewBox="0 0 24 24" aria-hidden="true">
      {mark}
    </svg>
  );
}

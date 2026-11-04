import * as stylex from '@stylexjs/stylex';

/** light-dark(light, dark): the document's color-scheme (theme/mode.ts) picks one. */
export const colors = stylex.defineVars({
  bg: 'light-dark(#f6f6f3, #0d0e10)',
  panel: 'light-dark(#ffffff, #15161a)',
  sunk: 'light-dark(#f1f1ed, #101114)',
  hover: 'light-dark(#ecece7, #1e1f25)',
  fg: 'light-dark(#16171a, #ececef)',
  muted: 'light-dark(#62636b, #a3a4ab)',
  faint: 'light-dark(#8e8f96, #7a7b83)',
  line: 'light-dark(#e7e6e1, #24252b)',
  line2: 'light-dark(#dcdbd5, #33343b)',
  accent: 'light-dark(#2f5ee8, #7d9bff)',
  accentFg: 'light-dark(#ffffff, #0d0e10)',
  accentSoft: 'light-dark(#e9effe, #1b2340)',
  ok: 'light-dark(#15803d, #4ade80)',
  okSoft: 'light-dark(#e4f4e8, #10251a)',
  warn: 'light-dark(#b45309, #fbbf24)',
  warnSoft: 'light-dark(#fbefda, #2b220e)',
  bad: 'light-dark(#c42b2b, #f87171)',
  badSoft: 'light-dark(#fbe7e6, #2d1414)',
  idleSoft: 'light-dark(#efefeb, #1d1e23)',
  onFill: '#ffffff', // text on a coloured fill
  paper: '#ffffff', // white in dark mode too, so QR codes scan
  shadow:
    'inset 0 1px 0 light-dark(transparent, rgba(255,255,255,.035)), 0 1px 2px light-dark(rgba(18,18,28,.04), rgba(0,0,0,.35)), 0 8px 24px light-dark(rgba(18,18,28,.05), rgba(0,0,0,.3))',
  liftShadow: '0 1px 2px light-dark(rgba(0,0,0,.12), rgba(0,0,0,.45))',
  popShadow: '0 12px 32px light-dark(rgba(0,0,0,.18), rgba(0,0,0,.6))',
  overlay: 'light-dark(rgba(10,10,14,.45), rgba(0,0,0,.6))',
});

export const chart = stylex.defineVars({
  c1: '#3b82f6',
  c2: '#10b981',
  c3: '#f59e0b',
  c4: '#8b5cf6',
  c5: '#ef4444',
  c6: '#14b8a6',
  c7: '#ec4899',
  c8: '#64748b',
});

/** Set per agent with hueTheme() (theme/hues.ts). */
export const agent = stylex.defineVars({
  hue: '#64748b',
});

export const space = stylex.defineVars({
  xxxs: '2px',
  xxs: '4px',
  xs: '6px',
  sm: '8px',
  md: '10px',
  lg: '12px',
  xl: '14px',
  xxl: '16px',
  xxxl: '20px',
  huge: '24px',
});

export const text = stylex.defineVars({
  xxs: '11px',
  xs: '12px',
  sm: '12.5px',
  md: '13px',
  base: '13.5px',
  body: '14.5px',
  lg: '16px',
  xl: '20px',
  xxl: '24px',
  display: '30px',
});

export const radius = stylex.defineVars({
  xs: '6px',
  sm: '8px',
  md: '10px',
  lg: '12px',
  xl: '14px',
  xxl: '16px',
  pill: '99px',
});

export const media = stylex.defineConsts({
  nav: '@media (max-width: 900px)',
  narrow: '@media (max-width: 760px)',
  table: '@media (max-width: 720px)',
  phone: '@media (max-width: 640px)',
});

export const font = stylex.defineVars({
  sans: 'Inter, ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
  mono: 'ui-monospace, SFMono-Regular, Menlo, Consolas, monospace',
});

import * as stylex from '@stylexjs/stylex';

/**
 * Control room: graphite (dark) or drafting paper (light), hairlines instead of shadows, and colour only for meaning:
 * amber = act (brand, primary, current, needs you), steel = running / live, green = ok, coral = broken.
 * light-dark(light, dark): the document's color-scheme (theme/mode.ts) picks one.
 */
export const colors = stylex.defineVars({
  bg: 'light-dark(#ecebe7, #121417)',
  panel: 'light-dark(#f7f6f3, #171a1e)',
  raised: 'light-dark(#fbfaf8, #1c2025)',
  sunk: 'light-dark(#e4e3de, #0e1013)',
  hover: 'light-dark(#e6e5e0, #22272d)',
  fg: 'light-dark(#15171a, #e6e8eb)',
  muted: 'light-dark(#51565e, #a2a9b3)',
  faint: 'light-dark(#7e838b, #6c737d)',
  line: 'light-dark(#d4d3cc, #2a2e35)',
  line2: 'light-dark(#bdbcb4, #3a3f48)',
  accent: 'light-dark(#a35d00, #f2a93b)',
  accentFg: 'light-dark(#ffffff, #1a1406)',
  accentSoft: 'light-dark(#f4e4c6, #2e2412)',
  info: 'light-dark(#2d6394, #8fb3d9)',
  infoSoft: 'light-dark(#dbe6f0, #17222d)',
  ok: 'light-dark(#1b7843, #6fcf97)',
  okSoft: 'light-dark(#dbede1, #13261b)',
  warn: 'light-dark(#a35d00, #f2a93b)',
  warnSoft: 'light-dark(#f4e4c6, #2e2412)',
  bad: 'light-dark(#bf3626, #ff6b57)',
  badSoft: 'light-dark(#f6ddd8, #2f1714)',
  idleSoft: 'light-dark(#e3e2dc, #1d2126)',
  onFill: '#ffffff', // text on a coloured fill
  paper: '#ffffff', // white in dark mode too, so QR codes scan
  // panels sit on hairlines, not shadows; only things that float (menus, dialogs, toasts) cast one
  shadow: 'none',
  liftShadow: 'none',
  hoverShadow: 'none',
  popShadow:
    '0 16px 40px light-dark(rgba(20,20,18,.2), rgba(0,0,0,.6)), 0 0 0 1px light-dark(rgba(20,20,18,.08), rgba(255,255,255,.04))',
  overlay: 'light-dark(rgba(24,24,22,.35), rgba(0,0,0,.6))',
});

export const chart = stylex.defineVars({
  c1: '#8fb3d9',
  c2: '#6fcf97',
  c3: '#f2a93b',
  c4: '#b39ddb',
  c5: '#ff6b57',
  c6: '#4fb3a9',
  c7: '#e88fb0',
  c8: '#8b929c',
});

/** Set per agent with hueTheme() (theme/hues.ts). */
export const agent = stylex.defineVars({
  hue: '#8b929c',
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
  giant: '32px',
});

export const text = stylex.defineVars({
  xxs: '11px',
  xs: '12px',
  sm: '12.5px',
  md: '13px',
  base: '13.5px',
  body: '14px',
  lg: '16px',
  xl: '19px',
  xxl: '24px',
  display: '30px',
  hero: '38px',
});

/** Nearly square: an instrument, not a toy. */
export const radius = stylex.defineVars({
  xs: '2px',
  sm: '2px',
  md: '3px',
  lg: '4px',
  xl: '4px',
  xxl: '6px',
  pill: '3px',
});

export const motion = stylex.defineConsts({
  settle: 'cubic-bezier(0.2, 0, 0, 1)',
  spring: 'cubic-bezier(0.2, 0, 0, 1)',
  still: '@media (prefers-reduced-motion: reduce)',
});

export const media = stylex.defineConsts({
  nav: '@media (max-width: 900px)',
  narrow: '@media (max-width: 760px)',
  table: '@media (max-width: 720px)',
  phone: '@media (max-width: 640px)',
  wide: '@media (min-width: 1280px)',
});

export const font = stylex.defineVars({
  sans: '"IBM Plex Sans", ui-sans-serif, -apple-system, "Segoe UI", Roboto, sans-serif',
  display: '"IBM Plex Sans Condensed", "IBM Plex Sans", ui-sans-serif, sans-serif',
  mono: '"IBM Plex Mono", ui-monospace, SFMono-Regular, Menlo, Consolas, monospace',
});

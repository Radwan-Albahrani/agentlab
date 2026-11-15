import * as stylex from '@stylexjs/stylex';

/** light-dark(light, dark): the document's color-scheme (theme/mode.ts) picks one. */
export const colors = stylex.defineVars({
  bg: 'light-dark(#f4f4f1, #07080b)',
  panel: 'light-dark(#ffffff, #101116)',
  raised: 'light-dark(#fbfbf9, #15161c)',
  sunk: 'light-dark(#eeeeea, #0b0c10)',
  hover: 'light-dark(#ecece7, #1b1c23)',
  fg: 'light-dark(#121316, #f1f1f4)',
  muted: 'light-dark(#5b5c64, #a6a7b0)',
  faint: 'light-dark(#8a8b93, #6f707a)',
  line: 'light-dark(#e6e5df, #1f2028)',
  line2: 'light-dark(#d9d8d1, #2d2e38)',
  accent: 'light-dark(#3654f5, #8ea3ff)',
  accentFg: 'light-dark(#ffffff, #07080b)',
  accentSoft: 'light-dark(#e8ecff, #171d3a)',
  ok: 'light-dark(#13803c, #46e08a)',
  okSoft: 'light-dark(#e2f5e8, #0d2418)',
  warn: 'light-dark(#b45309, #fbbf24)',
  warnSoft: 'light-dark(#fcefd8, #2a210b)',
  bad: 'light-dark(#c42b2b, #ff7a7a)',
  badSoft: 'light-dark(#fbe6e5, #2e1214)',
  idleSoft: 'light-dark(#efefeb, #1a1b21)',
  onFill: '#ffffff', // text on a coloured fill
  paper: '#ffffff', // white in dark mode too, so QR codes scan
  // the 1px top highlight sells depth in dark mode; light mode leans on the soft drop
  shadow:
    'inset 0 1px 0 light-dark(rgba(255,255,255,.7), rgba(255,255,255,.045)), 0 1px 2px light-dark(rgba(18,18,28,.05), rgba(0,0,0,.4)), 0 10px 30px -12px light-dark(rgba(18,18,28,.12), rgba(0,0,0,.55))',
  liftShadow: '0 1px 2px light-dark(rgba(0,0,0,.12), rgba(0,0,0,.45))',
  hoverShadow:
    'inset 0 1px 0 light-dark(rgba(255,255,255,.7), rgba(255,255,255,.06)), 0 2px 4px light-dark(rgba(18,18,28,.06), rgba(0,0,0,.4)), 0 18px 40px -14px light-dark(rgba(18,18,28,.22), rgba(0,0,0,.7))',
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
  giant: '32px',
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
  xxl: '26px',
  display: '34px',
  hero: '40px',
});

export const radius = stylex.defineVars({
  xs: '6px',
  sm: '8px',
  md: '10px',
  lg: '13px',
  xl: '18px',
  xxl: '22px',
  pill: '99px',
});

/** Motion: one settle curve everywhere (fast start, soft landing), so the whole app moves alike. */
export const motion = stylex.defineConsts({
  settle: 'cubic-bezier(0.32, 0.72, 0, 1)',
  spring: 'cubic-bezier(0.34, 1.56, 0.64, 1)',
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
  sans: 'Geist, Inter, ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
  mono: '"Geist Mono", ui-monospace, SFMono-Regular, Menlo, Consolas, monospace',
});

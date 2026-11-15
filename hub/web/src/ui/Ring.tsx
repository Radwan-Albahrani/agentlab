import * as stylex from '@stylexjs/stylex';
import type { ReactNode } from 'react';
import { Link } from 'react-router';
import { colors, motion, radius, space, text } from '../theme/tokens.stylex';
import { useTween } from './motion';

const R = 30;
const C = 2 * Math.PI * R;

const styles = stylex.create({
  tile: {
    display: 'flex',
    alignItems: 'center',
    gap: space.xxl,
    paddingBlock: space.xxl,
    paddingInline: space.xxxl,
    borderRadius: radius.xl,
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: colors.line,
    backgroundColor: colors.panel,
    boxShadow: colors.shadow,
    minWidth: 0,
    transitionProperty: 'transform, box-shadow, border-color',
    transitionDuration: '260ms',
    transitionTimingFunction: motion.settle,
  },
  // inside another panel: no card of its own
  bare: {
    paddingBlock: space.sm,
    paddingInline: 0,
    borderWidth: 0,
    backgroundColor: 'transparent',
    boxShadow: 'none',
    borderRadius: radius.md,
  },
  link: {
    borderColor: { default: colors.line, ':hover': colors.line2 },
    transform: { default: null, ':hover': 'translateY(-2px)', ':active': 'scale(.985)' },
    boxShadow: { default: colors.shadow, ':hover': colors.hoverShadow },
  },
  svg: { flexShrink: 0, transform: 'rotate(-90deg)' },
  track: { stroke: colors.sunk },
  ok: { stroke: colors.ok, color: colors.ok },
  warn: { stroke: colors.warn, color: colors.warn },
  bad: { stroke: colors.bad, color: colors.bad },
  label: { fontSize: text.sm, color: colors.muted, fontWeight: 550 },
  value: { fontSize: text.xxl, fontWeight: 700, letterSpacing: '-.03em', fontVariantNumeric: 'tabular-nums', lineHeight: 1.2 },
  sub: { fontSize: text.sm, color: colors.faint },
  center: { position: 'relative', display: 'grid', placeItems: 'center' },
  pct: { position: 'absolute', fontSize: text.sm, fontWeight: 700, fontVariantNumeric: 'tabular-nums' },
});

const toneOf = (p: number) => (p >= 90 ? 'bad' : p >= 75 ? 'warn' : 'ok');

/** A gauge tile: a ring filled to `pct`, coloured by how full it is, with a label, a value and a line under it. */
export function Ring({
  pct,
  label,
  value,
  sub,
  to,
  bare,
}: {
  pct: number;
  label: string;
  value: ReactNode;
  sub?: ReactNode;
  to?: string;
  bare?: boolean;
}) {
  const p = Math.max(0, Math.min(100, pct));
  const shown = useTween(p, 900);
  const tone = styles[toneOf(p)];
  const inner = (
    <>
      <span {...stylex.props(styles.center)}>
        <svg width="72" height="72" viewBox="0 0 72 72" {...stylex.props(styles.svg)} aria-hidden="true">
          <circle cx="36" cy="36" r={R} fill="none" strokeWidth="7" {...stylex.props(styles.track)} />
          <circle
            cx="36"
            cy="36"
            r={R}
            fill="none"
            strokeWidth="7"
            strokeLinecap="round"
            strokeDasharray={C}
            strokeDashoffset={C * (1 - shown / 100)}
            {...stylex.props(tone)}
          />
        </svg>
        <span {...stylex.props(styles.pct, tone)}>{shown.toFixed(0)}%</span>
      </span>
      <div>
        <div {...stylex.props(styles.label)}>{label}</div>
        <div {...stylex.props(styles.value)}>{value}</div>
        {sub && <div {...stylex.props(styles.sub)}>{sub}</div>}
      </div>
    </>
  );
  return to ? (
    <Link to={to} {...stylex.props(styles.tile, styles.link, bare && styles.bare)}>
      {inner}
    </Link>
  ) : (
    <div {...stylex.props(styles.tile, bare && styles.bare)}>{inner}</div>
  );
}

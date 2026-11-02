import * as stylex from '@stylexjs/stylex';
import type { ReactNode } from 'react';
import { Link } from 'react-router';
import { hueTheme } from '../theme/hues';
import { agent, colors, radius, space, text } from '../theme/tokens.stylex';
import { Icon } from './Icon';

export type Tone = 'ok' | 'warn' | 'bad' | 'info' | 'idle';

const pulse = stylex.keyframes({
  '0%': { boxShadow: '0 0 0 0 color-mix(in srgb, currentColor 45%, transparent)' },
  '70%': { boxShadow: '0 0 0 6px transparent' },
  '100%': { boxShadow: '0 0 0 0 transparent' },
});

const styles = stylex.create({
  count: {
    display: 'inline-grid',
    placeItems: 'center',
    minWidth: 20,
    height: 20,
    paddingInline: space.xs,
    borderRadius: radius.pill,
    fontSize: text.xxs,
    fontWeight: 700,
    backgroundColor: colors.bad,
    color: colors.onFill,
  },
  pill: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: space.xs,
    fontSize: text.xs,
    fontWeight: 600,
    paddingBlock: space.xxxs,
    paddingInline: space.md,
    borderRadius: radius.pill,
    whiteSpace: 'nowrap',
    backgroundColor: colors.idleSoft,
    color: colors.muted,
  },
  ok: { backgroundColor: colors.okSoft, color: colors.ok },
  warn: { backgroundColor: colors.warnSoft, color: colors.warn },
  bad: { backgroundColor: colors.badSoft, color: colors.bad },
  info: { backgroundColor: colors.accentSoft, color: colors.accent },
  idle: {},
  pillDot: { width: 7, height: 7, borderRadius: '50%', backgroundColor: 'currentColor' },
  pulsing: { animationName: pulse, animationDuration: '2s', animationIterationCount: 'infinite' },
  dot: { width: 7, height: 7, borderRadius: '50%', flexShrink: 0, display: 'inline-block' },
  dotOk: { backgroundColor: colors.ok },
  dotBad: { backgroundColor: colors.bad },
  meter: {
    height: 6,
    borderRadius: radius.pill,
    backgroundColor: colors.sunk,
    overflow: 'hidden',
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: colors.line,
  },
  meterBig: { height: 12 },
  fill: (pct: number) => ({
    display: 'block',
    height: '100%',
    borderRadius: radius.pill,
    width: `${pct}%`,
    transition: 'width .4s',
  }),
  fillOk: { backgroundColor: colors.ok },
  fillWarn: { backgroundColor: colors.warn },
  fillBad: { backgroundColor: colors.bad },
  badge: {
    width: 36,
    height: 36,
    borderRadius: radius.md,
    display: 'inline-grid',
    placeItems: 'center',
    fontWeight: 700,
    fontSize: text.lg,
    color: colors.onFill,
    backgroundColor: agent.hue,
    flexShrink: 0,
  },
  badgeXs: { width: 20, height: 20, fontSize: text.xxs, borderRadius: radius.xs },
  badgeSm: { width: 24, height: 24, fontSize: text.xs, borderRadius: radius.sm },
  badgeXl: { width: 56, height: 56, fontSize: text.xxl, borderRadius: radius.xxl },
  badgePin: {
    position: 'absolute',
    right: -5,
    bottom: -5,
    width: 16,
    height: 16,
    fontSize: 9.5,
    borderRadius: radius.xs,
    boxShadow: `0 0 0 2px ${colors.panel}`,
  },
  badgePinLg: { width: 22, height: 22, fontSize: text.xs, borderRadius: radius.sm },
  avatar: {
    position: 'relative',
    width: 36,
    height: 36,
    borderRadius: radius.md,
    display: 'inline-grid',
    placeItems: 'center',
    flexShrink: 0,
    color: agent.hue,
    backgroundColor: `color-mix(in srgb, ${agent.hue} 16%, ${colors.panel})`,
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: `color-mix(in srgb, ${agent.hue} 35%, transparent)`,
  },
  avatarSm: { width: 30, height: 30, borderRadius: radius.sm },
  avatarLg: { width: 56, height: 56, borderRadius: radius.xxl },
  tag: {
    fontSize: text.xxs,
    fontWeight: 600,
    whiteSpace: 'nowrap',
    paddingBlock: space.xxxs,
    paddingInline: space.sm,
    borderRadius: radius.xs,
    backgroundColor: colors.sunk,
    color: colors.muted,
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: colors.line,
    verticalAlign: 1,
    marginInlineStart: space.xs,
  },
  chip: {
    fontSize: text.xs,
    fontWeight: 600,
    paddingBlock: space.xxxs,
    paddingInline: space.sm,
    borderRadius: radius.sm,
    backgroundColor: colors.sunk,
    color: colors.muted,
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: colors.line,
    display: 'inline-flex',
    alignItems: 'center',
    gap: space.xs,
  },
  chipLink: {
    color: { default: colors.muted, ':hover': colors.fg },
    borderColor: { default: colors.line, ':hover': colors.line2 },
  },
  chipWarn: { backgroundColor: colors.warnSoft, borderColor: 'transparent', color: colors.warn },
  chipAvatar: { paddingBlock: space.xxs, paddingInlineStart: space.xxs, paddingInlineEnd: space.md, gap: space.sm },
});

export function Pill({ tone = 'idle', dot, children }: { tone?: Tone; dot?: boolean; children: ReactNode }) {
  return (
    <span {...stylex.props(styles.pill, styles[tone])}>
      {dot && <i {...stylex.props(styles.pillDot, tone === 'ok' && styles.pulsing)} />}
      {children}
    </span>
  );
}

/** How many things need you here, as a small red number. */
export const Count = ({ n }: { n: number }) => <span {...stylex.props(styles.count)}>{n}</span>;

export const Dot = ({ ok }: { ok: boolean }) => <i {...stylex.props(styles.dot, ok ? styles.dotOk : styles.dotBad)} />;

/** A filled bar. `share`: a part of a whole (e.g. votes), so it never turns warn / bad when full. */
export function Meter({ pct, big, share }: { pct: number; big?: boolean; share?: boolean }) {
  const p = Math.max(0, Math.min(100, pct));
  return (
    <div {...stylex.props(styles.meter, big && styles.meterBig)}>
      <span
        {...stylex.props(
          styles.fill(Number(p.toFixed(1))),
          share ? styles.fillOk : p >= 90 ? styles.fillBad : p >= 75 ? styles.fillWarn : styles.fillOk,
        )}
      />
    </div>
  );
}

const BADGE_SIZE = { '': null, xs: styles.badgeXs, sm: styles.badgeSm, xl: styles.badgeXl };

/** An agent's letter in its colour. */
export const Badge = ({ name, size = '' }: { name: string; size?: keyof typeof BADGE_SIZE }) => (
  <span {...stylex.props(hueTheme(name), styles.badge, BADGE_SIZE[size])}>{name.charAt(0).toUpperCase()}</span>
);

/** A companion: a bot in its agent's colour, wearing the agent's badge. */
export function CompanionAvatar({ profile, size = '' }: { profile: string; size?: '' | 'sm' | 'lg' }) {
  return (
    <span {...stylex.props(hueTheme(profile), styles.avatar, size === 'sm' && styles.avatarSm, size === 'lg' && styles.avatarLg)}>
      <Icon name="bot" size={size === 'lg' ? 28 : size === 'sm' ? 16 : 19} />
      <span {...stylex.props(styles.badge, styles.badgePin, size === 'lg' && styles.badgePinLg)}>
        {profile.charAt(0).toUpperCase()}
      </span>
    </span>
  );
}

export const Tag = ({ children }: { children: ReactNode }) => <span {...stylex.props(styles.tag)}>{children}</span>;

export function Chip({ to, warn, avatar, children }: { to?: string; warn?: boolean; avatar?: boolean; children: ReactNode }) {
  const props = stylex.props(styles.chip, !!to && styles.chipLink, warn && styles.chipWarn, avatar && styles.chipAvatar);
  return to ? (
    <Link {...props} to={to}>
      {children}
    </Link>
  ) : (
    <span {...props}>{children}</span>
  );
}

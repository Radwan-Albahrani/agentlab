import * as stylex from '@stylexjs/stylex';
import type { ReactNode } from 'react';
import { Link } from 'react-router';
import { hueTheme } from '../theme/hues';
import { agent, colors, motion, radius, space, text } from '../theme/tokens.stylex';
import { Icon } from './Icon';
import { Card } from './Card';
import { Num } from './motion';
import { Badge } from './status';
import { Eyebrow } from './text';

const shimmer = stylex.keyframes({ from: { backgroundPosition: '200% 0' }, to: { backgroundPosition: '-200% 0' } });

const styles = stylex.create({
  head: { display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', gap: space.xl, flexWrap: 'wrap' },
  h1: {
    fontSize: text.display,
    fontWeight: 700,
    lineHeight: 1.1,
    letterSpacing: '-.03em',
    marginBlockStart: space.xxxs,
    marginBlockEnd: space.xs,
    marginInline: 0,
    textWrap: 'balance',
    display: 'flex',
    alignItems: 'center',
    gap: space.md,
    flexWrap: 'wrap',
  },
  lede: { margin: 0, color: colors.muted, maxWidth: '68ch', fontSize: text.body },
  actions: { display: 'flex', gap: space.sm, flexWrap: 'wrap' },
  section: { display: 'grid', gap: space.lg, minWidth: 0, scrollMarginTop: 80 },
  sectionHead: { display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', gap: space.lg, flexWrap: 'wrap' },
  h2: { fontSize: text.xl, fontWeight: 650, margin: 0, letterSpacing: '-.02em' },
  sub: { marginBlockStart: space.xxxs, marginBlockEnd: '0', marginInline: 0, color: colors.muted, fontSize: text.md },
  hero: {
    position: 'relative',
    overflow: 'hidden',
    display: 'flex',
    gap: space.xxxl,
    alignItems: 'center',
    padding: space.huge,
    borderRadius: radius.xxl,
    flexWrap: 'wrap',
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: `color-mix(in srgb, ${agent.hue} 28%, ${colors.line})`,
    boxShadow: colors.shadow,
    backgroundColor: colors.panel,
    backgroundImage: `radial-gradient(120% 140% at 0% 0%, color-mix(in srgb, ${agent.hue} 24%, transparent), transparent 55%), radial-gradient(80% 120% at 100% 100%, color-mix(in srgb, ${agent.hue} 9%, transparent), transparent 60%)`,
  },
  heroText: { flex: '1', minWidth: 220 },
  heroTitle: {
    fontSize: text.display,
    fontWeight: 700,
    lineHeight: 1.1,
    marginBlock: space.xxs,
    marginInline: 0,
    display: 'flex',
    alignItems: 'center',
    gap: space.md,
    flexWrap: 'wrap',
    letterSpacing: '-.03em',
  },
  crumb: { display: 'inline-flex', alignItems: 'center', gap: space.xs, fontSize: text.sm, fontWeight: 600, color: colors.muted },
  crumbLink: { display: 'inline-flex', alignItems: 'center', gap: space.xs, color: { default: colors.fg, ':hover': agent.hue } },
  stat: {
    position: 'relative',
    overflow: 'hidden',
    backgroundColor: colors.panel,
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: colors.line,
    borderRadius: radius.xl,
    paddingBlock: space.xxl,
    paddingInline: space.xxxl,
    display: 'grid',
    gap: space.xxs,
    boxShadow: colors.shadow,
    transitionProperty: 'transform, box-shadow, border-color',
    transitionDuration: '260ms',
    transitionTimingFunction: motion.settle,
  },
  statLink: {
    borderColor: { default: colors.line, ':hover': colors.line2 },
    transform: { default: null, ':hover': 'translateY(-2px)', ':active': 'scale(.985)' },
    boxShadow: { default: colors.shadow, ':hover': colors.hoverShadow },
  },
  // a thin line of the number's tone along the top edge, fading out
  statGlow: {
    position: 'absolute',
    insetInline: 0,
    top: 0,
    height: 2,
    backgroundImage: 'linear-gradient(90deg, currentColor, transparent 75%)',
    pointerEvents: 'none',
  },
  statLabel: { fontSize: text.sm, color: colors.muted, fontWeight: 550 },
  statValue: {
    fontSize: text.display,
    fontWeight: 700,
    letterSpacing: '-.035em',
    lineHeight: 1.1,
    fontVariantNumeric: 'tabular-nums',
  },
  statSub: { fontSize: text.sm, color: colors.faint, minHeight: 18 },
  ok: { color: colors.ok },
  warn: { color: colors.warn },
  bad: { color: colors.bad },
  info: { color: colors.accent },
  idle: {},
  small: { fontSize: text.body, color: colors.faint, fontWeight: 500, letterSpacing: 0, marginInlineStart: 2 },
  empty: {
    display: 'flex',
    gap: space.xl,
    alignItems: 'center',
    padding: space.xxxl,
    color: colors.muted,
  },
  emptyIcon: {
    color: colors.ok,
    display: 'grid',
    placeItems: 'center',
    width: 40,
    height: 40,
    flexShrink: 0,
    borderRadius: radius.lg,
    backgroundColor: colors.okSoft,
  },
  emptyTitle: { color: colors.fg, fontWeight: 600 },
  emptyText: { marginBlockStart: space.xxxs, marginBlockEnd: '0', marginInline: 0, fontSize: text.md },
  loading: { display: 'grid', gap: space.huge },
  loadingRow: { display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: space.lg },
  bone: (height: number, width: string) => ({
    display: 'block',
    height,
    width,
    borderRadius: radius.xl,
    backgroundImage: `linear-gradient(90deg, ${colors.sunk} 0%, ${colors.hover} 50%, ${colors.sunk} 100%)`,
    backgroundSize: '200% 100%',
    animationName: shimmer,
    animationDuration: '1.6s',
    animationTimingFunction: 'linear',
    animationIterationCount: 'infinite',
  }),
});

export function PageHead({
  title,
  sub,
  right,
  eyebrow,
}: {
  title: ReactNode;
  sub?: ReactNode;
  right?: ReactNode;
  eyebrow?: ReactNode;
}) {
  return (
    <header {...stylex.props(styles.head)}>
      <div>
        {eyebrow && <Eyebrow>{eyebrow}</Eyebrow>}
        <h1 {...stylex.props(styles.h1)}>{title}</h1>
        {sub && <p {...stylex.props(styles.lede)}>{sub}</p>}
      </div>
      {right && <div {...stylex.props(styles.actions)}>{right}</div>}
    </header>
  );
}

export function Section({
  title,
  sub,
  right,
  id,
  children,
}: {
  title: string;
  sub?: ReactNode;
  right?: ReactNode;
  id?: string;
  children: ReactNode;
}) {
  return (
    <section {...stylex.props(styles.section)} id={id}>
      <div {...stylex.props(styles.sectionHead)}>
        <div>
          <h2 {...stylex.props(styles.h2)}>{title}</h2>
          {sub && <p {...stylex.props(styles.sub)}>{sub}</p>}
        </div>
        {right && <div {...stylex.props(styles.actions)}>{right}</div>}
      </div>
      {children}
    </section>
  );
}

export function Hero({
  profile,
  avatar,
  title,
  sub,
  actions,
}: {
  profile: string;
  avatar: ReactNode;
  title: ReactNode;
  sub: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <header {...stylex.props(hueTheme(profile), styles.hero)}>
      {avatar}
      <div {...stylex.props(styles.heroText)}>
        <h1 {...stylex.props(styles.heroTitle)}>{title}</h1>
        <p {...stylex.props(styles.lede)}>{sub}</p>
      </div>
      {actions && <div {...stylex.props(styles.actions)}>{actions}</div>}
    </header>
  );
}

export function Crumb({ profile, here }: { profile: string; here: string }) {
  return (
    <div {...stylex.props(hueTheme(profile), styles.crumb)}>
      <Link {...stylex.props(styles.crumbLink)} to={`/agents/${profile}`}>
        <Badge name={profile} size="xs" />
        {profile}
      </Link>
      <span>›</span>
      <span>{here}</span>
    </div>
  );
}

type StatTone = 'ok' | 'warn' | 'bad' | 'info' | 'idle';

/** `of` adds a quieter "/ total" or unit after the number; a number value counts up and glides on change. */
export function Stat({
  label,
  value,
  of,
  sub,
  tone = 'idle',
  to,
}: {
  label: string;
  value: ReactNode;
  of?: ReactNode;
  sub?: ReactNode;
  tone?: StatTone;
  to?: string | null;
}) {
  const inner = (
    <>
      {tone !== 'idle' && <span {...stylex.props(styles.statGlow, styles[tone])} />}
      <div {...stylex.props(styles.statLabel)}>{label}</div>
      <div {...stylex.props(styles.statValue, styles[tone])}>
        {typeof value === 'number' ? <Num value={value} /> : value}
        {of && <small {...stylex.props(styles.small)}>{of}</small>}
      </div>
      <div {...stylex.props(styles.statSub)}>{sub}</div>
    </>
  );
  return to ? (
    <Link {...stylex.props(styles.stat, styles.statLink)} to={to}>
      {inner}
    </Link>
  ) : (
    <div {...stylex.props(styles.stat)}>{inner}</div>
  );
}

export function Empty({ title, text, icon = 'check' }: { title: string; text?: string; icon?: string }) {
  return (
    <div {...stylex.props(styles.empty)}>
      <span {...stylex.props(styles.emptyIcon)}>
        <Icon name={icon} size={20} />
      </span>
      <div>
        <b {...stylex.props(styles.emptyTitle)}>{title}</b>
        {text && <p {...stylex.props(styles.emptyText)}>{text}</p>}
      </div>
    </div>
  );
}

export const EmptyCard = (props: { title: string; text?: string; icon?: string }) => (
  <Card>
    <Empty {...props} />
  </Card>
);

/** A skeleton of a typical page (title, a row of numbers, a block) while the first answer loads. */
export function Loading() {
  return (
    <div {...stylex.props(styles.loading)} aria-busy="true" aria-label="Loading">
      <span {...stylex.props(styles.bone(40, '38%'))} />
      <div {...stylex.props(styles.loadingRow)}>
        {[0, 1, 2].map((i) => (
          <span key={i} {...stylex.props(styles.bone(112, '100%'))} />
        ))}
      </div>
      <span {...stylex.props(styles.bone(260, '100%'))} />
    </div>
  );
}

import * as stylex from '@stylexjs/stylex';
import type { ReactNode } from 'react';
import { Link } from 'react-router';
import { hueTheme } from '../theme/hues';
import { agent, colors, radius, space, text } from '../theme/tokens.stylex';
import { Icon } from './Icon';
import { Card } from './Card';
import { Badge } from './status';
import { Eyebrow } from './text';

const blink = stylex.keyframes({ '50%': { opacity: 0.25 } });

const styles = stylex.create({
  head: { display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', gap: space.xl, flexWrap: 'wrap' },
  h1: {
    fontSize: text.xxl,
    lineHeight: 1.15,
    letterSpacing: '-.02em',
    marginBlockStart: space.xxxs,
    marginBlockEnd: space.xxs,
    marginInline: 0,
    textWrap: 'balance',
    display: 'flex',
    alignItems: 'center',
    gap: space.md,
    flexWrap: 'wrap',
  },
  lede: { margin: 0, color: colors.muted, maxWidth: '68ch' },
  actions: { display: 'flex', gap: space.sm, flexWrap: 'wrap' },
  section: { display: 'grid', gap: space.lg, minWidth: 0, scrollMarginTop: 80 },
  sectionHead: { display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', gap: space.lg, flexWrap: 'wrap' },
  h2: { fontSize: text.lg, margin: 0, letterSpacing: '-.01em' },
  sub: { marginBlockStart: space.xxxs, marginBlockEnd: '0', marginInline: 0, color: colors.muted, fontSize: text.md },
  hero: {
    display: 'flex',
    gap: space.xxl,
    alignItems: 'center',
    padding: space.xxl,
    borderRadius: radius.xl,
    flexWrap: 'wrap',
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: colors.line,
    borderTopWidth: 3,
    borderTopColor: agent.hue,
    backgroundImage: `linear-gradient(135deg, color-mix(in srgb, ${agent.hue} 14%, ${colors.panel}), ${colors.panel} 60%)`,
  },
  heroText: { flex: '1', minWidth: 220 },
  heroTitle: {
    fontSize: text.xxl,
    marginBlock: space.xxxs,
    marginInline: 0,
    display: 'flex',
    alignItems: 'center',
    gap: space.md,
    flexWrap: 'wrap',
    letterSpacing: '-.02em',
  },
  crumb: { display: 'inline-flex', alignItems: 'center', gap: space.xs, fontSize: text.sm, fontWeight: 600, color: colors.muted },
  crumbLink: { display: 'inline-flex', alignItems: 'center', gap: space.xs, color: { default: colors.fg, ':hover': agent.hue } },
  stat: {
    backgroundColor: colors.panel,
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: colors.line,
    borderRadius: radius.xl,
    paddingBlock: space.xl,
    paddingInline: space.xxl,
    display: 'grid',
    gap: space.xxxs,
    boxShadow: colors.shadow,
  },
  statLink: { borderColor: { default: colors.line, ':hover': colors.line2 } },
  statLabel: { fontSize: text.sm, color: colors.muted, fontWeight: 500 },
  statValue: {
    fontSize: text.xxl,
    fontWeight: 650,
    letterSpacing: '-.02em',
    lineHeight: 1.25,
    fontVariantNumeric: 'tabular-nums',
  },
  statSub: { fontSize: text.sm, color: colors.faint, minHeight: 18 },
  ok: { color: colors.ok },
  warn: { color: colors.warn },
  bad: { color: colors.bad },
  info: { color: colors.accent },
  idle: {},
  small: { fontSize: text.body, color: colors.faint, fontWeight: 500 },
  empty: {
    display: 'flex',
    gap: space.lg,
    alignItems: 'center',
    paddingBlock: space.xxl,
    paddingInline: space.xxl,
    color: colors.muted,
  },
  emptyIcon: { color: colors.ok, display: 'flex' },
  emptyTitle: { color: colors.fg, fontWeight: 600 },
  emptyText: { marginBlockStart: space.xxxs, marginBlockEnd: '0', marginInline: 0, fontSize: text.md },
  loading: { display: 'flex', gap: space.xs, paddingBlock: 40, justifyContent: 'center' },
  loadingDot: (delay: string) => ({
    width: 8,
    height: 8,
    borderRadius: '50%',
    backgroundColor: colors.faint,
    animationName: blink,
    animationDuration: '1s',
    animationIterationCount: 'infinite',
    animationDelay: delay,
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

/** `of` adds a quieter "/ total" or unit after the number. */
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
      <div {...stylex.props(styles.statLabel)}>{label}</div>
      <div {...stylex.props(styles.statValue, styles[tone])}>
        {value}
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
        <Icon name={icon} size={22} />
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

export function Loading() {
  return (
    <div {...stylex.props(styles.loading)} aria-busy="true">
      {['0s', '.15s', '.3s'].map((d) => (
        <span key={d} {...stylex.props(styles.loadingDot(d))} />
      ))}
    </div>
  );
}

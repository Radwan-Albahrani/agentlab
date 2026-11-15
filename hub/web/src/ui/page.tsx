import * as stylex from '@stylexjs/stylex';
import type { ReactNode } from 'react';
import { Link } from 'react-router';
import { hueTheme } from '../theme/hues';
import { colors, font, media, radius, space, text } from '../theme/tokens.stylex';
import { Icon } from './Icon';
import { Card } from './Card';
import { Num } from './motion';
import { Badge } from './status';

const pulse = stylex.keyframes({ '50%': { opacity: 0.45 } });

const styles = stylex.create({
  head: { display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', gap: space.xl, flexWrap: 'wrap' },
  headMain: { display: 'flex', alignItems: 'center', gap: space.xl, minWidth: 0 },
  headIcon: {
    width: 44,
    height: 44,
    flexShrink: 0,
    display: 'grid',
    placeItems: 'center',
    borderRadius: radius.lg,
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: colors.line2,
    backgroundColor: colors.panel,
    color: colors.accent,
  },
  kicker: {
    fontFamily: font.mono,
    fontSize: text.xs,
    letterSpacing: '.1em',
    textTransform: 'uppercase',
    color: colors.faint,
  },
  h1: {
    fontFamily: font.display,
    fontSize: text.display,
    fontWeight: 600,
    lineHeight: 1.1,
    letterSpacing: '-.01em',
    marginBlockStart: space.xxs,
    marginBlockEnd: space.xs,
    marginInline: 0,
    textWrap: 'balance',
    display: 'flex',
    alignItems: 'center',
    gap: space.md,
    flexWrap: 'wrap',
  },
  lede: { margin: 0, color: colors.muted, maxWidth: '72ch', fontSize: text.body },
  actions: { display: 'flex', gap: space.sm, flexWrap: 'wrap' },
  section: { display: 'grid', gap: space.lg, minWidth: 0, scrollMarginTop: 80 },
  // a mono label on a hairline rule, its count or action at the right
  sectionHead: { display: 'flex', alignItems: 'center', gap: space.lg, flexWrap: 'wrap', minHeight: 30 },
  rule: { flex: '1', minWidth: 24, height: 1, backgroundColor: colors.line },
  h2: {
    margin: 0,
    fontFamily: font.mono,
    fontSize: text.xs,
    fontWeight: 600,
    letterSpacing: '.12em',
    textTransform: 'uppercase',
    color: colors.fg,
  },
  sectionTitle: { display: 'flex', alignItems: 'center', gap: space.sm, color: colors.faint },
  sub: { margin: 0, color: colors.faint, fontSize: text.sm },
  hero: {
    display: 'flex',
    gap: space.xxxl,
    alignItems: 'center',
    paddingBlock: space.xxxl,
    paddingInline: space.huge,
    borderRadius: radius.xl,
    flexWrap: 'wrap',
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: colors.line,
    backgroundColor: colors.panel,
  },
  heroText: { flex: '1', minWidth: 220 },
  heroTitle: {
    fontFamily: font.display,
    fontSize: text.display,
    fontWeight: 600,
    lineHeight: 1.1,
    marginBlock: space.xxs,
    marginInline: 0,
    display: 'flex',
    alignItems: 'center',
    gap: space.md,
    flexWrap: 'wrap',
  },
  crumb: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: space.xs,
    fontFamily: font.mono,
    fontSize: text.xs,
    letterSpacing: '.06em',
    textTransform: 'uppercase',
    color: colors.faint,
  },
  crumbLink: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: space.xs,
    color: { default: colors.muted, ':hover': colors.fg },
  },
  // a cell of a number strip (StatGrid draws the hairlines between cells)
  stat: {
    position: 'relative',
    backgroundColor: colors.panel,
    boxShadow: `0 0 0 1px ${colors.line}`,
    paddingBlock: space.xl,
    paddingInline: space.xxl,
    display: 'grid',
    gap: space.xxs,
    alignContent: 'start',
    transitionProperty: 'background-color',
    transitionDuration: '140ms',
  },
  statLink: { backgroundColor: { default: colors.panel, ':hover': colors.hover } },
  statLabel: { fontSize: text.sm, color: colors.muted, display: 'flex', alignItems: 'center', gap: space.xs },
  statValue: {
    fontFamily: font.mono,
    fontSize: { default: text.display, [media.phone]: text.xxl },
    fontWeight: 500,
    letterSpacing: '-.03em',
    lineHeight: 1.1,
    fontVariantNumeric: 'tabular-nums',
  },
  statSub: { fontSize: text.sm, color: colors.faint, minHeight: 18 },
  ok: { color: colors.ok },
  warn: { color: colors.warn },
  bad: { color: colors.bad },
  info: { color: colors.info },
  idle: {},
  toneDot: { width: 7, height: 7, backgroundColor: 'currentColor', display: 'inline-block' },
  small: { fontSize: text.base, color: colors.faint, fontWeight: 400, letterSpacing: 0, marginInlineStart: 3 },
  empty: { display: 'flex', gap: space.xl, alignItems: 'center', padding: space.xxxl, color: colors.muted },
  emptyIcon: {
    color: colors.faint,
    display: 'grid',
    placeItems: 'center',
    width: 36,
    height: 36,
    flexShrink: 0,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderStyle: 'dashed',
    borderColor: colors.line2,
  },
  emptyOk: { color: colors.ok, borderStyle: 'solid', borderColor: `color-mix(in srgb, ${colors.ok} 40%, transparent)` },
  emptyTitle: { color: colors.fg, fontWeight: 600 },
  emptyText: { marginBlockStart: space.xxxs, marginBlockEnd: '0', marginInline: 0, fontSize: text.md },
  loading: { display: 'grid', gap: space.xxl },
  loadingRow: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))',
    gap: 1,
    backgroundColor: colors.line,
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: colors.line,
  },
  bone: (height: number, width: string) => ({
    display: 'block',
    height,
    width,
    borderRadius: radius.md,
    backgroundColor: colors.panel,
    animationName: pulse,
    animationDuration: '1.4s',
    animationIterationCount: 'infinite',
  }),
});

export function PageHead({
  title,
  sub,
  right,
  eyebrow,
  icon,
}: {
  title: ReactNode;
  sub?: ReactNode;
  right?: ReactNode;
  eyebrow?: ReactNode;
  icon?: string;
}) {
  return (
    <header {...stylex.props(styles.head)}>
      <div {...stylex.props(styles.headMain)}>
        {icon && (
          <span {...stylex.props(styles.headIcon)}>
            <Icon name={icon} size={22} />
          </span>
        )}
        <div>
          {eyebrow && <div {...stylex.props(styles.kicker)}>{eyebrow}</div>}
          <h1 {...stylex.props(styles.h1)}>{title}</h1>
          {sub && <p {...stylex.props(styles.lede)}>{sub}</p>}
        </div>
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
  icon,
  children,
}: {
  title: string;
  sub?: ReactNode;
  right?: ReactNode;
  id?: string;
  icon?: string;
  children: ReactNode;
}) {
  return (
    <section {...stylex.props(styles.section)} id={id}>
      <div {...stylex.props(styles.sectionHead)}>
        <div {...stylex.props(styles.sectionTitle)}>
          {icon && <Icon name={icon} size={14} />}
          <h2 {...stylex.props(styles.h2)}>{title}</h2>
        </div>
        {sub && <p {...stylex.props(styles.sub)}>{sub}</p>}
        <span {...stylex.props(styles.rule)} />
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
      <span>/</span>
      <span>{here}</span>
    </div>
  );
}

type StatTone = 'ok' | 'warn' | 'bad' | 'info' | 'idle';

/** A cell of a number strip (put several in a StatGrid). `of` adds a quieter "/ total" or unit after the number. */
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
      <div {...stylex.props(styles.statLabel)}>
        {tone !== 'idle' && <i {...stylex.props(styles.toneDot, styles[tone])} />}
        {label}
      </div>
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
      <span {...stylex.props(styles.emptyIcon, icon === 'check' && styles.emptyOk)}>
        <Icon name={icon} size={18} />
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

/** A skeleton of a typical page (title, a number strip, a panel) while the first answer loads. */
export function Loading() {
  return (
    <div {...stylex.props(styles.loading)} aria-busy="true" aria-label="Loading">
      <span {...stylex.props(styles.bone(34, '34%'))} />
      <div {...stylex.props(styles.loadingRow)}>
        {[0, 1, 2, 3].map((i) => (
          <span key={i} {...stylex.props(styles.bone(92, '100%'))} />
        ))}
      </div>
      <span {...stylex.props(styles.bone(240, '100%'))} />
    </div>
  );
}

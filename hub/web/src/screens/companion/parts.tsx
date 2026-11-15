import * as stylex from '@stylexjs/stylex';
import type { ReactNode } from 'react';
import { colors, font, radius, space, text } from '../../theme/tokens.stylex';
import { Icon } from '../../ui/Icon';

const run = stylex.keyframes({ to: { backgroundPosition: '20px 0' } });
const blink = stylex.keyframes({ '50%': { opacity: 0 } });

const styles = stylex.create({
  notice: {
    display: 'flex',
    alignItems: 'center',
    gap: space.lg,
    flexWrap: 'wrap',
    paddingBlock: space.lg,
    paddingInline: space.xxl,
    borderRadius: radius.xl,
    borderWidth: 1,
    borderStyle: 'solid',
    backgroundColor: colors.panel,
  },
  noticeWarn: { borderColor: `color-mix(in srgb, ${colors.warn} 55%, ${colors.line})` },
  noticeBad: { borderColor: `color-mix(in srgb, ${colors.bad} 55%, ${colors.line})` },
  noticeInfo: { borderColor: `color-mix(in srgb, ${colors.info} 45%, ${colors.line})` },
  noticeIcon: { width: 32, height: 32, flexShrink: 0, display: 'grid', placeItems: 'center', borderRadius: radius.lg },
  iconWarn: { backgroundColor: colors.warnSoft, color: colors.warn },
  iconBad: { backgroundColor: colors.badSoft, color: colors.bad },
  iconInfo: { backgroundColor: colors.infoSoft, color: colors.info },
  noticeText: { flexGrow: 1, flexShrink: 1, flexBasis: 260, minWidth: 0, overflowWrap: 'anywhere' },
  avatar: {
    display: 'inline-grid',
    placeItems: 'center',
    flexShrink: 0,
    borderRadius: '50%',
    objectFit: 'cover',
    fontFamily: font.mono,
    fontWeight: 600,
    color: colors.muted,
    backgroundColor: colors.raised,
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: colors.line2,
  },
  size: (px: number) => ({ width: `${px}px`, height: `${px}px`, fontSize: `${Math.round(px * 0.45)}px` }),
  ring: { boxShadow: `0 0 0 2px ${colors.panel}` },
  stack: { display: 'inline-flex', alignItems: 'center', flexShrink: 0 },
  overlap: { marginInlineStart: { default: -6, ':first-child': 0 } },
  more: { fontSize: text.xxs, letterSpacing: '-.02em' },
  mono: { fontFamily: font.mono, fontVariantNumeric: 'tabular-nums' },
  // the console's "work in progress": a dashed line that runs along the parent's bottom edge
  liveLine: {
    position: 'absolute',
    insetInline: 0,
    bottom: 0,
    height: 1,
    pointerEvents: 'none',
    backgroundImage: `repeating-linear-gradient(90deg, ${colors.info} 0 6px, transparent 6px 10px)`,
    backgroundSize: '20px 1px',
    animationName: run,
    animationDuration: '1s',
    animationTimingFunction: 'linear',
    animationIterationCount: 'infinite',
  },
  inline: { position: 'static', display: 'block', marginBlockStart: space.xs },
  block: {
    display: 'inline-block',
    width: 6,
    height: 11,
    flexShrink: 0,
    verticalAlign: -1,
    backgroundColor: colors.info,
    animationName: blink,
    animationDuration: '1s',
    animationTimingFunction: 'steps(1)',
    animationIterationCount: 'infinite',
  },
});

const NOTICE = {
  warn: [styles.noticeWarn, styles.iconWarn],
  bad: [styles.noticeBad, styles.iconBad],
  info: [styles.noticeInfo, styles.iconInfo],
} as const;

/** A hairline banner in its tone for something that needs a look, with its action at the end. */
export function Notice({
  tone,
  icon,
  action,
  children,
}: {
  tone: keyof typeof NOTICE;
  icon: string;
  action?: ReactNode;
  children: ReactNode;
}) {
  const [box, tile] = NOTICE[tone];
  return (
    <div {...stylex.props(styles.notice, box)}>
      <span {...stylex.props(styles.noticeIcon, tile)}>
        <Icon name={icon} size={17} />
      </span>
      <div {...stylex.props(styles.noticeText)}>{children}</div>
      {action}
    </div>
  );
}

/** Running dashed line; absolute along the parent's bottom edge, or `inline` as its own line. */
export const LiveLine = ({ inline }: { inline?: boolean }) => (
  <span {...stylex.props(styles.liveLine, inline && styles.inline)} aria-hidden="true" />
);

/** A blinking block cursor: working right now. */
export const Blink = () => <i {...stylex.props(styles.block)} aria-hidden="true" />;

/** Numbers, times and ids. */
export const Mono = ({ children }: { children: ReactNode }) => <span {...stylex.props(styles.mono)}>{children}</span>;

/** A person's round picture (people are round, agents square), or their initial when there is none. */
export function Avatar({ name, src, size = 22, ring }: { name: string; src?: string; size?: number; ring?: boolean }) {
  const look = stylex.props(styles.avatar, styles.size(size), ring && styles.ring);
  return src ? (
    <img {...look} src={src} alt="" title={name} loading="lazy" />
  ) : (
    <span {...look} title={name} aria-hidden="true">
      {name.charAt(0).toUpperCase()}
    </span>
  );
}

/** Overlapping faces, at most `max`, then "+n". */
export function Faces({
  people,
  max = 5,
  size = 22,
}: {
  people: { name: string; avatar?: string }[];
  max?: number;
  size?: number;
}) {
  const extra = people.length - max;
  return (
    <span {...stylex.props(styles.stack)} title={people.map((p) => p.name).join(', ')}>
      {people.slice(0, max).map((p, i) => (
        <span key={`${p.name}-${i}`} {...stylex.props(styles.overlap)}>
          <Avatar name={p.name} src={p.avatar} size={size} ring />
        </span>
      ))}
      {extra > 0 && (
        <span {...stylex.props(styles.overlap)}>
          <span {...stylex.props(styles.avatar, styles.size(size), styles.ring, styles.more)}>+{extra}</span>
        </span>
      )}
    </span>
  );
}

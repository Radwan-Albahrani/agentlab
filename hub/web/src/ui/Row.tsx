import * as stylex from '@stylexjs/stylex';
import type { ReactNode } from 'react';
import { hueTheme } from '../theme/hues';
import { agent, colors, media, motion, radius, space, text } from '../theme/tokens.stylex';
import { Icon } from './Icon';
import type { Tone } from './status';

const sweep = stylex.keyframes({ from: { transform: 'translateX(-100%)' }, to: { transform: 'translateX(250%)' } });

const styles = stylex.create({
  list: { display: 'grid' },
  row: {
    position: 'relative',
    display: 'flex',
    alignItems: 'center',
    gap: space.lg,
    paddingBlock: space.lg,
    paddingInline: space.xxl,
    minWidth: 0,
    transitionProperty: 'background-color',
    transitionDuration: '160ms',
    borderTopWidth: { default: 1, ':first-child': 0 },
    borderTopStyle: 'solid',
    borderTopColor: colors.line,
    flexWrap: { default: 'nowrap', [media.phone]: 'wrap' },
  },
  flat: { paddingInline: 0, paddingBlock: space.md },
  wrap: { flexWrap: 'wrap' },
  warn: { borderLeftWidth: 3, borderLeftStyle: 'solid', borderLeftColor: colors.warn },
  bad: { borderLeftWidth: 3, borderLeftStyle: 'solid', borderLeftColor: colors.bad },
  info: { borderLeftWidth: 3, borderLeftStyle: 'solid', borderLeftColor: colors.accent },
  nested: {
    marginInlineStart: space.huge,
    borderLeftWidth: 2,
    borderLeftStyle: 'solid',
    borderLeftColor: `color-mix(in srgb, ${agent.hue} 60%, transparent)`,
  },
  // a light sweeping along the bottom edge: work in progress
  liveBar: {
    position: 'absolute',
    insetInline: space.xxl,
    bottom: 0,
    height: 2,
    overflow: 'hidden',
    borderRadius: 99,
    backgroundColor: `color-mix(in srgb, ${colors.accent} 12%, transparent)`,
  },
  liveLight: {
    display: 'block',
    width: '40%',
    height: '100%',
    backgroundImage: `linear-gradient(90deg, transparent, ${colors.accent}, transparent)`,
    animationName: sweep,
    animationDuration: '1.8s',
    animationTimingFunction: motion.settle,
    animationIterationCount: 'infinite',
  },
  grow: { flex: '1', minWidth: 0 },
  title: { fontWeight: 600, overflowWrap: 'anywhere' },
  detail: { color: colors.muted, fontSize: text.md, overflowWrap: 'anywhere' },
  meta: { color: colors.faint, fontSize: text.sm, whiteSpace: 'nowrap', order: { default: null, [media.phone]: 3 } },
  actions: {
    display: 'flex',
    gap: space.xs,
    flexWrap: 'wrap',
    alignItems: 'center',
    justifyContent: { default: 'flex-end', [media.phone]: 'flex-start' },
    width: { default: null, [media.phone]: '100%' },
    paddingInlineStart: { default: 0, [media.phone]: 46 },
  },
  box: {
    width: 36,
    height: 36,
    borderRadius: radius.lg,
    display: 'grid',
    placeItems: 'center',
    flexShrink: 0,
    backgroundColor: colors.sunk,
    color: colors.muted,
  },
  ok: { backgroundColor: colors.okSoft, color: colors.ok },
  boxWarn: { backgroundColor: colors.warnSoft, color: colors.warn },
  boxBad: { backgroundColor: colors.badSoft, color: colors.bad },
  boxInfo: { backgroundColor: colors.accentSoft, color: colors.accent },
});

const BOX_TONE = { ok: styles.ok, warn: styles.boxWarn, bad: styles.boxBad, info: styles.boxInfo, idle: null };

export const List = ({ children }: { children: ReactNode }) => <div {...stylex.props(styles.list)}>{children}</div>;

export const IconBox = ({ icon, tone = 'idle', children }: { icon?: string; tone?: Tone; children?: ReactNode }) => (
  <div {...stylex.props(styles.box, BOX_TONE[tone])}>{icon ? <Icon name={icon} /> : children}</div>
);

interface RowProps {
  icon?: string;
  tone?: Tone;
  lead?: ReactNode;
  title: ReactNode;
  detail?: ReactNode;
  meta?: ReactNode;
  actions?: ReactNode;
  accent?: 'warn' | 'bad' | 'info';
  nestedUnder?: string | null; // a companion's row, indented under its agent and wearing its colour
  flat?: boolean;
  wrap?: boolean;
  live?: boolean; // work in progress: a light sweeps under it
}

export function Row({ icon, tone, lead, title, detail, meta, actions, accent, nestedUnder, flat, wrap, live }: RowProps) {
  return (
    <div
      {...stylex.props(
        hueTheme(nestedUnder),
        styles.row,
        flat && styles.flat,
        wrap && styles.wrap,
        accent && styles[accent],
        !!nestedUnder && styles.nested,
      )}
    >
      {lead ?? (icon && <IconBox icon={icon} tone={tone} />)}
      <div {...stylex.props(styles.grow)}>
        <div {...stylex.props(styles.title)}>{title}</div>
        {detail && <div {...stylex.props(styles.detail)}>{detail}</div>}
      </div>
      {meta && <div {...stylex.props(styles.meta)}>{meta}</div>}
      {actions && <div {...stylex.props(styles.actions)}>{actions}</div>}
      {live && (
        <span {...stylex.props(styles.liveBar)}>
          <i {...stylex.props(styles.liveLight)} />
        </span>
      )}
    </div>
  );
}

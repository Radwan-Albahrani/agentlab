import * as stylex from '@stylexjs/stylex';
import type { ReactNode } from 'react';
import { hueTheme } from '../theme/hues';
import { colors, media, radius, space, text } from '../theme/tokens.stylex';
import { Icon } from './Icon';
import type { Tone } from './status';

const run = stylex.keyframes({ to: { backgroundPosition: '20px 0' } });

const styles = stylex.create({
  // every row draws its own top hairline (wrappers like Appear break :first-child); the list hides the first one
  list: { display: 'grid', marginBlockStart: -1 },
  row: {
    position: 'relative',
    display: 'flex',
    alignItems: 'center',
    gap: space.lg,
    paddingBlock: space.lg,
    paddingInline: space.xxl,
    minWidth: 0,
    transitionProperty: 'background-color',
    transitionDuration: '140ms',
    borderTopWidth: 1,
    borderTopStyle: 'solid',
    borderTopColor: colors.line,
    flexWrap: { default: 'nowrap', [media.phone]: 'wrap' },
  },
  flat: { paddingInline: 0, paddingBlock: space.md },
  wrap: { flexWrap: 'wrap' },
  // the icon carries the tone; rows stay calm (no fills, no stripes)
  warn: {},
  bad: {},
  info: {},
  // a companion under its agent: indented on a neutral structural hairline
  nested: { marginInlineStart: space.huge, borderLeftWidth: 1, borderLeftStyle: 'solid', borderLeftColor: colors.line },
  // a dashed line running along the bottom edge: work in progress
  liveBar: {
    position: 'absolute',
    insetInline: 0,
    bottom: -1,
    height: 1,
    backgroundImage: `repeating-linear-gradient(90deg, ${colors.info} 0 6px, transparent 6px 10px)`,
    backgroundSize: '20px 1px',
    animationName: run,
    animationDuration: '1s',
    animationTimingFunction: 'linear',
    animationIterationCount: 'infinite',
  },
  grow: { flex: '1', minWidth: 0 },
  title: { fontWeight: 500, overflowWrap: 'anywhere' },
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
    width: 32,
    height: 32,
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
  boxInfo: { backgroundColor: colors.infoSoft, color: colors.info },
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
      {live && <span {...stylex.props(styles.liveBar)} />}
    </div>
  );
}

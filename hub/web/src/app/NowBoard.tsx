import * as stylex from '@stylexjs/stylex';
import { Link } from 'react-router';
import type { NowAgent } from '../api/types';
import { ago, elapsed, plural } from '../lib/format';
import { useNow } from '../lib/useNow';
import { hueTheme } from '../theme/hues';
import { agent, colors, font, media, radius, space, text } from '../theme/tokens.stylex';
import { Icon } from '../ui/Icon';

const run = stylex.keyframes({ to: { backgroundPosition: '20px 0' } });
const blink = stylex.keyframes({ '50%': { opacity: 0.2 } });

const styles = stylex.create({
  // lanes share one frame: hairlines between them instead of separate cards
  grid: {
    display: 'grid',
    gridTemplateColumns: { default: 'repeat(auto-fit, minmax(320px, 1fr))', [media.phone]: '1fr' },
    gap: 1,
    backgroundColor: colors.line,
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: colors.line,
    borderRadius: radius.xl,
    overflow: 'hidden',
  },
  lane: { backgroundColor: colors.panel, minWidth: 0, display: 'grid', alignContent: 'start' },
  single: { borderWidth: 1, borderStyle: 'solid', borderColor: colors.line, borderRadius: radius.xl, overflow: 'hidden' },
  head: {
    display: 'flex',
    alignItems: 'center',
    gap: space.md,
    paddingBlock: space.sm,
    paddingInline: space.xxl,
    backgroundColor: { default: colors.raised, ':hover': colors.hover },
    borderBottomWidth: 1,
    borderBottomStyle: 'solid',
    borderBottomColor: colors.line,
    transitionProperty: 'background-color',
    transitionDuration: '120ms',
  },
  tag: {
    fontFamily: font.mono,
    fontSize: text.xs,
    fontWeight: 600,
    letterSpacing: '.06em',
    textTransform: 'uppercase',
    paddingBlock: 1,
    paddingInline: space.xs,
    borderRadius: radius.xs,
    backgroundColor: agent.hue,
    color: colors.onFill,
  },
  state: { fontFamily: font.mono, fontSize: text.xs, color: colors.faint },
  stateBusy: { color: colors.info },
  stateWait: { color: colors.warn },
  open: { marginInlineStart: 'auto', color: colors.faint, display: 'flex' },
  row: {
    position: 'relative',
    display: 'grid',
    gridTemplateColumns: 'minmax(0, 1fr) auto',
    rowGap: 1,
    columnGap: space.lg,
    alignItems: 'baseline',
    paddingBlock: space.sm,
    paddingInline: space.xxl,
    borderBottomWidth: 1,
    borderBottomStyle: 'dashed',
    borderBottomColor: colors.line,
    backgroundColor: { default: 'transparent', ':hover': colors.hover },
    transitionProperty: 'background-color',
    transitionDuration: '120ms',
  },
  wait: { backgroundColor: `color-mix(in srgb, ${colors.warnSoft} 60%, transparent)` },
  title: { fontSize: text.base, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' },
  titleWait: { color: colors.warn, fontWeight: 500 },
  titleQuiet: { color: colors.muted },
  meta: {
    gridColumn: '1',
    fontSize: text.xs,
    color: colors.faint,
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
    display: 'flex',
    alignItems: 'center',
    gap: space.xs,
  },
  clock: { fontFamily: font.mono, fontSize: text.sm, fontVariantNumeric: 'tabular-nums', color: colors.info, textAlign: 'right' },
  clockWait: { color: colors.warn },
  clockDone: { color: colors.faint, fontSize: text.xs },
  // a dashed line running under a chat that's working
  bar: {
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
  block: {
    width: 6,
    height: 10,
    flexShrink: 0,
    backgroundColor: colors.info,
    animationName: blink,
    animationDuration: '1s',
    animationIterationCount: 'infinite',
  },
  helpers: { fontFamily: font.mono, color: colors.info },
  mark: { display: 'inline-flex' },
  ok: { color: colors.ok },
  bad: { color: colors.bad },
  label: {
    paddingBlockStart: space.md,
    paddingBlockEnd: space.xxs,
    paddingInline: space.xxl,
    fontFamily: font.mono,
    fontSize: text.xxs,
    letterSpacing: '.12em',
    textTransform: 'uppercase',
    color: colors.faint,
  },
  idle: { paddingBlock: space.lg, paddingInline: space.xxl, color: colors.faint, fontSize: text.md },
});

function laneState(a: NowAgent): [string, 'busy' | 'wait' | 'idle'] {
  const mine = a.running.filter((r) => !r.background).length;
  const bg = a.running.length - mine;
  const parts = [mine && `${mine} running`, bg && `${bg} background`, a.waiting.length && `${a.waiting.length} asks you`].filter(
    Boolean,
  );
  if (!parts.length) return ['idle', 'idle'];
  return [parts.join(' · '), a.waiting.length ? 'wait' : 'busy'];
}

/** One lane per agent: what it's doing this second, what waits on you, what just finished. */
export function NowBoard({ agents }: { agents: NowAgent[] }) {
  return (
    <div {...stylex.props(styles.grid)}>
      {agents.map((a) => (
        <Lane key={a.name} a={a} />
      ))}
    </div>
  );
}

/** One agent's lane; on its own page (linked false) it stands alone, framed, without a header. */
export function Lane({ a, linked = true }: { a: NowAgent; linked?: boolean }) {
  const now = useNow(1000);
  const [state, kind] = laneState(a);
  const recent = a.recent.slice(0, a.running.length + a.waiting.length ? 2 : 4);
  return (
    <div {...stylex.props(hueTheme(a.name), styles.lane, !linked && styles.single)}>
      {linked && (
        <Link to={`/agents/${a.name}`} {...stylex.props(styles.head)}>
          <span {...stylex.props(styles.tag)}>{a.name}</span>
          <span {...stylex.props(styles.state, kind === 'busy' && styles.stateBusy, kind === 'wait' && styles.stateWait)}>
            {state}
          </span>
          <span {...stylex.props(styles.open)}>
            <Icon name="arrow" size={16} />
          </span>
        </Link>
      )}
      {a.waiting.map((w) => (
        <a key={`w-${w.id}`} href={a.chat} target="_blank" rel="noopener" {...stylex.props(styles.row, styles.wait)}>
          <span {...stylex.props(styles.title, styles.titleWait)}>{w.title}</span>
          <span {...stylex.props(styles.clock, styles.clockWait)}>{elapsed(now - w.since)}</span>
          <span {...stylex.props(styles.meta)}>
            {w.kind === 'question' ? 'Asks you a question' : 'Wants your approval'}
            {w.project && ` · ${w.project}`}
          </span>
        </a>
      ))}
      {a.running.map((r) => (
        <a key={`r-${r.id}`} href={a.chat} target="_blank" rel="noopener" {...stylex.props(styles.row)}>
          <span {...stylex.props(styles.title, r.background && styles.titleQuiet)}>{r.title}</span>
          <span {...stylex.props(styles.clock)}>{elapsed(now - r.since)}</span>
          <span {...stylex.props(styles.meta)}>
            <i {...stylex.props(styles.block)} />
            {[r.background ? 'background' : '', r.project].filter(Boolean).join(' · ')}
            {r.helpers > 0 && <span {...stylex.props(styles.helpers)}>{plural(r.helpers, 'helper')}</span>}
          </span>
          <i {...stylex.props(styles.bar)} />
        </a>
      ))}
      {!a.running.length && !a.waiting.length && <div {...stylex.props(styles.idle)}>Nothing running right now.</div>}
      {recent.length > 0 && <div {...stylex.props(styles.label)}>Finished</div>}
      {recent.map((r) => {
        const failed = r.status === 'failed';
        const stopped = r.status === 'interrupted';
        return (
          <a key={`d-${r.id}`} href={a.chat} target="_blank" rel="noopener" {...stylex.props(styles.row)}>
            <span {...stylex.props(styles.title, styles.titleQuiet)}>{r.title}</span>
            <span {...stylex.props(styles.clock, styles.clockDone)}>{ago(r.at, now)}</span>
            <span {...stylex.props(styles.meta)}>
              <span {...stylex.props(styles.mark, failed ? styles.bad : !stopped && styles.ok)}>
                <Icon name={failed ? 'alert' : stopped ? 'x' : 'check'} size={13} />
              </span>
              {[failed ? 'failed' : stopped ? 'stopped' : 'done', r.background ? 'background' : '', r.project]
                .filter(Boolean)
                .join(' · ')}
            </span>
          </a>
        );
      })}
    </div>
  );
}

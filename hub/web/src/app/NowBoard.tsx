import * as stylex from '@stylexjs/stylex';
import { Link } from 'react-router';
import type { NowAgent } from '../api/types';
import { ago, elapsed, plural } from '../lib/format';
import { useNow } from '../lib/useNow';
import { hueTheme } from '../theme/hues';
import { agent, colors, media, motion, radius, space, text } from '../theme/tokens.stylex';
import { Icon } from '../ui/Icon';
import { Appear } from '../ui/motion';
import { Badge } from '../ui/status';

const spin = stylex.keyframes({ to: { transform: 'rotate(360deg)' } });
const sweep = stylex.keyframes({ from: { transform: 'translateX(-100%)' }, to: { transform: 'translateX(250%)' } });
const breathe = stylex.keyframes({ '50%': { opacity: 0.55 } });

const styles = stylex.create({
  grid: {
    display: 'grid',
    gridTemplateColumns: { default: 'repeat(auto-fill, minmax(340px, 1fr))', [media.phone]: '1fr' },
    gap: space.xxl,
    alignItems: 'start',
  },
  lane: {
    position: 'relative',
    overflow: 'hidden',
    borderRadius: radius.xxl,
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: `color-mix(in srgb, ${agent.hue} 22%, ${colors.line})`,
    backgroundColor: colors.panel,
    boxShadow: colors.shadow,
  },
  busyLane: { borderColor: `color-mix(in srgb, ${agent.hue} 45%, ${colors.line})` },
  head: {
    display: 'flex',
    alignItems: 'center',
    gap: space.lg,
    paddingBlock: space.xl,
    paddingInline: space.xxxl,
    backgroundImage: `linear-gradient(120deg, color-mix(in srgb, ${agent.hue} 18%, transparent), transparent 70%)`,
    color: { default: colors.fg, ':hover': colors.fg },
  },
  // a turning ring around the badge while the agent works
  ring: { position: 'relative', display: 'grid', placeItems: 'center', width: 44, height: 44, flexShrink: 0 },
  ringTrack: {
    position: 'absolute',
    inset: 0,
    borderRadius: radius.lg,
    backgroundImage: `conic-gradient(from 0deg, transparent 0 40%, ${agent.hue} 100%)`,
    // hollowed out: only a thin turning edge shows round the badge
    '::after': {
      content: '""',
      position: 'absolute',
      inset: 2,
      borderRadius: radius.md,
      backgroundColor: colors.panel,
    },
    animationName: spin,
    animationDuration: '1.6s',
    animationTimingFunction: 'linear',
    animationIterationCount: 'infinite',
  },
  over: { position: 'relative', display: 'flex' },
  name: { fontSize: text.lg, fontWeight: 700, letterSpacing: '-.01em' },
  state: { fontSize: text.sm, color: colors.muted },
  stateBusy: { color: agent.hue, fontWeight: 600 },
  stateWait: { color: colors.warn, fontWeight: 600 },
  open: { marginInlineStart: 'auto', color: colors.faint, display: 'flex' },
  body: { display: 'grid', paddingBlockEnd: space.sm },
  row: {
    position: 'relative',
    display: 'grid',
    gridTemplateColumns: '28px minmax(0, 1fr) auto',
    gap: space.md,
    alignItems: 'center',
    paddingBlock: space.md,
    paddingInline: space.xxxl,
    backgroundColor: { default: 'transparent', ':hover': colors.hover },
    transitionProperty: 'background-color',
    transitionDuration: '160ms',
  },
  icon: {
    width: 28,
    height: 28,
    borderRadius: radius.sm,
    display: 'grid',
    placeItems: 'center',
    backgroundColor: `color-mix(in srgb, ${agent.hue} 14%, transparent)`,
    color: agent.hue,
  },
  iconWait: { backgroundColor: colors.warnSoft, color: colors.warn },
  iconOk: { backgroundColor: 'transparent', color: colors.ok },
  iconBad: { backgroundColor: 'transparent', color: colors.bad },
  iconIdle: { backgroundColor: 'transparent', color: colors.faint },
  title: { fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', fontSize: text.base },
  titleQuiet: { fontWeight: 500, color: colors.muted },
  meta: { fontSize: text.xs, color: colors.faint, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' },
  time: {
    fontSize: text.xs,
    color: colors.faint,
    fontVariantNumeric: 'tabular-nums',
    whiteSpace: 'nowrap',
    textAlign: 'right',
  },
  timeLive: { color: agent.hue, fontWeight: 600 },
  timeWait: { color: colors.warn, fontWeight: 600 },
  // an indeterminate light sweeping under a running chat
  bar: {
    position: 'absolute',
    insetInline: space.xxxl,
    bottom: 0,
    height: 2,
    overflow: 'hidden',
    borderRadius: radius.pill,
    backgroundColor: `color-mix(in srgb, ${agent.hue} 12%, transparent)`,
  },
  barLight: {
    display: 'block',
    width: '40%',
    height: '100%',
    backgroundImage: `linear-gradient(90deg, transparent, ${agent.hue}, transparent)`,
    animationName: sweep,
    animationDuration: '1.8s',
    animationTimingFunction: motion.settle,
    animationIterationCount: 'infinite',
  },
  chip: {
    marginInlineEnd: space.xs,
    fontSize: text.xxs,
    fontWeight: 600,
    paddingBlock: 1,
    paddingInline: space.xs,
    borderRadius: radius.pill,
    backgroundColor: `color-mix(in srgb, ${agent.hue} 14%, transparent)`,
    color: agent.hue,
    verticalAlign: 1,
  },
  label: {
    paddingBlockStart: space.md,
    paddingBlockEnd: space.xxs,
    paddingInline: space.xxxl,
    fontSize: text.xxs,
    fontWeight: 650,
    letterSpacing: '.07em',
    textTransform: 'uppercase',
    color: colors.faint,
  },
  idle: { paddingBlock: space.xl, paddingInline: space.xxxl, color: colors.faint, fontSize: text.md },
  pulse: { animationName: breathe, animationDuration: '2s', animationIterationCount: 'infinite' },
});

type Outcome = readonly [icon: string, tone: stylex.StyleXStyles, word: string];
const DONE: Outcome = ['check', styles.iconOk, 'done'];
const OUTCOME: Partial<Record<string, Outcome>> = {
  failed: ['alert', styles.iconBad, 'failed'],
  interrupted: ['x', styles.iconIdle, 'stopped'],
};

function laneState(a: NowAgent): [string, 'busy' | 'wait' | 'idle'] {
  if (a.waiting.length) return [`${plural(a.waiting.length, 'chat')} waiting on you`, 'wait'];
  const mine = a.running.filter((r) => !r.background).length;
  const bg = a.running.length - mine;
  if (a.running.length)
    return [[mine && `working on ${plural(mine, 'chat')}`, bg && `${bg} in the background`].filter(Boolean).join(' · '), 'busy'];
  return ['Idle', 'idle'];
}

/** One lane per agent: what it's doing this second, what waits on you, what just finished. */
export function NowBoard({ agents }: { agents: NowAgent[] }) {
  return (
    <div {...stylex.props(styles.grid)}>
      {agents.map((a, i) => (
        <Appear key={a.name} i={i}>
          <Lane a={a} />
        </Appear>
      ))}
    </div>
  );
}

/** One agent's lane (also shown alone on its page). */
export function Lane({ a, linked = true }: { a: NowAgent; linked?: boolean }) {
  const now = useNow(1000);
  const [state, kind] = laneState(a);
  const recent = a.recent.slice(0, a.running.length + a.waiting.length ? 2 : 4);
  return (
    <div {...stylex.props(hueTheme(a.name), styles.lane, kind === 'busy' && styles.busyLane)}>
      {linked && (
        <Link to={`/agents/${a.name}`} {...stylex.props(styles.head)}>
          <span {...stylex.props(styles.ring)}>
            {a.running.length > 0 && <span {...stylex.props(styles.ringTrack)} />}
            <span {...stylex.props(styles.over)}>
              <Badge name={a.name} />
            </span>
          </span>
          <div>
            <div {...stylex.props(styles.name)}>{a.name}</div>
            <div {...stylex.props(styles.state, kind === 'busy' && styles.stateBusy, kind === 'wait' && styles.stateWait)}>
              {state}
            </div>
          </div>
          <span {...stylex.props(styles.open)}>
            <Icon name="arrow" size={18} />
          </span>
        </Link>
      )}
      <div {...stylex.props(styles.body)}>
        {a.waiting.map((w) => (
          <Appear key={`w-${w.id}`}>
            <a href={a.chat} target="_blank" rel="noopener" {...stylex.props(styles.row)}>
              <span {...stylex.props(styles.icon, styles.iconWait, styles.pulse)}>
                <Icon name={w.kind === 'question' ? 'chat' : 'alert'} size={16} />
              </span>
              <div>
                <div {...stylex.props(styles.title)}>{w.title}</div>
                <div {...stylex.props(styles.meta)}>
                  {w.kind === 'question' ? 'Asks you a question' : 'Wants your approval'}
                  {w.project && ` · ${w.project}`}
                </div>
              </div>
              <span {...stylex.props(styles.time, styles.timeWait)}>{elapsed(now - w.since)}</span>
            </a>
          </Appear>
        ))}
        {a.running.map((r) => (
          <Appear key={`r-${r.id}`}>
            <a href={a.chat} target="_blank" rel="noopener" {...stylex.props(styles.row)}>
              <span {...stylex.props(styles.icon)}>
                <Icon name={r.background ? 'bot' : 'chat'} size={16} />
              </span>
              <div>
                <div {...stylex.props(styles.title, r.background && styles.titleQuiet)}>{r.title}</div>
                <div {...stylex.props(styles.meta)}>
                  {r.helpers > 0 && <span {...stylex.props(styles.chip)}>{plural(r.helpers, 'helper')}</span>}
                  {[r.background ? 'Background' : '', r.project].filter(Boolean).join(' · ')}
                </div>
              </div>
              <span {...stylex.props(styles.time, styles.timeLive)}>{elapsed(now - r.since)}</span>
              <span {...stylex.props(styles.bar)}>
                <i {...stylex.props(styles.barLight)} />
              </span>
            </a>
          </Appear>
        ))}
        {!a.running.length && !a.waiting.length && <div {...stylex.props(styles.idle)}>Nothing running right now.</div>}
        {recent.length > 0 && <div {...stylex.props(styles.label)}>Finished</div>}
        {recent.map((r) => {
          const [icon, tone, word] = OUTCOME[r.status] ?? DONE;
          return (
            <a key={`d-${r.id}`} href={a.chat} target="_blank" rel="noopener" {...stylex.props(styles.row)}>
              <span {...stylex.props(styles.icon, tone)}>
                <Icon name={icon} size={16} />
              </span>
              <div>
                <div {...stylex.props(styles.title, styles.titleQuiet)}>{r.title}</div>
                <div {...stylex.props(styles.meta)}>
                  {[word, r.background ? 'background' : '', r.project].filter(Boolean).join(' · ')}
                </div>
              </div>
              <span {...stylex.props(styles.time)}>{ago(r.at, now)}</span>
            </a>
          );
        })}
      </div>
    </div>
  );
}

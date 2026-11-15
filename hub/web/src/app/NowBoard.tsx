import * as stylex from '@stylexjs/stylex';
import { Link } from 'react-router';
import type { NowAgent } from '../api/types';
import { hueTheme } from '../theme/hues';
import { agent, colors, font, media, radius, space, text } from '../theme/tokens.stylex';
import { Icon } from '../ui/Icon';

const blink = stylex.keyframes({ '50%': { opacity: 0.25 } });

const styles = stylex.create({
  list: {
    display: 'grid',
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: colors.line,
    borderRadius: radius.xl,
    backgroundColor: colors.panel,
    overflow: 'hidden',
  },
  row: {
    display: 'grid',
    gridTemplateColumns: { default: 'minmax(140px, 1fr) repeat(4, minmax(0, 130px)) auto', [media.phone]: '1fr 1fr' },
    alignItems: 'center',
    columnGap: space.xl,
    rowGap: space.md,
    paddingBlock: space.lg,
    paddingInline: space.xxl,
    borderTopWidth: 1,
    borderTopStyle: 'solid',
    borderTopColor: colors.line,
    marginBlockStart: -1,
  },
  name: { display: 'flex', alignItems: 'center', gap: space.md, fontWeight: 500, minWidth: 0 },
  swatch: { width: 10, height: 10, flexShrink: 0, borderRadius: radius.xs, backgroundColor: agent.hue },
  nameLink: { color: { default: colors.fg, ':hover': colors.accent } },
  count: { display: 'grid', gap: 1 },
  num: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: space.xs,
    fontFamily: font.mono,
    fontSize: text.lg,
    fontVariantNumeric: 'tabular-nums',
    color: colors.faint,
  },
  label: { fontSize: text.xs, color: colors.faint },
  live: { color: colors.info },
  asks: { color: colors.warn },
  bad: { color: colors.bad },
  block: {
    width: 5,
    height: 12,
    backgroundColor: colors.info,
    animationName: blink,
    animationDuration: '1s',
    animationIterationCount: 'infinite',
  },
  open: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: space.xs,
    fontSize: text.sm,
    color: { default: colors.muted, ':hover': colors.fg },
    justifySelf: { default: 'end', [media.phone]: 'start' },
  },
});

function Count({ n, label, tone }: { n: number; label: string; tone?: 'live' | 'asks' | 'bad' }) {
  return (
    <div {...stylex.props(styles.count)}>
      <span
        {...stylex.props(
          styles.num,
          n > 0 && tone === 'live' && styles.live,
          n > 0 && tone === 'asks' && styles.asks,
          n > 0 && tone === 'bad' && styles.bad,
        )}
      >
        {n > 0 && tone === 'live' && <i {...stylex.props(styles.block)} />}
        {n}
      </span>
      <span {...stylex.props(styles.label)}>{label}</span>
    </div>
  );
}

/** How busy one agent is, in counts only: never what its chats are about. */
export function AgentNow({ a, linked = true }: { a: NowAgent; linked?: boolean }) {
  return (
    <div {...stylex.props(hueTheme(a.name), styles.row)} data-agent={a.name}>
      <div {...stylex.props(styles.name)}>
        <i {...stylex.props(styles.swatch)} />
        {linked ? (
          <Link to={`/agents/${a.name}`} {...stylex.props(styles.nameLink)}>
            {a.name}
          </Link>
        ) : (
          <span>{a.name}</span>
        )}
      </div>
      <Count n={a.running} label="running" tone="live" />
      <Count n={a.background} label="in the background" tone="live" />
      <Count n={a.waiting} label="asking you" tone="asks" />
      <Count
        n={a.done + a.failed}
        label={a.failed ? `done · ${a.failed} failed` : 'done · last 6 h'}
        tone={a.failed ? 'bad' : undefined}
      />
      <a href={a.chat} target="_blank" rel="noopener" {...stylex.props(styles.open)}>
        Open chat <Icon name="ext" size={14} />
      </a>
    </div>
  );
}

export function NowBoard({ agents, linked = true }: { agents: NowAgent[]; linked?: boolean }) {
  return (
    <div {...stylex.props(styles.list)}>
      {agents.map((a) => (
        <AgentNow key={a.name} a={a} linked={linked} />
      ))}
    </div>
  );
}

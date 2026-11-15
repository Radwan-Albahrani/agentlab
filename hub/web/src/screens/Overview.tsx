import * as stylex from '@stylexjs/stylex';
import { Link } from 'react-router';
import { useNowBoard, useOverview } from '../api/queries';
import type { NowAgent, Overview as Data } from '../api/types';
import { NowBoard } from '../app/NowBoard';
import { Screen } from '../app/Screen';
import { StackLead, WATCHER_PENDING } from '../app/stacks';
import { useCanSee } from '../app/useCanSee';
import { ago, gb, pct, plural } from '../lib/format';
import { useNow } from '../lib/useNow';
import { hueTheme } from '../theme/hues';
import { agent, colors, media, motion, radius, space, text } from '../theme/tokens.stylex';
import { Actions } from '../ui/actions';
import { LinkButton } from '../ui/Button';
import { Card } from '../ui/Card';
import { Feed } from '../ui/Feed';
import { Icon } from '../ui/Icon';
import { Appear, Num } from '../ui/motion';
import { Empty, Section } from '../ui/page';
import { Ring } from '../ui/Ring';
import { List, Row } from '../ui/Row';
import { When } from '../ui/When';

const drift = stylex.keyframes({ from: { backgroundPosition: '0% 0%' }, to: { backgroundPosition: '100% 100%' } });

const styles = stylex.create({
  hero: {
    position: 'relative',
    overflow: 'hidden',
    display: 'grid',
    gridTemplateColumns: { default: 'minmax(0, 1fr) auto', [media.narrow]: '1fr' },
    gap: space.huge,
    alignItems: 'center',
    paddingBlock: { default: 36, [media.phone]: space.huge },
    paddingInline: { default: 40, [media.phone]: space.huge },
    borderRadius: 28,
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: colors.line,
    backgroundColor: colors.panel,
    boxShadow: colors.shadow,
    // an aurora behind the greeting, drifting slowly
    backgroundImage: `radial-gradient(60% 120% at 0% 0%, color-mix(in srgb, ${colors.accent} 22%, transparent), transparent 60%), radial-gradient(50% 120% at 100% 0%, color-mix(in srgb, #a855f7 16%, transparent), transparent 60%), radial-gradient(60% 90% at 60% 120%, color-mix(in srgb, ${colors.ok} 12%, transparent), transparent 60%)`,
    backgroundSize: '160% 160%',
    animationName: drift,
    animationDuration: '18s',
    animationTimingFunction: 'ease-in-out',
    animationIterationCount: 'infinite',
    animationDirection: 'alternate',
  },
  eyebrow: {
    display: 'flex',
    alignItems: 'center',
    gap: space.sm,
    fontSize: text.sm,
    color: colors.muted,
    fontVariantNumeric: 'tabular-nums',
  },
  dot: {
    width: 8,
    height: 8,
    borderRadius: '50%',
    backgroundColor: colors.ok,
    boxShadow: `0 0 0 4px color-mix(in srgb, ${colors.ok} 18%, transparent)`,
  },
  hello: {
    marginBlock: space.sm,
    marginInline: 0,
    fontSize: { default: '52px', [media.phone]: text.hero },
    fontWeight: 750,
    letterSpacing: '-.045em',
    lineHeight: 1,
    textWrap: 'balance',
  },
  summary: { margin: 0, fontSize: text.lg, color: colors.muted },
  hot: { color: colors.fg, fontWeight: 600 },
  warm: { color: colors.warn, fontWeight: 600 },
  metrics: {
    display: 'grid',
    gridTemplateColumns: { default: 'repeat(4, auto)', [media.phone]: 'repeat(2, minmax(0, 1fr))' },
    justifyContent: 'start',
    gap: { default: space.giant, [media.phone]: space.xl },
    marginBlockStart: space.giant,
  },
  metric: {
    display: 'grid',
    gap: space.xxxs,
    color: { default: colors.fg, ':hover': colors.fg },
    transitionProperty: 'transform',
    transitionDuration: '200ms',
    transitionTimingFunction: motion.settle,
    transform: { default: null, ':hover': 'translateY(-2px)' },
  },
  metricValue: {
    fontSize: text.display,
    fontWeight: 700,
    letterSpacing: '-.04em',
    lineHeight: 1,
    fontVariantNumeric: 'tabular-nums',
  },
  metricOf: { fontSize: text.lg, color: colors.faint, fontWeight: 500, marginInlineStart: 3, letterSpacing: 0 },
  metricLabel: { fontSize: text.sm, color: colors.muted, fontWeight: 550 },
  live: { color: colors.accent },
  waitTone: { color: colors.warn },
  okTone: { color: colors.ok },
  badTone: { color: colors.bad },
  gauges: {
    display: 'grid',
    gap: space.xs,
    minWidth: 240,
    paddingInlineStart: { default: space.huge, [media.narrow]: 0 },
    borderLeftWidth: { default: 1, [media.narrow]: 0 },
    borderLeftStyle: 'solid',
    borderLeftColor: colors.line,
  },
  attention: {
    borderRadius: radius.xxl,
    overflow: 'hidden',
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: `color-mix(in srgb, ${colors.warn} 35%, ${colors.line})`,
    backgroundColor: colors.panel,
    boxShadow: `${colors.shadow}, 0 0 0 4px color-mix(in srgb, ${colors.warn} 7%, transparent)`,
  },
  attentionBad: {
    borderColor: `color-mix(in srgb, ${colors.bad} 40%, ${colors.line})`,
    boxShadow: `${colors.shadow}, 0 0 0 4px color-mix(in srgb, ${colors.bad} 7%, transparent)`,
  },
  attentionHead: {
    display: 'flex',
    alignItems: 'center',
    gap: space.md,
    paddingBlock: space.lg,
    paddingInline: space.xxl,
    fontWeight: 650,
    color: colors.warn,
    backgroundImage: `linear-gradient(90deg, color-mix(in srgb, ${colors.warn} 14%, transparent), transparent 70%)`,
  },
  attentionHeadBad: {
    color: colors.bad,
    backgroundImage: `linear-gradient(90deg, color-mix(in srgb, ${colors.bad} 14%, transparent), transparent 70%)`,
  },
  clear: {
    display: 'flex',
    alignItems: 'center',
    gap: space.lg,
    paddingBlock: space.lg,
    paddingInline: space.xxxl,
    borderRadius: radius.xxl,
    borderWidth: 1,
    borderStyle: 'dashed',
    borderColor: colors.line2,
    color: colors.muted,
  },
  clearIcon: { color: colors.ok, display: 'flex' },
  split: {
    display: 'grid',
    gridTemplateColumns: { default: 'minmax(0, 1.25fr) minmax(0, 1fr)', [media.narrow]: '1fr' },
    gap: space.xxl,
    alignItems: 'start',
  },
  tiles: { display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(170px, 1fr))', gap: space.md },
  tile: {
    position: 'relative',
    display: 'flex',
    alignItems: 'center',
    gap: space.md,
    padding: space.lg,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: colors.line,
    backgroundColor: colors.panel,
    boxShadow: colors.shadow,
    minWidth: 0,
    transitionProperty: 'transform, border-color',
    transitionDuration: '220ms',
    transitionTimingFunction: motion.settle,
    transform: { default: null, ':hover': 'translateY(-1px)' },
  },
  tileDown: { borderColor: `color-mix(in srgb, ${colors.bad} 50%, ${colors.line})`, backgroundColor: colors.badSoft },
  tileName: { fontWeight: 600, fontSize: text.md, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' },
  tileSub: { fontSize: text.xs, color: colors.faint },
  tileText: { minWidth: 0, flex: '1' },
  health: { width: 8, height: 8, borderRadius: '50%', flexShrink: 0, backgroundColor: colors.ok },
  healthBad: { backgroundColor: colors.bad },
  nested: { borderLeftWidth: 3, borderLeftColor: agent.hue },
  note: { fontSize: text.sm, color: colors.faint, paddingBlockStart: space.xs },
});

export function Overview() {
  const query = useOverview();
  const now = useNowBoard();
  return (
    <Screen title="Overview" query={query}>
      {(d) => <OverviewView d={d} agents={now.data?.agents} />}
    </Screen>
  );
}

const greeting = (h: number) => (h < 5 ? 'Late night' : h < 12 ? 'Good morning' : h < 18 ? 'Good afternoon' : 'Good evening');

function Metric({
  value,
  of,
  label,
  tone,
  to,
}: {
  value: number;
  of?: number;
  label: string;
  tone?: stylex.StyleXStyles;
  to?: string | null;
}) {
  const inner = (
    <>
      <span {...stylex.props(styles.metricValue, tone)}>
        <Num value={value} />
        {of !== undefined && <small {...stylex.props(styles.metricOf)}>/ {of}</small>}
      </span>
      <span {...stylex.props(styles.metricLabel)}>{label}</span>
    </>
  );
  return to ? (
    <Link to={to} {...stylex.props(styles.metric)}>
      {inner}
    </Link>
  ) : (
    <div {...stylex.props(styles.metric)}>{inner}</div>
  );
}

/** The greeting, the state of things in one sentence, the numbers that matter, and the gauges. */
function HeroPanel({ d, agents }: { d: Data; agents?: NowAgent[] }) {
  const t = useNow(1000);
  const date = new Date(t * 1000);
  const running = agents?.reduce((n, a) => n + a.running.length, 0) ?? 0;
  const waiting = (agents?.reduce((n, a) => n + a.waiting.length, 0) ?? 0) + (d.needs?.length ?? 0);
  const busy = agents?.filter((a) => a.running.length).length ?? 0;
  const tiles = d.tiles;
  return (
    <header {...stylex.props(styles.hero)}>
      <div>
        <div {...stylex.props(styles.eyebrow)}>
          <i {...stylex.props(styles.dot)} />
          {date.toLocaleDateString(undefined, { weekday: 'long', month: 'long', day: 'numeric' })} ·{' '}
          {date.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })}
        </div>
        <h1 {...stylex.props(styles.hello)}>{greeting(date.getHours())}</h1>
        <p {...stylex.props(styles.summary)}>
          {running ? (
            <>
              <span {...stylex.props(styles.hot)}>{plural(running, 'chat')} running</span>
              {agents && agents.length > 1 && ` across ${plural(busy, 'agent')}`}
            </>
          ) : (
            'Your agents are idle'
          )}
          {' · '}
          {waiting ? <span {...stylex.props(styles.warm)}>{plural(waiting, 'thing')} need you</span> : 'nothing needs you'}
        </p>
        <div {...stylex.props(styles.metrics)}>
          <Metric value={running} label="Running now" tone={running ? styles.live : undefined} />
          <Metric value={waiting} label="Need you" tone={waiting ? styles.waitTone : undefined} />
          {tiles && (
            <Metric
              value={tiles.agents.online}
              of={tiles.agents.total}
              label="Agents online"
              tone={tiles.agents.online === tiles.agents.total ? styles.okTone : styles.badTone}
              to={tiles.agents.link ? '/agents' : null}
            />
          )}
          {tiles?.companions && (
            <Metric
              value={tiles.companions.live}
              of={tiles.companions.total}
              label="Companions live"
              tone={tiles.companions.live === tiles.companions.total ? styles.okTone : styles.badTone}
              to={tiles.companions.link}
            />
          )}
        </div>
      </div>
      {tiles && (!!tiles.memory || !!tiles.disk) && (
        <div {...stylex.props(styles.gauges)}>
          {tiles.memory && (
            <Ring
              bare
              label="Agent memory"
              pct={pct(tiles.memory.usedMB, tiles.memory.poolMB)}
              value={`${(tiles.memory.usedMB / 1024).toFixed(1)} GB`}
              sub={`of ${(tiles.memory.poolMB / 1024).toFixed(0)} GB shared`}
            />
          )}
          {tiles.disk && (
            <Ring
              bare
              label={tiles.diskLabel ?? 'Disk'}
              pct={pct(tiles.disk.used, tiles.disk.size)}
              value={`${gb(tiles.disk.avail, 0)} free`}
              sub={`of ${gb(tiles.disk.size, 0)}`}
              to="/storage"
            />
          )}
        </div>
      )}
    </header>
  );
}

function Needs({ needs }: { needs: NonNullable<Data['needs']> }) {
  if (!needs.length)
    return (
      <div {...stylex.props(styles.clear)}>
        <span {...stylex.props(styles.clearIcon)}>
          <Icon name="check" />
        </span>
        <span>
          <b>All clear.</b> Nothing needs you right now.
        </span>
      </div>
    );
  const bad = needs.some((n) => n.tone === 'bad');
  return (
    <div {...stylex.props(styles.attention, bad && styles.attentionBad)}>
      <div {...stylex.props(styles.attentionHead, bad && styles.attentionHeadBad)}>
        <Icon name="bell" size={18} />
        {needs.length === 1 ? 'One thing needs you' : `${needs.length} things need you`}
      </div>
      <List>
        {needs.map((n, i) => (
          <Appear key={`${n.title}-${i}`} i={i}>
            <Row
              accent={n.tone}
              icon={n.icon}
              tone={n.tone}
              title={n.title}
              detail={
                <>
                  {n.detail}
                  {n.since ? (
                    <>
                      {' '}
                      · {n.icon === 'bot' ? 'last heartbeat ' : 'started '}
                      {ago(n.since)}
                    </>
                  ) : null}
                </>
              }
              actions={n.actions.length ? <Actions actions={n.actions} /> : undefined}
            />
          </Appear>
        ))}
      </List>
    </div>
  );
}

function Stacks({ stacks }: { stacks: NonNullable<Data['stacks']> }) {
  const servicesLink = useCanSee()('/services');
  const down = stacks.rows.filter((s) => s.containers.some((c) => !c.healthy)).length;
  return (
    <Section
      title="Stacks"
      sub={stacks.rows.length ? (down ? `${plural(down, 'stack')} down` : 'everything healthy') : undefined}
      right={servicesLink ? <LinkButton label="Services" icon="layers" variant="quiet" small to="/services" /> : undefined}
    >
      {stacks.rows.length ? (
        <div {...stylex.props(styles.tiles)}>
          {stacks.rows.map((s, i) => {
            const bad = s.containers.filter((c) => !c.healthy);
            const nested = s.role && s.role !== 'agent' ? s.profile : null;
            return (
              <Appear key={s.id} i={i}>
                <div
                  {...stylex.props(hueTheme(nested), styles.tile, !!nested && styles.nested, bad.length > 0 && styles.tileDown)}
                  title={bad.length ? `Down: ${bad.map((c) => c.service).join(', ')}` : undefined}
                >
                  <StackLead stack={s} />
                  <div {...stylex.props(styles.tileText)}>
                    <div {...stylex.props(styles.tileName)}>{s.label}</div>
                    <div {...stylex.props(styles.tileSub)}>
                      {bad.length ? `${bad.length} of ${s.containers.length} down` : plural(s.containers.length, 'service')}
                    </div>
                  </div>
                  <i {...stylex.props(styles.health, bad.length > 0 && styles.healthBad)} />
                </div>
              </Appear>
            );
          })}
        </div>
      ) : (
        <Card>
          <Empty {...WATCHER_PENDING} />
        </Card>
      )}
      <div {...stylex.props(styles.note)}>
        Checked <When t={stacks.at} />
      </div>
    </Section>
  );
}

function OverviewView({ d, agents }: { d: Data; agents?: NowAgent[] }) {
  return (
    <>
      <HeroPanel d={d} agents={agents} />
      {d.needs && <Needs needs={d.needs} />}
      {agents && agents.length > 0 && (
        <Section title="Right now" sub="Every chat your agents are running, live. Click one to open it.">
          <NowBoard agents={agents} />
        </Section>
      )}
      {(d.activity ?? d.stacks) && (
        <div {...stylex.props(styles.split)}>
          {d.activity && (
            <Section title="Recent activity">
              <Card>
                <Feed events={d.activity} showSource />
              </Card>
            </Section>
          )}
          {d.stacks && <Stacks stacks={d.stacks} />}
        </div>
      )}
    </>
  );
}

import * as stylex from '@stylexjs/stylex';
import { useNowBoard, useOverview } from '../api/queries';
import type { NowAgent, Overview as Data } from '../api/types';
import { NowBoard } from '../app/NowBoard';
import { Reviews } from '../app/Reviews';
import { Screen } from '../app/Screen';
import { WATCHER_PENDING } from '../app/stacks';
import { useCanSee } from '../app/useCanSee';
import { ago, gb, pct, plural } from '../lib/format';
import { useNow } from '../lib/useNow';
import { hueTheme } from '../theme/hues';
import { agent, colors, media, radius, space, text } from '../theme/tokens.stylex';
import { Actions } from '../ui/actions';
import { LinkButton } from '../ui/Button';
import { Card } from '../ui/Card';
import { Feed } from '../ui/Feed';
import { Icon } from '../ui/Icon';
import { StatGrid } from '../ui/layout';
import { Empty, PageHead, Section, Stat } from '../ui/page';
import { List, Row } from '../ui/Row';
import { Meter } from '../ui/status';
import { When } from '../ui/When';

const styles = stylex.create({
  attention: {
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: `color-mix(in srgb, ${colors.warn} 45%, ${colors.line})`,
    borderRadius: radius.xl,
    backgroundColor: colors.panel,
    overflow: 'hidden',
  },
  attentionBad: { borderColor: `color-mix(in srgb, ${colors.bad} 50%, ${colors.line})` },
  attentionHead: {
    display: 'flex',
    alignItems: 'center',
    gap: space.sm,
    paddingBlock: space.sm,
    paddingInline: space.xxl,
    fontSize: text.xs,
    color: colors.warn,
    backgroundColor: colors.warnSoft,
    borderBottomWidth: 1,
    borderBottomStyle: 'solid',
    borderBottomColor: `color-mix(in srgb, ${colors.warn} 30%, ${colors.line})`,
  },
  attentionHeadBad: {
    color: colors.bad,
    backgroundColor: colors.badSoft,
    borderBottomColor: `color-mix(in srgb, ${colors.bad} 30%, ${colors.line})`,
  },
  clear: {
    display: 'flex',
    alignItems: 'center',
    gap: space.md,
    paddingBlock: space.md,
    paddingInline: space.xxl,
    borderRadius: radius.xl,
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: colors.line,
    backgroundColor: colors.panel,
    color: colors.muted,
    fontSize: text.md,
  },
  clearMark: { width: 7, height: 7, backgroundColor: colors.ok },
  meterCell: { display: 'grid', gap: space.xs, paddingBlockStart: space.xxs },
  split: {
    display: 'grid',
    gridTemplateColumns: { default: 'minmax(0, 1.3fr) minmax(0, 1fr)', [media.narrow]: '1fr' },
    gap: space.huge,
    alignItems: 'start',
  },
  // health as small multiples: a row per stack, one square per container
  health: { display: 'grid' },
  stack: {
    display: 'grid',
    gridTemplateColumns: '10px minmax(0, 1fr) auto',
    alignItems: 'center',
    gap: space.md,
    paddingBlock: space.sm,
    paddingInline: space.xxl,
    borderTopWidth: 1,
    borderTopStyle: 'solid',
    borderTopColor: colors.line,
    marginBlockStart: -1,
    fontSize: text.md,
  },
  swatch: { width: 10, height: 10, backgroundColor: agent.hue },
  swatchInfra: { backgroundColor: 'transparent', borderWidth: 1, borderStyle: 'solid', borderColor: colors.faint },
  stackName: { overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' },
  nested: { paddingInlineStart: 34 },
  dim: { color: colors.muted },
  cells: { display: 'flex', gap: 3, alignItems: 'center' },
  cell: { width: 10, height: 14, backgroundColor: colors.ok },
  cellBad: { backgroundColor: colors.bad },
  foot: {
    paddingBlock: space.sm,
    paddingInline: space.xxl,
    fontSize: text.xxs,
    color: colors.faint,
    borderTopWidth: 1,
    borderTopStyle: 'solid',
    borderTopColor: colors.line,
  },
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

const sum = (agents: NowAgent[] | undefined, key: 'running' | 'waiting') =>
  agents?.reduce((n, a) => n + (key === 'running' ? a.running + a.background : a.waiting), 0) ?? 0;

function Head({ d, running, waiting }: { d: Data; running: number; waiting: number }) {
  const t = useNow(30_000);
  const down = d.stacks?.rows.filter((s) => s.containers.some((c) => !c.healthy)).length ?? 0;
  const date = new Date(t * 1000).toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short' });
  return (
    <PageHead
      eyebrow={`${date} · ${down ? `${plural(down, 'stack')} down` : 'all systems nominal'}`}
      title={`${running ? plural(running, 'chat') : 'No chats'} running · ${waiting ? `${waiting} need you` : 'nothing needs you'}`}
    />
  );
}

function Strip({ t, agents, waiting }: { t: NonNullable<Data['tiles']>; agents?: NowAgent[]; waiting: number }) {
  const running = sum(agents, 'running');
  const busy = agents?.filter((a) => a.running + a.background > 0).length ?? 0;
  return (
    <StatGrid>
      <Stat
        label="Running now"
        value={running}
        sub={running ? `across ${plural(busy, 'agent')}` : 'all idle'}
        tone={running ? 'info' : 'idle'}
      />
      <Stat label="Need you" value={waiting} sub={waiting ? 'listed below' : 'all clear'} tone={waiting ? 'warn' : 'idle'} />
      <Stat
        label="Agents online"
        value={t.agents.online}
        of={`/${t.agents.total}`}
        sub={t.agents.online === t.agents.total ? 'all answering' : `${t.agents.total - t.agents.online} not answering`}
        tone={t.agents.online === t.agents.total ? 'ok' : 'bad'}
        to={t.agents.link ? '/agents' : null}
      />
      {t.companions && (
        <Stat
          label="Companions"
          value={t.companions.live}
          of={`/${t.companions.total}`}
          sub={t.companions.live === t.companions.total ? 'live in Slack' : 'some offline'}
          tone={t.companions.live === t.companions.total ? 'ok' : 'bad'}
          to={t.companions.link}
        />
      )}
      {t.memory && (
        <Stat
          label="Agent memory"
          value={(t.memory.usedMB / 1024).toFixed(1)}
          of=" GB"
          sub={
            <span {...stylex.props(styles.meterCell)}>
              <Meter pct={pct(t.memory.usedMB, t.memory.poolMB)} />
              {`of ${(t.memory.poolMB / 1024).toFixed(0)} GB shared`}
            </span>
          }
        />
      )}
      {t.disk && (
        <Stat
          label={t.diskLabel ?? 'Disk'}
          value={((t.disk.avail || 0) / 2 ** 30).toFixed(0)}
          of=" GB free"
          sub={
            <span {...stylex.props(styles.meterCell)}>
              <Meter pct={pct(t.disk.used, t.disk.size)} />
              {`of ${gb(t.disk.size, 0)}`}
            </span>
          }
          to="/storage"
        />
      )}
    </StatGrid>
  );
}

function Needs({ needs }: { needs: NonNullable<Data['needs']> }) {
  if (!needs.length)
    return (
      <div {...stylex.props(styles.clear)}>
        <i {...stylex.props(styles.clearMark)} />
        All clear: nothing needs you right now.
      </div>
    );
  const bad = needs.some((n) => n.tone === 'bad');
  return (
    <section {...stylex.props(styles.attention, bad && styles.attentionBad)} aria-label="Needs you">
      <div {...stylex.props(styles.attentionHead, bad && styles.attentionHeadBad)}>
        <Icon name="alert" size={14} />
        {needs.length} {needs.length === 1 ? 'thing needs' : 'things need'} you
      </div>
      <List>
        {needs.map((n, i) => (
          <Row
            key={`${n.title}-${i}`}
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
        ))}
      </List>
    </section>
  );
}

function Health({ stacks }: { stacks: NonNullable<Data['stacks']> }) {
  const servicesLink = useCanSee()('/services');
  const down = stacks.rows.filter((s) => s.containers.some((c) => !c.healthy)).length;
  const containers = stacks.rows.reduce((n, s) => n + s.containers.length, 0);
  return (
    <Section
      title="Health"
      sub={stacks.rows.length ? (down ? `${plural(down, 'stack')} down` : `${containers} containers up`) : undefined}
      right={servicesLink ? <LinkButton label="Services" icon="layers" variant="quiet" small to="/services" /> : undefined}
    >
      <Card>
        {stacks.rows.length ? (
          <div {...stylex.props(styles.health)}>
            {stacks.rows.map((s) => {
              const bad = s.containers.filter((c) => !c.healthy);
              const owner = s.role && s.role !== 'agent' ? s.profile : null;
              return (
                <div
                  key={s.id}
                  {...stylex.props(hueTheme(s.profile), styles.stack, !!owner && styles.nested)}
                  title={bad.length ? `Down: ${bad.map((c) => c.service).join(', ')}` : undefined}
                >
                  <i {...stylex.props(styles.swatch, !s.profile && styles.swatchInfra)} />
                  <span {...stylex.props(styles.stackName, !!owner && styles.dim)}>{s.label}</span>
                  <span
                    {...stylex.props(styles.cells)}
                    aria-label={bad.length ? `${bad.length} of ${s.containers.length} down` : `${s.containers.length} up`}
                  >
                    {s.containers.map((c) => (
                      <i
                        key={c.name}
                        {...stylex.props(styles.cell, !c.healthy && styles.cellBad)}
                        title={`${c.service}: ${c.healthy ? 'up' : 'down'}`}
                      />
                    ))}
                  </span>
                </div>
              );
            })}
          </div>
        ) : (
          <Empty {...WATCHER_PENDING} />
        )}
        <div {...stylex.props(styles.foot)}>
          Checked <When t={stacks.at} />
        </div>
      </Card>
    </Section>
  );
}

function OverviewView({ d, agents }: { d: Data; agents?: NowAgent[] }) {
  const running = sum(agents, 'running');
  const waiting = sum(agents, 'waiting') + (d.needs?.length ?? 0);
  return (
    <>
      <Head d={d} running={running} waiting={waiting} />
      {d.tiles && <Strip t={d.tiles} agents={agents} waiting={waiting} />}
      {d.needs && <Needs needs={d.needs} />}
      {agents && agents.length > 0 && (
        <Section title="Your agents, now" sub="live · refreshes every 3 s">
          <NowBoard agents={agents} />
        </Section>
      )}
      {!!d.reviews?.length && (
        <Section title="Pull request reviews" sub="click a count to see those pull requests">
          <Reviews reviews={d.reviews} />
        </Section>
      )}
      {(d.activity ?? d.stacks) && (
        <div {...stylex.props(styles.split)}>
          {d.activity && (
            <Section title="Recent activity">
              <Card>
                <Feed events={d.activity.slice(0, 6)} showSource />
              </Card>
            </Section>
          )}
          {d.stacks && <Health stacks={d.stacks} />}
        </div>
      )}
    </>
  );
}

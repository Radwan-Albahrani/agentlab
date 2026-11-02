import { useOverview } from '../api/queries';
import type { Overview as Data } from '../api/types';
import { Screen } from '../app/Screen';
import { StackLead, StackName, WATCHER_PENDING } from '../app/stacks';
import { useCanSee } from '../app/useCanSee';
import { ago, gb, pct, plural, toneFor } from '../lib/format';
import { Actions } from '../ui/actions';
import { LinkButton } from '../ui/Button';
import { Card, CardBody } from '../ui/Card';
import { Feed } from '../ui/Feed';
import { Grid2, StatGrid } from '../ui/layout';
import { Empty, PageHead, Section, Stat } from '../ui/page';
import { List, Row } from '../ui/Row';
import { Pill } from '../ui/status';
import { Note } from '../ui/text';
import { When } from '../ui/When';

export function Overview() {
  const query = useOverview();
  return (
    <Screen title="Overview" query={query}>
      {(d) => <OverviewView d={d} />}
    </Screen>
  );
}

function Tiles({ t }: { t: NonNullable<Data['tiles']> }) {
  const disk = t.disk ? pct(t.disk.used, t.disk.size) : 0;
  return (
    <StatGrid>
      <Stat
        label="Agents online"
        value={t.agents.online}
        of={` / ${t.agents.total}`}
        sub="agents answering"
        tone={t.agents.online === t.agents.total ? 'ok' : 'bad'}
        to={t.agents.link ? '/agents' : null}
      />
      {t.companions && (
        <Stat
          label="Companions"
          value={t.companions.live}
          of={` / ${t.companions.total}`}
          sub={t.companions.waiting ? `${t.companions.waiting} waiting on you` : 'live in Slack'}
          tone={t.companions.waiting ? 'warn' : t.companions.live === t.companions.total ? 'ok' : 'bad'}
          to={t.companions.link}
        />
      )}
      {'disk' in t && (
        <Stat
          label={t.diskLabel ?? 'Disk'}
          value={t.disk ? disk.toFixed(0) : '–'}
          of={t.disk ? '%' : undefined}
          sub={t.disk ? `${gb(t.disk.avail, 0)} free of ${gb(t.disk.size, 0)}` : 'no data yet'}
          tone={t.disk ? toneFor(disk) : 'idle'}
          to="/storage"
        />
      )}
      {t.memory && (
        <Stat
          label="Agent memory"
          value={(t.memory.usedMB / 1024).toFixed(1)}
          of=" GB"
          sub={`of ${(t.memory.poolMB / 1024).toFixed(0)} GB shared`}
        />
      )}
    </StatGrid>
  );
}

function Needs({ needs }: { needs: NonNullable<Data['needs']> }) {
  return (
    <Section title="Needs you" sub={needs.length ? plural(needs.length, 'item') : undefined}>
      <Card>
        {needs.length ? (
          <List>
            {needs.map((n, i) => (
              <Row
                key={i}
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
        ) : (
          <Empty title="All clear" text="Nothing needs you right now." />
        )}
      </Card>
    </Section>
  );
}

function Stacks({ stacks }: { stacks: NonNullable<Data['stacks']> }) {
  const servicesLink = useCanSee()('/services');
  return (
    <Section
      title="Stacks"
      right={servicesLink ? <LinkButton label="Services" icon="layers" variant="quiet" small to="/services" /> : undefined}
    >
      <Card>
        {stacks.rows.length ? (
          <List>
            {stacks.rows.map((s) => {
              const down = s.containers.filter((c) => !c.healthy);
              return (
                <Row
                  key={s.id}
                  nestedUnder={s.role && s.role !== 'agent' ? s.profile : null}
                  lead={<StackLead stack={s} />}
                  title={<StackName stack={s} />}
                  detail={
                    down.length
                      ? `${down.length} of ${s.containers.length} down: ${down.map((c) => c.service).join(', ')}`
                      : `${plural(s.containers.length, 'service')} running`
                  }
                  actions={<Pill tone={down.length ? 'bad' : 'ok'}>{down.length ? 'Down' : 'Healthy'}</Pill>}
                />
              );
            })}
          </List>
        ) : (
          <Empty {...WATCHER_PENDING} />
        )}
        <CardBody>
          <Note>
            Checked <When t={stacks.at} />
          </Note>
        </CardBody>
      </Card>
    </Section>
  );
}

function OverviewView({ d }: { d: Data }) {
  return (
    <>
      <PageHead title="Overview" sub="What needs you, and what your agents are doing." />
      {d.tiles && <Tiles t={d.tiles} />}
      {d.needs && <Needs needs={d.needs} />}
      {(d.activity ?? d.stacks) && (
        <Grid2>
          {d.activity && (
            <Section title="Recent activity">
              <Card>
                <Feed events={d.activity} showSource />
              </Card>
            </Section>
          )}
          {d.stacks && <Stacks stacks={d.stacks} />}
        </Grid2>
      )}
    </>
  );
}

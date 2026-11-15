import * as stylex from '@stylexjs/stylex';
import { useParams } from 'react-router';
import { useAgent, useNowBoard } from '../api/queries';
import type { AgentPage } from '../api/types';
import { AgentCard, Launch } from '../app/AgentCard';
import { Lane } from '../app/NowBoard';
import { Screen } from '../app/Screen';
import { StackBlock } from '../app/stacks';
import { useCanSee } from '../app/useCanSee';
import { STATE_PILL } from '../lib/companion';
import { gb, pct, plural } from '../lib/format';
import { media, space } from '../theme/tokens.stylex';
import { Devices } from './accounts/Devices';
import { LinkButton } from '../ui/Button';
import { AgentLinkCard, Card, CardBody } from '../ui/Card';
import { Grow, Split, Stack } from '../ui/layout';
import { Empty, Hero, Section } from '../ui/page';
import { Ring } from '../ui/Ring';
import { Badge, CompanionAvatar, Pill, Tag } from '../ui/status';
import { Text } from '../ui/text';

const styles = stylex.create({
  grid: {
    display: 'grid',
    gridTemplateColumns: { default: 'minmax(0, 1.1fr) minmax(0, 1fr)', [media.narrow]: '1fr' },
    gap: space.xxl,
    alignItems: 'start',
  },
  side: { display: 'grid', gap: space.xxl, minWidth: 0 },
  launch: { maxWidth: 560 },
});

export function Agent() {
  const { name = '' } = useParams();
  const query = useAgent(name);
  return (
    <Screen title={name} query={query}>
      {(d) => <AgentView name={name} d={d} />}
    </Screen>
  );
}

function AgentView({ name, d }: { name: string; d: AgentPage }) {
  const canSee = useCanSee();
  const live = useNowBoard().data?.agents.find((a) => a.name === name);
  const r = d.agent.resources;
  return (
    <>
      <Hero
        profile={name}
        avatar={<Badge name={name} size="xl" />}
        title={
          <>
            {name}{' '}
            <Pill tone={d.up ? 'ok' : 'bad'} dot>
              {d.up ? 'Running' : 'Down'}
            </Pill>
          </>
        }
        sub={
          <>
            {d.owner ? `${d.owner} · ` : ''}
            {plural(d.companions.length, 'companion')}
            {d.agent.online ? '' : ' · not answering'}
          </>
        }
        actions={
          <>
            <LinkButton label="Sign-ins & connectors" icon="key" to={`/agents/${name}/accounts`} />
            {canSee('/config') && <LinkButton label="Config" icon="sliders" to={`/config/agentlab-agent-${name}`} />}
          </>
        }
      />
      {d.agent.links && (
        <div {...stylex.props(styles.launch)}>
          <Launch links={d.agent.links} />
        </div>
      )}
      {d.agent.online && d.agent.onboarded === false && (
        <Card accent="info">
          <CardBody>
            <Split>
              <Text>
                <b>Finish setting up {name}.</b> Sign in to Claude Code or Codex; the chat opens once that is done.
              </Text>
              <LinkButton label="Set up" icon="arrow" variant="primary" to={`/agents/${name}/onboarding`} />
            </Split>
          </CardBody>
        </Card>
      )}
      {live && (
        <Section
          title="Right now"
          sub={`${live.running.length} running · ${live.waiting.length} waiting on you · click one to open the chat`}
        >
          <Lane a={live} linked={false} />
        </Section>
      )}
      <div {...stylex.props(styles.grid)}>
        <Section title="Accounts">
          <AgentCard a={d.agent} linked={false} />
        </Section>
        <div {...stylex.props(styles.side)}>
          {(!!r || !!d.disk) && (
            <Section title="Resources">
              <Stack gap="lg">
                {r && (
                  <Ring
                    label="Memory"
                    pct={pct(r.usedMB, r.limitMB || 1)}
                    value={`${(r.usedMB / 1024).toFixed(1)} GB`}
                    sub={`of ${((r.limitMB || 0) / 1024).toFixed(0)} GB${r.running.length ? ` · ${r.running.length} heavy running` : ''}`}
                  />
                )}
                {d.disk && (
                  <Ring
                    label="Disk"
                    pct={pct(d.disk.used, d.disk.size)}
                    value={`${gb(d.disk.avail, 0)} free`}
                    sub={`${gb(d.disk.used)} of ${gb(d.disk.size, 0)} used`}
                  />
                )}
              </Stack>
            </Section>
          )}
          <Section title="Companions">
            {d.companions.length ? (
              <Stack>
                {d.companions.map((c) => {
                  const [label, tone] = STATE_PILL[c.state] ?? ['Unknown', 'bad'];
                  return (
                    <AgentLinkCard key={c.name} profile={name} to={`/agents/${name}/${c.name}`}>
                      <CompanionAvatar profile={name} />
                      <Grow>
                        <Text weight="semibold">{c.display}</Text>
                        <Tag>companion</Tag>
                        <Text block tone="muted" size="md">
                          {c.working} working · {c.waiting} waiting on you · {plural(c.tasks, 'task')}
                        </Text>
                      </Grow>
                      <Pill tone={tone} dot>
                        {label}
                      </Pill>
                    </AgentLinkCard>
                  );
                })}
              </Stack>
            ) : (
              <Card>
                <Empty title="No companions" text="Bots that work in this agent's name show up here." icon="bot" />
              </Card>
            )}
          </Section>
        </div>
      </div>
      {d.agent.online && <Devices agent={name} />}
      {d.containers && (
        <Section title="Containers">
          <Card>
            {d.containers.length ? (
              d.containers.map((s) => <StackBlock key={s.id} stack={s} />)
            ) : (
              <Empty title="No containers found" icon="layers" />
            )}
          </Card>
        </Section>
      )}
    </>
  );
}

import { useParams } from 'react-router';
import { useAgent } from '../api/queries';
import type { AgentPage, Pool } from '../api/types';
import { AgentCard } from '../app/AgentCard';
import { Screen } from '../app/Screen';
import { StackBlock } from '../app/stacks';
import { useCanSee } from '../app/useCanSee';
import { STATE_PILL } from '../lib/companion';
import { gb, pct, plural } from '../lib/format';
import { Devices } from './accounts/Devices';
import { LinkButton } from '../ui/Button';
import { AgentLinkCard, Card, CardBody } from '../ui/Card';
import { Grid2, Grow, Split, Stack } from '../ui/layout';
import { Empty, Hero, Section } from '../ui/page';
import { Badge, CompanionAvatar, Meter, Pill, Tag } from '../ui/status';
import { Text } from '../ui/text';

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
            Agent profile · {plural(d.companions.length, 'companion')}
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
      <Grid2>
        <AgentCard a={d.agent} linked={false} />
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
      </Grid2>
      {d.disk && <DiskCard disk={d.disk} />}
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

function DiskCard({ disk }: { disk: Pool }) {
  return (
    <Card>
      <CardBody>
        <Split>
          <b>Disk</b>
          <Text tone="muted">
            {gb(disk.used)} of {gb(disk.size, 0)}
          </Text>
        </Split>
        <Meter pct={pct(disk.used, disk.size)} />
      </CardBody>
    </Card>
  );
}

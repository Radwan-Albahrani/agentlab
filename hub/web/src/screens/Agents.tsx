import { useAgents } from '../api/queries';
import type { Agents as Data } from '../api/types';
import { AgentCard } from '../app/AgentCard';
import { Screen } from '../app/Screen';
import { pct } from '../lib/format';
import { Card, CardBody } from '../ui/Card';
import { Grid2, Split } from '../ui/layout';
import { PageHead } from '../ui/page';
import { Meter } from '../ui/status';
import { Text } from '../ui/text';

export function Agents() {
  const query = useAgents();
  return (
    <Screen title="Agents" query={query}>
      {(d) => <AgentsView d={d} />}
    </Screen>
  );
}

function AgentsView({ d }: { d: Data }) {
  return (
    <>
      <PageHead title="Agents" sub="Sign-ins, connectors and quick links for every agent." />
      {d.memory && <SharedMemory usedMB={d.memory.usedMB} poolMB={d.memory.poolMB} />}
      <Grid2>
        {d.agents.map((a) => (
          <AgentCard key={a.name} a={a} />
        ))}
      </Grid2>
    </>
  );
}

function SharedMemory({ usedMB, poolMB }: { usedMB: number; poolMB: number }) {
  return (
    <Card>
      <CardBody>
        <Split>
          <b>Shared agent memory</b>
          <Text tone="muted">
            {(usedMB / 1024).toFixed(1)} of {(poolMB / 1024).toFixed(0)} GB
          </Text>
        </Split>
        <Meter pct={pct(usedMB, poolMB)} />
      </CardBody>
    </Card>
  );
}

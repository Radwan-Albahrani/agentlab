import { useAgents } from '../api/queries';
import type { Agents as Data } from '../api/types';
import { AgentCard } from '../app/AgentCard';
import { Screen } from '../app/Screen';
import { pct } from '../lib/format';
import { Grid2 } from '../ui/layout';
import { Appear } from '../ui/motion';
import { PageHead } from '../ui/page';
import { Ring } from '../ui/Ring';

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
      <PageHead title="Agents" sub="Sign-ins, connectors and the ways into every agent." />
      {d.memory && (
        <Ring
          label="Shared agent memory"
          pct={pct(d.memory.usedMB, d.memory.poolMB)}
          value={`${(d.memory.usedMB / 1024).toFixed(1)} GB`}
          sub={`of ${(d.memory.poolMB / 1024).toFixed(0)} GB for every agent together`}
        />
      )}
      <Grid2>
        {d.agents.map((a, i) => (
          <Appear key={a.name} i={i}>
            <AgentCard a={a} />
          </Appear>
        ))}
      </Grid2>
    </>
  );
}

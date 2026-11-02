import { useParams } from 'react-router-dom';
import { useAccounts } from '../../api/queries';
import type { AccountsPage } from '../../api/types';
import { Screen } from '../../app/Screen';
import { LinkButton } from '../../ui/Button';
import { Card, CardBody } from '../../ui/Card';
import { Crumb, Hero, Section } from '../../ui/page';
import { List } from '../../ui/Row';
import { Badge } from '../../ui/status';
import { AddConnector, ConnectorRow } from './Connectors';
import { EnvVars } from './EnvVars';
import { SignIn } from './SignIn';

export function Accounts() {
  const { name = '' } = useParams();
  const query = useAccounts(name);
  return (
    <Screen title={`${name} sign-ins`} query={query}>
      {(d) => <AccountsView agent={name} d={d} />}
    </Screen>
  );
}

function AccountsView({ agent, d }: { agent: string; d: AccountsPage }) {
  return (
    <>
      <Crumb profile={agent} here="Sign-ins & connectors" />
      <Hero
        profile={agent}
        avatar={<Badge name={agent} size="xl" />}
        title="Sign-ins & connectors"
        sub={
          <>
            Everything the <b>{agent}</b> agent signs into. Logins and tokens stay in this agent only.
          </>
        }
        actions={
          <>
            {d.browserUrl && <LinkButton label="Live browser" icon="browser" to={d.browserUrl} />}
            <LinkButton label={`${agent} agent`} icon="arrow" to={`/agents/${agent}`} />
          </>
        }
      />
      {d.notice && (
        <Card accent="warn">
          <CardBody>{d.notice}</CardBody>
        </Card>
      )}
      <Section title="AI accounts" sub="One is enough: Claude or Codex.">
        <Card>
          <List>
            {d.ai.map((f) => (
              <SignIn key={f.key} agent={agent} f={f} keys={d.keys} />
            ))}
          </List>
        </Card>
      </Section>
      <Section title="GitHub">
        <Card>
          <List>
            <SignIn agent={agent} f={d.github} keys={d.keys} />
          </List>
        </Card>
      </Section>
      <Section
        title="Connectors"
        sub="Each becomes a tool for both Claude and Codex; one sign-in each, and new chats pick it up."
      >
        <Card>
          <List>
            {d.connectors.map((c) => (
              <ConnectorRow key={c.key} agent={agent} c={c} />
            ))}
            <AddConnector agent={agent} />
          </List>
        </Card>
      </Section>
      {d.env && <EnvVars agent={agent} env={d.env} />}
    </>
  );
}

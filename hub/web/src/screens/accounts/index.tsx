import * as stylex from '@stylexjs/stylex';
import { useParams } from 'react-router';
import { useAccounts } from '../../api/queries';
import type { AccountsPage, Flow } from '../../api/types';
import { Screen } from '../../app/Screen';
import { hueTheme } from '../../theme/hues';
import { space } from '../../theme/tokens.stylex';
import { LinkButton } from '../../ui/Button';
import { StatGrid } from '../../ui/layout';
import { Crumb, Hero, Section, Stat } from '../../ui/page';
import { Badge, Pill } from '../../ui/status';
import { AddConnector, ConnectorGrid, ConnectorTile } from './Connectors';
import { EnvVars } from './EnvVars';
import { Callout } from './flow';
import { ProviderGrid, SignIn } from './SignIn';

const styles = stylex.create({
  page: { display: 'grid', gap: space.giant, minWidth: 0 },
});

const names = (flows: Flow[]) =>
  flows
    .filter((f) => f.signedIn)
    .map((f) => f.name)
    .join(' + ');

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
  const tools = [d.github, ...(d.tools ?? [])];
  const ai = names(d.ai);
  const added = d.connectors.filter((c) => c.added);
  const ready = added.filter((c) => c.ready).length;
  const waiting = added.length - ready;
  const more = d.connectors.length - added.length;
  return (
    <div {...stylex.props(hueTheme(agent), styles.page)}>
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
      {d.notice && <Callout tone="warn" icon="alert" title={d.notice} />}
      {!ai && (
        <Callout tone="warn" icon="bot" title="No AI account yet">
          Sign in to Claude or Codex below; the agent can&apos;t work without one.
        </Callout>
      )}
      <StatGrid>
        <Stat
          label="AI accounts"
          value={d.ai.filter((f) => f.signedIn).length}
          of={`/ ${d.ai.length}`}
          sub={ai || 'None signed in'}
          tone={ai ? 'ok' : 'warn'}
          to="#ai"
        />
        <Stat
          label="GitHub & tools"
          value={tools.filter((f) => f.signedIn).length}
          of={`/ ${tools.length}`}
          sub={names(tools) || 'Optional'}
          tone={d.github.signedIn ? 'ok' : 'idle'}
          to="#tools"
        />
        <Stat
          label="Connectors"
          value={ready}
          of="ready"
          sub={waiting ? `${waiting} waiting for sign-in` : more ? `${more} more available` : 'All added'}
          tone={waiting ? 'warn' : ready ? 'ok' : 'idle'}
          to="#connectors"
        />
      </StatGrid>
      <Section id="ai" icon="bot" title="AI accounts" sub="One is enough: Claude or Codex.">
        <ProviderGrid>
          {d.ai.map((f) => (
            <SignIn key={f.key} agent={agent} f={f} keys={d.keys} next={!ai} />
          ))}
        </ProviderGrid>
      </Section>
      <Section id="tools" icon="github" title="GitHub & developer tools" sub="Command-line tools the agent uses as you.">
        <ProviderGrid>
          {tools.map((f) => (
            <SignIn key={f.key} agent={agent} f={f} keys={d.keys} />
          ))}
        </ProviderGrid>
      </Section>
      <Section
        id="connectors"
        icon="layers"
        title="Connectors"
        sub="Each becomes a tool for both Claude and Codex; one sign-in each, and new chats pick it up."
        right={added.length > 0 && <Pill tone={waiting ? 'warn' : 'ok'}>{`${ready} of ${added.length} ready`}</Pill>}
      >
        <ConnectorGrid>
          {d.connectors.map((c) => (
            <ConnectorTile key={c.key} agent={agent} c={c} />
          ))}
          <AddConnector agent={agent} />
        </ConnectorGrid>
      </Section>
      {d.env && <EnvVars agent={agent} env={d.env} />}
    </div>
  );
}

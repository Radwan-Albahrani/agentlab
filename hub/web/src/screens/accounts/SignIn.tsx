import type { ReactNode } from 'react';
import type { AccountsPage, Flow } from '../../api/types';
import { CopyButton } from '../../ui/actions';
import { Button } from '../../ui/Button';
import { Brand } from '../../ui/Icon';
import { SubmitField } from '../../ui/inputs';
import { Inline } from '../../ui/layout';
import { IconBox, Row } from '../../ui/Row';
import { Pill, Tag } from '../../ui/status';
import { Note, Text } from '../../ui/text';
import { DeviceCode, FlowBox, FlowEnd, OpenSignInStep, Step, Steps, Terminal } from './flow';
import { useAccountAct } from './useAccountAct';

type Keys = AccountsPage['keys'];

export function SignIn({ agent, f, keys }: { agent: string; f: Flow; keys: Keys }) {
  const run = useAccountAct(agent);
  const start = (how?: string) => run({ action: 'start', p: f.key, how });
  let actions: ReactNode;
  if (f.active) actions = <Pill tone="info">Signing in…</Pill>;
  else if (f.signedIn)
    actions = (
      <>
        <Pill tone="ok">Signed in</Pill>
        <Button label="Switch" variant="quiet" small onClick={() => start()} />
        <Button
          label="Sign out"
          variant="quiet"
          small
          onClick={() => run({ action: 'logout', p: f.key }, `Sign ${agent} out of ${f.name}?`)}
        />
      </>
    );
  else
    actions = (
      <>
        {f.key === 'codex' && <Button label="Browser link" variant="quiet" small onClick={() => start('browser')} />}
        <Button label="Sign in" variant="primary" small onClick={() => start()} />
      </>
    );
  const detail = f.signedIn
    ? f.detail
    : `Not signed in${f.key === 'codex' ? ' · use Browser link if your ChatGPT workspace has device-code login off' : ''}`;
  return (
    <>
      <Row
        lead={
          <IconBox>
            <Brand name={f.key} />
          </IconBox>
        }
        title={
          <>
            {f.name}
            {f.key === 'github' && f.mcpReady && <Tag>git · gh · MCP</Tag>}
          </>
        }
        detail={detail}
        actions={actions}
      />
      {f.active && <SignInSteps agent={agent} f={f} keys={keys} />}
      {f.key === 'github' && f.signedIn && !f.mcpReady && !f.active && <GithubToken agent={agent} />}
    </>
  );
}

function SecondStep({ f, send }: { f: Flow; send: (text: string) => unknown }) {
  if (f.key === 'codex' && f.mode === 'browser')
    return (
      <Step
        n={2}
        title="Paste the address that fails to load"
        sub={
          <>
            After signing in, ChatGPT sends you to <b>localhost:1455</b> or <b>127.0.0.1:1455</b>, which won&apos;t open. Copy
            that whole address here.
          </>
        }
      >
        <SubmitField placeholder="127.0.0.1:1455/auth/callback?…" button="Finish" onSubmit={send} />
      </Step>
    );
  if (f.key === 'codex' || f.key === 'github' || f.key === 'expo')
    return (
      <Step
        n={2}
        done={f.done}
        title={f.key === 'expo' ? 'Approve if the page shows this code' : 'Enter this code'}
        sub={
          f.key === 'expo'
            ? 'If it then shows a number, pick the same one in the terminal below with ↑ ↓ and Enter.'
            : 'On the page that opens.'
        }
      >
        {f.code ? (
          <Inline>
            <DeviceCode code={f.code} />
            <CopyButton text={f.code} />
          </Inline>
        ) : (
          <Note>Waiting for the code…</Note>
        )}
      </Step>
    );
  return (
    <Step n={2} title="Paste the code (if shown)" sub="Some browsers show a code instead of returning.">
      <SubmitField placeholder="Paste code" button="Submit" onSubmit={send} />
    </Step>
  );
}

function SignInSteps({ agent, f, keys }: { agent: string; f: Flow; keys: Keys }) {
  const run = useAccountAct(agent);
  return (
    <FlowBox>
      <Steps>
        <OpenSignInStep provider={f.name} url={f.url} sub={f.hint} />
        <SecondStep f={f} send={(text) => run({ action: 'send', p: f.key, text })} />
        <Step n={3} done={f.done} title="Done" sub={`This updates by itself when ${f.name} confirms.`} />
      </Steps>
      {f.done && (
        <Text tone="ok" weight="semibold">
          ✓ Signed in.
        </Text>
      )}
      <Terminal screen={f.screen}>
        <Inline gap="xs">
          {keys.map((k) => (
            <Button
              key={k.value}
              label={k.label}
              variant="quiet"
              small
              onClick={() => run({ action: 'key', p: f.key, key: k.value })}
            />
          ))}
        </Inline>
      </Terminal>
      <FlowEnd finished={f.done} onEnd={() => run({ action: 'stop', p: f.key })} />
    </FlowBox>
  );
}

function GithubToken({ agent }: { agent: string }) {
  const run = useAccountAct(agent);
  return (
    <FlowBox>
      <Note>
        git and gh are signed in. For the GitHub MCP tools, paste a{' '}
        <a
          href={`https://github.com/settings/tokens/new?scopes=repo,read:org,workflow&description=agent-${agent}`}
          target="_blank"
          rel="noopener"
        >
          <u>personal access token</u>
        </a>
        :
      </Note>
      <SubmitField placeholder="ghp_…" button="Save" onSubmit={(token) => run({ action: 'token', p: 'github', token })} />
    </FlowBox>
  );
}

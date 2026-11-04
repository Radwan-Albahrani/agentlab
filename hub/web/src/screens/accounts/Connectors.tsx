import { useState } from 'react';
import type { Connector } from '../../api/types';
import { Button } from '../../ui/Button';
import { Brand } from '../../ui/Icon';
import { InlineForm, SubmitField, TextInput } from '../../ui/inputs';
import { IconBox, Row } from '../../ui/Row';
import { Pill } from '../../ui/status';
import { Note, Text } from '../../ui/text';
import { FlowBox, FlowEnd, OpenSignInStep, Step, Steps, Terminal } from './flow';
import { useAccountAct } from './useAccountAct';

export function ConnectorRow({ agent, c }: { agent: string; c: Connector }) {
  const run = useAccountAct(agent);
  const f = c.flow;
  const actions = !c.added ? (
    <Button label="Connect" small onClick={() => run({ action: 'mcp-add', p: c.key })} />
  ) : (
    <>
      <Pill tone={c.ready ? 'ok' : 'warn'}>{c.ready ? 'Ready' : 'Not signed in'}</Pill>
      {!c.ready && !f?.active && (
        <Button label="Sign in" variant="primary" small onClick={() => run({ action: 'mcp-login', p: c.key })} />
      )}
      <Button
        label={c.ready ? 'Sign out' : 'Remove'}
        variant="quiet"
        small
        onClick={() => run({ action: 'mcp-remove', p: c.key }, `${c.ready ? 'Sign out of' : 'Remove'} ${c.name} on ${agent}?`)}
      />
    </>
  );
  return (
    <>
      <Row
        lead={
          <IconBox>
            <Brand name={c.key} label={c.name} />
          </IconBox>
        }
        title={c.name}
        detail={c.what}
        actions={actions}
      />
      {f?.active && (
        <FlowBox>
          <Steps>
            <OpenSignInStep provider={c.name} url={f.url} title="Open the sign-in page and approve" />
            <Step
              n={2}
              done={f.finished}
              title="Paste the address that fails to load"
              sub={
                <>
                  After approving you land on a <b>localhost</b> or <b>127.0.0.1</b> page that won&apos;t open. Copy that whole
                  address here.
                </>
              }
            >
              <SubmitField
                placeholder="localhost:…/oauth/callback?code=…"
                button="Finish"
                onSubmit={(text) => run({ action: 'mcp-send', p: c.key, text })}
              />
            </Step>
          </Steps>
          {f.ok && (
            <Text tone="ok" weight="semibold">
              ✓ Signed in, for Claude and Codex.
            </Text>
          )}
          {f.finished && !f.ok && <Note>Sign-in ended without success; see Terminal and try again.</Note>}
          <Terminal screen={f.screen} />
          <FlowEnd finished={f.finished} onEnd={() => run({ action: 'mcp-stop', p: c.key })} />
        </FlowBox>
      )}
    </>
  );
}

export function AddConnector({ agent }: { agent: string }) {
  const run = useAccountAct(agent);
  const [server, setServer] = useState({ name: '', url: '' });
  const add = async () => {
    if (await run({ action: 'mcp-custom', ...server })) setServer({ name: '', url: '' });
  };
  return (
    <Row
      wrap
      lead={<IconBox icon="plus" />}
      title="Any MCP server"
      detail="A remote MCP address from the service's docs, with a short name."
      actions={
        <InlineForm onSubmit={add}>
          <TextInput
            width="short"
            value={server.name}
            onChange={(v) => {
              setServer({ ...server, name: v });
            }}
            placeholder="name, e.g. stripe"
          />
          <TextInput
            value={server.url}
            onChange={(v) => {
              setServer({ ...server, url: v });
            }}
            placeholder="https://mcp.example.com/mcp"
          />
          <Button type="submit" label="Add" />
        </InlineForm>
      }
    />
  );
}

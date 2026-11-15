import * as stylex from '@stylexjs/stylex';
import { useState } from 'react';
import { useEnvValue } from '../../api/queries';
import type { AccountsPage } from '../../api/types';
import { colors, font, radius, space, text } from '../../theme/tokens.stylex';
import { Button } from '../../ui/Button';
import { Card, CardBody } from '../../ui/Card';
import { Disclosure } from '../../ui/controls';
import { useAct } from '../../ui/feedback';
import { InlineForm, TextArea, TextInput } from '../../ui/inputs';
import { Empty, Section } from '../../ui/page';
import { List, Row } from '../../ui/Row';
import { Pill } from '../../ui/status';
import { Eyebrow } from '../../ui/text';

type Env = NonNullable<AccountsPage['env']>;

const styles = stylex.create({
  name: { fontFamily: font.mono, fontSize: text.md, fontWeight: 600, overflowWrap: 'anywhere' },
  value: {
    display: 'inline-block',
    maxWidth: '100%',
    marginTop: space.xxs,
    paddingBlock: 1,
    paddingInline: space.sm,
    borderRadius: radius.xs,
    fontFamily: font.mono,
    fontSize: text.xs,
    color: colors.muted,
    backgroundColor: colors.sunk,
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: colors.line,
    overflowWrap: 'anywhere',
  },
  shown: { color: colors.fg },
  add: { display: 'grid', gap: space.md },
});

export function EnvVars({ agent, env }: { agent: string; env: Env }) {
  const keys = Object.keys(env).sort();
  return (
    <Section
      title="Environment variables"
      icon="terminal"
      sub="Every command the agent runs gets these; a change applies to the next command."
      right={keys.length > 0 && <Pill>{keys.length === 1 ? '1 variable' : `${keys.length} variables`}</Pill>}
    >
      <Card>
        {keys.length ? (
          <List>
            {keys.map((k) => (
              <EnvRow key={k} agent={agent} name={k} masked={env[k]?.masked ?? ''} />
            ))}
          </List>
        ) : (
          <Empty title="No variables yet" text="Add an API key or setting below, or paste a whole .env file." icon="key" />
        )}
        <CardBody divided>
          <div {...stylex.props(styles.add)}>
            <Eyebrow>Add a variable</Eyebrow>
            <SetVar agent={agent} />
          </div>
          <ImportVars agent={agent} />
        </CardBody>
      </Card>
    </Section>
  );
}

const envUrl = (agent: string, what: 'set' | 'delete' | 'import') => `/api/agents/${agent}/accounts/env/${what}`;

function EnvRow({ agent, name, masked }: { agent: string; name: string; masked: string }) {
  const act = useAct();
  const [shown, setShown] = useState(false);
  const { data } = useEnvValue(agent, name, shown);
  return (
    <Row
      icon="key"
      title={<span {...stylex.props(styles.name)}>{name}</span>}
      detail={
        <span {...stylex.props(styles.value, shown && !!data && styles.shown)}>
          {shown && data ? (data.value ?? '') : masked}
        </span>
      }
      actions={
        <>
          <Button
            label={shown ? 'Hide' : 'Show'}
            icon="eye"
            variant="quiet"
            small
            onClick={() => {
              setShown(!shown);
            }}
          />
          <Button
            label="Remove"
            icon="trash"
            variant="danger"
            small
            iconOnly
            onClick={() => act(envUrl(agent, 'delete'), { key: name }, { confirm: `Remove ${name} from ${agent}?` })}
          />
        </>
      }
    />
  );
}

function SetVar({ agent }: { agent: string }) {
  const act = useAct();
  const [form, setForm] = useState({ key: '', value: '' });
  const save = async () => {
    if (await act(envUrl(agent, 'set'), form)) setForm({ key: '', value: '' });
  };
  return (
    <InlineForm onSubmit={save}>
      <TextInput
        width="short"
        mono
        value={form.key}
        onChange={(v) => {
          setForm({ ...form, key: v });
        }}
        placeholder="NAME"
      />
      <TextInput
        type="password"
        value={form.value}
        onChange={(v) => {
          setForm({ ...form, value: v });
        }}
        placeholder="value"
      />
      <Button type="submit" label="Set" />
    </InlineForm>
  );
}

function ImportVars({ agent }: { agent: string }) {
  const act = useAct();
  const [file, setFile] = useState('');
  const save = async () => {
    if (await act(envUrl(agent, 'import'), { text: file })) setFile('');
  };
  return (
    <Disclosure label="Paste a .env file">
      <InlineForm onSubmit={save}>
        <TextArea value={file} onChange={setFile} placeholder={'API_KEY=…\nOTHER=…'} />
        <Button type="submit" label="Import" />
      </InlineForm>
    </Disclosure>
  );
}

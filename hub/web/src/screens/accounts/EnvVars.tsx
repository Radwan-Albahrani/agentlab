import { useState } from 'react';
import { useEnvValue } from '../../api/queries';
import type { AccountsPage } from '../../api/types';
import { Button } from '../../ui/Button';
import { Card, CardBody } from '../../ui/Card';
import { Disclosure } from '../../ui/controls';
import { useAct } from '../../ui/feedback';
import { InlineForm, TextArea, TextInput } from '../../ui/inputs';
import { Section } from '../../ui/page';
import { List, Row } from '../../ui/Row';
import { Mono } from '../../ui/text';

type Env = NonNullable<AccountsPage['env']>;

export function EnvVars({ agent, env }: { agent: string; env: Env }) {
  const keys = Object.keys(env).sort();
  return (
    <Section title="Environment variables" sub="Every command the agent runs gets these; a change applies to the next command.">
      <Card>
        <List>
          {keys.map((k) => (
            <EnvRow key={k} agent={agent} name={k} masked={env[k]?.masked ?? ''} />
          ))}
        </List>
        <CardBody divided={keys.length > 0}>
          <SetVar agent={agent} />
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
      title={<Mono>{name}</Mono>}
      detail={<Mono>{shown && data ? (data.value ?? '') : masked}</Mono>}
      actions={
        <>
          <Button
            label={shown ? 'Hide' : 'Show'}
            icon="eye"
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
  const [text, setText] = useState('');
  const save = async () => {
    if (await act(envUrl(agent, 'import'), { text })) setText('');
  };
  return (
    <Disclosure label="Paste a .env file">
      <InlineForm onSubmit={save}>
        <TextArea value={text} onChange={setText} placeholder={'API_KEY=…\nOTHER=…'} />
        <Button type="submit" label="Import" />
      </InlineForm>
    </Disclosure>
  );
}

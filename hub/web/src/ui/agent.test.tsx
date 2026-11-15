import { render, screen } from '@testing-library/react';
import { createAgent, registerTools, type AgentStep } from '@ui-sdk/react/agent';
import { useState } from 'react';
import { Button } from './Button';
import { RadioCards, Segments, Switch } from './controls';
import { ConfirmDialog } from './Dialog';
import { Field, TextInput } from './inputs';
import { MoreMenu } from './Menu';
import { Picker } from './Picker';
import { Select } from './Select';
import { Tabs } from './Tabs';

declare global {
  var IS_REACT_ACT_ENVIRONMENT: boolean | undefined;
}
// an agent's steps arrive like a person's events, outside act, and the SDK checks each controlled value took;
// Testing Library turns the act environment on in its own beforeAll, which runs first
beforeAll(() => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = false;
});

// one bridge per file: it has no destroy and remembers what earlier tests removed
const agent = createAgent();
const run = (steps: AgentStep[]) => agent.act({ steps });

interface Seen {
  name: string;
  presenting: boolean;
  filter: string;
  mode: string;
  channel: string;
  view: string;
  files: string;
  ran: string[];
}

function Settings({ seen }: { seen: Seen }) {
  const [name, setName] = useState('');
  const [presenting, setPresenting] = useState(false);
  const [filter, setFilter] = useState('all');
  const [mode, setMode] = useState('auto');
  const [channel, setChannel] = useState('');
  const [view, setView] = useState('overview');
  const [files, setFiles] = useState<'keep' | 'delete'>('keep');
  const [ask, setAsk] = useState<string | null>(null);
  Object.assign(seen, { name, presenting, filter, mode, channel, view, files });
  return (
    <>
      <Field label="Agent name">
        <TextInput value={name} onChange={setName} />
      </Field>
      <Switch
        on={presenting}
        label="Presenting"
        onToggle={() => {
          setPresenting(!presenting);
        }}
      />
      <Segments
        label="Filter tasks"
        value={filter}
        options={[
          { value: 'all', label: 'All' },
          { value: 'errands', label: 'Errands' },
        ]}
        onChange={setFilter}
      />
      <Select
        label="Review mode"
        value={mode}
        options={[
          { value: 'auto', label: 'Automatic' },
          { value: 'ask', label: 'On request' },
        ]}
        onChange={setMode}
      />
      <Picker
        label="Channel"
        placeholder="Pick a channel"
        items={[
          { value: 'C1', label: '#general' },
          { value: 'C2', label: '#random' },
        ]}
        value={channel}
        onChange={setChannel}
      />
      <Tabs
        label="Scout views"
        value={view}
        onChange={setView}
        items={[
          { value: 'overview', label: 'Overview', content: 'Everything' },
          { value: 'tasks', label: 'Tasks', content: 'The tasks' },
        ]}
      />
      <RadioCards
        label="What happens to its files"
        value={files}
        options={[
          { value: 'keep', title: 'Keep them' },
          { value: 'delete', title: 'Delete them', danger: true },
        ]}
        onChange={setFiles}
      />
      <Button label="Refresh" icon="refresh" iconOnly onClick={() => seen.ran.push('refresh')} />
      <MoreMenu label="More for scout" entries={[{ label: 'Show history', onSelect: () => seen.ran.push('history') }]} />
      <Button
        label="Restart scout"
        onClick={() => {
          setAsk('Restarts scout and drops its open chats');
        }}
      />
      <ConfirmDialog
        text={ask}
        onAnswer={(ok) => {
          if (ok) seen.ran.push('restart');
          setAsk(null);
        }}
      />
    </>
  );
}

const fresh = (): Seen => ({ name: '', presenting: false, filter: '', mode: '', channel: '', view: '', files: '', ran: [] });

test('an agent can find and change every control by name', async () => {
  const seen = fresh();
  render(<Settings seen={seen} />);

  const components = agent.snapshot().filter((entry) => !entry.offPage && entry.component !== 'more');
  for (const entry of components) expect(entry.label, `${entry.component} ${entry.ref} has no name`).toBeTruthy();
  const labels = components.map((entry) => entry.label);
  for (const label of [
    'Agent name',
    'Presenting',
    'Filter tasks',
    'Review mode',
    'Channel',
    'Scout views',
    'What happens to its files',
    'More for scout',
    'Refresh',
    'Restart scout',
  ])
    expect(labels, `${label} is missing from the snapshot`).toContain(label);

  const result = await run([
    { ref: 'Agent name', action: 'setValue', args: ['scout'] },
    { ref: 'Presenting', action: 'setChecked', args: [true] },
    { ref: 'Filter tasks', action: 'setValue', args: [['errands']] },
    { ref: 'Review mode', action: 'setValue', args: ['On request'] },
    { ref: 'Channel', action: 'setValue', args: ['#random'] },
    { ref: 'Scout views', action: 'setValue', args: ['Tasks'] },
    { ref: 'What happens to its files', action: 'setValue', args: ['Delete them'] },
    { ref: 'More for scout', action: 'press', args: ['Show history'] },
    { ref: 'Refresh', action: 'press' },
  ]);
  expect(result.error?.message).toBeUndefined();
  expect(result.ok).toBe(true);
  expect(seen).toMatchObject({
    name: 'scout',
    presenting: true,
    filter: 'errands',
    mode: 'ask',
    channel: 'C2',
    view: 'tasks',
    files: 'delete',
    ran: ['history', 'refresh'],
  });
  expect(screen.getByRole<HTMLInputElement>('textbox', { name: 'Agent name' }).value).toBe('scout');
});

test('the confirm dialog opens for an agent, but only a person can say Continue', async () => {
  const seen = fresh();
  render(<Settings seen={seen} />);
  const opened = await run([{ ref: 'Restart scout', action: 'press' }]);
  expect(opened.error?.message).toBeUndefined();
  const confirmed = await run([{ ref: 'Are you sure?', action: 'press', args: ['Continue'] }]);
  expect(confirmed.ok).toBe(false);
  expect(confirmed.error?.message).toMatch(/Needs a person/);
  expect(seen.ran).toEqual([]);
});

test('a browser agent gets the same tools through WebMCP, and still cannot confirm', async () => {
  const tools = new Map<string, { execute: (input: object) => unknown }>();
  Object.assign(document, {
    modelContext: {
      registerTool: (tool: { name: string; execute: (input: object) => unknown }) => {
        tools.set(tool.name, tool);
        return Promise.resolve();
      },
    },
  });
  const unregister = registerTools(agent, { allow: (step) => !step.confirm });
  render(<Settings seen={fresh()} />);
  expect([...tools.keys()].sort()).toEqual(['act', 'query', 'snapshot']);
  expect(await tools.get('snapshot')!.execute({})).toBeInstanceOf(Array);
  unregister();
});

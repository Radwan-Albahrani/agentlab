import { useState } from 'react';
import type { Manage, ManagedAgent } from '../../api/types';
import { gb } from '../../lib/format';
import { Button } from '../../ui/Button';
import { Dialog, DialogActions } from '../../ui/Dialog';
import { useAct } from '../../ui/feedback';
import { Field, TextInput } from '../../ui/inputs';
import { Stack } from '../../ui/layout';
import { Note, Text } from '../../ui/text';

/** POST, then close on success. */
function useSubmit(url: string, onClose: () => void) {
  const act = useAct();
  const [busy, setBusy] = useState(false);
  return {
    busy,
    send: async (body: Record<string, unknown>) => {
      setBusy(true);
      const ok = await act(url, body);
      setBusy(false);
      if (ok) onClose();
    },
  };
}

const slug = (v: string) =>
  v
    .toLowerCase()
    .replace(/[^a-z0-9-]+/g, '-')
    .replace(/^-+/, '')
    .slice(0, 32);

export function AddDialog({ open, d, onClose }: { open: boolean; d: Manage; onClose: () => void }) {
  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="Add an agent"
      text="It gets its own container, files and sign-in. The person can open it as soon as it's up; setting up their AI accounts happens on first visit."
    >
      {open && <AddForm d={d} onClose={onClose} />}
    </Dialog>
  );
}

function AddForm({ d, onClose }: { d: Manage; onClose: () => void }) {
  const [id, setId] = useState('');
  const [email, setEmail] = useState('');
  const [memory, setMemory] = useState('');
  const [cpus, setCpus] = useState('');
  const { busy, send } = useSubmit('/api/manage/add', onClose);
  const fromEmail = (v: string) => {
    setEmail(v);
    if (!id || id === slug(email.split('@')[0] ?? '')) setId(slug(v.split('@')[0] ?? ''));
  };
  const newPerson = email.includes('@') && !d.owners.includes(email.trim().toLowerCase());
  const perPerson = d.storage.mode === 'per-person';
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        void send({ id, email, memory, cpus });
      }}
    >
      <Stack gap="lg">
        <Field label="Who it's for (the email they sign in with)">
          <TextInput value={email} onChange={fromEmail} placeholder="sara@example.com" list="agent-owners" />
          <datalist id="agent-owners">
            {d.owners.map((o) => (
              <option key={o} value={o}>
                {o}
              </option>
            ))}
          </datalist>
        </Field>
        <Field label="Agent name (part of its address)">
          <TextInput
            value={id}
            onChange={(v) => {
              setId(slug(v));
            }}
            placeholder="sara"
            mono
          />
        </Field>
        <Field label={`Memory (default ${d.defaults.memory ?? ''})`}>
          <TextInput value={memory} onChange={setMemory} placeholder={d.defaults.memory ?? '12g'} width="short" />
        </Field>
        <Field label={`CPUs (default ${d.defaults.cpus ?? ''})`}>
          <TextInput value={cpus} onChange={setCpus} placeholder={String(d.defaults.cpus ?? 4)} width="short" />
        </Field>
        {perPerson && newPerson && (
          <Note>
            {d.storage.personSize === 'auto'
              ? 'A new person gets a disk of their own; everyone’s share is recalculated, and disks that shrink stop their agents for a few minutes.'
              : `A new person gets a disk of ${d.storage.personSize}. If the server is short of room, set disk sizes to auto first.`}
          </Note>
        )}
        <DialogActions>
          <Button label="Cancel" onClick={onClose} />
          <Button
            label="Add agent"
            icon="plus"
            variant="primary"
            type="submit"
            busy={busy}
            disabled={!id || !email.includes('@')}
          />
        </DialogActions>
      </Stack>
    </form>
  );
}

export function ResizeDialog({ agent, d, onClose }: { agent: ManagedAgent | null; d: Manage; onClose: () => void }) {
  return (
    <Dialog
      open={agent !== null}
      onClose={onClose}
      title={agent ? `Resize ${agent.id}` : ''}
      text="The agent restarts with the new limits (its chats and files stay). If it's in the middle of a task, the change waits until the task ends."
    >
      {agent && <ResizeForm key={agent.id} agent={agent} d={d} onClose={onClose} />}
    </Dialog>
  );
}

function ResizeForm({ agent, d, onClose }: { agent: ManagedAgent; d: Manage; onClose: () => void }) {
  const [memory, setMemory] = useState(agent.customMemory ? agent.memory : '');
  const [cpus, setCpus] = useState(agent.customCpus ? String(agent.cpus) : '');
  const { busy, send } = useSubmit('/api/manage/resize', onClose);
  const body = () => {
    const out: Record<string, string> = { id: agent.id };
    const m = memory.trim() || 'default';
    const c = cpus.trim() || 'default';
    if (m !== (agent.customMemory ? agent.memory : 'default')) out.memory = m;
    if (c !== (agent.customCpus ? String(agent.cpus) : 'default')) out.cpus = c;
    return out;
  };
  const changed = Object.keys(body()).length > 1;
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        void send(body());
      }}
    >
      <Stack gap="lg">
        <Field label={`Memory (empty: the default, ${d.defaults.memory ?? ''})`}>
          <TextInput value={memory} onChange={setMemory} placeholder={d.defaults.memory ?? ''} width="short" />
        </Field>
        <Field label={`CPUs (empty: the default, ${d.defaults.cpus ?? ''})`}>
          <TextInput value={cpus} onChange={setCpus} placeholder={String(d.defaults.cpus ?? '')} width="short" />
        </Field>
        <DialogActions>
          <Button label="Cancel" onClick={onClose} />
          <Button label="Resize" variant="primary" type="submit" busy={busy} disabled={!changed} />
        </DialogActions>
      </Stack>
    </form>
  );
}

export function RemoveDialog({ agent, onClose }: { agent: ManagedAgent | null; onClose: () => void }) {
  return (
    <Dialog open={agent !== null} onClose={onClose} title={agent ? `Remove ${agent.id}` : ''}>
      {agent && <RemoveForm key={agent.id} agent={agent} onClose={onClose} />}
    </Dialog>
  );
}

function RemoveForm({ agent, onClose }: { agent: ManagedAgent; onClose: () => void }) {
  const [deleteData, setDeleteData] = useState(false);
  const [confirm, setConfirm] = useState('');
  const { busy, send } = useSubmit('/api/manage/remove', onClose);
  const size = agent.used ? ` (${gb(agent.used)})` : '';
  return (
    <Stack gap="lg">
      <Text>
        Its container stops and goes, and {agent.owner} can no longer open it. Choose what happens to its files{size}:
      </Text>
      <Stack gap="sm">
        <label>
          <input
            type="radio"
            checked={!deleteData}
            onChange={() => {
              setDeleteData(false);
            }}
          />{' '}
          <b>Keep its files</b>{' '}
          <Text tone="muted">
            — home, workspace and chats stay on the server; adding an agent with the same name brings them back.
          </Text>
        </label>
        <label>
          <input
            type="radio"
            checked={deleteData}
            onChange={() => {
              setDeleteData(true);
            }}
          />{' '}
          <b>Delete everything</b> <Text tone="muted">— frees the space; it cannot be undone.</Text>
        </label>
      </Stack>
      {deleteData && (
        <Field label={`Type ${agent.id} to confirm`}>
          <TextInput value={confirm} onChange={setConfirm} mono />
        </Field>
      )}
      <DialogActions>
        <Button label="Cancel" onClick={onClose} />
        <Button
          label={deleteData ? 'Remove and delete' : 'Remove'}
          icon="trash"
          variant="danger"
          busy={busy}
          disabled={deleteData && confirm !== agent.id}
          onClick={() => send({ id: agent.id, deleteData, confirm })}
        />
      </DialogActions>
    </Stack>
  );
}

export function DisksDialog({ open, d, onClose }: { open: boolean; d: Manage; onClose: () => void }) {
  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="Disk sizes"
      text="Disks grow while agents run. A disk that shrinks stops its agents for a few minutes, never goes below what it holds, and waits while they're mid-task."
    >
      {open && <DisksForm d={d} onClose={onClose} />}
    </Dialog>
  );
}

function DisksForm({ d, onClose }: { d: Manage; onClose: () => void }) {
  const s = d.storage;
  const [auto, setAuto] = useState(s.personSize === 'auto');
  const [size, setSize] = useState(s.personSize === 'auto' ? '' : s.personSize);
  const [reserve, setReserve] = useState(s.hostReserve);
  const { busy, send } = useSubmit('/api/manage/disks', onClose);
  const people = Math.max(1, s.people.length);
  const reserveBytes = reserve.endsWith('%') ? ((s.host?.size ?? 0) * parseFloat(reserve)) / 100 : parseFloat(reserve) * 2 ** 30;
  const share = s.host ? Math.floor((s.host.size - (Number.isFinite(reserveBytes) ? reserveBytes : 0)) / people) : 0;
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        void send({ personSize: auto ? 'auto' : size, hostReserve: auto ? reserve : '' });
      }}
    >
      <Stack gap="lg">
        <Stack gap="sm">
          <label>
            <input
              type="radio"
              checked={auto}
              onChange={() => {
                setAuto(true);
              }}
            />{' '}
            <b>Automatic</b>{' '}
            <Text tone="muted">
              — the server's disk, minus a reserve, split evenly between everyone. Recalculated when people come and go.
            </Text>
          </label>
          <label>
            <input
              type="radio"
              checked={!auto}
              onChange={() => {
                setAuto(false);
              }}
            />{' '}
            <b>The same fixed size for everyone</b>
          </label>
        </Stack>
        {auto ? (
          <Field label="Keep for the server (a share like 15% or a size like 64g)">
            <TextInput value={reserve} onChange={setReserve} width="short" />
          </Field>
        ) : (
          <Field label="Each person's disk">
            <TextInput value={size} onChange={setSize} placeholder="80g" width="short" />
          </Field>
        )}
        {auto && share > 0 && (
          <Note>
            About {gb(share, 0)} for each of the {people} {people === 1 ? 'person' : 'people'} now.
          </Note>
        )}
        <DialogActions>
          <Button label="Cancel" onClick={onClose} />
          <Button label="Apply" variant="primary" type="submit" busy={busy} disabled={!auto && !size} />
        </DialogActions>
      </Stack>
    </form>
  );
}

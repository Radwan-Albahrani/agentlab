import { useState } from 'react';
import { useManage } from '../../api/queries';
import type { Manage as Data, ManagedAgent } from '../../api/types';
import { Screen } from '../../app/Screen';
import { gb, pct } from '../../lib/format';
import { ActButton } from '../../ui/actions';
import { Button } from '../../ui/Button';
import { Card, CardBody } from '../../ui/Card';
import { Inline, Split } from '../../ui/layout';
import { EmptyCard, PageHead, Section } from '../../ui/page';
import { Badge, Meter, Pill } from '../../ui/status';
import { Table, Td, Th, Tr } from '../../ui/Table';
import { Note, Text } from '../../ui/text';
import { AddDialog, DisksDialog, RemoveDialog, ResizeDialog } from './dialogs';
import { Jobs } from './jobs';

type Opened = { kind: 'add' } | { kind: 'disks' } | { kind: 'resize' | 'remove'; agent: ManagedAgent } | null;

export function Manage() {
  const query = useManage();
  return (
    <Screen title="Manage agents" query={query}>
      {(d) => <ManageView d={d} />}
    </Screen>
  );
}

function ManageView({ d }: { d: Data }) {
  const [opened, setOpened] = useState<Opened>(null);
  const close = () => {
    setOpened(null);
  };
  const busy = d.jobs.some((j) => j.state === 'queued' || j.state === 'running');
  return (
    <>
      <PageHead
        title="Manage agents"
        sub="Add, resize and remove agents. Each change sets up everything it needs (disk, containers, sign-in, Cloudflare) and shows its progress here."
        right={
          <>
            <ActButton
              label="Reclaim space"
              icon="broom"
              url="/api/storage/cleanup"
              confirm="Clear unused Docker images and build caches, settled worktrees and duplicate package files in every agent, and give freed space back to the server? Nothing anyone is working on is touched."
            />
            <Button
              label="Add agent"
              icon="plus"
              variant="primary"
              disabled={!d.watcher}
              onClick={() => {
                setOpened({ kind: 'add' });
              }}
            />
          </>
        }
      />
      {!d.watcher && (
        <EmptyCard
          title="The host watcher is not running"
          text="Changes start from agentlab-watch on the server. Run `sudo systemctl start agentlab-watch` there, or `agentctl doctor`."
          icon="alert"
        />
      )}
      <Jobs jobs={d.jobs} />
      <Section
        title="Agents"
        sub={`${d.agents.length} running on this server. Default limits: ${d.defaults.memory ?? '?'} memory, ${d.defaults.cpus ?? '?'} CPUs.`}
      >
        <Card>
          <Table
            head={
              <>
                <Th>Agent</Th>
                <Th wide>Owner</Th>
                <Th num>Memory</Th>
                <Th num>CPUs</Th>
                <Th num wide>
                  Files
                </Th>
                <Th fit />
              </>
            }
          >
            {d.agents.map((a) => (
              <Tr key={a.id}>
                <Td>
                  <Inline gap="sm">
                    <Badge name={a.id} size="sm" />
                    <b>{a.id}</b>
                    <StatePill state={a.state} />
                  </Inline>
                </Td>
                <Td wide muted>
                  {a.owner}
                </Td>
                <Td num>
                  {a.memory}
                  {!a.customMemory && <Text tone="muted"> ·default</Text>}
                </Td>
                <Td num>
                  {a.cpus}
                  {!a.customCpus && <Text tone="muted"> ·default</Text>}
                </Td>
                <Td num wide muted>
                  {a.used ? gb(a.used) : '—'}
                </Td>
                <Td fit>
                  <Inline gap="xs">
                    <Button
                      label="Resize"
                      icon="sliders"
                      small
                      disabled={!d.watcher}
                      onClick={() => {
                        setOpened({ kind: 'resize', agent: a });
                      }}
                    />
                    <Button
                      label={`Remove ${a.id}`}
                      icon="trash"
                      small
                      iconOnly
                      variant="danger"
                      disabled={!d.watcher}
                      onClick={() => {
                        setOpened({ kind: 'remove', agent: a });
                      }}
                    />
                  </Inline>
                </Td>
              </Tr>
            ))}
          </Table>
        </Card>
      </Section>
      <Disks
        d={d}
        onEdit={() => {
          setOpened({ kind: 'disks' });
        }}
      />
      <AddDialog open={opened?.kind === 'add'} d={d} onClose={close} />
      <DisksDialog open={opened?.kind === 'disks'} d={d} onClose={close} />
      <ResizeDialog agent={opened?.kind === 'resize' ? opened.agent : null} d={d} onClose={close} />
      <RemoveDialog agent={opened?.kind === 'remove' ? opened.agent : null} onClose={close} />
      {busy && <Note>Changes run one at a time; a queued one starts when the one before it finishes.</Note>}
    </>
  );
}

function StatePill({ state }: { state: ManagedAgent['state'] }) {
  if (state === 'up') return <Pill tone="ok">up</Pill>;
  if (state === 'starting') return <Pill tone="warn">starting</Pill>;
  return <Pill tone="bad">down</Pill>;
}

function Disks({ d, onEdit }: { d: Data; onEdit: () => void }) {
  const s = d.storage;
  if (s.mode === 'shared') {
    return (
      <Section
        title="Storage"
        sub="Every agent shares one pool on this server. Reclaim space clears what the agents can rebuild."
      >
        {s.pool ? (
          <UsageCard title="Agents pool" used={s.pool.used} size={s.pool.size} />
        ) : (
          <EmptyCard title="No numbers yet" icon="clock" />
        )}
      </Section>
    );
  }
  const sizing = s.personSize === 'auto' ? `split evenly, keeping ${s.hostReserve} for the server` : `${s.personSize} each`;
  return (
    <Section
      title="Disks"
      sub={`Each person's agents share a disk of their own: ${sizing}. Adding a person makes room automatically when sizes are on auto.`}
      right={<Button label="Disk sizes" icon="disk" small disabled={!d.watcher} onClick={onEdit} />}
    >
      {s.host && <UsageCard title="Server disk" used={s.host.used} size={s.host.size} />}
      <Card>
        {s.people.map((p, n) => (
          <CardBody key={p.email} divided={n > 0}>
            <Split>
              <Inline gap="sm">
                <b>{p.email}</b>
                {p.agents.map((a) => (
                  <Badge key={a} name={a} size="xs" />
                ))}
              </Inline>
              <Text tone="muted">{p.size ? `${gb(p.used)} of ${gb(p.size, 0)}` : 'not mounted'}</Text>
            </Split>
            {p.size ? <Meter pct={pct(p.used ?? 0, p.size)} /> : null}
          </CardBody>
        ))}
      </Card>
    </Section>
  );
}

function UsageCard({ title, used, size }: { title: string; used: number; size: number }) {
  return (
    <Card>
      <CardBody>
        <Split>
          <b>{title}</b>
          <Text tone="muted">
            {gb(used)} of {gb(size, 0)} · {gb(size - used)} free
          </Text>
        </Split>
        <Meter pct={pct(used, size)} />
      </CardBody>
    </Card>
  );
}

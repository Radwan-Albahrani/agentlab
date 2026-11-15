import * as stylex from '@stylexjs/stylex';
import { useState } from 'react';
import { useManage } from '../../api/queries';
import type { Job, Manage as Data, ManagedAgent, PersonDisk, Pool } from '../../api/types';
import { Screen } from '../../app/Screen';
import { gb, pct, plural } from '../../lib/format';
import { colors, font, radius, space, text } from '../../theme/tokens.stylex';
import { ActButton } from '../../ui/actions';
import { Button } from '../../ui/Button';
import { Icon } from '../../ui/Icon';
import { StatGrid } from '../../ui/layout';
import { Appear } from '../../ui/motion';
import { EmptyCard, PageHead, Section, Stat } from '../../ui/page';
import { Ring } from '../../ui/Ring';
import { Badge } from '../../ui/status';
import { Mono } from '../../ui/text';
import { AddDialog, DisksDialog, RemoveDialog, ResizeDialog } from './dialogs';
import { AddTile, AgentTile, size } from './AgentTile';
import { ActiveJobs, jobAgent, JobHistory } from './jobs';

const styles = stylex.create({
  tiles: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fill, minmax(min(100%, 320px), 1fr))',
    gap: space.lg,
  },
  // the watcher is down: one amber-edged panel at the top, since nothing can change until it is back
  warn: {
    display: 'flex',
    alignItems: 'center',
    gap: space.lg,
    paddingBlock: space.lg,
    paddingInline: space.xxl,
    borderRadius: radius.xl,
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: `color-mix(in srgb, ${colors.warn} 55%, ${colors.line})`,
    backgroundColor: colors.warnSoft,
  },
  warnIcon: { display: 'flex', flexShrink: 0, color: colors.warn },
  warnTitle: { fontWeight: 600, color: colors.fg },
  warnText: { margin: 0, fontSize: text.md, color: colors.muted },
  disks: { display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(min(100%, 280px), 1fr))', gap: space.lg },
  disk: {
    display: 'grid',
    gap: space.xxs,
    paddingBlock: space.lg,
    paddingInline: space.xxl,
    borderRadius: radius.xl,
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: colors.line,
    backgroundColor: colors.panel,
    minWidth: 0,
  },
  diskHead: { display: 'flex', alignItems: 'center', gap: space.sm, minWidth: 0 },
  diskName: {
    flex: '1',
    minWidth: 0,
    fontFamily: font.mono,
    fontSize: text.sm,
    fontWeight: 500,
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
  },
  badges: { display: 'flex', gap: space.xxs, flexShrink: 0 },
  missing: {
    display: 'flex',
    alignItems: 'center',
    gap: space.sm,
    color: colors.warn,
    fontFamily: font.mono,
    fontSize: text.xs,
    textTransform: 'uppercase',
    letterSpacing: '.06em',
    paddingBlock: space.lg,
  },
});

type Opened = { kind: 'add' } | { kind: 'disks' } | { kind: 'resize' | 'remove'; agent: ManagedAgent } | null;

export function Manage() {
  const query = useManage();
  return (
    <Screen title="Manage agents" query={query}>
      {(d) => <ManageView d={d} />}
    </Screen>
  );
}

const live = (j: Job) => j.state === 'queued' || j.state === 'running';

function ManageView({ d }: { d: Data }) {
  const [opened, setOpened] = useState<Opened>(null);
  const close = () => {
    setOpened(null);
  };
  const active = d.jobs.filter(live);
  const jobFor = (id: string) => active.find((j) => jobAgent(j) === id);
  const up = d.agents.filter((a) => a.state === 'up').length;
  return (
    <>
      <PageHead
        eyebrow={`${up}/${plural(d.agents.length, 'agent')} up · ${active.length ? `${plural(active.length, 'change')} running` : 'idle'}${d.watcher ? '' : ' · watcher down'}`}
        title="Manage agents"
        sub={`Add, resize and remove agents. Each change sets up everything it needs (${d.access.published ? 'container, files and tailnet ports' : d.access.cloudflare ? 'disk, container, sign-in and Cloudflare' : 'disk, container and sign-in'}) and shows its progress here.`}
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
        <div {...stylex.props(styles.warn)}>
          <span {...stylex.props(styles.warnIcon)}>
            <Icon name="alert" size={18} />
          </span>
          <div>
            <div {...stylex.props(styles.warnTitle)}>The host watcher is not running</div>
            <p {...stylex.props(styles.warnText)}>
              Changes start from agentlab-watch on the server. Run <Mono>sudo systemctl start agentlab-watch</Mono> there, or{' '}
              <Mono>agentctl doctor</Mono>.
            </p>
          </div>
        </div>
      )}
      <StatGrid>
        <Stat
          label="Agents running"
          value={up}
          of={`/ ${d.agents.length}`}
          tone={!d.agents.length ? 'idle' : up === d.agents.length ? 'ok' : 'bad'}
          sub={d.agents.length - up ? `${d.agents.length - up} starting or stopped` : 'all up'}
        />
        <Stat
          label="Default memory"
          value={d.defaults.memory ? size(d.defaults.memory).join(' ') : '?'}
          sub={`${d.defaults.cpus ?? '?'} CPUs each, unless resized`}
        />
        <Stat
          label="Changes"
          value={active.length}
          tone={active.length ? 'info' : 'idle'}
          sub={active.length ? `${plural(active.length, 'change')} in progress` : 'nothing running'}
        />
      </StatGrid>
      <ActiveJobs jobs={d.jobs} />
      <Section title="Agents" icon="agents" sub={`${plural(d.agents.length, 'agent')} on this server.`}>
        <div {...stylex.props(styles.tiles)}>
          {d.agents.map((a, i) => (
            <Appear key={a.id} i={i}>
              <AgentTile
                a={a}
                job={jobFor(a.id)}
                disabled={!d.watcher}
                onResize={() => {
                  setOpened({ kind: 'resize', agent: a });
                }}
                onRemove={() => {
                  setOpened({ kind: 'remove', agent: a });
                }}
              />
            </Appear>
          ))}
          <Appear i={d.agents.length}>
            <AddTile
              disabled={!d.watcher}
              onAdd={() => {
                setOpened({ kind: 'add' });
              }}
            />
          </Appear>
        </div>
      </Section>
      <Disks
        d={d}
        onEdit={() => {
          setOpened({ kind: 'disks' });
        }}
      />
      <JobHistory jobs={d.jobs} />
      <AddDialog open={opened?.kind === 'add'} d={d} onClose={close} />
      <DisksDialog open={opened?.kind === 'disks'} d={d} onClose={close} />
      <ResizeDialog agent={opened?.kind === 'resize' ? opened.agent : null} d={d} onClose={close} />
      <RemoveDialog agent={opened?.kind === 'remove' ? opened.agent : null} onClose={close} />
    </>
  );
}

function Disks({ d, onEdit }: { d: Data; onEdit: () => void }) {
  const s = d.storage;
  if (s.mode === 'shared') {
    return (
      <Section
        title="Storage"
        icon="disk"
        sub="Every agent shares one pool on this server. Reclaim space clears what the agents can rebuild."
      >
        {s.pool ? <UsageRing title="Agents pool" disk={s.pool} /> : <EmptyCard title="No numbers yet" icon="clock" />}
      </Section>
    );
  }
  const sizing = s.personSize === 'auto' ? `split evenly, keeping ${s.hostReserve} for the server` : `${s.personSize} each`;
  return (
    <Section
      title="Disks"
      icon="disk"
      sub={`Each person's agents share a disk of their own: ${sizing}. Adding a person makes room automatically when sizes are on auto.`}
      right={<Button label="Disk sizes" icon="disk" small disabled={!d.watcher} onClick={onEdit} />}
    >
      <div {...stylex.props(styles.disks)}>
        {s.host && <UsageRing title="Server disk" disk={s.host} />}
        {s.people.map((p) => (
          <PersonDiskTile key={p.email} p={p} />
        ))}
      </div>
    </Section>
  );
}

const UsageRing = ({ title, disk }: { title: string; disk: Pool }) => (
  <Ring
    label={title}
    pct={pct(disk.used, disk.size)}
    value={`${gb(disk.size - disk.used)} free`}
    sub={`${gb(disk.used)} of ${gb(disk.size, 0)} used`}
  />
);

function PersonDiskTile({ p }: { p: PersonDisk }) {
  return (
    <div {...stylex.props(styles.disk)}>
      <div {...stylex.props(styles.diskHead)}>
        <span {...stylex.props(styles.diskName)} title={p.email}>
          {p.email}
        </span>
        <span {...stylex.props(styles.badges)}>
          {p.agents.map((a) => (
            <Badge key={a} name={a} size="xs" />
          ))}
        </span>
      </div>
      {p.size ? (
        <Ring bare label="Used" pct={pct(p.used ?? 0, p.size)} value={gb(p.used)} sub={`of ${gb(p.size, 0)}`} />
      ) : (
        <div {...stylex.props(styles.missing)}>
          <Icon name="alert" size={16} />
          not mounted
        </div>
      )}
    </div>
  );
}

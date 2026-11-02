import { useStorage } from '../api/queries';
import type { DiskScan, Pool, ProfileUsage, Storage as Data } from '../api/types';
import { Screen } from '../app/Screen';
import { ago, gb, pct } from '../lib/format';
import { ActButton } from '../ui/actions';
import { Card, CardBody } from '../ui/Card';
import { FeedSection } from '../ui/Feed';
import { Inline, Split } from '../ui/layout';
import { Empty, EmptyCard, PageHead, Section } from '../ui/page';
import { StackedBar } from '../ui/StackedBar';
import { Badge, Meter } from '../ui/status';
import { Table, Td, Tr } from '../ui/Table';
import { BigNumber, Eyebrow, MidNumber, Note, Text } from '../ui/text';

export function Storage() {
  const query = useStorage();
  return (
    <Screen title="Storage" query={query}>
      {(d) => <StorageView d={d} />}
    </Screen>
  );
}

function StorageView({ d }: { d: Data }) {
  const shared = d.mode === 'shared';
  return (
    <>
      <PageHead
        title="Storage"
        sub={
          shared
            ? 'All agents share one pool on the server. Above 80 % it shows under Needs you.'
            : "Each person's agents share a disk of their own, so one full disk never stops anyone else. Above 80 % it shows under Needs you."
        }
        right={
          d.manage && (
            <>
              <ActButton label="Rescan" icon="refresh" url="/api/storage/rescan" />
              <ActButton
                label="Clean up now"
                icon="broom"
                variant="primary"
                url="/api/storage/cleanup"
                confirm="Remove Docker images, build cache and stopped containers unused for 3+ days inside every agent?"
              />
            </>
          )
        }
      />
      {d.reported ? (
        <>
          {d.pool && <DiskCard title="Agents pool" disk={d.pool} />}
          {d.people.map((p) =>
            p.size ? (
              <DiskCard key={p.email} title={p.email} disk={p as Pool} agents={p.agents} />
            ) : (
              <EmptyCard
                key={p.email}
                title={`${p.email}: disk not mounted`}
                text="Their agents cannot start without it."
                icon="alert"
              />
            ),
          )}
          <Breakdown scan={d.scan} />
        </>
      ) : (
        <EmptyCard title="No numbers yet" text="The host watcher (agentlab-watch) reports every 30 s." icon="alert" />
      )}
      {d.manage && <FeedSection title="Cleanups and alerts" sub="Nightly cleanup, plus any you start here." events={d.events} />}
    </>
  );
}

function DiskCard({ title, disk: p, agents }: { title: string; disk: Pool; agents?: string[] }) {
  const used = pct(p.used, p.size);
  return (
    <Card>
      <CardBody roomy>
        <Split>
          <div>
            <Eyebrow>{title}</Eyebrow>
            <BigNumber>
              {gb(p.used)}{' '}
              <Text tone="muted" size="lg">
                of {gb(p.size, 0)}
              </Text>
            </BigNumber>
          </div>
          <div>
            <Eyebrow>Free</Eyebrow>
            <MidNumber>{gb(p.avail)}</MidNumber>
          </div>
        </Split>
        <Meter pct={used} big />
        <Split>
          <Note>{used.toFixed(0)}% used</Note>
          {agents && (
            <Inline gap="xs">
              {agents.map((a) => (
                <Badge key={a} name={a} size="xs" />
              ))}
            </Inline>
          )}
        </Split>
      </CardBody>
    </Card>
  );
}

function Breakdown({ scan }: { scan: DiskScan | undefined }) {
  const sub = scan
    ? `Measured ${ago(scan.at)} (took ${scan.took} s); every 3 hours.`
    : 'First measurement runs in the background.';
  return (
    <Section title="Where the space goes" sub={sub}>
      <Card>
        {scan?.profiles.length ? (
          scan.profiles.map((x, n) => <ProfileBreakdown key={x.name} usage={x} divided={n > 0} />)
        ) : (
          <Empty title="Measuring…" text="A full scan takes about a minute." icon="clock" />
        )}
      </Card>
    </Section>
  );
}

function ProfileBreakdown({ usage: x, divided }: { usage: ProfileUsage; divided: boolean }) {
  return (
    <CardBody divided={divided}>
      <Split>
        <Inline>
          <Badge name={x.name} size="sm" />
          <b>{x.name}</b>
        </Inline>
        <Text tone="muted">{gb(x.total)}</Text>
      </Split>
      <StackedBar parts={x.top.map((i) => ({ label: i.path, bytes: i.bytes }))} total={x.total} />
      {x.biggest.length > 0 && (
        <Table>
          {x.biggest.map((i) => (
            <Tr key={i.path}>
              <Td mono>{i.path}</Td>
              <Td num>{gb(i.bytes)}</Td>
            </Tr>
          ))}
        </Table>
      )}
    </CardBody>
  );
}

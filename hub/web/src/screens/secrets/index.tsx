import { useState } from 'react';
import { useSecrets } from '../../api/queries';
import type { Secrets as Data } from '../../api/types';
import { Screen } from '../../app/Screen';
import { filterSecrets } from '../../lib/secretFilter';
import { Button } from '../../ui/Button';
import { Card } from '../../ui/Card';
import { FeedSection } from '../../ui/Feed';
import { HScroll } from '../../ui/layout';
import { Empty, PageHead, Section } from '../../ui/page';
import { Table, Th } from '../../ui/Table';
import { Mono } from '../../ui/text';
import { SecretDialog, type Opened } from './SecretDialog';
import { SecretFilters } from './SecretFilters';
import { SecretRow } from './SecretRow';
import { useSecretFilter } from './useSecretFilter';
import { VersionsDialog } from './VersionsDialog';

export function Secrets() {
  const query = useSecrets();
  return (
    <Screen title="Secrets" query={query}>
      {(d) => <SecretsView d={d} />}
    </Screen>
  );
}

function SecretsView({ d }: { d: Data }) {
  const [opened, setOpened] = useState<Opened | null>(null);
  const [history, setHistory] = useState<string | null>(null);
  const [filter, setFilter] = useSecretFilter();
  const shown = filterSecrets(d.items, filter);
  return (
    <>
      <PageHead
        title="Secrets"
        sub={
          <>
            Everything in the server's <Mono>secrets</Mono> folder (a companion's in <Mono>companions/&lt;name&gt;/</Mono>). A
            change applies by itself within 30 s: copied to the agents that use it, services restarted where needed. The last 5
            versions are kept.
          </>
        }
        right={
          <Button
            label="New secret"
            icon="plus"
            variant="primary"
            onClick={() => {
              setOpened({ mode: 'new' });
            }}
          />
        }
      />
      <SecretFilters items={d.items} filter={filter} onChange={setFilter} />
      <Section
        title="All secrets"
        sub={shown.length === d.items.length ? `${d.items.length} files` : `${shown.length} of ${d.items.length} files`}
      >
        <Card>
          {shown.length ? (
            <HScroll>
              <Table
                head={
                  <>
                    <Th>Secret</Th>
                    <Th wide>Used by · on change</Th>
                    <Th wide fit>
                      Updated
                    </Th>
                    <Th fit />
                  </>
                }
              >
                {shown.map((s) => (
                  <SecretRow
                    key={s.name}
                    s={s}
                    onView={() => {
                      setOpened({ mode: 'view', name: s.name });
                    }}
                    onEdit={() => {
                      setOpened({ mode: 'edit', name: s.name });
                    }}
                    onHistory={() => {
                      setHistory(s.name);
                    }}
                  />
                ))}
              </Table>
            </HScroll>
          ) : (
            <Empty
              title={d.items.length ? 'No secrets match' : 'No secrets'}
              text={d.items.length ? 'Try another search or clear a filter.' : undefined}
              icon="key"
            />
          )}
        </Card>
      </Section>
      <FeedSection title="Recent changes" sub="What the watcher did after each change." events={d.events} />
      <SecretDialog
        opened={opened}
        onClose={() => {
          setOpened(null);
        }}
      />
      <VersionsDialog
        name={history}
        onClose={() => {
          setHistory(null);
        }}
      />
    </>
  );
}

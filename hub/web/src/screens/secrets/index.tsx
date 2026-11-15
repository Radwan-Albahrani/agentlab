import * as stylex from '@stylexjs/stylex';
import { useState } from 'react';
import { useSecrets } from '../../api/queries';
import type { Secrets as Data, Secret } from '../../api/types';
import { Screen } from '../../app/Screen';
import { filterSecrets } from '../../lib/secretFilter';
import { ago, plural } from '../../lib/format';
import { colors, font, radius, space, text } from '../../theme/tokens.stylex';
import { Button } from '../../ui/Button';
import { FeedSection } from '../../ui/Feed';
import { Icon } from '../../ui/Icon';
import { HScroll, StatGrid } from '../../ui/layout';
import { Appear } from '../../ui/motion';
import { PageHead, Stat } from '../../ui/page';
import { Table, Th } from '../../ui/Table';
import { Mono } from '../../ui/text';
import { SecretDialog, type Opened } from './SecretDialog';
import { SecretFilters } from './SecretFilters';
import { SecretRow } from './SecretRow';
import { useSecretFilter } from './useSecretFilter';
import { VersionsDialog } from './VersionsDialog';

const styles = stylex.create({
  vault: {
    overflow: 'hidden',
    borderRadius: radius.xl,
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: colors.line,
    backgroundColor: colors.panel,
    minWidth: 0,
  },
  vaultHead: {
    display: 'flex',
    alignItems: 'center',
    gap: space.sm,
    paddingBlock: space.md,
    paddingInline: space.xxl,
    backgroundColor: colors.raised,
    borderBottomWidth: 1,
    borderBottomStyle: 'solid',
    borderBottomColor: colors.line,
  },
  vaultIcon: { display: 'flex', color: colors.faint },
  vaultTitle: {
    margin: 0,
    fontSize: text.xs,
    fontWeight: 600,
  },
  vaultCount: {
    marginInlineStart: 'auto',
    fontFamily: font.mono,
    fontSize: text.xs,
    color: colors.faint,
    fontVariantNumeric: 'tabular-nums',
    whiteSpace: 'nowrap',
  },
  none: {
    display: 'grid',
    justifyItems: 'center',
    textAlign: 'center',
    gap: space.md,
    paddingBlock: space.giant,
    paddingInline: space.xxxl,
    borderRadius: radius.xl,
    borderWidth: 1,
    borderStyle: 'dashed',
    borderColor: colors.line2,
    color: colors.muted,
  },
  noneIcon: {
    width: 36,
    height: 36,
    display: 'grid',
    placeItems: 'center',
    borderRadius: radius.lg,
    borderWidth: 1,
    borderStyle: 'dashed',
    borderColor: colors.line2,
    color: colors.faint,
  },
  noneTitle: { color: colors.fg, fontFamily: font.display, fontWeight: 600, fontSize: text.lg },
  noneText: { margin: 0, fontSize: text.md },
});

/** The cluster's own secrets first, then each extra folder's; only groups with something to show. */
function groups(shown: Secret[], all: Secret[]): [string, Secret[], number][] {
  const names = [...new Set(['', ...all.map((s) => s.group)])];
  return names
    .map((g): [string, Secret[], number] => [g, shown.filter((s) => s.group === g), all.filter((s) => s.group === g).length])
    .filter(([, items]) => items.length > 0);
}

export function Secrets() {
  const query = useSecrets();
  return (
    <Screen title="Secrets" query={query}>
      {(d) => <SecretsView d={d} />}
    </Screen>
  );
}

const count = (items: Secret[], kind: Secret['kinds'][number]) => items.filter((s) => s.kinds.includes(kind)).length;

function SecretsView({ d }: { d: Data }) {
  const [opened, setOpened] = useState<Opened | null>(null);
  const [history, setHistory] = useState<string | null>(null);
  const [filter, setFilter] = useSecretFilter();
  const shown = filterSecrets(d.items, filter);
  const filtered = !!filter.q || filter.kind !== 'all' || !!filter.usedBy;
  const latest = d.items.reduce<Secret | null>((a, s) => (!a || s.modified > a.modified ? s : a), null);
  const unmapped = count(d.items, 'unmapped');
  return (
    <>
      <PageHead
        eyebrow={`${plural(d.items.length, 'file')} · ${unmapped ? `${unmapped} not mapped` : 'all mapped'} · 5 versions kept`}
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
      <StatGrid>
        <Stat label="Secrets" value={d.items.length} sub={latest ? `last changed ${ago(latest.modified)}` : undefined} />
        <Stat label="Restart a service" value={count(d.items, 'restart')} sub="on change" />
        <Stat label="Copied into agents" value={count(d.items, 'copy')} sub="on change" />
        <Stat
          label="Not mapped"
          value={unmapped}
          sub={unmapped ? 'applied nowhere yet' : 'every file is used'}
          tone={unmapped ? 'warn' : 'ok'}
        />
      </StatGrid>
      <SecretFilters items={d.items} filter={filter} onChange={setFilter} />
      {shown.length ? (
        groups(shown, d.items).map(([group, items, total], n) => (
          <Appear key={group} i={n}>
            <section {...stylex.props(styles.vault)} aria-label={group || 'Cluster secrets'}>
              <div {...stylex.props(styles.vaultHead)}>
                <span {...stylex.props(styles.vaultIcon)}>
                  <Icon name={group ? 'bot' : 'key'} size={14} />
                </span>
                <h2 {...stylex.props(styles.vaultTitle)}>{group || 'Cluster secrets'}</h2>
                <span {...stylex.props(styles.vaultCount)}>
                  {items.length === total ? plural(total, 'file') : `${items.length} of ${plural(total, 'file')}`}
                </span>
              </div>
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
                  {items.map((s) => (
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
            </section>
          </Appear>
        ))
      ) : (
        <div {...stylex.props(styles.none)}>
          <span {...stylex.props(styles.noneIcon)}>
            <Icon name={filtered ? 'search' : 'key'} size={18} />
          </span>
          <span {...stylex.props(styles.noneTitle)}>{filtered ? 'No secrets match' : 'No secrets yet'}</span>
          <p {...stylex.props(styles.noneText)}>
            {filtered ? 'Try another search or clear the filters.' : 'Add the first one; it is applied wherever it is mapped.'}
          </p>
          {filtered ? (
            <Button
              label="Clear filters"
              icon="x"
              small
              onClick={() => {
                setFilter({ q: '', kind: 'all', usedBy: '' });
              }}
            />
          ) : (
            <Button
              label="New secret"
              icon="plus"
              small
              onClick={() => {
                setOpened({ mode: 'new' });
              }}
            />
          )}
        </div>
      )}
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

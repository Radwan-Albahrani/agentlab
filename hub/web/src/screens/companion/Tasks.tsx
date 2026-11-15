import * as stylex from '@stylexjs/stylex';
import { useState } from 'react';
import type { Task } from '../../api/types';
import { filterTasks, TASK_FILTERS, TASK_PILL, taskAge, taskWho, WAITING, type TaskFilter } from '../../lib/companion';
import { ago, capitalize, elapsed, plural } from '../../lib/format';
import { usePages } from '../../lib/usePages';
import { useNow } from '../../lib/useNow';
import { colors, font, media, radius, space, text } from '../../theme/tokens.stylex';
import { LinkButton } from '../../ui/Button';
import { Card } from '../../ui/Card';
import { Segments } from '../../ui/controls';
import { Icon } from '../../ui/Icon';
import { HScroll, Inline } from '../../ui/layout';
import { Appear } from '../../ui/motion';
import { Empty, Section } from '../../ui/page';
import { Pager } from '../../ui/Pager';
import { IconBox, List, Row } from '../../ui/Row';
import { Count, Pill } from '../../ui/status';
import { Table, Td, Th, Tr } from '../../ui/Table';
import { When } from '../../ui/When';
import { Blink, LiveLine, Mono } from './parts';

const PAGE = 12;

const styles = stylex.create({
  // the one amber-edged panel: what waits on you, each with the button that takes you there
  attention: {
    overflow: 'hidden',
    borderRadius: radius.xl,
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: `color-mix(in srgb, ${colors.warn} 55%, ${colors.line})`,
    backgroundColor: colors.panel,
  },
  attentionHead: {
    display: 'flex',
    alignItems: 'center',
    gap: space.md,
    flexWrap: 'wrap',
    paddingBlock: space.md,
    paddingInline: space.xxl,
    fontFamily: font.mono,
    fontSize: text.xs,
    fontWeight: 600,
    letterSpacing: '.1em',
    textTransform: 'uppercase',
    color: colors.warn,
    backgroundColor: colors.warnSoft,
    borderBottomWidth: 1,
    borderBottomStyle: 'solid',
    borderBottomColor: `color-mix(in srgb, ${colors.warn} 30%, ${colors.line})`,
  },
  hint: {
    marginInlineStart: 'auto',
    fontFamily: font.sans,
    fontSize: text.sm,
    fontWeight: 400,
    letterSpacing: 0,
    textTransform: 'none',
    color: colors.muted,
  },
  live: {
    position: 'relative',
    display: 'grid',
    gridTemplateColumns: '32px minmax(0, 1fr) auto auto',
    gap: space.md,
    alignItems: 'center',
    paddingBlock: space.md,
    paddingInline: { default: space.xxl, [media.phone]: space.lg },
    borderTopWidth: 1,
    borderTopStyle: 'solid',
    borderTopColor: colors.line,
    backgroundColor: { default: 'transparent', ':hover': colors.hover },
    transitionProperty: 'background-color',
    transitionDuration: '140ms',
  },
  liveTitle: { fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' },
  liveMeta: { fontSize: text.sm, color: colors.faint, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' },
  timer: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: space.xs,
    fontFamily: font.mono,
    fontSize: text.md,
    fontWeight: 500,
    color: colors.info,
    fontVariantNumeric: 'tabular-nums',
    whiteSpace: 'nowrap',
  },
  links: { display: 'flex', gap: space.xxs },
  title: { fontWeight: 500, overflowWrap: 'anywhere' },
  detail: {
    display: 'flex',
    alignItems: 'center',
    gap: space.xs,
    color: colors.muted,
    fontSize: text.md,
    overflowWrap: 'anywhere',
  },
  meta: {
    fontFamily: font.mono,
    fontSize: text.sm,
    color: colors.faint,
    whiteSpace: 'nowrap',
    fontVariantNumeric: 'tabular-nums',
  },
});

const KIND_ICON: Record<string, string> = { errand: 'send', task: 'chat', review: 'pr' };

function TaskLinks({ t, primary = false, compact = false }: { t: Task; primary?: boolean; compact?: boolean }) {
  return (
    <>
      {t.slack && (
        <LinkButton
          label={compact ? 'Open in Slack' : 'Slack'}
          icon="slack"
          variant={primary ? 'primary' : compact ? 'quiet' : 'default'}
          small
          iconOnly={compact}
          to={t.slack}
        />
      )}
      {t.t3 && (
        <LinkButton label={compact ? 'Open in T3' : 'T3'} icon="chat" variant="quiet" small iconOnly={compact} to={t.t3} />
      )}
    </>
  );
}

/** Status first: each task that needs a decision, with the button that takes you there. */
export function WaitingTasks({ tasks }: { tasks: Task[] }) {
  const now = useNow(15_000);
  const waiting = tasks.filter((t) => t.status === 'waiting');
  if (!waiting.length) return null;
  return (
    <section {...stylex.props(styles.attention)} aria-label="Waiting on you">
      <div {...stylex.props(styles.attentionHead)}>
        <Count n={waiting.length} />
        {waiting.length === 1 ? 'One task waits on you' : `${waiting.length} tasks wait on you`}
        <span {...stylex.props(styles.hint)}>Decide in Slack; this page updates by itself.</span>
      </div>
      <List>
        {waiting.map((t, i) => (
          <Appear key={t.id} i={i}>
            <Row
              lead={<IconBox icon={WAITING[t.waiting]?.icon ?? 'alert'} tone="warn" />}
              title={t.title}
              detail={`${WAITING[t.waiting]?.label ?? 'Needs you'}${t.requester ? ` · ${taskWho(t)}` : ''}`}
              meta={t.startedAt ? <Mono>started {ago(t.startedAt, now)}</Mono> : undefined}
              actions={<TaskLinks t={t} primary />}
            />
          </Appear>
        ))}
      </List>
    </section>
  );
}

/** What runs this second, each with a ticking stopwatch and a dashed line running under it. */
export function WorkingTasks({ tasks, name }: { tasks: Task[]; name: string }) {
  const now = useNow(1000);
  const working = tasks.filter((t) => t.status === 'working');
  return (
    <Section
      title="Working now"
      icon="bot"
      sub={working.length ? `${plural(working.length, 'task')} in progress, live` : undefined}
    >
      <Card>
        {working.length ? (
          <List>
            {working.map((t, i) => (
              <Appear key={t.id} i={i}>
                <div {...stylex.props(styles.live)}>
                  <IconBox icon={t.poll ? 'poll' : (KIND_ICON[t.kind] ?? 'bot')} tone="info" />
                  <div>
                    <div {...stylex.props(styles.liveTitle)} title={t.title}>
                      {t.title}
                    </div>
                    <div {...stylex.props(styles.liveMeta)}>{t.poll ? t.outcome : `${capitalize(t.kind)} · ${taskWho(t)}`}</div>
                  </div>
                  <span {...stylex.props(styles.timer)} title="Running for">
                    {t.startedAt ? elapsed(now - t.startedAt) : ''}
                    <Blink />
                  </span>
                  <span {...stylex.props(styles.links)}>
                    <TaskLinks t={t} compact />
                  </span>
                  <LiveLine />
                </div>
              </Appear>
            ))}
          </List>
        ) : (
          <Empty
            icon="bot"
            title="Nothing running right now"
            text={`Tag @${name} in Slack to hand it a task; it shows up here live.`}
          />
        )}
      </Card>
    </Section>
  );
}

export function TaskTable({ tasks, now }: { tasks: Task[]; now: number }) {
  const [filter, setFilter] = useState<TaskFilter>('all');
  const pages = usePages(filterTasks(tasks, filter), PAGE);
  const options = TASK_FILTERS.map((f) => ({ ...f, count: filterTasks(tasks, f.value).length }));
  return (
    <Section
      title="Tasks"
      icon="log"
      sub="Everything it took on, with who asked and how it went."
      right={
        <Inline gap="md">
          <Segments
            label="Filter tasks"
            value={filter}
            options={options}
            onChange={(v) => {
              setFilter(v);
              pages.setPage(0);
            }}
          />
          <Pager {...pages} />
        </Inline>
      }
    >
      <Card>
        {tasks.length === 0 ? (
          <Empty title="No tasks yet" text="Tag the companion in Slack to give it one." icon="bot" />
        ) : pages.shown.length === 0 ? (
          <Empty title="Nothing here" text="No task matches this filter." icon="filter" />
        ) : (
          <HScroll>
            <Table
              head={
                <>
                  <Th>Task</Th>
                  <Th>Status</Th>
                  <Th wide>Started</Th>
                  <Th num wide>
                    Took
                  </Th>
                  <Th />
                </>
              }
            >
              {pages.shown.map((t) => (
                <TaskRow key={t.id} t={t} now={now} />
              ))}
            </Table>
          </HScroll>
        )}
      </Card>
    </Section>
  );
}

function TaskRow({ t, now }: { t: Task; now: number }) {
  const [label, tone] = TASK_PILL[t.status] ?? [t.status, 'idle'];
  const took = taskAge(t, now);
  const going = t.status === 'working' || t.status === 'waiting';
  return (
    <Tr>
      <Td>
        <div {...stylex.props(styles.title)}>{t.title}</div>
        <div {...stylex.props(styles.detail)}>
          <Icon name={KIND_ICON[t.kind] ?? 'chat'} size={13} />
          <span>
            {capitalize(t.kind)} · {taskWho(t)}
            {t.outcome ? ` · ${t.outcome}` : ''}
          </span>
        </div>
        {t.status === 'working' && <LiveLine inline />}
      </Td>
      <Td fit>
        <Pill tone={tone} dot={going}>
          {label}
        </Pill>
      </Td>
      <Td wide fit>
        <span {...stylex.props(styles.meta)}>
          <When t={t.startedAt} />
        </span>
      </Td>
      <Td num wide>
        {took && <span {...stylex.props(styles.meta)}>{took}</span>}
      </Td>
      <Td num>
        <Inline gap="xs" end nowrap>
          <TaskLinks t={t} compact />
        </Inline>
      </Td>
    </Tr>
  );
}

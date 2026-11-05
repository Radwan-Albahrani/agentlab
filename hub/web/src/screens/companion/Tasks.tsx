import { useState } from 'react';
import type { Task } from '../../api/types';
import { filterTasks, TASK_FILTERS, TASK_PILL, taskAge, taskWho, WAITING, type TaskFilter } from '../../lib/companion';
import { capitalize } from '../../lib/format';
import { LinkButton } from '../../ui/Button';
import { Card } from '../../ui/Card';
import { Segments } from '../../ui/controls';
import { HScroll, Inline } from '../../ui/layout';
import { Empty, Section } from '../../ui/page';
import { List, Row } from '../../ui/Row';
import { Pill } from '../../ui/status';
import { Table, Td, Th, Tr } from '../../ui/Table';
import { Text } from '../../ui/text';
import { When } from '../../ui/When';
import { usePages } from '../../lib/usePages';
import { Pager } from '../../ui/Pager';

const PAGE = 12;

function TaskLinks({ t, primary = false }: { t: Task; primary?: boolean }) {
  return (
    <>
      {t.slack && <LinkButton label="Slack" icon="slack" variant={primary ? 'primary' : 'default'} small to={t.slack} />}
      {t.t3 && <LinkButton label="T3" icon="chat" variant="quiet" small to={t.t3} />}
    </>
  );
}

export function WaitingTasks({ tasks }: { tasks: Task[] }) {
  const waiting = tasks.filter((t) => t.status === 'waiting');
  if (!waiting.length) return null;
  return (
    <Section title="Waiting on you" sub="Decide in Slack; this page updates by itself.">
      <Card>
        <List>
          {waiting.map((t) => (
            <Row
              key={t.id}
              accent="warn"
              icon={WAITING[t.waiting]?.icon ?? 'alert'}
              tone="warn"
              title={t.title}
              detail={`${WAITING[t.waiting]?.label ?? 'Needs you'}${t.requester ? ` · ${taskWho(t)}` : ''}`}
              meta={<When t={t.startedAt} />}
              actions={<TaskLinks t={t} primary />}
            />
          ))}
        </List>
      </Card>
    </Section>
  );
}

export function WorkingTasks({ tasks, now }: { tasks: Task[]; now: number }) {
  const working = tasks.filter((t) => t.status === 'working');
  return (
    <Section title="Working now">
      <Card>
        {working.length ? (
          <List>
            {working.map((t) => (
              <Row
                key={t.id}
                icon={t.poll ? 'poll' : 'clock'}
                tone="info"
                title={t.title}
                detail={t.poll ? t.outcome : `${t.requester ? `${taskWho(t)} · ` : ''}running ${taskAge(t, now)}`}
                meta={<When t={t.startedAt} />}
                actions={<TaskLinks t={t} />}
              />
            ))}
          </List>
        ) : (
          <Empty title="Idle" text="Nothing running right now." icon="clock" />
        )}
      </Card>
    </Section>
  );
}

export function TaskTable({ tasks, now }: { tasks: Task[]; now: number }) {
  const [filter, setFilter] = useState<TaskFilter>('all');
  const pages = usePages(filterTasks(tasks, filter), PAGE);
  const shown = pages.shown;
  return (
    <Section
      title="Tasks"
      right={
        <Inline gap="md">
          <Segments
            label="Filter tasks"
            value={filter}
            options={TASK_FILTERS}
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
              {shown.map((t) => (
                <TaskRow key={t.id} t={t} now={now} />
              ))}
              {shown.length === 0 && (
                <Tr>
                  <Td muted colSpan={5}>
                    Nothing here.
                  </Td>
                </Tr>
              )}
            </Table>
          </HScroll>
        )}
      </Card>
    </Section>
  );
}

function TaskRow({ t, now }: { t: Task; now: number }) {
  const [label, tone] = TASK_PILL[t.status] ?? [t.status, 'idle'];
  return (
    <Tr>
      <Td>
        <Text weight="semibold" block>
          {t.title}
        </Text>
        <Text tone="muted" size="md" block>
          {capitalize(t.kind)} · {taskWho(t)}
          {t.outcome ? ` · ${t.outcome}` : ''}
        </Text>
      </Td>
      <Td>
        <Pill tone={tone}>{label}</Pill>
      </Td>
      <Td wide muted>
        <When t={t.startedAt} />
      </Td>
      <Td num wide muted>
        {taskAge(t, now)}
      </Td>
      <Td num>
        <Inline gap="xs" end>
          <TaskLinks t={t} />
        </Inline>
      </Td>
    </Tr>
  );
}

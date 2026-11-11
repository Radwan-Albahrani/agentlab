import * as stylex from '@stylexjs/stylex';
import { useEffect, useRef, useState } from 'react';
import { useJobLog } from '../../api/queries';
import type { Job } from '../../api/types';
import { duration } from '../../lib/format';
import { useNow } from '../../lib/useNow';
import { colors, font, radius, space, text } from '../../theme/tokens.stylex';
import { Button } from '../../ui/Button';
import { Card, CardBody } from '../../ui/Card';
import { Icon } from '../../ui/Icon';
import { Inline, Spacer, Stack } from '../../ui/layout';
import { Section } from '../../ui/page';
import { Pill } from '../../ui/status';
import { Note, Text } from '../../ui/text';
import { When } from '../../ui/When';

const spin = stylex.keyframes({ to: { transform: 'rotate(360deg)' } });

const styles = stylex.create({
  spinner: {
    width: 16,
    height: 16,
    flexShrink: 0,
    borderRadius: '50%',
    borderWidth: 2,
    borderStyle: 'solid',
    borderColor: colors.line2,
    borderTopColor: colors.accent,
    animationName: spin,
    animationDuration: '0.8s',
    animationIterationCount: 'infinite',
    animationTimingFunction: 'linear',
  },
  log: {
    margin: 0,
    maxHeight: 320,
    overflow: 'auto',
    whiteSpace: 'pre-wrap',
    overflowWrap: 'anywhere',
    fontFamily: font.mono,
    fontSize: text.xs,
    lineHeight: 1.5,
    padding: space.lg,
    borderRadius: radius.md,
    backgroundColor: colors.sunk,
    color: colors.fg,
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: colors.line,
  },
  title: { fontWeight: 700, minWidth: 0, overflowWrap: 'anywhere' },
  ok: { color: colors.ok, display: 'inline-flex' },
  bad: { color: colors.bad, display: 'inline-flex' },
});

const live = (j: Job) => j.state === 'queued' || j.state === 'running';

/** What is running now (log open, following), then recent changes (log on demand). */
export function Jobs({ jobs }: { jobs: Job[] }) {
  const active = jobs.filter(live);
  const done = jobs.filter((j) => !live(j)).slice(0, 8);
  return (
    <>
      {active.length > 0 && (
        <Section title="In progress">
          {active.map((j) => (
            <JobCard key={j.id} job={j} open />
          ))}
        </Section>
      )}
      {done.length > 0 && (
        <Section title="Recent changes">
          <Card>
            {done.map((j, n) => (
              <JobRow key={j.id} job={j} divided={n > 0} />
            ))}
          </Card>
        </Section>
      )}
    </>
  );
}

function JobCard({ job, open }: { job: Job; open: boolean }) {
  const now = useNow(1000);
  return (
    <Card accent="info">
      <CardBody>
        <Inline gap="sm">
          <span {...stylex.props(styles.spinner)} />
          <span {...stylex.props(styles.title)}>{job.title}</span>
          <Spacer />
          {job.state === 'queued' ? (
            <Pill tone="idle">waiting its turn</Pill>
          ) : (
            <Text tone="muted">{duration(now - (job.started ?? now))}</Text>
          )}
        </Inline>
        {job.state === 'running' && open && <Log id={job.id} live />}
        {job.state === 'running' && (
          <Note>You can leave this page; the change carries on on the server, and finishes even if this page reloads.</Note>
        )}
      </CardBody>
    </Card>
  );
}

function JobRow({ job, divided }: { job: Job; divided: boolean }) {
  const [open, setOpen] = useState(false);
  return (
    <CardBody divided={divided}>
      <Stack gap="sm">
        <Inline gap="sm">
          <span {...stylex.props(job.ok ? styles.ok : styles.bad)}>
            <Icon name={job.ok ? 'check' : 'alert'} size={16} />
          </span>
          <span {...stylex.props(styles.title)}>{job.title}</span>
          <Spacer />
          <Text tone="muted" size="md">
            {job.started && job.finished ? `${duration(job.finished - job.started)} · ` : ''}
            <When t={job.finished} />
          </Text>
          <Button
            label={open ? 'Hide log' : 'Log'}
            icon="log"
            small
            variant="quiet"
            onClick={() => {
              setOpen(!open);
            }}
          />
        </Inline>
        {job.message && job.message !== 'Done.' && <Text tone={job.ok ? 'muted' : undefined}>{job.message}</Text>}
        {open && <Log id={job.id} live={false} />}
      </Stack>
    </CardBody>
  );
}

function Log({ id, live: following }: { id: string; live: boolean }) {
  const { data } = useJobLog(id, following);
  const ref = useRef<HTMLPreElement>(null);
  const text = data?.text ?? '';
  useEffect(() => {
    const el = ref.current;
    if (el && following) el.scrollTop = el.scrollHeight;
  }, [text, following]);
  return (
    <pre ref={ref} {...stylex.props(styles.log)}>
      {text || 'Starting…'}
    </pre>
  );
}

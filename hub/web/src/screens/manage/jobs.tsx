import * as stylex from '@stylexjs/stylex';
import { useEffect, useRef, useState } from 'react';
import { useJobLog } from '../../api/queries';
import type { Job } from '../../api/types';
import { duration, elapsed } from '../../lib/format';
import { useNow } from '../../lib/useNow';
import { colors, font, radius, space, text } from '../../theme/tokens.stylex';
import { Button } from '../../ui/Button';
import { Icon } from '../../ui/Icon';
import { Appear } from '../../ui/motion';
import { Section } from '../../ui/page';
import { Badge, Pill } from '../../ui/status';
import { When } from '../../ui/When';

const run = stylex.keyframes({ to: { backgroundPosition: '20px 0' } });
const blink = stylex.keyframes({ '50%': { opacity: 0.2 } });

const styles = stylex.create({
  live: {
    position: 'relative',
    overflow: 'hidden',
    borderRadius: radius.xl,
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: `color-mix(in srgb, ${colors.info} 45%, ${colors.line})`,
    backgroundColor: colors.panel,
  },
  liveHead: {
    position: 'relative',
    display: 'flex',
    alignItems: 'center',
    gap: space.md,
    flexWrap: 'wrap',
    paddingBlock: space.lg,
    paddingInline: space.xxl,
    backgroundColor: colors.raised,
  },
  // a small blinking block: working
  working: {
    width: 8,
    height: 14,
    flexShrink: 0,
    backgroundColor: colors.info,
    animationName: blink,
    animationDuration: '1s',
    animationTimingFunction: 'steps(1)',
    animationIterationCount: 'infinite',
  },
  waitIcon: { display: 'flex', color: colors.faint },
  liveText: { flex: '1', minWidth: 0 },
  liveTitle: { fontFamily: font.display, fontWeight: 600, fontSize: text.lg, overflowWrap: 'anywhere' },
  liveSub: { fontSize: text.sm, color: colors.muted },
  timer: {
    fontFamily: font.mono,
    fontSize: text.xl,
    fontWeight: 500,
    letterSpacing: '-.02em',
    fontVariantNumeric: 'tabular-nums',
    color: colors.info,
  },
  // the running dashed line: work in progress
  bar: {
    position: 'absolute',
    insetInline: 0,
    bottom: 0,
    height: 1,
    backgroundImage: `repeating-linear-gradient(90deg, ${colors.info} 0 6px, transparent 6px 10px)`,
    backgroundSize: '20px 1px',
    animationName: run,
    animationDuration: '1s',
    animationTimingFunction: 'linear',
    animationIterationCount: 'infinite',
  },
  liveBody: {
    display: 'grid',
    gap: space.md,
    paddingBlock: space.lg,
    paddingInline: space.xxl,
    borderTopWidth: 1,
    borderTopStyle: 'solid',
    borderTopColor: colors.line,
  },
  note: { fontSize: text.sm, color: colors.faint },
  console: {
    overflow: 'hidden',
    borderRadius: radius.md,
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: colors.line,
    backgroundColor: colors.sunk,
    minWidth: 0,
  },
  consoleBar: {
    display: 'flex',
    alignItems: 'center',
    gap: space.sm,
    paddingBlock: space.xs,
    paddingInline: space.lg,
    fontFamily: font.mono,
    fontSize: text.xxs,
    letterSpacing: '.1em',
    textTransform: 'uppercase',
    color: colors.faint,
    backgroundColor: colors.raised,
    borderBottomWidth: 1,
    borderBottomStyle: 'solid',
    borderBottomColor: colors.line,
  },
  following: { marginInlineStart: 'auto', display: 'inline-flex', alignItems: 'center', gap: space.xs, color: colors.info },
  followDot: {
    width: 6,
    height: 6,
    backgroundColor: colors.info,
    animationName: blink,
    animationDuration: '1.4s',
    animationIterationCount: 'infinite',
  },
  log: {
    margin: 0,
    maxHeight: 320,
    overflow: 'auto',
    whiteSpace: 'pre-wrap',
    overflowWrap: 'anywhere',
    fontFamily: font.mono,
    fontSize: text.xs,
    lineHeight: 1.6,
    paddingBlock: space.lg,
    paddingInline: space.xl,
    color: colors.fg,
  },
  // history: rows on hairlines, newest first
  history: {
    overflow: 'hidden',
    borderRadius: radius.xl,
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: colors.line,
    backgroundColor: colors.panel,
  },
  row: {
    position: 'relative',
    display: 'grid',
    gridTemplateColumns: '24px minmax(0, 1fr) auto',
    gap: space.lg,
    alignItems: 'start',
    paddingBlock: space.md,
    paddingInline: space.xxl,
    borderTopWidth: { default: 1, ':first-child': 0 },
    borderTopStyle: 'solid',
    borderTopColor: colors.line,
  },
  mark: {
    width: 24,
    height: 24,
    display: 'grid',
    placeItems: 'center',
    borderRadius: radius.md,
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: `color-mix(in srgb, ${colors.ok} 30%, transparent)`,
    color: colors.ok,
    backgroundColor: colors.okSoft,
  },
  markBad: {
    color: colors.bad,
    backgroundColor: colors.badSoft,
    borderColor: `color-mix(in srgb, ${colors.bad} 35%, transparent)`,
  },
  rowTitle: { display: 'flex', alignItems: 'center', gap: space.sm, fontWeight: 500, overflowWrap: 'anywhere' },
  rowMeta: { fontFamily: font.mono, fontSize: text.xs, color: colors.faint, fontVariantNumeric: 'tabular-nums' },
  message: { fontSize: text.md, color: colors.muted, marginBlockStart: space.xxs, overflowWrap: 'anywhere' },
  messageBad: { color: colors.bad },
  rowLog: { gridColumnStart: 2, gridColumnEnd: -1, minWidth: 0 },
});

const live = (j: Job) => j.state === 'queued' || j.state === 'running';

/** The agent a job is about, read from its title ("Resize sara", "Add sara for …", "Remove sara …"). */
export const jobAgent = (j: Job) => /^(?:Add|Resize|Remove) ([a-z0-9-]+)/.exec(j.title || '')?.[1];

/** What is running now, log open and following. */
export function ActiveJobs({ jobs }: { jobs: Job[] }) {
  const active = jobs.filter(live);
  if (!active.length) return null;
  return (
    <Section
      title="In progress"
      icon="refresh"
      sub="Changes run one at a time; a queued one starts when the one before it finishes."
    >
      {active.map((j, i) => (
        <Appear key={j.id} i={i}>
          <JobCard job={j} />
        </Appear>
      ))}
    </Section>
  );
}

/** Recent changes, log on demand. */
export function JobHistory({ jobs }: { jobs: Job[] }) {
  const done = jobs.filter((j) => !live(j)).slice(0, 8);
  if (!done.length) return null;
  return (
    <Section title="Recent changes" icon="history">
      <div {...stylex.props(styles.history)}>
        {done.map((j) => (
          <JobRow key={j.id} job={j} />
        ))}
      </div>
    </Section>
  );
}

function JobCard({ job }: { job: Job }) {
  const now = useNow(1000);
  const running = job.state === 'running';
  const who = jobAgent(job);
  return (
    <div {...stylex.props(styles.live)}>
      <div {...stylex.props(styles.liveHead)}>
        {running ? (
          <span {...stylex.props(styles.working)} />
        ) : (
          <span {...stylex.props(styles.waitIcon)}>
            <Icon name="clock" size={16} />
          </span>
        )}
        {who && <Badge name={who} size="sm" />}
        <div {...stylex.props(styles.liveText)}>
          <div {...stylex.props(styles.liveTitle)}>{job.title}</div>
          <div {...stylex.props(styles.liveSub)}>
            {running ? (
              <>
                started <When t={job.started} />
              </>
            ) : (
              'waiting its turn'
            )}
            {job.by && ` · by ${job.by}`}
          </div>
        </div>
        {running ? (
          <span {...stylex.props(styles.timer)}>{elapsed(now - (job.started ?? now))}</span>
        ) : (
          <Pill tone="idle">queued</Pill>
        )}
        {running && <span {...stylex.props(styles.bar)} />}
      </div>
      {running && (
        <div {...stylex.props(styles.liveBody)}>
          <Log id={job.id} live />
          <span {...stylex.props(styles.note)}>
            You can leave this page; the change carries on on the server, and finishes even if this page reloads.
          </span>
        </div>
      )}
    </div>
  );
}

function JobRow({ job }: { job: Job }) {
  const [open, setOpen] = useState(false);
  const who = jobAgent(job);
  return (
    <div {...stylex.props(styles.row)}>
      <span {...stylex.props(styles.mark, !job.ok && styles.markBad)}>
        <Icon name={job.ok ? 'check' : 'alert'} size={14} />
      </span>
      <div>
        <div {...stylex.props(styles.rowTitle)}>
          {who && <Badge name={who} size="xs" />}
          {job.title}
        </div>
        <div {...stylex.props(styles.rowMeta)}>
          {job.started && job.finished ? `took ${duration(job.finished - job.started)} · ` : ''}
          <When t={job.finished} />
        </div>
        {job.message && job.message !== 'Done.' && (
          <div {...stylex.props(styles.message, !job.ok && styles.messageBad)}>{job.message}</div>
        )}
      </div>
      <Button
        label={open ? 'Hide log' : 'Log'}
        icon="log"
        small
        variant="quiet"
        onClick={() => {
          setOpen(!open);
        }}
      />
      {open && (
        <div {...stylex.props(styles.rowLog)}>
          <Log id={job.id} live={false} />
        </div>
      )}
    </div>
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
    <div {...stylex.props(styles.console)}>
      <div {...stylex.props(styles.consoleBar)}>
        <Icon name="terminal" size={13} />
        Log
        {following && (
          <span {...stylex.props(styles.following)}>
            <i {...stylex.props(styles.followDot)} />
            following
          </span>
        )}
      </div>
      <pre ref={ref} {...stylex.props(styles.log)}>
        {text || 'Starting…'}
      </pre>
    </div>
  );
}

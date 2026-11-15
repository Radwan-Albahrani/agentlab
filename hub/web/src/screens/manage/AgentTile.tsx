import * as stylex from '@stylexjs/stylex';
import type { Job, ManagedAgent } from '../../api/types';
import { elapsed, gb, pct } from '../../lib/format';
import { useNow } from '../../lib/useNow';
import { colors, font, radius, space, text } from '../../theme/tokens.stylex';
import { Button } from '../../ui/Button';
import { Icon } from '../../ui/Icon';
import { MoreMenu } from '../../ui/Menu';
import { Badge, Meter, Pill } from '../../ui/status';

const run = stylex.keyframes({ to: { backgroundPosition: '20px 0' } });

const styles = stylex.create({
  tile: {
    position: 'relative',
    display: 'grid',
    overflow: 'hidden',
    borderRadius: radius.xl,
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: { default: colors.line, ':hover': colors.line2 },
    backgroundColor: colors.panel,
    minWidth: 0,
    transitionProperty: 'border-color',
    transitionDuration: '140ms',
  },
  // a whole border in the tone, never a stripe down one edge
  busy: { borderColor: { default: `color-mix(in srgb, ${colors.info} 45%, ${colors.line})`, ':hover': colors.info } },
  down: { borderColor: { default: `color-mix(in srgb, ${colors.bad} 50%, ${colors.line})`, ':hover': colors.bad } },
  head: {
    display: 'flex',
    alignItems: 'center',
    gap: space.md,
    paddingBlock: space.lg,
    paddingInline: space.xxl,
    backgroundColor: colors.raised,
    borderBottomWidth: 1,
    borderBottomStyle: 'solid',
    borderBottomColor: colors.line,
  },
  headDown: { backgroundColor: colors.badSoft },
  who: { flex: '1', minWidth: 0 },
  name: { fontFamily: font.display, fontSize: text.lg, fontWeight: 600, lineHeight: 1.2 },
  owner: {
    fontFamily: font.mono,
    fontSize: text.xs,
    color: colors.muted,
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
  },
  body: { display: 'grid', gap: space.lg, paddingBlock: space.lg, paddingInline: space.xxl },
  // a hairline number strip
  stats: {
    display: 'grid',
    gridTemplateColumns: 'repeat(3, minmax(0, 1fr))',
    gap: 1,
    backgroundColor: colors.line,
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: colors.line,
    borderRadius: radius.md,
    overflow: 'hidden',
  },
  stat: {
    backgroundColor: colors.panel,
    paddingBlock: space.sm,
    paddingInline: space.md,
    display: 'grid',
    gap: space.xxxs,
    minWidth: 0,
  },
  label: {
    fontSize: text.xxs,
    color: colors.faint,
  },
  value: {
    fontFamily: font.mono,
    fontSize: text.xl,
    fontWeight: 500,
    fontVariantNumeric: 'tabular-nums',
    whiteSpace: 'nowrap',
    letterSpacing: '-.02em',
  },
  unit: { fontSize: text.xs, color: colors.faint, fontWeight: 400, marginInlineStart: space.xxxs, letterSpacing: 0 },
  custom: {
    fontSize: text.xxs,
    color: colors.muted,
    minHeight: 15,
  },
  disk: { display: 'grid', gap: space.xs },
  diskText: {
    display: 'flex',
    justifyContent: 'space-between',
    gap: space.sm,
    fontFamily: font.mono,
    fontSize: text.xxs,
    color: colors.faint,
    fontVariantNumeric: 'tabular-nums',
  },
  job: {
    position: 'relative',
    display: 'flex',
    alignItems: 'center',
    gap: space.sm,
    paddingBlock: space.sm,
    paddingInline: space.md,
    borderRadius: radius.md,
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: `color-mix(in srgb, ${colors.info} 30%, transparent)`,
    fontSize: text.md,
    fontWeight: 500,
    color: colors.info,
    backgroundColor: colors.infoSoft,
    overflow: 'hidden',
  },
  jobTitle: { flex: '1', minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' },
  jobTime: { fontFamily: font.mono, fontVariantNumeric: 'tabular-nums', fontSize: text.xs },
  // the running dashed line: work in progress
  jobBar: {
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
  foot: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: space.sm,
    paddingBlock: space.sm,
    paddingInline: space.xxl,
    borderTopWidth: 1,
    borderTopStyle: 'solid',
    borderTopColor: colors.line,
  },
  add: {
    width: '100%',
    height: '100%',
    minHeight: 220,
    display: 'grid',
    placeItems: 'center',
    alignContent: 'center',
    gap: space.sm,
    borderRadius: radius.xl,
    borderWidth: 1,
    borderStyle: 'dashed',
    borderColor: { default: colors.line2, ':hover': colors.faint },
    backgroundColor: { default: 'transparent', ':hover': colors.hover },
    color: { default: colors.muted, ':hover': colors.fg },
    cursor: 'pointer',
    fontSize: text.body,
    fontWeight: 500,
    fontFamily: 'inherit',
    transitionProperty: 'background-color, border-color, color',
    transitionDuration: '140ms',
    opacity: { default: 1, ':active': 0.85 },
    outline: { default: 'none', ':focus-visible': `2px solid ${colors.accent}` },
    outlineOffset: 2,
  },
  addIcon: {
    width: 36,
    height: 36,
    display: 'grid',
    placeItems: 'center',
    borderRadius: radius.lg,
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: colors.line2,
    color: colors.accent,
    backgroundColor: colors.panel,
  },
  addSub: { fontSize: text.md, color: colors.faint, fontWeight: 400 },
  addDisabled: { cursor: 'not-allowed', opacity: 0.5 },
});

/** "12g" -> ["12", "GB"] */
export function size(v: string): [string, string] {
  const m = /^([\d.]+)\s*([kmgt]?)/i.exec(v);
  if (!m) return [v, ''];
  return [m[1] ?? v, m[2] ? `${m[2].toUpperCase()}B` : 'B'];
}

function Stat({ label, value, unit, custom }: { label: string; value: string; unit?: string; custom?: boolean }) {
  return (
    <div {...stylex.props(styles.stat)}>
      <span {...stylex.props(styles.label)}>{label}</span>
      <span {...stylex.props(styles.value)}>
        {value}
        {unit && <span {...stylex.props(styles.unit)}>{unit}</span>}
      </span>
      <span {...stylex.props(styles.custom)}>{custom ? 'custom' : ''}</span>
    </div>
  );
}

const STATE = {
  up: (
    <Pill tone="ok" dot>
      Running
    </Pill>
  ),
  starting: <Pill tone="warn">Starting</Pill>,
  down: <Pill tone="bad">Stopped</Pill>,
};

function JobStrip({ job }: { job: Job }) {
  const now = useNow(1000);
  const running = job.state === 'running';
  return (
    <div {...stylex.props(styles.job)}>
      <Icon name={running ? 'refresh' : 'clock'} size={14} />
      <span {...stylex.props(styles.jobTitle)}>{job.title}</span>
      <span {...stylex.props(styles.jobTime)}>{running ? elapsed(now - (job.started ?? now)) : 'queued'}</span>
      {running && <span {...stylex.props(styles.jobBar)} />}
    </div>
  );
}

export function AgentTile({
  a,
  job,
  disabled,
  onResize,
  onRemove,
}: {
  a: ManagedAgent;
  job?: Job;
  disabled: boolean;
  onResize: () => void;
  onRemove: () => void;
}) {
  const [mem, memUnit] = size(a.memory);
  const files = a.used ? (a.used / 2 ** 30).toFixed(1) : '—';
  return (
    <div {...stylex.props(styles.tile, !!job && styles.busy, a.state === 'down' && styles.down)}>
      <div {...stylex.props(styles.head, a.state === 'down' && styles.headDown)}>
        <Badge name={a.id} />
        <div {...stylex.props(styles.who)}>
          <div {...stylex.props(styles.name)}>{a.id}</div>
          <div {...stylex.props(styles.owner)} title={a.owner}>
            {a.owner}
          </div>
        </div>
        {STATE[a.state]}
      </div>
      <div {...stylex.props(styles.body)}>
        <div {...stylex.props(styles.stats)}>
          <Stat label="Memory" value={mem} unit={memUnit} custom={a.customMemory} />
          <Stat label="CPUs" value={String(a.cpus)} custom={a.customCpus} />
          <Stat label="Files" value={files} unit={a.used ? 'GB' : undefined} />
        </div>
        {a.disk && a.disk.size > 0 && (
          <div {...stylex.props(styles.disk)}>
            <Meter pct={pct(a.disk.used, a.disk.size)} />
            <div {...stylex.props(styles.diskText)}>
              <span>{"Owner's disk"}</span>
              <span>
                {gb(a.disk.used)} of {gb(a.disk.size, 0)}
              </span>
            </div>
          </div>
        )}
        {job && <JobStrip job={job} />}
      </div>
      <div {...stylex.props(styles.foot)}>
        <Button label="Resize" icon="sliders" small disabled={disabled} onClick={onResize} />
        <MoreMenu
          label={`More for ${a.id}`}
          entries={[{ label: 'Remove agent…', icon: 'trash', danger: true, disabled, onSelect: onRemove }]}
        />
      </div>
    </div>
  );
}

export function AddTile({ disabled, onAdd }: { disabled: boolean; onAdd: () => void }) {
  return (
    <button type="button" {...stylex.props(styles.add, disabled && styles.addDisabled)} disabled={disabled} onClick={onAdd}>
      <span {...stylex.props(styles.addIcon)}>
        <Icon name="plus" size={18} />
      </span>
      <span>Add an agent</span>
      <span {...stylex.props(styles.addSub)}>Everything it needs is set up for you</span>
    </button>
  );
}

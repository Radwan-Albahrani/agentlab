import * as stylex from '@stylexjs/stylex';
import type { ReactNode } from 'react';
import { useStorage } from '../api/queries';
import type { DiskScan, Event, PersonDisk, Pool, ProfileUsage, Storage as Data } from '../api/types';
import { Screen } from '../app/Screen';
import { ago, gb, pct, plural, toneFor } from '../lib/format';
import { colors, font, media, motion, radius, space, text } from '../theme/tokens.stylex';
import { ActButton } from '../ui/actions';
import { FeedSection } from '../ui/Feed';
import { Icon } from '../ui/Icon';
import { Appear, Num, useTween } from '../ui/motion';
import { Empty, EmptyCard, PageHead, Section } from '../ui/page';
import { Ring } from '../ui/Ring';
import { StackedBar } from '../ui/StackedBar';
import { Badge } from '../ui/status';
import { Eyebrow } from '../ui/text';
import { When } from '../ui/When';

const ALERT_AT = 80; // matches the Needs you alert

const styles = stylex.create({
  hero: {
    display: 'grid',
    gridTemplateColumns: { default: 'auto minmax(0, 1fr) minmax(0, 300px)', [media.narrow]: '1fr' },
    gap: { default: space.huge, [media.phone]: space.xxxl },
    alignItems: 'center',
    paddingBlock: { default: space.huge, [media.phone]: space.xxxl },
    paddingInline: { default: space.huge, [media.phone]: space.xxl },
    borderRadius: radius.xl,
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: colors.line,
    backgroundColor: colors.panel,
  },
  heroSolo: { gridTemplateColumns: { default: 'auto minmax(0, 1fr)', [media.narrow]: '1fr' } },
  gauge: { position: 'relative', display: 'grid', placeItems: 'center', justifySelf: { default: null, [media.narrow]: 'start' } },
  gaugeSvg: { transform: 'rotate(-90deg)' },
  track: { stroke: colors.sunk },
  ok: { stroke: colors.ok, color: colors.ok },
  warn: { stroke: colors.warn, color: colors.warn },
  bad: { stroke: colors.bad, color: colors.bad },
  gaugeText: { position: 'absolute', display: 'grid', justifyItems: 'center', lineHeight: 1 },
  gaugePct: {
    fontFamily: font.mono,
    fontSize: text.xxl,
    fontWeight: 500,
    letterSpacing: '-.03em',
    fontVariantNumeric: 'tabular-nums',
  },
  gaugeLabel: {
    fontSize: text.xxs,
    color: colors.faint,
    marginBlockStart: space.xxs,
  },
  facts: { display: 'grid', gap: space.sm, minWidth: 0 },
  free: {
    fontFamily: font.mono,
    fontSize: { default: text.hero, [media.phone]: text.display },
    fontWeight: 500,
    letterSpacing: '-.04em',
    lineHeight: 1,
    fontVariantNumeric: 'tabular-nums',
  },
  freeUnit: {
    fontFamily: font.mono,
    fontSize: text.lg,
    color: colors.faint,
    fontWeight: 400,
    marginInlineStart: space.xs,
    letterSpacing: 0,
  },
  used: { fontFamily: font.mono, color: colors.muted, fontSize: text.md, fontVariantNumeric: 'tabular-nums' },
  // the bar with a tick where the alert starts
  bar: {
    position: 'relative',
    height: 10,
    marginBlockStart: space.sm,
    borderRadius: radius.xs,
    backgroundColor: colors.sunk,
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: colors.line,
  },
  barFill: (p: number) => ({
    display: 'block',
    height: '100%',
    width: `${p}%`,
    transitionProperty: 'width',
    transitionDuration: '600ms',
    transitionTimingFunction: motion.settle,
  }),
  fillOk: { backgroundColor: colors.ok },
  fillWarn: { backgroundColor: colors.warn },
  fillBad: { backgroundColor: colors.bad },
  tick: {
    position: 'absolute',
    top: -5,
    bottom: -5,
    left: `${ALERT_AT}%`,
    width: 2,
    backgroundColor: colors.warn,
  },
  scale: {
    display: 'flex',
    justifyContent: 'space-between',
    fontSize: text.xxs,
    color: colors.faint,
  },
  tickLabel: { color: colors.warn },
  cleanup: {
    display: 'grid',
    gap: space.md,
    alignContent: 'start',
    paddingBlock: space.xl,
    paddingInline: space.xxl,
    borderRadius: radius.lg,
    backgroundColor: colors.raised,
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: colors.line,
  },
  cleanupHead: {
    display: 'flex',
    alignItems: 'center',
    gap: space.sm,
    fontSize: text.xs,
    fontWeight: 600,
  },
  cleanupIcon: { display: 'flex', color: colors.faint },
  cleanupText: { margin: 0, fontSize: text.md, color: colors.muted },
  cleanupLast: { fontFamily: font.mono, fontSize: text.xs, color: colors.faint, fontVariantNumeric: 'tabular-nums' },
  cleanupFreed: { color: colors.ok },
  // one hairline grid: each cell rings itself into the 1px gap, so neighbours share a line and empty slots stay clear
  people: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fill, minmax(min(100%, 300px), 1fr))',
    gap: 1,
    padding: 1,
  },
  person: {
    display: 'grid',
    gap: space.xs,
    paddingBlock: space.lg,
    paddingInline: space.xxl,
    backgroundColor: colors.panel,
    boxShadow: `0 0 0 1px ${colors.line}`,
    minWidth: 0,
  },
  personWarn: { backgroundColor: colors.warnSoft },
  personBad: { backgroundColor: colors.badSoft },
  personHead: { display: 'flex', alignItems: 'center', gap: space.sm, minWidth: 0 },
  email: {
    fontFamily: font.mono,
    fontSize: text.sm,
    fontWeight: 500,
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
    flex: '1',
    minWidth: 0,
  },
  badges: { display: 'flex', gap: space.xxs, flexShrink: 0 },
  missing: {
    display: 'flex',
    alignItems: 'center',
    gap: space.md,
    color: colors.warn,
    fontSize: text.md,
    paddingBlock: space.md,
  },
  // breakdown: one hairline panel per agent, its colour only on the badge
  usage: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 420px), 1fr))',
    gap: space.xxl,
    alignItems: 'start',
  },
  usageCard: {
    overflow: 'hidden',
    borderRadius: radius.xl,
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: colors.line,
    backgroundColor: colors.panel,
    minWidth: 0,
  },
  usageHead: {
    display: 'flex',
    alignItems: 'center',
    gap: space.md,
    paddingBlock: space.md,
    paddingInline: space.xxl,
    backgroundColor: colors.raised,
    borderBottomWidth: 1,
    borderBottomStyle: 'solid',
    borderBottomColor: colors.line,
  },
  usageName: {
    flex: '1',
    minWidth: 0,
    fontSize: text.xs,
    fontWeight: 600,
  },
  usageTotal: {
    fontFamily: font.mono,
    fontSize: text.lg,
    fontWeight: 500,
    textAlign: 'right',
    fontVariantNumeric: 'tabular-nums',
  },
  usageShare: { fontFamily: font.mono, fontSize: text.xxs, color: colors.faint, textAlign: 'right' },
  usageBody: { display: 'grid', gap: space.lg, paddingBlock: space.xl, paddingInline: space.xxl },
  rank: { display: 'grid', gap: space.sm, margin: 0, padding: 0, listStyle: 'none' },
  rankRow: {
    display: 'grid',
    gridTemplateColumns: 'minmax(0, 1fr) auto',
    gap: space.xxs,
    columnGap: space.lg,
    alignItems: 'center',
    fontFamily: font.mono,
    fontSize: text.xs,
  },
  rankPath: { color: colors.fg, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' },
  rankSize: { color: colors.muted, fontVariantNumeric: 'tabular-nums' },
  rankTrack: { gridColumnStart: 1, gridColumnEnd: -1, height: 4, backgroundColor: colors.sunk, overflow: 'hidden' },
  rankFill: (p: number) => ({ display: 'block', height: '100%', width: `${p}%`, backgroundColor: colors.faint }),
});

const FILL = { ok: styles.fillOk, warn: styles.fillWarn, bad: styles.fillBad };

export function Storage() {
  const query = useStorage();
  return (
    <Screen title="Storage" query={query}>
      {(d) => <StorageView d={d} />}
    </Screen>
  );
}

const mounted = (p: PersonDisk): p is PersonDisk & Pool => !!p.size;

function StorageView({ d }: { d: Data }) {
  const shared = d.mode === 'shared';
  const disks = d.people.filter(mounted);
  // per person, the headline adds up every mounted disk
  const total: Pool | null =
    d.pool ??
    (disks.length
      ? disks.reduce((a, p) => ({ size: a.size + p.size, used: a.used + p.used, avail: a.avail + p.avail }), {
          size: 0,
          used: 0,
          avail: 0,
        })
      : null);
  const cleanup = d.manage ? <Cleanup events={d.events} /> : null;
  return (
    <>
      <PageHead
        eyebrow={
          total
            ? `${shared ? 'shared pool' : plural(disks.length, 'disk')} · ${pct(total.used, total.size).toFixed(0)}% used`
            : shared
              ? 'shared pool'
              : 'a disk per person'
        }
        title="Storage"
        sub={
          shared
            ? `All agents share one pool on the server. Above ${ALERT_AT} % it shows under Needs you.`
            : `Each person's agents share a disk of their own, so one full disk never stops anyone else. Above ${ALERT_AT} % it shows under Needs you.`
        }
        right={d.manage && <ActButton label="Rescan" icon="refresh" url="/api/storage/rescan" />}
      />
      {d.reported ? (
        <>
          {total ? (
            <Capacity
              disk={total}
              title={d.pool ? 'Agents pool' : disks.length === 1 ? 'One disk' : `${disks.length} disks together`}
              side={cleanup}
            />
          ) : (
            cleanup
          )}
          {!shared && d.people.length > 0 && (
            <Section title="Disks" icon="disk" sub="One per person, shared by their agents.">
              <div {...stylex.props(styles.people)}>
                {d.people.map((p, i) => (
                  <Appear key={p.email} i={i}>
                    <PersonTile p={p} />
                  </Appear>
                ))}
              </div>
            </Section>
          )}
          <Breakdown scan={d.scan} />
        </>
      ) : (
        <>
          <EmptyCard title="No numbers yet" text="The host watcher (agentlab-watch) reports every 30 s." icon="alert" />
          {cleanup}
        </>
      )}
      {d.manage && <FeedSection title="Cleanups and alerts" sub="Nightly cleanup, plus any you start here." events={d.events} />}
    </>
  );
}

const SIZE = 148;
const STROKE = 10;

function Gauge({ p }: { p: number }) {
  const r = (SIZE - STROKE) / 2;
  const c = 2 * Math.PI * r;
  const shown = useTween(Math.max(0, Math.min(100, p)), 900);
  const tone = styles[toneFor(p)];
  return (
    <div {...stylex.props(styles.gauge)}>
      <svg width={SIZE} height={SIZE} viewBox={`0 0 ${SIZE} ${SIZE}`} {...stylex.props(styles.gaugeSvg)} aria-hidden="true">
        <circle cx={SIZE / 2} cy={SIZE / 2} r={r} fill="none" strokeWidth={STROKE} {...stylex.props(styles.track)} />
        <circle
          cx={SIZE / 2}
          cy={SIZE / 2}
          r={r}
          fill="none"
          strokeWidth={STROKE}
          strokeLinecap="butt"
          strokeDasharray={c}
          strokeDashoffset={c * (1 - shown / 100)}
          {...stylex.props(tone)}
        />
      </svg>
      <div {...stylex.props(styles.gaugeText)}>
        <span {...stylex.props(styles.gaugePct, tone)}>{shown.toFixed(0)}%</span>
        <span {...stylex.props(styles.gaugeLabel)}>used</span>
      </div>
    </div>
  );
}

function Capacity({ disk, title, side }: { disk: Pool; title: string; side: ReactNode }) {
  const used = pct(disk.used, disk.size);
  return (
    <section {...stylex.props(styles.hero, !side && styles.heroSolo)} aria-label="Capacity">
      <Gauge p={used} />
      <div {...stylex.props(styles.facts)}>
        <Eyebrow>{title}</Eyebrow>
        <div {...stylex.props(styles.free)}>
          <Num value={disk.avail / 2 ** 30} digits={disk.avail < 10 * 2 ** 30 ? 1 : 0} />
          <span {...stylex.props(styles.freeUnit)}>GB free</span>
        </div>
        <div {...stylex.props(styles.used)}>
          {gb(disk.used)} used of {gb(disk.size, 0)}
        </div>
        <div {...stylex.props(styles.bar)}>
          <span {...stylex.props(styles.barFill(Number(Math.min(100, used).toFixed(1))), FILL[toneFor(used)])} />
          <i {...stylex.props(styles.tick)} title={`Alert at ${ALERT_AT} %`} />
        </div>
        <div {...stylex.props(styles.scale)}>
          <span>0</span>
          <span {...stylex.props(styles.tickLabel)}>alert at {ALERT_AT} %</span>
        </div>
      </div>
      {side}
    </section>
  );
}

function Cleanup({ events }: { events: Event[] }) {
  const last = events.filter((e) => e.kind === 'cleanup').sort((a, b) => b.at - a.at)[0];
  return (
    <div {...stylex.props(styles.cleanup)}>
      <div {...stylex.props(styles.cleanupHead)}>
        <span {...stylex.props(styles.cleanupIcon)}>
          <Icon name="broom" size={14} />
        </span>
        Reclaim space
      </div>
      <p {...stylex.props(styles.cleanupText)}>
        Removes Docker images, build cache and stopped containers unused for 3+ days inside every agent. It also runs nightly.
      </p>
      {last && (
        <div {...stylex.props(styles.cleanupLast)}>
          Last: <When t={last.at} />
          {last.detail && <span {...stylex.props(styles.cleanupFreed)}> · {last.detail}</span>}
        </div>
      )}
      <div>
        <ActButton
          label="Clean up now"
          icon="broom"
          variant="primary"
          url="/api/storage/cleanup"
          confirm="Remove Docker images, build cache and stopped containers unused for 3+ days inside every agent?"
        />
      </div>
    </div>
  );
}

function PersonTile({ p }: { p: PersonDisk }) {
  const used = mounted(p) ? pct(p.used, p.size) : 0;
  const tone = toneFor(used);
  return (
    <div
      {...stylex.props(
        styles.person,
        (!mounted(p) || tone === 'warn') && styles.personWarn,
        mounted(p) && tone === 'bad' && styles.personBad,
      )}
    >
      <div {...stylex.props(styles.personHead)}>
        <span {...stylex.props(styles.email)} title={p.email}>
          {p.email}
        </span>
        <span {...stylex.props(styles.badges)}>
          {p.agents.map((a) => (
            <Badge key={a} name={a} size="xs" />
          ))}
        </span>
      </div>
      {mounted(p) ? (
        <Ring bare pct={used} label="Used" value={gb(p.used)} sub={`of ${gb(p.size, 0)} · ${gb(p.avail)} free`} />
      ) : (
        <div {...stylex.props(styles.missing)}>
          <Icon name="alert" size={18} />
          Disk not mounted: their agents cannot start without it.
        </div>
      )}
    </div>
  );
}

function Breakdown({ scan }: { scan: DiskScan | undefined }) {
  const sub = scan
    ? `Measured ${ago(scan.at)} (took ${scan.took} s); every 3 hours.`
    : 'First measurement runs in the background.';
  const all = scan?.profiles.reduce((n, x) => n + x.total, 0) ?? 0;
  return (
    <Section title="Where the space goes" icon="poll" sub={sub}>
      {scan?.profiles.length ? (
        <div {...stylex.props(styles.usage)}>
          {scan.profiles.map((x, i) => (
            <Appear key={x.name} i={i}>
              <ProfileBreakdown usage={x} share={scan.profiles.length > 1 ? pct(x.total, all) : null} />
            </Appear>
          ))}
        </div>
      ) : (
        <EmptyMeasuring />
      )}
    </Section>
  );
}

const EmptyMeasuring = () => (
  <div {...stylex.props(styles.usageCard)}>
    <Empty title="Measuring…" text="A full scan takes about a minute." icon="clock" />
  </div>
);

function ProfileBreakdown({ usage: x, share }: { usage: ProfileUsage; share: number | null }) {
  const top = x.biggest[0]?.bytes ?? 0;
  return (
    <div {...stylex.props(styles.usageCard)}>
      <div {...stylex.props(styles.usageHead)}>
        <Badge name={x.name} size="xs" />
        <span {...stylex.props(styles.usageName)}>{x.name}</span>
        <div>
          <div {...stylex.props(styles.usageTotal)}>{gb(x.total)}</div>
          {share !== null && <div {...stylex.props(styles.usageShare)}>{share.toFixed(0)}% of all</div>}
        </div>
      </div>
      <div {...stylex.props(styles.usageBody)}>
        <StackedBar parts={x.top.map((i) => ({ label: i.path, bytes: i.bytes }))} total={x.total} />
        {x.biggest.length > 0 && (
          <>
            <Eyebrow>Biggest folders</Eyebrow>
            <ul {...stylex.props(styles.rank)}>
              {x.biggest.map((i) => (
                <li key={i.path} {...stylex.props(styles.rankRow)}>
                  <span {...stylex.props(styles.rankPath)} title={i.path}>
                    {i.path}
                  </span>
                  <span {...stylex.props(styles.rankSize)}>{gb(i.bytes)}</span>
                  <span {...stylex.props(styles.rankTrack)}>
                    <i {...stylex.props(styles.rankFill(Number(pct(i.bytes, top).toFixed(1))))} />
                  </span>
                </li>
              ))}
            </ul>
          </>
        )}
      </div>
    </div>
  );
}

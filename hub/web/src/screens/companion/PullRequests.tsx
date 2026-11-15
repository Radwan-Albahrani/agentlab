import * as stylex from '@stylexjs/stylex';
import { useState } from 'react';
import { useCompanionPoll, usePullsRefresh } from '../../api/queries';
import type { Ci, Pull, PullReview, Pulls } from '../../api/types';
import { ago, plural } from '../../lib/format';
import { arrange, FILTERS, grouped, outdated, type PullFilter, type PullSort, SORTS } from '../../lib/pulls';
import { usePages } from '../../lib/usePages';
import { colors, font, media, radius, space, text } from '../../theme/tokens.stylex';
import { Button, LinkButton } from '../../ui/Button';
import { Card } from '../../ui/Card';
import { Segments } from '../../ui/controls';
import { useAct } from '../../ui/feedback';
import { Icon } from '../../ui/Icon';
import { SearchInput } from '../../ui/inputs';
import { Inline, Spacer } from '../../ui/layout';
import { PickMenu } from '../../ui/Menu';
import { Appear, Num } from '../../ui/motion';
import { Empty, EmptyCard, Section } from '../../ui/page';
import { Pager } from '../../ui/Pager';
import { IconBox } from '../../ui/Row';
import { Pill } from '../../ui/status';
import { Avatar, Blink, LiveLine } from './parts';

const PAGE = 10;

const run = stylex.keyframes({ to: { backgroundPosition: '20px 0' } });

const styles = stylex.create({
  // the whole list's review state: a strip of counts over one proportional bar
  health: {
    display: 'grid',
    gap: 1,
    overflow: 'hidden',
    borderRadius: radius.xl,
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: colors.line,
    backgroundColor: colors.line,
  },
  cells: {
    display: 'grid',
    gridTemplateColumns: { default: 'repeat(auto-fit, minmax(120px, 1fr))', [media.phone]: 'repeat(2, minmax(0, 1fr))' },
    gap: 1,
  },
  cell: { display: 'grid', gap: space.xxxs, paddingBlock: space.md, paddingInline: space.xl, backgroundColor: colors.panel },
  cellValue: {
    fontFamily: font.mono,
    fontSize: text.xl,
    fontWeight: 500,
    letterSpacing: '-.02em',
    lineHeight: 1.15,
    fontVariantNumeric: 'tabular-nums',
  },
  cellLabel: {
    display: 'flex',
    alignItems: 'center',
    gap: space.xs,
    fontFamily: font.mono,
    fontSize: text.xxs,
    letterSpacing: '.08em',
    textTransform: 'uppercase',
    color: colors.muted,
  },
  bar: { display: 'flex', gap: 1, height: 4 },
  part: (n: number) => ({ flexGrow: n, flexBasis: 0, minWidth: 6 }),
  swatch: { width: 7, height: 7, flexShrink: 0 },
  blocking: { backgroundColor: colors.bad },
  findings: { backgroundColor: colors.warn },
  clean: { backgroundColor: colors.ok },
  // a bar that's still filling: dashes running along it
  reviewing: {
    backgroundColor: colors.infoSoft,
    backgroundImage: `repeating-linear-gradient(90deg, ${colors.info} 0 6px, transparent 6px 10px)`,
    backgroundSize: '20px 100%',
    animationName: run,
    animationDuration: '1s',
    animationTimingFunction: 'linear',
    animationIterationCount: 'infinite',
  },
  failed: { backgroundColor: `color-mix(in srgb, ${colors.bad} 45%, ${colors.sunk})` },
  unreviewed: { backgroundColor: colors.line2 },
  draft: {
    backgroundColor: colors.sunk,
    backgroundImage: `repeating-linear-gradient(135deg, ${colors.line2} 0 2px, transparent 2px 6px)`,
  },
  toneBad: { color: colors.bad },
  toneWarn: { color: colors.warn },
  toneOk: { color: colors.ok },
  toneInfo: { color: colors.info },
  toneFaint: { color: colors.faint },
  batch: {
    position: 'relative',
    display: 'grid',
    gap: space.lg,
    paddingBlock: space.lg,
    paddingInline: space.xxl,
    overflow: 'hidden',
    borderRadius: radius.xl,
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: `color-mix(in srgb, ${colors.info} 45%, ${colors.line})`,
    backgroundColor: colors.panel,
  },
  batchDone: { borderColor: `color-mix(in srgb, ${colors.ok} 45%, ${colors.line})` },
  batchHead: { display: 'flex', alignItems: 'center', gap: space.lg, flexWrap: 'wrap' },
  batchText: { flexGrow: 1, flexShrink: 1, flexBasis: 220, minWidth: 0 },
  batchTitle: {
    display: 'flex',
    alignItems: 'center',
    gap: space.sm,
    fontFamily: font.display,
    fontWeight: 600,
    fontSize: text.lg,
  },
  batchSub: { fontSize: text.md, color: colors.muted, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' },
  batchCount: {
    fontFamily: font.mono,
    fontSize: text.sm,
    color: colors.muted,
    fontVariantNumeric: 'tabular-nums',
    whiteSpace: 'nowrap',
  },
  batchDoneNum: { fontSize: text.lg, fontWeight: 600, color: colors.fg },
  segments: { display: 'flex', gap: space.xxs },
  segment: { flex: '1', display: 'grid', gap: space.xxs, minWidth: 0 },
  segBar: { height: 4, backgroundColor: colors.sunk, boxShadow: `inset 0 0 0 1px ${colors.line}` },
  segDone: { backgroundColor: colors.ok, boxShadow: 'none' },
  segLabel: {
    fontFamily: font.mono,
    fontSize: text.xxs,
    color: colors.faint,
    fontVariantNumeric: 'tabular-nums',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
  },
  segLabelOn: { color: colors.info, fontWeight: 600 },
  toolbar: { display: 'flex', gap: space.sm, alignItems: 'center', flexWrap: 'wrap' },
  search: { flexGrow: '1', flexShrink: '1', flexBasis: '260px', minWidth: 0 },
  group: {
    display: 'flex',
    alignItems: 'center',
    gap: space.sm,
    paddingBlock: space.xs,
    paddingInline: space.xxl,
    fontFamily: font.mono,
    fontSize: text.xxs,
    fontWeight: 600,
    letterSpacing: '.12em',
    textTransform: 'uppercase',
    color: colors.muted,
    borderTopWidth: { default: 1, ':first-child': 0 },
    borderTopStyle: 'solid',
    borderTopColor: colors.line,
    backgroundColor: colors.raised,
  },
  groupCount: { letterSpacing: 0, color: colors.faint, fontVariantNumeric: 'tabular-nums' },
  row: {
    position: 'relative',
    display: 'flex',
    alignItems: 'flex-start',
    gap: space.lg,
    paddingBlock: space.lg,
    paddingInline: { default: space.xxl, [media.phone]: space.lg },
    minWidth: 0,
    borderTopWidth: 1,
    borderTopStyle: 'solid',
    borderTopColor: colors.line,
    backgroundColor: { default: 'transparent', ':hover': colors.hover },
    transitionProperty: 'background-color',
    transitionDuration: '140ms',
  },
  // what's wrong tints the whole row before you read a word
  rowBad: { backgroundColor: { default: colors.badSoft, ':hover': `color-mix(in srgb, ${colors.bad} 18%, ${colors.panel})` } },
  rowWarn: { backgroundColor: { default: colors.warnSoft, ':hover': `color-mix(in srgb, ${colors.warn} 22%, ${colors.panel})` } },
  stateIcon: {
    position: 'relative',
    width: 32,
    height: 32,
    flexShrink: 0,
    borderRadius: radius.lg,
    display: 'grid',
    placeItems: 'center',
    backgroundColor: colors.sunk,
    color: colors.muted,
  },
  drafted: {
    color: colors.faint,
    backgroundColor: 'transparent',
    borderWidth: 1,
    borderStyle: 'dashed',
    borderColor: colors.line2,
  },
  ci: {
    position: 'absolute',
    right: -4,
    bottom: -4,
    width: 15,
    height: 15,
    borderRadius: radius.xs,
    display: 'grid',
    placeItems: 'center',
    color: colors.onFill,
    boxShadow: `0 0 0 2px ${colors.panel}`,
  },
  passing: { backgroundColor: colors.ok },
  failing: { backgroundColor: colors.bad },
  running: { backgroundColor: colors.info },
  body: {
    flex: '1',
    minWidth: 0,
    display: 'flex',
    alignItems: 'center',
    gap: { default: space.xl, [media.narrow]: space.md },
    flexWrap: { default: 'nowrap', [media.narrow]: 'wrap' },
  },
  main: {
    flexGrow: 1,
    flexShrink: 1,
    flexBasis: { default: 0, [media.narrow]: '100%' },
    minWidth: 0,
    display: 'grid',
    gap: space.xxs,
  },
  title: {
    color: { default: colors.fg, ':hover': colors.info },
    fontWeight: 500,
    fontSize: text.body,
    lineHeight: 1.35,
    textDecoration: 'none',
    overflowWrap: 'anywhere',
  },
  number: {
    fontFamily: font.mono,
    fontSize: text.md,
    color: colors.faint,
    fontVariantNumeric: 'tabular-nums',
    marginInlineEnd: space.sm,
  },
  meta: {
    display: 'flex',
    alignItems: 'center',
    gap: space.sm,
    rowGap: space.xxs,
    flexWrap: 'wrap',
    color: colors.muted,
    fontSize: text.md,
    minWidth: 0,
  },
  author: { display: 'inline-flex', alignItems: 'center', gap: space.xs, color: colors.fg },
  sep: { color: colors.line2 },
  mono: { fontFamily: font.mono, fontSize: text.sm, fontVariantNumeric: 'tabular-nums' },
  faint: { color: colors.faint },
  label: (hex: string) => ({
    paddingBlock: 0,
    paddingInline: space.xs,
    borderRadius: radius.xs,
    fontFamily: font.mono,
    fontSize: text.xxs,
    lineHeight: 1.7,
    color: `color-mix(in srgb, #${hex} 70%, ${colors.fg})`,
    backgroundColor: `color-mix(in srgb, #${hex} 14%, transparent)`,
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: `color-mix(in srgb, #${hex} 35%, transparent)`,
  }),
  diff: {
    display: 'grid',
    justifyItems: { default: 'end', [media.narrow]: 'start' },
    gap: space.xxs,
    whiteSpace: 'nowrap',
    width: { default: 96, [media.narrow]: 'auto' },
    flexShrink: 0,
  },
  lines: { fontFamily: font.mono, fontSize: text.sm, fontVariantNumeric: 'tabular-nums' },
  plus: { color: colors.ok },
  minus: { color: colors.bad },
  blocks: { display: 'flex', alignItems: 'center', gap: 2 },
  block: { width: 7, height: 7, backgroundColor: colors.line2 },
  blockPlus: { backgroundColor: colors.ok },
  blockMinus: { backgroundColor: colors.bad },
  size: { marginInlineStart: space.xs, fontFamily: font.mono, fontSize: text.xxs, fontWeight: 600, color: colors.faint },
  review: {
    display: 'grid',
    justifyItems: 'end',
    gap: space.xxs,
    width: { default: 290, [media.narrow]: 'auto' },
    flexShrink: 0,
    marginInlineStart: { default: 0, [media.narrow]: 'auto' },
  },
  place: {
    fontFamily: font.mono,
    fontSize: text.xxs,
    color: colors.faint,
    fontVariantNumeric: 'tabular-nums',
    whiteSpace: 'nowrap',
  },
  when: { fontFamily: font.mono, fontSize: text.xxs, color: colors.faint, whiteSpace: 'nowrap' },
  // the review's outcome as one joined tag: findings | QA
  result: {
    display: 'inline-flex',
    alignItems: 'stretch',
    borderRadius: radius.xs,
    overflow: 'hidden',
    textDecoration: 'none',
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: { default: colors.line2, ':hover': colors.faint },
    transitionProperty: 'border-color, opacity',
    transitionDuration: '120ms',
    opacity: { default: 1, ':active': 0.85 },
  },
  chip: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: space.xxs,
    paddingBlock: space.xxxs,
    paddingInline: space.xs,
    fontFamily: font.mono,
    fontSize: text.xxs,
    fontWeight: 500,
    letterSpacing: '.05em',
    textTransform: 'uppercase',
    whiteSpace: 'nowrap',
  },
  chipSplit: { borderLeftWidth: 1, borderLeftStyle: 'solid', borderLeftColor: colors.line2 },
  ok: { backgroundColor: colors.okSoft, color: colors.ok },
  warn: { backgroundColor: colors.warnSoft, color: colors.warn },
  bad: { backgroundColor: colors.badSoft, color: colors.bad },
  idle: { backgroundColor: colors.idleSoft, color: colors.muted },
  newCommits: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: space.xxs,
    paddingBlock: space.xxxs,
    paddingInline: space.xs,
    borderRadius: radius.xs,
    fontFamily: font.mono,
    fontSize: text.xxs,
    fontWeight: 500,
    letterSpacing: '.05em',
    textTransform: 'uppercase',
    whiteSpace: 'nowrap',
    color: colors.warn,
    borderWidth: 1,
    borderStyle: 'dashed',
    borderColor: `color-mix(in srgb, ${colors.warn} 55%, transparent)`,
  },
});

type Outcome = 'blocking' | 'findings' | 'clean' | 'reviewing' | 'failed' | 'unreviewed' | 'draft';

const BUSY = new Set(['queued', 'working', 'waiting']);

function outcomeOf(p: Pull): Outcome {
  const r = p.review;
  if (!r) return p.draft ? 'draft' : 'unreviewed';
  if (BUSY.has(r.status)) return 'reviewing';
  if (r.status !== 'done') return 'failed';
  if (r.counts?.blocking) return 'blocking';
  if (r.counts && (r.counts.findings || r.counts.open)) return 'findings';
  return 'clean';
}

const LEGEND: [Outcome, string][] = [
  ['blocking', 'blocking'],
  ['findings', 'with findings'],
  ['clean', 'clean'],
  ['reviewing', 'in review'],
  ['failed', 'review failed'],
  ['unreviewed', 'not reviewed'],
  ['draft', 'drafts'],
];

const OUTCOME_TONE: Record<Outcome, stylex.StyleXStyles | null> = {
  blocking: styles.toneBad,
  findings: styles.toneWarn,
  clean: styles.toneOk,
  reviewing: styles.toneInfo,
  failed: styles.toneBad,
  unreviewed: null,
  draft: styles.toneFaint,
};

export function PullRequests({ name, pulls }: { name: string; pulls: Pulls }) {
  const { github } = pulls;
  const [refreshing, refresh] = usePullsRefresh(name, github.at);
  const [query, setQuery] = useState('');
  const [sort, setSort] = useState<PullSort>('updated');
  const [filter, setFilter] = useState<PullFilter>('all');
  if (!github.ready && github.error === 'not set up')
    return (
      <Section title="Pull requests" icon="pr" id="pulls">
        <EmptyCard
          icon="github"
          title="Connect a GitHub App"
          text={`Add its App ID and private key on the Secrets page (companions/${name}/github-app-id.txt and github-app-key.pem). Every repository the App is installed on shows up here.`}
        />
      </Section>
    );
  const shown = arrange(pulls.items, query, sort, filter);
  const filters = FILTERS.map((f) => ({ ...f, count: arrange(pulls.items, query, sort, f.value).length }));
  const { mine, others } = grouped(shown, pulls.me);
  const where = github.accounts.length ? ` in ${github.accounts.join(', ')}` : '';
  return (
    <Section
      title="Pull requests"
      icon="pr"
      id="pulls"
      sub={
        github.error
          ? `GitHub didn't answer: ${github.error}`
          : `Open pull requests ${github.bot ? `${github.bot}[bot]` : 'the App'} can see${where}${github.at ? ` · checked ${ago(github.at)}` : ''}`
      }
      right={<Button label="Refresh" icon="refresh" small iconOnly busy={refreshing} onClick={refresh} />}
    >
      <Batch items={pulls.items} />
      {pulls.items.length > 0 && <Health items={pulls.items} />}
      <div {...stylex.props(styles.toolbar)}>
        <div {...stylex.props(styles.search)}>
          <SearchInput label="Search pull requests, or label:bug" value={query} onChange={setQuery} />
        </div>
        <Segments label="Filter pull requests" value={filter} options={filters} onChange={setFilter} />
        <PickMenu label="Sort" icon="sort" value={sort} options={SORTS} onChange={setSort} />
      </div>
      <Card>
        {shown.length ? (
          <>
            <Group title="Authored" icon="edit" items={mine} name={name} />
            <Group title="Others" icon="agents" items={others} name={name} />
          </>
        ) : (
          <Empty
            icon="pr"
            title={pulls.items.length ? 'Nothing matches' : refreshing ? 'Looking…' : 'No open pull requests'}
            text={
              pulls.items.length
                ? 'Try other words or another filter.'
                : 'New pull requests in the repositories the App can see show up here.'
            }
          />
        )}
      </Card>
    </Section>
  );
}

/** How many open pull requests are clean, have findings, block, or wait for a review: a strip of counts over one bar. */
function Health({ items }: { items: Pull[] }) {
  const count = new Map<Outcome, number>();
  for (const p of items) count.set(outcomeOf(p), (count.get(outcomeOf(p)) ?? 0) + 1);
  const parts = LEGEND.filter(([key]) => count.get(key));
  return (
    <div {...stylex.props(styles.health)}>
      <div {...stylex.props(styles.cells)}>
        <div {...stylex.props(styles.cell)}>
          <span {...stylex.props(styles.cellValue)}>
            <Num value={items.length} />
          </span>
          <span {...stylex.props(styles.cellLabel)}>open</span>
        </div>
        {parts.map(([key, label]) => (
          <div key={key} {...stylex.props(styles.cell)}>
            <span {...stylex.props(styles.cellValue, OUTCOME_TONE[key])}>{count.get(key)}</span>
            <span {...stylex.props(styles.cellLabel)}>
              <i {...stylex.props(styles.swatch, styles[key])} />
              {label}
            </span>
          </div>
        ))}
      </div>
      <div {...stylex.props(styles.bar)} aria-hidden="true">
        {parts.map(([key]) => (
          <i key={key} {...stylex.props(styles.part(count.get(key) ?? 0), styles[key])} />
        ))}
      </div>
    </div>
  );
}

/** The reviews asked for together, one segment each, until the last one is done. */
function Batch({ items }: { items: Pull[] }) {
  const run = items.flatMap((p) =>
    p.review?.run ? [{ ...p.review.run, status: p.review.status, number: p.number, title: p.title }] : [],
  );
  if (run.length < 2) return null;
  run.sort((a, b) => a.n - b.n);
  const done = run.filter((r) => r.done).length;
  const all = done === run.length;
  const busy = (r: (typeof run)[number]) => !r.done && (r.status === 'working' || r.status === 'waiting');
  const current = run.find(busy);
  return (
    <section {...stylex.props(styles.batch, all && styles.batchDone)} aria-label="Review batch">
      <div {...stylex.props(styles.batchHead)}>
        <IconBox icon={all ? 'check' : 'pr'} tone={all ? 'ok' : 'info'} />
        <div {...stylex.props(styles.batchText)}>
          <div {...stylex.props(styles.batchTitle)}>
            {all ? `All ${run.length} reviews done` : `Reviewing ${plural(run.length, 'pull request')}`}
            {!all && <Blink />}
          </div>
          <div {...stylex.props(styles.batchSub)}>
            {all
              ? 'Each result is on its pull request below.'
              : current
                ? `Now: #${current.number} ${current.title}`
                : 'Waiting for a free slot'}
          </div>
        </div>
        <span {...stylex.props(styles.batchCount)}>
          <span {...stylex.props(styles.batchDoneNum)}>{done}</span> of {run.length} done
        </span>
      </div>
      <div {...stylex.props(styles.segments)}>
        {run.map((r) => (
          <div key={r.n} {...stylex.props(styles.segment)} title={`#${r.number} ${r.title}`}>
            <i {...stylex.props(styles.segBar, r.done && styles.segDone, busy(r) && styles.reviewing)} />
            <span {...stylex.props(styles.segLabel, busy(r) && styles.segLabelOn)}>#{r.number}</span>
          </div>
        ))}
      </div>
      {!all && <LiveLine />}
    </section>
  );
}

function Group({ title, icon, items, name }: { title: string; icon: string; items: Pull[]; name: string }) {
  const { shown, page, pages, setPage } = usePages(items, PAGE);
  if (!items.length) return null;
  return (
    <>
      <div {...stylex.props(styles.group)}>
        <Icon name={icon} size={14} />
        <span>{title}</span>
        <span {...stylex.props(styles.groupCount)}>{items.length}</span>
        <Spacer />
        <Pager page={page} pages={pages} setPage={setPage} />
      </div>
      {shown.map((p, i) => (
        <Appear key={p.id} i={i}>
          <PullRow p={p} name={name} />
        </Appear>
      ))}
    </>
  );
}

function PullRow({ p, name }: { p: Pull; name: string }) {
  const outcome = outcomeOf(p);
  const status = p.review?.status;
  return (
    <div
      {...stylex.props(styles.row, outcome === 'blocking' && styles.rowBad, status === 'waiting' && styles.rowWarn)}
      data-testid="pull"
    >
      <StateIcon p={p} />
      <div {...stylex.props(styles.body)}>
        <div {...stylex.props(styles.main)}>
          <a {...stylex.props(styles.title)} href={p.url} target="_blank" rel="noopener">
            <span {...stylex.props(styles.number)}>#{p.number}</span>
            {p.title}
          </a>
          <div {...stylex.props(styles.meta)}>
            <span {...stylex.props(styles.author)}>
              <Avatar name={p.author} src={p.avatar} size={18} />
              {p.author}
            </span>
            <span {...stylex.props(styles.sep)}>·</span>
            <span {...stylex.props(styles.mono)}>{p.repo}</span>
            <span {...stylex.props(styles.sep)}>·</span>
            <span {...stylex.props(styles.mono, styles.faint)}>updated {ago(Date.parse(p.updated) / 1000)}</span>
            {p.labels.map((l) => (
              <span key={l.name} {...stylex.props(styles.label(l.color))}>
                {l.name}
              </span>
            ))}
          </div>
        </div>
        <Diff p={p} />
        <div {...stylex.props(styles.review)}>
          <ReviewCell p={p} name={name} />
        </div>
      </div>
      {status === 'working' && <LiveLine />}
    </div>
  );
}

const CI_MARK: Record<Exclude<Ci, ''>, [string, string]> = {
  passing: ['check', 'Checks passing'],
  failing: ['x', 'Checks failing'],
  running: ['clock', 'Checks running'],
};

/** Open or draft, with the checks' state pinned to its corner. */
function StateIcon({ p }: { p: Pull }) {
  const ci = p.ci ? CI_MARK[p.ci] : null;
  return (
    <span {...stylex.props(styles.stateIcon, p.draft && styles.drafted)} title={p.draft ? 'Draft' : 'Open'}>
      <Icon name={p.draft ? 'draft' : 'pr'} size={17} />
      {p.ci && ci && (
        <span {...stylex.props(styles.ci, styles[p.ci])} title={ci[1]} aria-label={ci[1]}>
          <Icon name={ci[0]} size={10} />
        </span>
      )}
    </span>
  );
}

const sizeOf = (n: number) => (n < 10 ? 'XS' : n < 50 ? 'S' : n < 250 ? 'M' : n < 1000 ? 'L' : 'XL');

/** +added −removed, and five blocks split green / red like GitHub's. */
function Diff({ p }: { p: Pull }) {
  const total = p.additions + p.deletions;
  const green = total ? Math.round((5 * p.additions) / total) : 0;
  return (
    <div {...stylex.props(styles.diff)} title={`${total.toLocaleString()} lines changed`}>
      <span {...stylex.props(styles.lines)}>
        <span {...stylex.props(styles.plus)}>+{p.additions.toLocaleString()}</span>{' '}
        <span {...stylex.props(styles.minus)}>−{p.deletions.toLocaleString()}</span>
      </span>
      <span {...stylex.props(styles.blocks)}>
        {[0, 1, 2, 3, 4].map((i) => (
          <i key={i} {...stylex.props(styles.block, total > 0 && (i < green ? styles.blockPlus : styles.blockMinus))} />
        ))}
        <span {...stylex.props(styles.size)}>{sizeOf(total)}</span>
      </span>
    </div>
  );
}

function ReviewCell({ p, name }: { p: Pull; name: string }) {
  const act = useAct();
  const r = p.review;
  // the review task shown at click time; "Starting…" until a newer one is queued or running
  const [clickedOver, setClickedOver] = useState<string | null>(null);
  const starting = clickedOver !== null && r?.status !== 'queued' && (r?.task ?? '') === clickedOver;
  useCompanionPoll(name, starting, () => {
    setClickedOver(null);
  });
  const start = async () => {
    const before = r?.task ?? '';
    setClickedOver(before);
    if (!(await act(`/api/companions/${name}/review`, { pr: p.id }, { quiet: true }))) setClickedOver(null);
  };
  if (starting)
    return (
      <Pill tone="info" dot>
        Starting…
      </Pill>
    );
  const again = (label: string) => <Button label={label} icon="refresh" small iconOnly variant="quiet" onClick={start} />;
  if (!r) return <Button label="Review" icon="eye" small variant="primary" onClick={start} />;
  const place = r.run && !r.run.done && <span {...stylex.props(styles.place)}>{`${r.run.n} of ${r.run.of}`}</span>;
  if (r.status === 'queued')
    return (
      <Inline gap="xs" nowrap>
        <Pill tone="idle">
          <Icon name="clock" size={12} />
          Queued
        </Pill>
        {place}
      </Inline>
    );
  if (r.status === 'working' || r.status === 'waiting')
    return (
      <Inline gap="xs" nowrap>
        <Pill tone={r.status === 'waiting' ? 'warn' : 'info'} dot>
          {r.status === 'waiting' ? 'Waiting on you' : 'Reviewing'}
        </Pill>
        {place}
        {r.t3 && <LinkButton label="Open the review chat" icon="ext" small iconOnly variant="quiet" to={r.t3} />}
      </Inline>
    );
  if (r.status !== 'done')
    return (
      <Inline gap="xs" nowrap>
        <Pill tone="bad">
          <Icon name="alert" size={12} />
          {r.status === 'failed' ? 'Review failed' : 'Stopped'}
        </Pill>
        {again('Retry')}
      </Inline>
    );
  const reviewed = Date.parse(r.at);
  return (
    <>
      <Inline gap="xs" nowrap>
        <a {...stylex.props(styles.result)} href={r.url || p.url} target="_blank" rel="noopener" title={r.outcome}>
          <ResultChips r={r} />
        </a>
        {outdated(p) && (
          <span {...stylex.props(styles.newCommits)}>
            <Icon name="history" size={11} />
            new commits
          </span>
        )}
        {again(outdated(p) ? 'Review the new commits' : 'Review again')}
      </Inline>
      {reviewed > 0 && <span {...stylex.props(styles.when)}>reviewed {ago(reviewed / 1000)}</span>}
    </>
  );
}

type ChipTone = 'ok' | 'warn' | 'bad' | 'idle';

const QA_CHIP: Record<string, [ChipTone, string]> = {
  pass: ['ok', 'QA ✓'],
  fail: ['bad', 'QA ✗'],
  partial: ['warn', 'QA partial'],
};

function ResultChips({ r }: { r: PullReview }) {
  const c = r.counts;
  if (!c)
    return (
      <span {...stylex.props(styles.chip, styles.idle)}>
        <Icon name="check" size={12} />
        Reviewed
      </span>
    );
  const [tone, icon, label]: [ChipTone, string, string] = c.blocking
    ? ['bad', 'alert', `${c.blocking} blocking`]
    : c.findings
      ? ['warn', 'eye', plural(c.findings, 'finding')]
      : c.open
        ? ['warn', 'history', `${c.open} still open`]
        : ['ok', 'check', 'Clean'];
  const qa = QA_CHIP[c.qa];
  return (
    <>
      <span {...stylex.props(styles.chip, styles[tone])}>
        <Icon name={icon} size={12} />
        {label}
      </span>
      {qa && <span {...stylex.props(styles.chip, styles.chipSplit, styles[qa[0]])}>{qa[1]}</span>}
    </>
  );
}

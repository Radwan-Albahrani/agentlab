import * as stylex from '@stylexjs/stylex';
import { useState } from 'react';
import { Link, useLocation, useNavigate, useSearchParams } from 'react-router';
import { useCompanionPoll, usePullsRefresh } from '../../api/queries';
import type { Ci, Pull, PullReview, Pulls } from '../../api/types';
import { resumesLabel, slackPlain } from '../../lib/companion';
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
import { Spacer } from '../../ui/layout';
import { PickMenu } from '../../ui/Menu';
import { Appear } from '../../ui/motion';
import { Empty, EmptyCard, Section } from '../../ui/page';
import { Pager } from '../../ui/Pager';
import { Blink, LiveLine } from './parts';
import { ReviewView } from './ReviewView';

const PAGE = 10;

const styles = stylex.create({
  toolbar: { display: 'flex', gap: space.sm, alignItems: 'center', flexWrap: 'wrap' },
  search: { flexGrow: '1', flexShrink: '1', flexBasis: '260px', minWidth: 0 },
  num: { fontFamily: font.mono, fontSize: text.xs, fontVariantNumeric: 'tabular-nums' },
  sep: { color: colors.faint },
  glyph: { display: 'inline-flex' },
  faint: { color: colors.faint },
  bad: { color: colors.bad },
  warn: { color: colors.warn },
  ok: { color: colors.ok },
  info: { color: colors.info },
  batch: {
    position: 'relative',
    display: 'flex',
    alignItems: 'center',
    gap: space.sm,
    minWidth: 0,
    paddingBlock: space.md,
    paddingInline: space.xxl,
    overflow: 'hidden',
    borderRadius: radius.xl,
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: colors.line,
    backgroundColor: colors.panel,
    fontSize: text.md,
    color: colors.muted,
    fontVariantNumeric: 'tabular-nums',
    flexWrap: { default: 'nowrap', [media.phone]: 'wrap' },
    whiteSpace: { default: 'nowrap', [media.phone]: 'normal' },
  },
  batchTitle: { color: colors.fg, fontWeight: 500 },
  batchNow: { flexShrink: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis' },
  track: { position: 'absolute', insetInline: 0, bottom: 0, height: 2, backgroundColor: colors.line },
  fill: (pct: number) => ({ width: `${pct}%` }),
  fillBusy: {
    display: 'block',
    height: '100%',
    backgroundColor: colors.info,
    transitionProperty: 'width',
    transitionDuration: '300ms',
  },
  fillDone: { backgroundColor: colors.ok },
  group: {
    display: 'flex',
    alignItems: 'center',
    gap: space.sm,
    minHeight: 40,
    paddingBlock: space.xxs,
    paddingInline: { default: space.xxl, [media.phone]: space.lg },
    borderTopWidth: 1,
    borderTopStyle: 'solid',
    borderTopColor: colors.line,
    fontSize: text.md,
    fontWeight: 600,
    color: colors.fg,
  },
  row: {
    // scrolled to, it stops below the sticky status line and tab bar instead of under them
    scrollMarginTop: 120,
    position: 'relative',
    display: 'flex',
    alignItems: 'center',
    flexWrap: { default: 'nowrap', [media.narrow]: 'wrap' },
    columnGap: space.md,
    rowGap: space.xs,
    paddingBlock: space.md,
    paddingInline: { default: space.xxl, [media.phone]: space.lg },
    minWidth: 0,
    borderTopWidth: 1,
    borderTopStyle: 'solid',
    borderTopColor: colors.line,
    backgroundColor: { default: 'transparent', ':hover': colors.hover },
    transitionProperty: 'background-color',
    transitionDuration: '120ms',
  },
  // GitHub's convention, which people already read at a glance: green = open and ready, grey = draft
  state: { alignSelf: 'flex-start', display: 'grid', placeItems: 'center', height: 20, flexShrink: 0, color: colors.ok },
  stateDraft: { color: colors.faint },
  titleDraft: { color: { default: colors.muted, ':hover': colors.info } },
  draftTag: {
    fontSize: text.xs,
    paddingInline: space.xs,
    borderRadius: radius.lg,
    backgroundColor: colors.idleSoft,
    color: colors.muted,
  },
  main: { flexGrow: 1, flexShrink: 1, flexBasis: 0, minWidth: 0, display: 'grid', gap: space.xxxs },
  line1: { fontSize: text.body, lineHeight: 1.45, overflowWrap: 'anywhere' },
  title: {
    color: { default: colors.fg, ':hover': colors.info },
    fontWeight: 500,
    textDecoration: 'none',
  },
  ci: { display: 'inline-flex', verticalAlign: -2, marginInlineStart: space.xs },
  ciDot: { width: 6, height: 6, marginBlock: 4, marginInline: 3, borderRadius: '50%', backgroundColor: colors.info },
  label: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: space.xxs,
    marginInlineStart: space.xs,
    paddingInline: space.xs,
    verticalAlign: 1,
    borderRadius: radius.md,
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: colors.line,
    fontSize: text.xxs,
    lineHeight: 1.6,
    color: colors.muted,
    maxWidth: '100%',
    overflow: 'hidden',
  },
  labelName: { minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' },
  swatch: (hex: string) => ({ width: 7, height: 7, borderRadius: '50%', backgroundColor: `#${hex}` }),
  meta: {
    display: 'flex',
    alignItems: 'baseline',
    flexWrap: 'wrap',
    columnGap: space.xs,
    fontSize: text.sm,
    color: colors.muted,
  },
  plus: { color: `color-mix(in srgb, ${colors.ok} 75%, ${colors.muted})` },
  minus: { color: `color-mix(in srgb, ${colors.bad} 75%, ${colors.muted})` },
  review: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: { default: 'flex-end', [media.narrow]: 'flex-start' },
    flexWrap: 'wrap',
    columnGap: space.xs,
    rowGap: space.xxs,
    flexShrink: 0,
    flexBasis: { default: 'auto', [media.narrow]: '100%' },
    minWidth: 0,
    maxWidth: '100%',
    minHeight: 28,
    paddingInlineStart: { default: 0, [media.narrow]: 26 },
    fontSize: text.sm,
    color: colors.muted,
  },
  nowrap: { whiteSpace: 'nowrap' },
  status: { display: 'inline-flex', alignItems: 'center', gap: space.xs, whiteSpace: 'nowrap' },
  result: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: space.xs,
    whiteSpace: 'nowrap',
    color: { default: colors.fg, ':hover': colors.info },
    textDecoration: 'none',
  },
  // the "review again" button shows on row hover or keyboard focus (always on touch screens)
  again: {
    display: 'inline-flex',
    opacity: {
      default: 0,
      ':focus-within': 1,
      [stylex.when.ancestor(':hover')]: 1,
      [stylex.when.ancestor(':focus-within')]: 1,
      '@media (hover: none)': 1,
      [media.phone]: 1,
    },
    transitionProperty: 'opacity',
    transitionDuration: '120ms',
  },
});

const Sep = () => (
  <span {...stylex.props(styles.sep)} aria-hidden="true">
    ·
  </span>
);

export function PullRequests({ name, pulls }: { name: string; pulls: Pulls }) {
  const { github } = pulls;
  const [refreshing, refresh] = usePullsRefresh(name, github.at);
  const [query, setQuery] = useState('');
  const [sort, setSort] = useState<PullSort>('updated');
  // the filter and the open review live in the URL, so the Overview can link to "Blocking" and Back closes a review
  const [params] = useSearchParams();
  const asked = params.get('filter');
  const filter: PullFilter = FILTERS.some((f) => f.value === asked) ? (asked as PullFilter) : 'all';
  // navigate, not setParams: setParams drops the #pulls hash, and the page would fall back to the first tab
  const navigate = useNavigate();
  const { hash } = useLocation();
  const setParam = (key: string, value: string | null) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    const search = next.toString();
    void navigate(
      { search: search ? `?${search}` : '', hash: hash || '#pulls' },
      { replace: key === 'filter' || !value, preventScrollReset: true },
    );
  };
  const setFilter = (v: PullFilter) => {
    setParam('filter', v === 'all' ? null : v);
  };
  const open = pulls.items.find((p) => String(p.number) === params.get('pr') && p.id) ?? null;
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
  // one clickable count per outcome that has any (the selected one stays even at 0, so it can be left)
  const filters = FILTERS.map((f) => ({ ...f, count: arrange(pulls.items, query, sort, f.value).length })).filter(
    (f) => f.value === 'all' || f.value === filter || f.count > 0,
  );
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
      <ReviewView
        p={open}
        onClose={() => {
          setParam('pr', null);
        }}
      />
      <Batch items={pulls.items} />
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
            <Group title="Authored" items={mine} name={name} />
            <Group title="Others" items={others} name={name} />
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

/** The reviews asked for together: one line and a thin bar until the last one is done. */
function Batch({ items }: { items: Pull[] }) {
  const run = items.flatMap((p) =>
    p.review?.run
      ? [{ ...p.review.run, status: p.review.status, resumes: p.review.resumes_at, number: p.number, title: p.title }]
      : [],
  );
  if (run.length < 2) return null;
  run.sort((a, b) => a.n - b.n);
  const done = run.filter((r) => r.done).length;
  const all = done === run.length;
  const current = run.find((r) => !r.done && (r.status === 'working' || r.status === 'waiting'));
  const paused = run.filter((r) => !r.done && r.status === 'paused');
  const resumes = Math.max(0, ...paused.map((r) => r.resumes ?? 0));
  return (
    <section {...stylex.props(styles.batch)} aria-label="Review batch">
      {all ? (
        <span {...stylex.props(styles.glyph, styles.ok)}>
          <Icon name="check" size={14} />
        </span>
      ) : !current && paused.length ? (
        <span {...stylex.props(styles.glyph, styles.warn)}>
          <Icon name="clock" size={14} />
        </span>
      ) : (
        <Blink />
      )}
      <span {...stylex.props(styles.batchTitle)}>
        {all ? `All ${run.length} reviews done` : `Reviewing ${plural(run.length, 'pull request')}`}
      </span>
      <Sep />
      {all ? (
        <span {...stylex.props(styles.batchNow)}>each result is on its pull request below</span>
      ) : (
        <>
          <span>{`${done} of ${run.length} done`}</span>
          <Sep />
          {paused.length > 0 && (
            <>
              <span {...stylex.props(styles.warn)}>{`${paused.length} paused · ${resumesLabel(resumes)}`}</span>
              <Sep />
            </>
          )}
          <span {...stylex.props(styles.batchNow)} title={current?.title}>
            {current
              ? `now #${current.number} ${current.title}`
              : paused.length
                ? 'waiting for the usage limit to reset'
                : 'waiting for a free slot'}
          </span>
        </>
      )}
      <span {...stylex.props(styles.track)} aria-hidden="true">
        <i {...stylex.props(styles.fillBusy, all && styles.fillDone, styles.fill((100 * done) / run.length))} />
      </span>
    </section>
  );
}

function Group({ title, items, name }: { title: string; items: Pull[]; name: string }) {
  const { shown, page, pages, setPage } = usePages(items, PAGE);
  if (!items.length) return null;
  return (
    <>
      <div {...stylex.props(styles.group)}>
        <span>{title}</span>
        <span {...stylex.props(styles.num, styles.faint)}>{items.length}</span>
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
  const [params] = useSearchParams();
  const review = new URLSearchParams(params);
  review.set('pr', String(p.number));
  return (
    <div {...stylex.props(stylex.defaultMarker(), styles.row)} data-testid="pull">
      <span {...stylex.props(styles.state, p.draft && styles.stateDraft)} title={p.draft ? 'Draft' : 'Open'}>
        <Icon name={p.draft ? 'draft' : 'pr'} size={16} />
      </span>
      <div {...stylex.props(styles.main)}>
        <div {...stylex.props(styles.line1)}>
          <Link
            {...stylex.props(styles.title, p.draft && styles.titleDraft)}
            to={{ search: `?${review.toString()}`, hash: '#pulls' }}
            preventScrollReset
          >
            {p.title}
          </Link>
          {p.ci && <Checks ci={p.ci} />}
          {p.labels.map((l) => (
            <span key={l.name} {...stylex.props(styles.label)}>
              <i {...stylex.props(styles.swatch(l.color))} />
              <span {...stylex.props(styles.labelName)}>{l.name}</span>
            </span>
          ))}
        </div>
        <div {...stylex.props(styles.meta)}>
          {p.draft && (
            <>
              <span {...stylex.props(styles.draftTag)}>Draft</span>
              <Sep />
            </>
          )}
          <span {...stylex.props(styles.num)}>#{p.number}</span>
          <Sep />
          <span>{p.author}</span>
          <Sep />
          <span>updated {ago(Date.parse(p.updated) / 1000)}</span>
          <Sep />
          <span {...stylex.props(styles.num)} title={`${(p.additions + p.deletions).toLocaleString()} lines changed`}>
            <span {...stylex.props(styles.plus)}>+{p.additions.toLocaleString()}</span>{' '}
            <span {...stylex.props(styles.minus)}>−{p.deletions.toLocaleString()}</span>
          </span>
        </div>
      </div>
      <div {...stylex.props(styles.review)}>
        <ReviewCell p={p} name={name} />
      </div>
      {p.review?.status === 'working' && <LiveLine />}
    </div>
  );
}

const CI_MARK: Record<Exclude<Ci, ''>, [string, string, stylex.StyleXStyles]> = {
  passing: ['check', 'Checks passing', styles.ok],
  failing: ['x', 'Checks failing', styles.bad],
  running: ['', 'Checks running', styles.info],
};

/** The checks' state as a tiny mark after the title, like GitHub's. */
function Checks({ ci }: { ci: Exclude<Ci, ''> }) {
  const [icon, label, tone] = CI_MARK[ci];
  return (
    <span {...stylex.props(styles.ci, tone)} title={label} aria-label={label}>
      {icon ? <Icon name={icon} size={14} /> : <i {...stylex.props(styles.ciDot)} />}
    </span>
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
      <span {...stylex.props(styles.status, styles.info)}>
        <Blink />
        <span>Starting…</span>
      </span>
    );
  if (!r) return <Button label="Review" icon="eye" small onClick={start} />;
  const place = r.run && !r.run.done && (
    <>
      <Sep />
      <span {...stylex.props(styles.num, styles.faint, styles.nowrap)}>{`${r.run.n} of ${r.run.of}`}</span>
    </>
  );
  if (r.status === 'queued')
    return (
      <>
        <span {...stylex.props(styles.status)}>
          <span {...stylex.props(styles.glyph, styles.faint)}>
            <Icon name="clock" size={14} />
          </span>
          Queued
        </span>
        {place}
      </>
    );
  if (r.status === 'paused')
    return (
      <>
        <span
          {...stylex.props(styles.status, styles.warn)}
          title="Stopped by the usage limit; T3 picks the review up again on its own"
        >
          <Icon name="clock" size={14} />
          {`Paused · ${resumesLabel(r.resumes_at)}`}
        </span>
        {place}
        {r.t3 && <LinkButton label="Open the review chat" icon="ext" small iconOnly variant="quiet" to={r.t3} />}
      </>
    );
  if (r.status === 'working' || r.status === 'waiting')
    return (
      <>
        {r.status === 'waiting' ? (
          <span {...stylex.props(styles.status, styles.warn)}>
            <Icon name="alert" size={14} />
            Waiting on you
          </span>
        ) : (
          <span {...stylex.props(styles.status, styles.info)}>
            <Blink />
            Reviewing…
          </span>
        )}
        {place}
        {r.t3 && <LinkButton label="Open the review chat" icon="ext" small iconOnly variant="quiet" to={r.t3} />}
      </>
    );
  if (r.status !== 'done')
    return (
      <>
        <span {...stylex.props(styles.status)}>
          <span {...stylex.props(styles.glyph, styles.bad)}>
            <Icon name="alert" size={14} />
          </span>
          {r.status === 'failed' ? 'Review failed' : 'Stopped'}
        </span>
        <Button label="Retry" icon="refresh" small iconOnly variant="quiet" onClick={start} />
      </>
    );
  const reviewed = Date.parse(r.at);
  const newer = outdated(p);
  return (
    <>
      <a {...stylex.props(styles.result)} href={r.url || p.url} target="_blank" rel="noopener" title={slackPlain(r.outcome)}>
        <Result r={r} />
      </a>
      {newer && (
        <>
          <Sep />
          <span {...stylex.props(styles.faint, styles.nowrap)} title="The pull request has commits the review hasn't seen">
            new commits
          </span>
        </>
      )}
      <span {...stylex.props(styles.again)}>
        <Button
          label={newer ? 'Review the new commits' : 'Review again'}
          hint={reviewed > 0 ? `Review again · last reviewed ${ago(reviewed / 1000)}` : undefined}
          icon="refresh"
          small
          iconOnly
          variant="quiet"
          onClick={start}
        />
      </span>
    </>
  );
}

const QA: Record<string, [string, stylex.StyleXStyles]> = {
  pass: ['QA ✓', styles.ok],
  fail: ['QA ✗', styles.bad],
  partial: ['QA partial', styles.warn],
};

/** The review's outcome in plain words: its worst finding, then QA. */
function Result({ r }: { r: PullReview }) {
  const c = r.counts;
  const [tone, icon, label]: [stylex.StyleXStyles, string, string] = !c
    ? [styles.faint, 'check', 'Reviewed']
    : c.blocking
      ? [styles.bad, 'alert', `${c.blocking} blocking`]
      : c.findings
        ? [styles.warn, 'eye', plural(c.findings, 'finding')]
        : c.open
          ? [styles.warn, 'history', `${c.open} still open`]
          : [styles.ok, 'check', 'Clean'];
  const qa = c ? QA[c.qa] : undefined;
  return (
    <>
      <span {...stylex.props(styles.glyph, tone)}>
        <Icon name={icon} size={14} />
      </span>
      <span {...stylex.props(tone)}>{label}</span>
      {qa && (
        <>
          <Sep />
          <span {...stylex.props(qa[1])}>{qa[0]}</span>
        </>
      )}
    </>
  );
}

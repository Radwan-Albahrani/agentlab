import * as stylex from '@stylexjs/stylex';
import { useState } from 'react';
import { useCompanionPoll, usePullsRefresh } from '../../api/queries';
import type { Ci, Pull, PullReview, Pulls } from '../../api/types';
import { usePages } from '../../lib/usePages';
import { ago, plural } from '../../lib/format';
import { arrange, FILTERS, grouped, outdated, type PullFilter, type PullSort, SORTS } from '../../lib/pulls';
import { colors, font, media, radius, space, text } from '../../theme/tokens.stylex';
import { Button, LinkButton } from '../../ui/Button';
import { Card } from '../../ui/Card';
import { useAct } from '../../ui/feedback';
import { Icon } from '../../ui/Icon';
import { SearchInput } from '../../ui/inputs';
import { Inline, Spacer } from '../../ui/layout';
import { PickMenu } from '../../ui/Menu';
import { Empty, EmptyCard, Section } from '../../ui/page';
import { Pager } from '../../ui/Pager';
import { Pill, Tag, type Tone } from '../../ui/status';
import { Text } from '../../ui/text';

const PAGE = 10;

const styles = stylex.create({
  toolbar: { display: 'flex', gap: space.sm, alignItems: 'center', flexWrap: 'wrap', marginBottom: space.lg },
  search: { flexGrow: '1', flexShrink: '1', flexBasis: '260px', minWidth: 0 },
  group: {
    display: 'flex',
    alignItems: 'center',
    gap: space.sm,
    paddingBlock: space.md,
    paddingInline: space.xxl,
    color: colors.muted,
    fontSize: text.md,
    fontWeight: 600,
    borderTopWidth: { default: 1, ':first-child': 0 },
    borderTopStyle: 'solid',
    borderTopColor: colors.line,
    backgroundColor: colors.sunk,
  },
  row: {
    display: 'flex',
    alignItems: 'center',
    gap: space.lg,
    paddingBlock: space.lg,
    paddingInline: space.xxl,
    minWidth: 0,
    borderTopWidth: 1,
    borderTopStyle: 'solid',
    borderTopColor: colors.line,
    flexWrap: { default: 'nowrap', [media.phone]: 'wrap' },
  },
  state: { display: 'inline-flex', alignSelf: 'flex-start', paddingTop: 2 },
  open: { color: colors.ok },
  draft: { color: colors.faint },
  main: { flex: '1', minWidth: 0, display: 'grid', gap: space.xs },
  title: {
    color: { default: colors.fg, ':hover': colors.accent },
    fontWeight: 600,
    fontSize: text.body,
    textDecoration: 'none',
    overflowWrap: 'anywhere',
  },
  number: { color: colors.muted, fontWeight: 500, marginInlineEnd: space.sm },
  meta: {
    display: 'flex',
    alignItems: 'center',
    gap: space.sm,
    flexWrap: 'wrap',
    color: colors.muted,
    fontSize: text.md,
    minWidth: 0,
  },
  avatar: { width: 18, height: 18, borderRadius: radius.pill, objectFit: 'cover' },
  label: (hex: string) => ({
    paddingInline: space.sm,
    borderRadius: radius.xs,
    fontSize: text.xs,
    fontWeight: 600,
    lineHeight: 1.7,
    color: `color-mix(in srgb, #${hex} 72%, ${colors.fg})`,
    backgroundColor: `color-mix(in srgb, #${hex} 16%, transparent)`,
  }),
  side: { display: 'grid', justifyItems: 'end', gap: space.xs, whiteSpace: 'nowrap' },
  size: { fontFamily: font.mono, fontSize: text.md },
  plus: { color: colors.ok },
  minus: { color: colors.bad },
  when: { color: colors.faint, fontSize: text.sm },
  review: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'flex-end',
    gap: space.xs,
    width: 260,
    flexShrink: 0,
    flexWrap: 'wrap',
  },
  result: { display: 'inline-flex', gap: space.xs, alignItems: 'center', opacity: { default: 1, ':hover': 0.8 } },
  ci: { display: 'inline-flex', verticalAlign: 'middle', marginInlineStart: space.sm },
  passing: { color: colors.ok },
  failing: { color: colors.bad },
  running: { color: colors.warn },
});

/** The open pull requests a companion's GitHub App can see, mine first, each with a Review button that sends the
 * companion's agent to review and QA it (the result is posted on the PR). */
export function PullRequests({ name, pulls }: { name: string; pulls: Pulls }) {
  const { github } = pulls;
  const [refreshing, refresh] = usePullsRefresh(name, github.at);
  const [query, setQuery] = useState('');
  const [sort, setSort] = useState<PullSort>('updated');
  const [filter, setFilter] = useState<PullFilter>('all');
  if (!github.ready && github.error === 'not set up')
    return (
      <Section title="Pull requests" id="pulls">
        <EmptyCard
          icon="github"
          title="Connect a GitHub App"
          text={`Add its App ID and private key on the Secrets page (companions/${name}/github-app-id.txt and github-app-key.pem). Every repository the App is installed on shows up here.`}
        />
      </Section>
    );
  const shown = arrange(pulls.items, query, sort, filter);
  const { mine, others } = grouped(shown, pulls.me);
  const where = github.accounts.length ? ` in ${github.accounts.join(', ')}` : '';
  return (
    <Section
      title="Pull requests"
      id="pulls"
      sub={
        github.error
          ? `GitHub didn't answer: ${github.error}`
          : `Open pull requests ${github.bot ? `${github.bot}[bot]` : 'the App'} can see${where}${github.at ? ` · checked ${ago(github.at)}` : ''}`
      }
      right={<Button label="Refresh" icon="refresh" small iconOnly busy={refreshing} onClick={refresh} />}
    >
      <div {...stylex.props(styles.toolbar)}>
        <div {...stylex.props(styles.search)}>
          <SearchInput label="Search pull requests, or label:bug" value={query} onChange={setQuery} />
        </div>
        <PickMenu label="Sort" icon="sort" value={sort} options={SORTS} onChange={setSort} />
        <PickMenu label="Filters" icon="filter" value={filter} options={FILTERS} onChange={setFilter} />
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
            text={pulls.items.length ? 'Try other words or another filter.' : undefined}
          />
        )}
      </Card>
    </Section>
  );
}

function Group({ title, icon, items, name }: { title: string; icon: string; items: Pull[]; name: string }) {
  const { shown, page, pages, setPage } = usePages(items, PAGE);
  if (!items.length) return null;
  return (
    <>
      <div {...stylex.props(styles.group)}>
        <Icon name={icon} size={16} />
        <span>{title}</span>
        <Text tone="faint" size="xs">
          {items.length}
        </Text>
        <Spacer />
        <Pager page={page} pages={pages} setPage={setPage} />
      </div>
      {shown.map((p) => (
        <PullRow key={p.id} p={p} name={name} />
      ))}
    </>
  );
}

function PullRow({ p, name }: { p: Pull; name: string }) {
  return (
    <div {...stylex.props(styles.row)} data-testid="pull">
      <span {...stylex.props(styles.state, p.draft ? styles.draft : styles.open)} title={p.draft ? 'Draft' : 'Open'}>
        <Icon name={p.draft ? 'draft' : 'pr'} size={18} />
      </span>
      <div {...stylex.props(styles.main)}>
        <div>
          <a {...stylex.props(styles.title)} href={p.url} target="_blank" rel="noopener">
            <span {...stylex.props(styles.number)}>#{p.number}</span>
            {p.title}
          </a>
          <CiMark ci={p.ci} />
        </div>
        <div {...stylex.props(styles.meta)}>
          {p.avatar && <img {...stylex.props(styles.avatar)} src={p.avatar} alt="" loading="lazy" />}
          <span>{p.author}</span>
          <span>{p.repo}</span>
          {p.labels.map((l) => (
            <span key={l.name} {...stylex.props(styles.label(l.color))}>
              {l.name}
            </span>
          ))}
        </div>
      </div>
      <div {...stylex.props(styles.side)}>
        <span {...stylex.props(styles.size)}>
          <span {...stylex.props(styles.plus)}>+{p.additions.toLocaleString()}</span>{' '}
          <span {...stylex.props(styles.minus)}>-{p.deletions.toLocaleString()}</span>
        </span>
        <span {...stylex.props(styles.when)}>{ago(Date.parse(p.updated) / 1000)}</span>
      </div>
      <div {...stylex.props(styles.review)}>
        <ReviewCell p={p} name={name} />
      </div>
    </div>
  );
}

const CI_MARK: Record<Exclude<Ci, ''>, [string, string]> = {
  passing: ['check', 'Checks passing'],
  failing: ['x', 'Checks failing'],
  running: ['clock', 'Checks running'],
};

function CiMark({ ci }: { ci: Ci }) {
  if (!ci) return null;
  const [icon, label] = CI_MARK[ci];
  return (
    <span {...stylex.props(styles.ci, styles[ci])} title={label} aria-label={label}>
      <Icon name={icon} size={15} />
    </span>
  );
}

/** Review it, or where its latest review is: queued, running (with its chat), or what it found. */
function ReviewCell({ p, name }: { p: Pull; name: string }) {
  const act = useAct();
  const r = p.review;
  // the review task shown when Review was clicked: "Starting…" until the companion has queued or started a new one
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
  if (r.status === 'queued') return <Pill tone="idle">Queued</Pill>;
  if (r.status === 'working' || r.status === 'waiting')
    return (
      <Inline gap="xs" nowrap>
        <Pill tone={r.status === 'waiting' ? 'warn' : 'info'} dot>
          {r.status === 'waiting' ? 'Waiting on you' : 'Reviewing'}
        </Pill>
        {r.t3 && <LinkButton label="Open the review chat" icon="ext" small iconOnly variant="quiet" to={r.t3} />}
      </Inline>
    );
  if (r.status !== 'done')
    return (
      <Inline gap="xs" nowrap>
        <Pill tone="bad">{r.status === 'failed' ? 'Review failed' : 'Stopped'}</Pill>
        {again('Retry')}
      </Inline>
    );
  return (
    <Inline gap="xs" nowrap>
      <a {...stylex.props(styles.result)} href={r.url || p.url} target="_blank" rel="noopener" title={r.outcome}>
        <ResultChips r={r} />
      </a>
      {outdated(p) && <Tag>new commits</Tag>}
      {again(outdated(p) ? 'Review the new commits' : 'Review again')}
    </Inline>
  );
}

const QA_CHIP: Record<string, [Tone, string]> = {
  pass: ['ok', 'QA ✓'],
  fail: ['bad', 'QA ✗'],
  partial: ['warn', 'QA partial'],
};

/** A finished review at a glance: what it found (blocking first) and how QA went; the sentence is the tooltip. */
function ResultChips({ r }: { r: PullReview }) {
  const c = r.counts;
  if (!c) return <Pill tone="idle">Reviewed</Pill>; // what it found is in the tooltip
  const [tone, label]: [Tone, string] = c.blocking
    ? ['bad', `${c.blocking} blocking`]
    : c.findings
      ? ['warn', plural(c.findings, 'finding')]
      : c.open
        ? ['warn', `${c.open} still open`]
        : ['ok', 'Clean'];
  const qa = QA_CHIP[c.qa];
  return (
    <>
      <Pill tone={tone}>{label}</Pill>
      {qa && <Pill tone={qa[0]}>{qa[1]}</Pill>}
    </>
  );
}

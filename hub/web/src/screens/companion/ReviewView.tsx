import * as stylex from '@stylexjs/stylex';
import type { Pull, ReviewDetail } from '../../api/types';
import { resumesLabel } from '../../lib/companion';
import { ago, plural } from '../../lib/format';
import { outcomeOf, outdated } from '../../lib/pulls';
import { colors, font, radius, space, text } from '../../theme/tokens.stylex';
import { LinkButton } from '../../ui/Button';
import { Dialog } from '../../ui/Dialog';
import { Icon } from '../../ui/Icon';

const styles = stylex.create({
  body: { display: 'grid', gap: space.xxl, minWidth: 0 },
  meta: { display: 'flex', flexWrap: 'wrap', columnGap: space.sm, rowGap: space.xxs, color: colors.muted, fontSize: text.md },
  num: { fontFamily: font.mono, fontVariantNumeric: 'tabular-nums' },
  plus: { color: colors.ok },
  minus: { color: colors.bad },
  verdict: {
    display: 'flex',
    alignItems: 'center',
    gap: space.md,
    paddingBlock: space.md,
    paddingInline: space.lg,
    borderRadius: radius.lg,
    backgroundColor: colors.sunk,
    fontWeight: 500,
    flexWrap: 'wrap',
  },
  verdictNote: { color: colors.faint, fontWeight: 400, fontSize: text.sm },
  actions: { display: 'flex', gap: space.sm, flexWrap: 'wrap' },
  heading: { margin: 0, fontSize: text.body, fontWeight: 600 },
  list: { display: 'grid' },
  finding: {
    display: 'grid',
    gap: space.xxs,
    paddingBlock: space.md,
    borderTopWidth: 1,
    borderTopStyle: 'solid',
    borderTopColor: colors.line,
    minWidth: 0,
  },
  findingHead: { display: 'flex', alignItems: 'baseline', gap: space.sm, flexWrap: 'wrap' },
  tag: { fontSize: text.xs, fontWeight: 500, paddingInline: space.sm, borderRadius: radius.lg, whiteSpace: 'nowrap' },
  tagBlocking: { backgroundColor: colors.badSoft, color: colors.bad },
  tagNote: { backgroundColor: colors.warnSoft, color: colors.warn },
  findingTitle: { fontWeight: 500, overflowWrap: 'anywhere' },
  where: {
    fontFamily: font.mono,
    fontSize: text.sm,
    color: { default: colors.info, ':hover': colors.fg },
    overflowWrap: 'anywhere',
  },
  excerpt: {
    margin: 0,
    color: colors.muted,
    fontSize: text.md,
    whiteSpace: 'pre-wrap',
    overflowWrap: 'anywhere',
    display: '-webkit-box',
    WebkitLineClamp: 4,
    WebkitBoxOrient: 'vertical',
    overflow: 'hidden',
  },
  qa: { whiteSpace: 'pre-wrap', margin: 0, color: colors.muted, fontSize: text.md, overflowWrap: 'anywhere' },
  ok: { color: colors.ok },
  warn: { color: colors.warn },
  bad: { color: colors.bad },
  info: { color: colors.info },
  faint: { color: colors.faint },
  section: { display: 'grid', gap: space.sm },
});

const QA_WORD: Record<string, [string, stylex.StyleXStyles]> = {
  pass: ['QA passed', styles.ok],
  fail: ['QA found problems', styles.bad],
  partial: ['QA partly verified', styles.warn],
  skipped: ['QA skipped: nothing runnable changed', styles.faint],
};

function Verdict({ p }: { p: Pull }) {
  const r = p.review;
  const o = outcomeOf(p);
  const c = r?.counts;
  const [icon, tone, words] =
    o === 'blocking'
      ? ['alert', styles.bad, `Changes requested · ${plural(c?.blocking ?? 0, 'blocking finding')}`]
      : o === 'findings'
        ? ['eye', styles.warn, plural((c?.findings ?? 0) || (c?.open ?? 0), 'finding')]
        : o === 'clean'
          ? ['check', styles.ok, 'Approved · no findings']
          : o === 'reviewing' && r?.status === 'paused'
            ? ['clock', styles.warn, `Paused for the usage limit · ${resumesLabel(r.resumes_at)}`]
            : o === 'reviewing'
              ? ['clock', styles.info, r?.status === 'queued' ? 'Queued for review' : 'Being reviewed now']
              : o === 'failed'
                ? ['alert', styles.bad, 'The review failed']
                : ['eye', styles.faint, p.draft ? 'Draft · not reviewed yet' : 'Not reviewed yet'];
  const reviewed = r?.at ? Date.parse(r.at) / 1000 : 0;
  return (
    <div {...stylex.props(styles.verdict)}>
      <span {...stylex.props(tone)}>
        <Icon name={icon} size={16} />
      </span>
      <span {...stylex.props(tone)}>{words}</span>
      {r?.status === 'done' && reviewed > 0 && (
        <span {...stylex.props(styles.verdictNote)}>
          reviewed {ago(reviewed)}
          {outdated(p) && ' · new commits since'}
        </span>
      )}
    </div>
  );
}

function Findings({ d }: { d: ReviewDetail }) {
  if (!d.findings.length) return null;
  return (
    <div {...stylex.props(styles.section)}>
      <h3 {...stylex.props(styles.heading)}>{plural(d.findings.length, 'finding')}</h3>
      <div {...stylex.props(styles.list)}>
        {d.findings.map((f, i) => (
          <div key={`${f.path}:${f.line ?? 0}:${i}`} {...stylex.props(styles.finding)}>
            <div {...stylex.props(styles.findingHead)}>
              <span {...stylex.props(styles.tag, f.severity === 'blocking' ? styles.tagBlocking : styles.tagNote)}>
                {f.severity === 'blocking' ? 'Blocking' : 'Non-blocking'}
              </span>
              <span {...stylex.props(styles.findingTitle)}>{f.title}</span>
            </div>
            {f.path &&
              (f.link ? (
                <a href={f.link} target="_blank" rel="noopener" {...stylex.props(styles.where)}>
                  {f.path}
                  {f.line ? `:${f.start_line ? `${f.start_line}-` : ''}${f.line}` : ''}
                </a>
              ) : (
                <span {...stylex.props(styles.where)}>{f.path}</span>
              ))}
            {f.body && <p {...stylex.props(styles.excerpt)}>{f.body}</p>}
          </div>
        ))}
      </div>
    </div>
  );
}

function Qa({ d }: { d: ReviewDetail }) {
  if (!d.qa.verdict) return null;
  const [word, tone] = QA_WORD[d.qa.verdict] ?? [`QA: ${d.qa.verdict}`, styles.faint];
  return (
    <div {...stylex.props(styles.section)}>
      <h3 {...stylex.props(styles.heading)}>
        <span {...stylex.props(tone)}>{word}</span>
      </h3>
      {d.qa.text && <p {...stylex.props(styles.qa)}>{d.qa.text}</p>}
    </div>
  );
}

/** A pull request's review in brief: the verdict, each finding with its place in the code, and QA. GitHub has the rest. */
export function ReviewView({ p, onClose }: { p: Pull | null; onClose: () => void }) {
  const d = p?.review?.detail;
  return (
    <Dialog open={!!p} onClose={onClose} wide title={p ? `#${p.number} ${p.title}` : ''}>
      {p && (
        <div {...stylex.props(styles.body)}>
          <div {...stylex.props(styles.meta)}>
            <span>{p.author}</span>
            <span>·</span>
            <span>{p.repo}</span>
            <span>·</span>
            <span {...stylex.props(styles.num)}>
              <span {...stylex.props(styles.plus)}>+{p.additions.toLocaleString()}</span>{' '}
              <span {...stylex.props(styles.minus)}>−{p.deletions.toLocaleString()}</span>
            </span>
            <span>·</span>
            <span>updated {ago(Date.parse(p.updated) / 1000)}</span>
          </div>
          <Verdict p={p} />
          {d ? (
            <>
              <Findings d={d} />
              <Qa d={d} />
            </>
          ) : (
            p.review?.status === 'done' && (
              <p {...stylex.props(styles.qa)}>{p.review.outcome || 'Reviewed.'} The full review is on GitHub.</p>
            )
          )}
          <div {...stylex.props(styles.actions)}>
            {(d?.review_url ?? p.review?.url) && (
              <LinkButton label="Open the review on GitHub" icon="ext" to={d?.review_url ?? p.review?.url ?? p.url} />
            )}
            {d?.qa.url && <LinkButton label="Open the QA report" icon="ext" to={d.qa.url} />}
            <LinkButton label="Open the pull request" icon="github" variant="quiet" to={p.url} />
          </div>
        </div>
      )}
    </Dialog>
  );
}

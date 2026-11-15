import * as stylex from '@stylexjs/stylex';
import { Link } from 'react-router';
import type { ReviewSummary } from '../api/types';
import { FILTERS, type Outcome } from '../lib/pulls';
import { hueTheme } from '../theme/hues';
import { agent, colors, font, media, radius, space, text } from '../theme/tokens.stylex';
import { Icon } from '../ui/Icon';

const blink = stylex.keyframes({ '50%': { opacity: 0.25 } });

const styles = stylex.create({
  panel: {
    display: 'grid',
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: colors.line,
    borderRadius: radius.xl,
    backgroundColor: colors.panel,
    overflow: 'hidden',
  },
  item: {
    display: 'grid',
    gap: space.md,
    paddingBlock: space.lg,
    paddingInline: { default: space.xxl, [media.phone]: space.lg },
    borderTopWidth: 1,
    borderTopStyle: 'solid',
    borderTopColor: colors.line,
    marginBlockStart: -1,
  },
  head: { display: 'flex', alignItems: 'center', gap: space.md, flexWrap: 'wrap' },
  swatch: { width: 10, height: 10, borderRadius: radius.xs, backgroundColor: agent.hue, flexShrink: 0 },
  name: { fontWeight: 600, color: { default: colors.fg, ':hover': colors.accent } },
  open: { color: colors.faint, fontSize: text.sm },
  num: { fontFamily: font.mono, fontVariantNumeric: 'tabular-nums' },
  all: { marginInlineStart: 'auto', display: 'inline-flex', alignItems: 'center', gap: space.xxs, fontSize: text.sm },
  allLink: { color: { default: colors.muted, ':hover': colors.fg } },
  batch: { display: 'grid', gap: space.xs },
  batchLine: { display: 'flex', alignItems: 'center', gap: space.sm, flexWrap: 'wrap', fontSize: text.md, minWidth: 0 },
  now: { color: colors.muted, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', minWidth: 0, flex: '1' },
  block: {
    width: 5,
    height: 12,
    backgroundColor: colors.info,
    animationName: blink,
    animationDuration: '1s',
    animationIterationCount: 'infinite',
  },
  track: { height: 3, borderRadius: radius.xs, backgroundColor: colors.sunk, overflow: 'hidden' },
  fill: (pct: number) => ({
    display: 'block',
    height: '100%',
    width: `${pct}%`,
    backgroundColor: colors.info,
    transition: 'width .4s',
  }),
  // each count is a way into the filtered list
  counts: { display: 'flex', flexWrap: 'wrap', gap: space.xs },
  count: {
    display: 'inline-flex',
    alignItems: 'baseline',
    gap: space.xs,
    paddingBlock: space.xxs,
    paddingInline: space.md,
    borderRadius: radius.lg,
    fontSize: text.md,
    backgroundColor: { default: colors.sunk, ':hover': colors.hover },
    color: colors.muted,
    transitionProperty: 'background-color',
    transitionDuration: '120ms',
  },
  dot: { width: 7, height: 7, borderRadius: '50%', alignSelf: 'center', backgroundColor: colors.faint },
  blocking: { backgroundColor: colors.bad },
  findings: { backgroundColor: colors.warn },
  clean: { backgroundColor: colors.ok },
  reviewing: { backgroundColor: colors.info },
  failed: { backgroundColor: colors.bad },
  unreviewed: {},
  draft: {},
});

const LABEL = new Map(FILTERS.map((f) => [f.value, f.label]));
const ORDER: Outcome[] = ['blocking', 'findings', 'clean', 'reviewing', 'failed', 'unreviewed', 'draft'];

function Item({ r }: { r: ReviewSummary }) {
  const base = `/agents/${r.profile}/${r.name}`;
  const b = r.batch;
  return (
    <div {...stylex.props(hueTheme(r.profile), styles.item)}>
      <div {...stylex.props(styles.head)}>
        <i {...stylex.props(styles.swatch)} />
        <Link to={`${base}#pulls`} {...stylex.props(styles.name)}>
          {r.display}
        </Link>
        <span {...stylex.props(styles.open)}>
          <span {...stylex.props(styles.num)}>{r.open}</span> open pull requests
        </span>
        <span {...stylex.props(styles.all)}>
          <Link to={`${base}#pulls`} {...stylex.props(styles.allLink)}>
            All
          </Link>
          <Icon name="arrow" size={14} />
        </span>
      </div>
      {b && (
        <div {...stylex.props(styles.batch)}>
          <div {...stylex.props(styles.batchLine)}>
            {b.done < b.of && <i {...stylex.props(styles.block)} />}
            <span>
              {b.done < b.of ? 'Reviewing' : 'Reviewed'} <span {...stylex.props(styles.num)}>{b.of}</span> ·{' '}
              <span {...stylex.props(styles.num)}>{b.done}</span> done
            </span>
            {b.now && (
              <span {...stylex.props(styles.now)}>
                · now #{b.now.number} {b.now.title}
              </span>
            )}
          </div>
          <div {...stylex.props(styles.track)}>
            <span {...stylex.props(styles.fill(Math.round((100 * b.done) / b.of)))} />
          </div>
        </div>
      )}
      <div {...stylex.props(styles.counts)}>
        {ORDER.filter((o) => r.counts[o]).map((o) => (
          <Link key={o} to={`${base}?filter=${o}#pulls`} {...stylex.props(styles.count)}>
            <i {...stylex.props(styles.dot, styles[o])} />
            {LABEL.get(o)}
            <span {...stylex.props(styles.num)}>{r.counts[o]}</span>
          </Link>
        ))}
      </div>
    </div>
  );
}

/** Each companion's PR reviews in one glance; every count opens the list filtered to it. */
export function Reviews({ reviews }: { reviews: ReviewSummary[] }) {
  return (
    <div {...stylex.props(styles.panel)}>
      {reviews.map((r) => (
        <Item key={r.name} r={r} />
      ))}
    </div>
  );
}

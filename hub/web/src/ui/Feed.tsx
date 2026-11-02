import * as stylex from '@stylexjs/stylex';
import type { Event } from '../api/types';
import { colors, space, text } from '../theme/tokens.stylex';
import { Card } from './Card';
import { Empty, Section } from './page';
import { When } from './When';
import { usePages } from '../lib/usePages';
import { Pager } from './Pager';

const styles = stylex.create({
  feed: { display: 'grid' },
  ev: {
    display: 'grid',
    gridTemplateColumns: '22px minmax(0, 1fr) auto',
    gap: space.md,
    paddingBlock: space.md,
    paddingInline: space.xxl,
    alignItems: 'start',
    borderTopWidth: { default: 1, ':first-child': 0 },
    borderTopStyle: 'solid',
    borderTopColor: colors.line,
  },
  dot: {
    width: 9,
    height: 9,
    borderRadius: '50%',
    marginTop: space.xs,
    marginInlineStart: space.xs,
    backgroundColor: colors.faint,
  },
  ok: { backgroundColor: colors.ok },
  bad: { backgroundColor: colors.bad },
  info: { backgroundColor: colors.accent },
  warn: { backgroundColor: colors.warn },
  body: { minWidth: 0 },
  src: { fontSize: text.xxs, color: colors.faint, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '.05em' },
  title: { fontWeight: 550, overflowWrap: 'anywhere' },
  detail: {
    color: colors.muted,
    fontSize: text.md,
    overflowWrap: 'anywhere',
    display: '-webkit-box',
    WebkitLineClamp: 2,
    WebkitBoxOrient: 'vertical',
    overflow: 'hidden',
  },
  when: { color: colors.faint, fontSize: text.xs, whiteSpace: 'nowrap' },
});

const TONE: Record<string, 'ok' | 'bad' | 'info' | 'warn'> = {
  sent: 'ok',
  files: 'ok',
  finished: 'ok',
  approved: 'ok',
  cleanup: 'ok',
  live: 'info',
  started: 'info',
  secret: 'info',
  restart: 'info',
  approval: 'warn',
  retry: 'warn',
  alert: 'warn',
  failed: 'bad',
};

interface FeedProps {
  events: Event[];
  showSource?: boolean;
  empty?: string;
}

/** Things that happened, newest first. */
export function Feed({ events, showSource = false, empty = 'Activity shows up here as it happens.' }: FeedProps) {
  if (!events.length) return <Empty title="Nothing yet" text={empty} icon="clock" />;
  return (
    <div {...stylex.props(styles.feed)}>
      {events.map((e, i) => {
        const tone = e.ok === false ? 'bad' : TONE[e.kind];
        return (
          <div key={`${e.at}-${i}`} {...stylex.props(styles.ev)}>
            <i {...stylex.props(styles.dot, tone && styles[tone])} />
            <div {...stylex.props(styles.body)}>
              {showSource && e.source && <div {...stylex.props(styles.src)}>{e.source}</div>}
              <div {...stylex.props(styles.title)}>
                {e.title}
                {e.to && (
                  <>
                    {' '}
                    → <b>{e.to}</b>
                  </>
                )}
              </div>
              {e.detail && <div {...stylex.props(styles.detail)}>{e.detail}</div>}
            </div>
            <div {...stylex.props(styles.when)}>
              <When t={e.at} />
            </div>
          </div>
        );
      })}
    </div>
  );
}

const PAGE = 8;

/** A titled section holding one feed, a page at a time. */
export function FeedSection({ title, sub, events, ...feed }: FeedProps & { title: string; sub?: string }) {
  const pages = usePages(events, PAGE);
  return (
    <Section title={title} sub={sub} right={<Pager {...pages} />}>
      <Card>
        <Feed events={pages.shown} {...feed} />
      </Card>
    </Section>
  );
}

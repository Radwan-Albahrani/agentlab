import * as stylex from '@stylexjs/stylex';
import type { Event } from '../api/types';
import { colors, font, space, text } from '../theme/tokens.stylex';
import { Card } from './Card';
import { Empty, Section } from './page';
import { When } from './When';
import { usePages } from '../lib/usePages';
import { Pager } from './Pager';

const styles = stylex.create({
  feed: { display: 'grid', paddingBlock: space.sm },
  // a timeline: each event hangs off one thin line running down the left
  ev: {
    position: 'relative',
    display: 'grid',
    gridTemplateColumns: '22px minmax(0, 1fr) auto',
    gap: space.md,
    paddingBlock: space.md,
    paddingInline: space.xxl,
    alignItems: 'start',
    backgroundColor: { default: 'transparent', ':hover': colors.hover },
    transitionProperty: 'background-color',
    transitionDuration: '160ms',
    '::before': {
      content: '""',
      position: 'absolute',
      insetInlineStart: 31,
      top: 0,
      bottom: 0,
      width: 1,
      backgroundColor: colors.line2,
    },
  },
  dot: {
    position: 'relative',
    zIndex: 1,
    width: 9,
    height: 9,
    marginTop: space.xs,
    marginInlineStart: 5,
    backgroundColor: colors.faint,
    boxShadow: `0 0 0 4px ${colors.panel}`,
  },
  ok: { backgroundColor: colors.ok },
  bad: { backgroundColor: colors.bad },
  info: { backgroundColor: colors.info },
  warn: { backgroundColor: colors.warn },
  body: { minWidth: 0 },
  src: { fontFamily: font.mono, fontSize: text.xxs, color: colors.faint, textTransform: 'uppercase', letterSpacing: '.08em' },
  title: { fontWeight: 500, overflowWrap: 'anywhere' },
  detail: {
    color: colors.muted,
    fontSize: text.md,
    overflowWrap: 'anywhere',
    display: '-webkit-box',
    WebkitLineClamp: 2,
    WebkitBoxOrient: 'vertical',
    overflow: 'hidden',
  },
  when: { fontFamily: font.mono, color: colors.faint, fontSize: text.xs, whiteSpace: 'nowrap' },
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

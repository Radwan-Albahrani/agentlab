import * as stylex from '@stylexjs/stylex';
import { useState } from 'react';
import type { Event } from '../../api/types';
import { SENT_FILTERS, dayLabel, delivery, sentTo, type SentTo } from '../../lib/companion';
import { usePages } from '../../lib/usePages';
import { colors, font, media, space, text } from '../../theme/tokens.stylex';
import { Card } from '../../ui/Card';
import { Segments } from '../../ui/controls';
import { Icon } from '../../ui/Icon';
import { Inline } from '../../ui/layout';
import { Empty, Section } from '../../ui/page';
import { Pager } from '../../ui/Pager';

const PAGE = 15;

const ICON = { person: 'chat', channel: 'slack', github: 'github' } as const;

const styles = stylex.create({
  day: {
    paddingBlock: space.sm,
    paddingInline: { default: space.xxl, [media.phone]: space.lg },
    backgroundColor: colors.sunk,
    color: colors.muted,
    fontSize: text.sm,
    fontWeight: 500,
  },
  // one line each: where it went, what it was, when
  row: {
    display: 'grid',
    gridTemplateColumns: { default: '18px minmax(0, 13rem) minmax(0, 1fr) auto', [media.phone]: '18px minmax(0, 1fr) auto' },
    gridTemplateAreas: { default: '"icon to what when"', [media.phone]: '"icon to when" ". what what"' },
    columnGap: space.md,
    rowGap: space.xxs,
    alignItems: 'baseline',
    paddingBlock: space.md,
    paddingInline: { default: space.xxl, [media.phone]: space.lg },
    borderTopWidth: 1,
    borderTopStyle: 'solid',
    borderTopColor: colors.line,
  },
  icon: {
    gridColumnEnd: 'icon',
    gridColumnStart: 'icon',
    gridRowEnd: 'icon',
    gridRowStart: 'icon',
    alignSelf: 'center',
    display: 'flex',
    color: colors.faint,
  },
  to: {
    gridColumnEnd: 'to',
    gridColumnStart: 'to',
    gridRowEnd: 'to',
    gridRowStart: 'to',
    fontWeight: 600,
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
    color: colors.fg,
  },
  toLink: { color: { default: colors.fg, ':hover': colors.accent } },
  what: {
    gridColumnEnd: 'what',
    gridColumnStart: 'what',
    gridRowEnd: 'what',
    gridRowStart: 'what',
    minWidth: 0,
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
  },
  note: { color: colors.muted },
  // a failure keeps its reason in view, over two lines if it needs them
  wrap: { whiteSpace: 'normal', display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical' },
  when: {
    gridColumnEnd: 'when',
    gridColumnStart: 'when',
    gridRowEnd: 'when',
    gridRowStart: 'when',
    fontFamily: font.mono,
    fontSize: text.sm,
    color: colors.faint,
    whiteSpace: 'nowrap',
  },
  bad: { color: colors.bad },
});

function Item({ e }: { e: Event }) {
  const d = delivery(e);
  const failed = e.ok === false;
  return (
    <div {...stylex.props(styles.row)} title={[d.to, d.what, d.note].filter(Boolean).join(' · ')}>
      <span {...stylex.props(styles.icon, failed && styles.bad)}>
        <Icon name={failed ? 'alert' : ICON[d.where]} size={16} />
      </span>
      {d.link ? (
        <a href={d.link} target="_blank" rel="noopener" {...stylex.props(styles.to, styles.toLink)}>
          {d.to}
        </a>
      ) : (
        <span {...stylex.props(styles.to)}>{d.to}</span>
      )}
      <span {...stylex.props(styles.what, failed && styles.wrap)}>
        {failed ? <span {...stylex.props(styles.bad)}>Not sent: {d.what}</span> : d.what}
        {d.note && <span {...stylex.props(styles.note, failed && styles.bad)}> · {d.note}</span>}
      </span>
      <span {...stylex.props(styles.when)}>
        {new Date(e.at * 1000).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}
      </span>
    </div>
  );
}

/** Everything the companion delivered, by day: who or where on the left, what it was in the middle. */
export function Delivered({ events: all }: { events: Event[] }) {
  const [to, setTo] = useState<SentTo>('all');
  const events = to === 'all' ? all : all.filter((e) => sentTo(e) === to);
  const pages = usePages(events, PAGE);
  const options = SENT_FILTERS.map((f) => ({
    ...f,
    count: f.value === 'all' ? all.length : all.filter((e) => sentTo(e) === f.value).length,
  }));
  const days: [string, Event[]][] = [];
  for (const e of pages.shown) {
    const label = dayLabel(e.at);
    const last = days.at(-1);
    if (last?.[0] === label) last[1].push(e);
    else days.push([label, [e]]);
  }
  return (
    <Section
      title="Sent"
      icon="send"
      sub="Who or where it sent to, and what."
      right={
        <Inline gap="md">
          <Segments
            label="Filter deliveries"
            value={to}
            options={options}
            onChange={(v) => {
              setTo(v);
              pages.setPage(0);
            }}
          />
          <Pager {...pages} />
        </Inline>
      }
    >
      <Card>
        {events.length ? (
          days.map(([label, list]) => (
            <section key={label} aria-label={label}>
              <div {...stylex.props(styles.day)}>{label}</div>
              {list.map((e, i) => (
                <Item key={`${e.at}-${i}`} e={e} />
              ))}
            </section>
          ))
        ) : (
          <Empty
            title={all.length ? 'Nothing here' : 'Nothing sent yet'}
            text={all.length ? 'Nothing it sent matches this filter.' : 'Messages, files and logins sent for you show up here.'}
            icon="send"
          />
        )}
      </Card>
    </Section>
  );
}

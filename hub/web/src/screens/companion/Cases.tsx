import * as stylex from '@stylexjs/stylex';
import { useState } from 'react';
import type { CaseItem, Task } from '../../api/types';
import {
  type CaseFilter,
  casesOf,
  filterCases,
  ITEM_PILL,
  itemHistory,
  lineOf,
  needsYou,
  isOpen,
  PHASE_PILL,
  routeLine,
  waitingOnYou,
} from '../../lib/companion';
import { plural } from '../../lib/format';
import { usePages } from '../../lib/usePages';
import { colors, font, media, radius, space, text } from '../../theme/tokens.stylex';
import { LinkButton } from '../../ui/Button';
import { Segments } from '../../ui/controls';
import { Expandable } from '../../ui/Expandable';
import { Icon } from '../../ui/Icon';
import { Inline } from '../../ui/layout';
import { Empty, Section } from '../../ui/page';
import { Pager } from '../../ui/Pager';
import { Badge, Pill } from '../../ui/status';
import { When } from '../../ui/When';
import { SlackText } from './parts';

const PAGE = 10;

const styles = stylex.create({
  list: { display: 'grid', gap: space.md },
  summary: { display: 'grid', gridTemplateColumns: 'auto minmax(0, 1fr) auto', alignItems: 'center', gap: space.lg },
  who: { display: 'grid', gap: space.xxxs, minWidth: 0 },
  name: { fontWeight: 600, display: 'flex', alignItems: 'center', gap: space.sm },
  ask: { color: colors.muted, fontSize: text.md, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' },
  side: { display: 'grid', justifyItems: 'end', gap: space.xxs, color: colors.faint, fontSize: text.sm },
  pills: { display: 'flex', gap: space.xs, flexWrap: 'wrap', justifyContent: 'flex-end' },
  body: { display: 'grid', gap: space.lg },
  // what waits on the owner, on top: decided in Slack, where the cards are
  waiting: {
    display: 'grid',
    gap: space.sm,
    padding: space.lg,
    borderRadius: radius.sm,
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: colors.line2,
    backgroundColor: colors.sunk,
  },
  waitingHead: { display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: space.md, flexWrap: 'wrap' },
  waitingTitle: { fontWeight: 600, display: 'flex', alignItems: 'center', gap: space.sm },
  waitingList: { margin: 0, paddingInlineStart: space.xl, display: 'grid', gap: space.xxs, fontSize: text.md },
  convo: { display: 'grid', gap: space.md },
  msg: {
    display: 'grid',
    gap: space.xxs,
    maxWidth: { default: '78%', [media.phone]: '100%' },
    paddingBlock: space.md,
    paddingInline: space.lg,
    borderRadius: radius.sm,
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: colors.line,
    backgroundColor: colors.panel,
  },
  theirs: { justifySelf: 'start' },
  ours: { justifySelf: 'end', backgroundColor: colors.raised },
  // between the owner and the companion: never seen by the colleague
  private: { justifySelf: 'end', backgroundColor: colors.sunk, borderStyle: 'dashed', borderColor: colors.line2 },
  head: { display: 'flex', alignItems: 'center', gap: space.sm, flexWrap: 'wrap', fontSize: text.sm, color: colors.muted },
  from: { fontWeight: 600, color: colors.fg },
  text: { whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', lineHeight: 1.5, fontSize: text.md },
  note: { fontSize: text.sm, color: colors.muted, overflowWrap: 'anywhere' },
  // a decision or a change (approval, login, edit, poll change): a line across, its state on the right
  event: {
    display: 'grid',
    gridTemplateColumns: { default: 'auto minmax(0, 1fr) auto', [media.phone]: 'auto minmax(0, 1fr)' },
    alignItems: 'start',
    gap: space.sm,
    paddingBlock: space.sm,
    paddingInline: space.md,
    borderRadius: radius.sm,
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: colors.line,
    fontSize: text.md,
  },
  eventText: { display: 'grid', gap: space.xxxs, minWidth: 0 },
  // on a phone the state drops under the text instead of squeezing it
  eventState: { gridColumn: { default: 'auto', [media.phone]: '2' } },
  eventIcon: { color: colors.muted, paddingTop: space.xxxs },
  tag: {
    fontFamily: font.mono,
    fontSize: text.xxs,
    paddingInline: space.xs,
    borderRadius: radius.xs,
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: colors.line2,
    color: colors.muted,
  },
  foot: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: space.sm, flexWrap: 'wrap' },
  route: { display: 'flex', alignItems: 'center', gap: space.xs, color: colors.faint, fontSize: text.sm, minWidth: 0 },
  links: { display: 'flex', justifyContent: 'flex-end', gap: space.sm, flexWrap: 'wrap', marginInlineStart: 'auto' },
});

const lastAt = (t: Task) => t.items.at(-1)?.at ?? t.startedAt;

const firstAsk = (t: Task) => t.items.find((i) => i.kind === 'in' && !i.private)?.text ?? t.title;

/** The item's state, with how it got there on hover; nothing for a message that simply went out. */
function State({ it }: { it: CaseItem }) {
  if ((it.kind === 'message' || it.kind === 'final') && it.state === 'sent') return null;
  if (it.kind === 'in') return null;
  const [label, tone] = ITEM_PILL[it.state];
  return (
    <span title={itemHistory(it)}>
      <Pill tone={tone} dot={it.state === 'awaiting_owner'}>
        {label}
      </Pill>
    </span>
  );
}

const DECISION: Record<string, { icon: string; what: (it: CaseItem) => string }> = {
  approval: { icon: 'alert', what: (it) => `Approval: ${it.action || it.text || ''}` },
  credential: { icon: 'key', what: (it) => `Login to DM: ${it.text || ''}` },
  edit: { icon: 'edit', what: (it) => `Edit of a message${it.label ? ` to ${it.label}` : ''}` },
  poll_change: { icon: 'poll', what: () => 'Poll change' },
  review: { icon: 'eye', what: (it) => `Sent to PR review: ${it.text || ''}` },
};

function Item({ it, who, me }: { it: CaseItem; who: string; me: string }) {
  const line = lineOf(it, who, me);
  if (!line || it.state === 'silent') {
    const d = DECISION[it.kind] ?? { icon: 'check', what: () => `Nothing to say: ${it.text || ''}` };
    return (
      <div {...stylex.props(styles.event)} aria-label={d.what(it)}>
        <span {...stylex.props(styles.eventIcon)}>
          <Icon name={d.icon} size={14} />
        </span>
        <div {...stylex.props(styles.eventText)}>
          <span>{d.what(it)}</span>
          {it.details && <span {...stylex.props(styles.note)}>{it.details}</span>}
          {it.note && <span {...stylex.props(styles.note)}>{it.note}</span>}
        </div>
        <div {...stylex.props(styles.eventState)}>
          <Inline gap="sm">
            <State it={it} />
            <When t={it.at} />
          </Inline>
        </div>
      </div>
    );
  }
  const look = { theirs: styles.theirs, ours: styles.ours, private: styles.private }[line.side];
  return (
    <article {...stylex.props(styles.msg, look)} aria-label={`${line.from} to ${line.to}`}>
      <div {...stylex.props(styles.head)}>
        <span {...stylex.props(styles.from)}>{line.from}</span>
        <Icon name="arrow" size={12} />
        <span>{line.to}</span>
        {line.side === 'private' && <span {...stylex.props(styles.tag)}>private</span>}
        {it.side && <span {...stylex.props(styles.tag)}>side answer</span>}
        {it.question && <span {...stylex.props(styles.tag)}>question</span>}
        <State it={it} />
        <When t={it.at} />
      </div>
      {it.text && (
        <div {...stylex.props(styles.text)}>
          <SlackText text={it.text} />
        </div>
      )}
      {filesLine(it) && <span {...stylex.props(styles.note)}>Files: {filesLine(it)}</span>}
      {it.note && it.state !== 'sent' && <span {...stylex.props(styles.note)}>{it.note}</span>}
    </article>
  );
}

/** "a.xlsx · run.sh held (file type not allowed)": an outgoing message's files with any state but sent, or the names
 * of the files someone sent in. */
function filesLine(it: CaseItem): string {
  if (it.attachments?.length) {
    return it.attachments
      .map((a) => (a.state === 'sent' ? a.name : `${a.name} ${a.state}${a.note ? ` (${a.note})` : ''}`))
      .join(' · ');
  }
  return it.files?.join(', ') ?? '';
}

function Waiting({ t }: { t: Task }) {
  const items = waitingOnYou(t);
  if (!items.length) return null;
  return (
    <div {...stylex.props(styles.waiting)}>
      <div {...stylex.props(styles.waitingHead)}>
        <span {...stylex.props(styles.waitingTitle)}>
          <Icon name="alert" size={16} />
          {plural(items.length, 'thing')} waiting on you
        </span>
        {t.caseLink && <LinkButton label="Decide in Slack" icon="slack" to={t.caseLink} small />}
      </div>
      <ul {...stylex.props(styles.waitingList)}>
        {items.map((it) => (
          <li key={it.seq}>{it.kind === 'approval' ? it.action : `${it.label ? `To ${it.label}: ` : ''}${it.text}`}</li>
        ))}
      </ul>
    </div>
  );
}

function Case({ t, me }: { t: Task; me: string }) {
  const [label, tone] = t.phase ? PHASE_PILL[t.phase] : ['Unknown', 'idle' as const];
  const who = t.requester || 'Someone';
  const waiting = waitingOnYou(t).length;
  return (
    <Expandable
      summary={
        <div {...stylex.props(styles.summary)}>
          <Badge name={who} size="sm" />
          <div {...stylex.props(styles.who)}>
            <span {...stylex.props(styles.name)}>
              {who}
              {t.party === 'errand' && <span {...stylex.props(styles.tag)}>errand</span>}
            </span>
            <span {...stylex.props(styles.ask)}>{firstAsk(t).split('\n')[0]}</span>
          </div>
          <div {...stylex.props(styles.side)}>
            <div {...stylex.props(styles.pills)}>
              {waiting > 0 && t.phase !== 'waiting_owner' && <Pill tone="warn">{waiting} for you</Pill>}
              <Pill tone={tone} dot={isOpen(t)}>
                {label}
              </Pill>
            </div>
            <When t={lastAt(t)} />
          </div>
        </div>
      }
    >
      <div {...stylex.props(styles.body)}>
        <Waiting t={t} />
        <div {...stylex.props(styles.convo)}>
          {t.items.map((it) => (
            <Item key={it.seq} it={it} who={who} me={me} />
          ))}
        </div>
        <div {...stylex.props(styles.foot)}>
          {t.route && (
            <span {...stylex.props(styles.route)} title={t.route.why}>
              <Icon name="files" size={14} />
              {routeLine(t.route)}
            </span>
          )}
          <div {...stylex.props(styles.links)}>
            {t.caseLink && <LinkButton label="Case in Slack" icon="slack" to={t.caseLink} small />}
            {t.slack && (
              <LinkButton label={t.party === 'errand' ? 'Your thread' : 'Their thread'} icon="slack" to={t.slack} small />
            )}
            {t.t3 && <LinkButton label="Open in T3" icon="chat" to={t.t3} small />}
          </div>
        </div>
      </div>
    </Expandable>
  );
}

/** Every conversation someone else has with the companion: what came in, what went out (and what became of it), your
 *  private exchange with the companion, and what waits on you. */
export function Cases({ tasks, me }: { tasks: Task[]; me: string }) {
  const all = casesOf(tasks).sort((a, b) => lastAt(b) - lastAt(a));
  const [filter, setFilter] = useState<CaseFilter>(all.some(needsYou) ? 'you' : 'all');
  const cases = filterCases(all, filter);
  const pages = usePages(cases, PAGE);
  return (
    <Section
      title="Cases"
      icon="chat"
      sub={`Conversations colleagues and errands have with ${me}. Private lines are between you and ${me} only.`}
      right={
        <Inline gap="md">
          <Segments<CaseFilter>
            label="Show"
            value={filter}
            onChange={setFilter}
            options={[
              { value: 'you', label: 'Needs you', count: filterCases(all, 'you').length },
              { value: 'open', label: 'Open', count: filterCases(all, 'open').length },
              { value: 'all', label: 'All', count: all.length },
            ]}
          />
          <Pager {...pages} />
        </Inline>
      }
    >
      {cases.length ? (
        <div {...stylex.props(styles.list)}>
          {pages.shown.map((t) => (
            <Case key={t.id} t={t} me={me} />
          ))}
        </div>
      ) : (
        <Empty
          title={filter === 'all' ? 'No cases yet' : 'Nothing here'}
          text={
            filter === 'all'
              ? `When a colleague messages ${me}, the conversation shows up here.`
              : filter === 'you'
                ? 'Nothing waits on you.'
                : 'No case is open.'
          }
          icon="chat"
        />
      )}
    </Section>
  );
}

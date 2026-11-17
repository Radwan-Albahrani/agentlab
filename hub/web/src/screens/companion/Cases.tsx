import * as stylex from '@stylexjs/stylex';
import type { CaseEntry, Task } from '../../api/types';
import { TASK_PILL } from '../../lib/companion';
import { usePages } from '../../lib/usePages';
import { colors, font, media, radius, space, text } from '../../theme/tokens.stylex';
import { LinkButton } from '../../ui/Button';
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
  name: { fontWeight: 600 },
  ask: { color: colors.muted, fontSize: text.md, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' },
  side: { display: 'grid', justifyItems: 'end', gap: space.xxs, color: colors.faint, fontSize: text.sm },
  convo: { display: 'grid', gap: space.md },
  // one message: who to whom on top, the text below
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
  body: { whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', lineHeight: 1.5, fontSize: text.md },
  // approvals and the like: a small line across
  event: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: space.sm,
    color: colors.faint,
    fontSize: text.sm,
    textAlign: 'center',
  },
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
  links: { display: 'flex', justifyContent: 'flex-end', gap: space.sm, flexWrap: 'wrap' },
});

/** A task is a case when a colleague started it: its timeline holds what they wrote. */
export const casesOf = (tasks: Task[]) => tasks.filter((t) => t.timeline?.some((e) => e.kind === 'received'));

const lastAt = (t: Task) => t.timeline?.at(-1)?.at ?? t.startedAt;

const SYSTEM: Record<string, { icon: string; label: (e: CaseEntry) => string }> = {
  approval: { icon: 'alert', label: (e) => e.title },
  approved: { icon: 'check', label: (e) => e.title },
  rejected: { icon: 'x', label: (e) => e.title },
  withdrawn: { icon: 'back', label: (e) => e.title },
};

function Entry({ e, who, me }: { e: CaseEntry; who: string; me: string }) {
  const sys = SYSTEM[e.kind];
  if (sys)
    return (
      <div {...stylex.props(styles.event)}>
        <Icon name={sys.icon} size={14} />
        <span>{sys.label(e)}</span>
        <When t={e.at} />
      </div>
    );
  const own = e.title.endsWith('(on your word)');
  const [from, to, look] =
    e.kind === 'received'
      ? [who, me, styles.theirs]
      : e.kind === 'sent'
        ? [me, e.to || who, styles.ours]
        : e.title.startsWith('You')
          ? ['You', me, styles.private]
          : [me, 'you', styles.private];
  return (
    <article {...stylex.props(styles.msg, look)} aria-label={`${from} to ${to}`}>
      <div {...stylex.props(styles.head)}>
        <span {...stylex.props(styles.from)}>{from}</span>
        <Icon name="arrow" size={12} />
        <span>{to}</span>
        {e.kind === 'private' && <span {...stylex.props(styles.tag)}>private</span>}
        {own && <span {...stylex.props(styles.tag)}>on your word</span>}
        <When t={e.at} />
      </div>
      <div {...stylex.props(styles.body)}>
        <SlackText text={e.detail || ''} />
      </div>
    </article>
  );
}

function Case({ t, me }: { t: Task; me: string }) {
  const [label, tone] = TASK_PILL[t.status] ?? [t.status, 'idle'];
  const who = t.requester || 'Someone';
  const first = t.timeline?.find((e) => e.kind === 'received')?.detail ?? t.title;
  return (
    <Expandable
      summary={
        <div {...stylex.props(styles.summary)}>
          <Badge name={who} size="sm" />
          <div {...stylex.props(styles.who)}>
            <span {...stylex.props(styles.name)}>{who}</span>
            <span {...stylex.props(styles.ask)}>{first.split('\n')[0]}</span>
          </div>
          <div {...stylex.props(styles.side)}>
            <Pill tone={tone} dot={t.status === 'working' || t.status === 'waiting'}>
              {label}
            </Pill>
            <When t={lastAt(t)} />
          </div>
        </div>
      }
    >
      <div {...stylex.props(styles.convo)}>
        {(t.timeline ?? []).map((e, i) => (
          <Entry key={`${e.at}-${i}`} e={e} who={who} me={me} />
        ))}
      </div>
      <div {...stylex.props(styles.links)}>
        {t.slack && <LinkButton label="Their thread" icon="slack" to={t.slack} small />}
        {t.t3 && <LinkButton label="Open in T3" icon="chat" to={t.t3} small />}
      </div>
    </Expandable>
  );
}

/** Every conversation a colleague had with the companion: what they wrote, what went to them, and the owner's
 *  private exchange with the companion about it. */
export function Cases({ tasks, me }: { tasks: Task[]; me: string }) {
  const cases = casesOf(tasks).sort((a, b) => lastAt(b) - lastAt(a));
  const pages = usePages(cases, PAGE);
  return (
    <Section
      title="Cases"
      icon="chat"
      sub={`Conversations colleagues had with ${me}. Private lines are between you and ${me} only.`}
      right={
        <Inline gap="md">
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
        <Empty title="No cases yet" text={`When a colleague messages ${me}, the conversation shows up here.`} icon="chat" />
      )}
    </Section>
  );
}

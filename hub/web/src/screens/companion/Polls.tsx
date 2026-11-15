import * as stylex from '@stylexjs/stylex';
import { useState } from 'react';
import type { Poll } from '../../api/types';
import { pollSummary } from '../../lib/companion';
import { fromLocalInput, pct, plural, toLocalInput } from '../../lib/format';
import { colors, font, media, motion, radius, space, text } from '../../theme/tokens.stylex';
import { ActButton } from '../../ui/actions';
import { LinkButton } from '../../ui/Button';
import { Disclosure, Segments } from '../../ui/controls';
import { useAct } from '../../ui/feedback';
import { Icon } from '../../ui/Icon';
import { TextInput } from '../../ui/inputs';
import { Spacer } from '../../ui/layout';
import { Appear } from '../../ui/motion';
import { Section } from '../../ui/page';
import { IconBox } from '../../ui/Row';
import { Pill, Tag } from '../../ui/status';
import { Faces } from './parts';

const styles = stylex.create({
  list: { display: 'grid', gap: space.lg },
  card: {
    display: 'grid',
    gap: space.xl,
    paddingBlock: space.xl,
    paddingInline: { default: space.xxl, [media.phone]: space.lg },
    borderRadius: radius.xl,
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: colors.line,
    backgroundColor: colors.panel,
    minWidth: 0,
  },
  cardOpen: { borderColor: `color-mix(in srgb, ${colors.info} 45%, ${colors.line})` },
  head: { display: 'flex', alignItems: 'flex-start', gap: space.lg, flexWrap: 'wrap' },
  headText: { flexGrow: 1, flexShrink: 1, flexBasis: 260, minWidth: 0 },
  question: {
    margin: 0,
    fontFamily: font.display,
    fontSize: text.xl,
    fontWeight: 600,
    lineHeight: 1.2,
    overflowWrap: 'anywhere',
  },
  summary: { marginBlockStart: space.xxs, marginBlockEnd: 0, marginInline: 0, fontSize: text.md, color: colors.muted },
  channel: { fontFamily: font.mono, fontSize: text.sm, color: colors.fg },
  aside: { display: 'flex', alignItems: 'center', gap: space.sm },
  options: { display: 'grid', gap: space.sm },
  option: { display: 'grid', gap: space.xxs },
  // the bar is the option: label over a fill as wide as its share of voters
  track: {
    position: 'relative',
    overflow: 'hidden',
    display: 'flex',
    alignItems: 'center',
    gap: space.md,
    minHeight: 36,
    paddingInline: space.lg,
    borderRadius: radius.md,
    backgroundColor: colors.sunk,
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: colors.line,
  },
  fill: (width: string) => ({
    position: 'absolute',
    insetBlock: 0,
    insetInlineStart: 0,
    width,
    transitionProperty: 'width',
    transitionDuration: '400ms',
    transitionTimingFunction: motion.settle,
    backgroundColor: colors.idleSoft,
    borderInlineEndWidth: 1,
    borderInlineEndStyle: 'solid',
    borderInlineEndColor: colors.line2,
  }),
  fillTop: { backgroundColor: colors.infoSoft, borderInlineEndColor: colors.info },
  fillWon: { backgroundColor: colors.okSoft, borderInlineEndColor: colors.ok },
  label: {
    position: 'relative',
    flex: '1',
    minWidth: 0,
    display: 'flex',
    alignItems: 'center',
    gap: space.xs,
    fontWeight: 500,
    overflowWrap: 'anywhere',
  },
  won: { color: colors.ok, display: 'flex' },
  votes: {
    position: 'relative',
    display: 'flex',
    alignItems: 'center',
    gap: space.md,
    fontFamily: font.mono,
    fontSize: text.sm,
    color: colors.muted,
    fontVariantNumeric: 'tabular-nums',
    whiteSpace: 'nowrap',
  },
  voteWord: { display: { default: null, [media.phone]: 'none' } },
  share: { color: colors.fg, fontWeight: 600, minWidth: 38, textAlign: 'end' },
  names: { fontSize: text.sm, color: colors.faint, paddingInlineStart: space.lg, overflowWrap: 'anywhere' },
  foot: {
    display: 'flex',
    flexWrap: 'wrap',
    alignItems: 'flex-start',
    gap: space.md,
    paddingTop: space.md,
    borderTopWidth: 1,
    borderTopStyle: 'solid',
    borderTopColor: colors.line,
  },
  manage: { flexGrow: 1, minWidth: 0, paddingTop: space.xs },
  controls: { display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: space.md, paddingTop: space.sm },
});

type Choice = 'single' | 'multiple';
const CHOICES: { value: Choice; label: string; icon: string }[] = [
  { value: 'single', label: 'Single choice', icon: 'single' },
  { value: 'multiple', label: 'Multiple choice', icon: 'multiple' },
];

export function Polls({ name, polls }: { name: string; polls: Poll[] }) {
  if (!polls.length) return null;
  const open = polls.filter((p) => p.open).length;
  return (
    <Section
      title="Polls"
      icon="poll"
      sub="Live results; changes reach Slack within seconds."
      id="polls"
      right={
        <Pill tone={open ? 'info' : 'idle'} dot={open > 0}>
          {open ? `${open} open` : 'All closed'}
        </Pill>
      }
    >
      <div {...stylex.props(styles.list)}>
        {polls.map((p, i) => (
          <Appear key={p.id} i={i}>
            <PollCard name={name} p={p} />
          </Appear>
        ))}
      </div>
    </Section>
  );
}

function PollCard({ name, p }: { name: string; p: Poll }) {
  return (
    <article {...stylex.props(styles.card, p.open && styles.cardOpen)}>
      <div {...stylex.props(styles.head)}>
        <IconBox icon="poll" tone={p.open ? 'info' : 'idle'} />
        <div {...stylex.props(styles.headText)}>
          <h3 {...stylex.props(styles.question)}>{p.question}</h3>
          <p {...stylex.props(styles.summary)}>
            <span {...stylex.props(styles.channel)}>#{p.channel}</span> · {pollSummary(p)}
          </p>
        </div>
        <div {...stylex.props(styles.aside)}>
          <Tag>{p.multiple ? 'multiple choice' : 'single choice'}</Tag>
          <Pill tone={p.open ? 'info' : 'idle'} dot>
            {p.open ? 'Open' : 'Closed'}
          </Pill>
        </div>
      </div>
      <Results p={p} />
      {p.open ? (
        <div {...stylex.props(styles.foot)}>
          <div {...stylex.props(styles.manage)}>
            <Disclosure label="Change the poll">
              <div {...stylex.props(styles.controls)}>
                <Controls name={name} p={p} />
              </div>
            </Disclosure>
          </div>
          {p.link && <LinkButton label="Open in Slack" icon="slack" small variant="quiet" to={p.link} />}
        </div>
      ) : (
        p.link && (
          <div {...stylex.props(styles.foot)}>
            <Spacer />
            <LinkButton label="Open in Slack" icon="slack" small variant="quiet" to={p.link} />
          </div>
        )
      )}
    </article>
  );
}

function Results({ p }: { p: Poll }) {
  const top = Math.max(0, ...p.options.map((o) => o.votes));
  // each voter counts once, so a multiple-choice poll's shares can add up past 100%
  const people = Math.max(top, new Set(p.options.flatMap((o) => o.voters.map((v) => v.name))).size);
  return (
    <div {...stylex.props(styles.options)}>
      {p.options.map((o) => {
        const lead = top > 0 && o.votes === top;
        const share = pct(o.votes, people);
        return (
          <div key={o.label} {...stylex.props(styles.option)}>
            <div {...stylex.props(styles.track)}>
              <span {...stylex.props(styles.fill(`${share.toFixed(1)}%`), lead && (p.open ? styles.fillTop : styles.fillWon))} />
              <span {...stylex.props(styles.label)}>
                {lead && !p.open && (
                  <span {...stylex.props(styles.won)}>
                    <Icon name="check" size={16} />
                  </span>
                )}
                {o.label}
              </span>
              <span {...stylex.props(styles.votes)}>
                {o.voters.length > 0 && <Faces people={o.voters} size={24} />}
                <span {...stylex.props(styles.voteWord)}>{plural(o.votes, 'vote')}</span>
                <span {...stylex.props(styles.share)}>{share.toFixed(0)}%</span>
              </span>
            </div>
            {o.voters.length > 0 && <div {...stylex.props(styles.names)}>{o.voters.map((v) => v.name).join(', ')}</div>}
          </div>
        );
      })}
    </div>
  );
}

function Controls({ name, p }: { name: string; p: Poll }) {
  const act = useAct();
  const [closes, setCloses] = useState(toLocalInput(p.closes));
  const url = `/api/companions/${name}/poll`;
  return (
    <>
      <Segments
        label="Choice"
        value={p.multiple ? 'multiple' : 'single'}
        options={CHOICES}
        onChange={(v) => act(url, { poll: p.id, multiple: v === 'multiple' })}
      />
      <TextInput
        type="datetime-local"
        width="datetime"
        value={closes}
        onChange={setCloses}
        onEnter={() => act(url, { poll: p.id, closes: fromLocalInput(closes) })}
        title="Closing time: press Enter to save"
      />
      <Spacer />
      <ActButton
        label="Close the poll now"
        icon="power"
        variant="danger"
        small
        url={url}
        body={{ poll: p.id, close: true }}
        confirm={`Close "${p.question}" now and announce the result in ${p.channel}?`}
      />
    </>
  );
}

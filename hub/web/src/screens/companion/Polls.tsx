import * as stylex from '@stylexjs/stylex';
import { useState } from 'react';
import type { Poll } from '../../api/types';
import { pollSummary } from '../../lib/companion';
import { fromLocalInput, pct, plural, toLocalInput } from '../../lib/format';
import { colors, radius, space } from '../../theme/tokens.stylex';
import { ActButton } from '../../ui/actions';
import { LinkButton } from '../../ui/Button';
import { Segments } from '../../ui/controls';
import { Expandable } from '../../ui/Expandable';
import { useAct } from '../../ui/feedback';
import { TextInput } from '../../ui/inputs';
import { Inline, Spacer, Split, Stack } from '../../ui/layout';
import { Section } from '../../ui/page';
import { Meter, Pill, Tag } from '../../ui/status';
import { Text } from '../../ui/text';

const styles = stylex.create({
  avatars: { display: 'flex', alignItems: 'center', gap: space.xs, flexWrap: 'wrap', minWidth: 0 },
  avatar: {
    width: 22,
    height: 22,
    borderRadius: radius.pill,
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: colors.line2,
    objectFit: 'cover',
  },
  controls: {
    display: 'flex',
    flexWrap: 'wrap',
    alignItems: 'center',
    gap: space.md,
    paddingTop: space.lg,
    borderTopWidth: 1,
    borderTopStyle: 'solid',
    borderTopColor: colors.line,
  },
});

type Choice = 'single' | 'multiple';
const CHOICES: { value: Choice; label: string; icon: string }[] = [
  { value: 'single', label: 'Single choice', icon: 'single' },
  { value: 'multiple', label: 'Multiple choice', icon: 'multiple' },
];

/** The polls a companion runs: one summary line each, opening to live results, voters and the owner's controls. */
export function Polls({ name, polls }: { name: string; polls: Poll[] }) {
  if (!polls.length) return null;
  return (
    <Section title="Polls" sub="Live results; changes reach Slack within seconds." id="polls">
      <Stack gap="md">
        {polls.map((p) => (
          <Expandable
            key={p.id}
            summary={
              <>
                <Text block weight="bold" size="lg">
                  {p.question}
                </Text>
                <Text block tone="muted" size="md">
                  {p.channel} · {pollSummary(p)}
                </Text>
              </>
            }
            aside={
              <Inline gap="sm" nowrap>
                <Tag>{p.multiple ? 'multiple choice' : 'single choice'}</Tag>
                <Pill tone={p.open ? 'info' : 'idle'} dot>
                  {p.open ? 'Open' : 'Closed'}
                </Pill>
              </Inline>
            }
          >
            <Results p={p} />
            {p.open ? (
              <Controls name={name} p={p} />
            ) : (
              p.link && (
                <Inline gap="sm">
                  <LinkButton label="Open in Slack" icon="slack" small to={p.link} />
                </Inline>
              )
            )}
          </Expandable>
        ))}
      </Stack>
    </Section>
  );
}

function Results({ p }: { p: Poll }) {
  const top = Math.max(1, ...p.options.map((o) => o.votes));
  return (
    <Stack gap="md">
      {p.options.map((o) => (
        <Stack key={o.label} gap="xs">
          <Split>
            <Text weight="semibold">{o.label}</Text>
            <Text tone="muted" size="md">
              {plural(o.votes, 'vote')}
            </Text>
          </Split>
          <Meter share pct={pct(o.votes, top)} />
          {o.voters.length > 0 && (
            <div {...stylex.props(styles.avatars)}>
              {o.voters.map(
                (v) => v.avatar && <img key={v.name} {...stylex.props(styles.avatar)} src={v.avatar} alt="" title={v.name} />,
              )}
              <Text tone="faint" size="md">
                {o.voters.map((v) => v.name).join(', ')}
              </Text>
            </div>
          )}
        </Stack>
      ))}
    </Stack>
  );
}

/** Choice as an icon toggle, the closing time saved with Enter, Slack and an off button: no words needed. */
function Controls({ name, p }: { name: string; p: Poll }) {
  const act = useAct();
  const [closes, setCloses] = useState(toLocalInput(p.closes));
  const url = `/api/companions/${name}/poll`;
  return (
    <div {...stylex.props(styles.controls)}>
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
      {p.link && <LinkButton label="Open in Slack" icon="slack" small iconOnly to={p.link} />}
      <ActButton
        label="Close the poll now"
        icon="power"
        variant="danger"
        small
        iconOnly
        url={url}
        body={{ poll: p.id, close: true }}
        confirm={`Close "${p.question}" now and announce the result in ${p.channel}?`}
      />
    </div>
  );
}

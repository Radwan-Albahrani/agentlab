import * as stylex from '@stylexjs/stylex';
import { useState } from 'react';
import type { Channel } from '../../api/types';
import { colors, font, media, radius, space, text } from '../../theme/tokens.stylex';
import { Button } from '../../ui/Button';
import { Switch } from '../../ui/controls';
import { useAct } from '../../ui/feedback';
import { Section } from '../../ui/page';
import { TextArea } from '../../ui/inputs';
import { Picker, type PickItem } from '../../ui/Picker';

const styles = stylex.create({
  // one composer: the text, then a footer with where it goes and how
  composer: {
    borderRadius: radius.xl,
    overflow: 'hidden',
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: { default: colors.line, ':hover': colors.line2, ':focus-within': colors.accent },
    backgroundColor: colors.panel,
    transitionProperty: 'border-color',
    transitionDuration: '140ms',
  },
  area: {
    display: 'block',
    width: '100%',
    minHeight: 124,
    resize: 'vertical',
    paddingBlock: space.xl,
    paddingInline: space.xxl,
    borderWidth: 0,
    outline: 'none',
    fontFamily: 'inherit',
    fontSize: text.body,
    lineHeight: 1.55,
    color: colors.fg,
    backgroundColor: 'transparent',
    '::placeholder': { color: colors.faint },
  },
  foot: {
    display: 'flex',
    flexWrap: 'wrap',
    alignItems: 'center',
    gap: space.lg,
    paddingBlock: space.md,
    paddingInline: { default: space.xxl, [media.phone]: space.lg },
    borderTopWidth: 1,
    borderTopStyle: 'solid',
    borderTopColor: colors.line,
    backgroundColor: colors.raised,
  },
  review: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: space.sm,
    fontSize: text.md,
    color: colors.muted,
    whiteSpace: 'nowrap',
  },
  send: { marginInlineStart: 'auto' },
  hint: { marginBlock: 0, marginInline: space.xxs, fontSize: text.xs, color: colors.faint },
  kbd: {
    fontFamily: font.mono,
    fontSize: text.xxs,
    fontWeight: 500,
    paddingInline: space.xxs,
    borderRadius: radius.xs,
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: colors.line2,
    backgroundColor: colors.sunk,
    color: colors.muted,
  },
});

const PLACEHOLDER = 'Announce that staging is frozen on Thursday…\nor paste a list and say “make a poll, ends at 2pm”';

/** Postable channels first; the rest stay listed (disabled). */
const pickItems = (channels: Channel[], name: string): PickItem[] =>
  [...channels]
    .sort((a, b) => Number(b.member) - Number(a.member) || a.name.localeCompare(b.name))
    .map((c) => ({
      value: c.id,
      label: `#${c.name}`,
      disabled: !c.member,
      hint: c.member ? undefined : `invite @${name} first`,
    }));

export function AskBox({ name, display, channels }: { name: string; display: string; channels: Channel[] }) {
  const act = useAct();
  const [draft, setDraft] = useState('');
  const [channel, setChannel] = useState('');
  const [review, setReview] = useState(true);
  const [busy, setBusy] = useState(false);
  const nice = display;
  const send = async () => {
    if (!draft.trim() || busy) return;
    setBusy(true);
    const ok = await act(`/api/companions/${name}/ask`, { text: draft, channel, review });
    setBusy(false);
    if (ok) setDraft('');
  };
  return (
    <Section
      title={`Tell ${nice}`}
      icon="send"
      sub="Post or run a poll in a channel. Say it in plain words; the agent prepares it."
    >
      <div {...stylex.props(styles.composer)}>
        <TextArea
          look={styles.area}
          value={draft}
          onChange={setDraft}
          placeholder={PLACEHOLDER}
          label={`Tell ${nice}`}
          spellCheck
          onKeyDown={(e) => {
            if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) void send();
          }}
        />
        <div {...stylex.props(styles.foot)}>
          <Picker
            label="Channel"
            items={pickItems(channels, name)}
            value={channel}
            onChange={setChannel}
            placeholder="Channel: or name it in your words"
            empty="No channel by that name"
          />
          <span {...stylex.props(styles.review)}>
            <Switch
              on={review}
              label="Show me before it posts"
              onToggle={() => {
                setReview(!review);
              }}
            />
            Show me first
          </span>
          <span {...stylex.props(styles.send)}>
            <Button label="Send" icon="send" variant="primary" busy={busy} disabled={!draft.trim()} onClick={send} />
          </span>
        </div>
      </div>
      <p {...stylex.props(styles.hint)}>
        {review
          ? `${nice} shows you the post in your Slack DM; it goes out when you tap Post it. `
          : 'It goes out as soon as it is ready. '}
        <kbd {...stylex.props(styles.kbd)}>Ctrl</kbd> + <kbd {...stylex.props(styles.kbd)}>Enter</kbd> sends.
      </p>
    </Section>
  );
}

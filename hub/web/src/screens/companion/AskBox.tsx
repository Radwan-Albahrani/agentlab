import * as stylex from '@stylexjs/stylex';
import { useState } from 'react';
import type { Channel } from '../../api/types';
import { space } from '../../theme/tokens.stylex';
import { Button } from '../../ui/Button';
import { Card, CardBody } from '../../ui/Card';
import { Switch } from '../../ui/controls';
import { useAct } from '../../ui/feedback';
import { TextArea } from '../../ui/inputs';
import { Inline, Stack } from '../../ui/layout';
import { Section } from '../../ui/page';
import { Picker, type PickItem } from '../../ui/Picker';
import { Text } from '../../ui/text';

const styles = stylex.create({
  row: { display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: space.lg },
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
  const [text, setText] = useState('');
  const [channel, setChannel] = useState('');
  const [review, setReview] = useState(true);
  const [busy, setBusy] = useState(false);
  const nice = display;
  const send = async () => {
    if (!text.trim() || busy) return;
    setBusy(true);
    const ok = await act(`/api/companions/${name}/ask`, { text, channel, review });
    setBusy(false);
    if (ok) setText('');
  };
  return (
    <Section title={`Tell ${nice}`} sub="Post or run a poll in a channel. Say it in plain words; the agent prepares it.">
      <Card>
        <CardBody>
          <Stack gap="lg">
            <TextArea
              prose
              value={text}
              onChange={setText}
              placeholder={PLACEHOLDER}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) void send();
              }}
            />
            <div {...stylex.props(styles.row)}>
              <Picker
                label="Channel"
                items={pickItems(channels, name)}
                value={channel}
                onChange={setChannel}
                placeholder="Channel: or name it in your words"
                empty="No channel by that name"
              />
              <Inline gap="sm" nowrap>
                <Switch
                  on={review}
                  label="Show me before it posts"
                  onToggle={() => {
                    setReview(!review);
                  }}
                />
                <Text size="md" tone="muted">
                  Show me first
                </Text>
              </Inline>
              <Button label="Send" icon="send" variant="primary" busy={busy} onClick={send} />
            </div>
            <Text size="xs" tone="faint">
              {review
                ? `${nice} shows you the post in your Slack DM; it goes out when you tap Post it. Ctrl+Enter sends.`
                : `It goes out as soon as it is ready. Ctrl+Enter sends.`}
            </Text>
          </Stack>
        </CardBody>
      </Card>
    </Section>
  );
}

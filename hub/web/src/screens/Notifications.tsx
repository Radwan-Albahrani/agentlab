import { useNotifications } from '../api/queries';
import type { Notifications as Data } from '../api/types';
import { Screen } from '../app/Screen';
import { ActButton } from '../ui/actions';
import { Card, CardBody } from '../ui/Card';
import { useAct } from '../ui/feedback';
import { FeedSection } from '../ui/Feed';
import { SubmitField } from '../ui/inputs';
import { Grid2, Inline, Split } from '../ui/layout';
import { EmptyCard, PageHead } from '../ui/page';
import { Pill } from '../ui/status';
import { HelpSteps, KeyValues, Mono, Text } from '../ui/text';

export function Notifications() {
  const query = useNotifications();
  return (
    <Screen title="Notifications" query={query}>
      {(d) => <NotificationsView d={d} />}
    </Screen>
  );
}

function NotificationsView({ d }: { d: Data }) {
  if (!d.configured)
    return (
      <>
        <PageHead title="Notifications" sub="Phone pings when an agent asks you something or a long chat finishes." />
        <EmptyCard
          title="Phone pushes are off"
          text="They go through a Bark server (an iPhone app with a small push server). Run one and give the hub its address in BARK_URL (and BARK_PUBLIC for the phone) to turn them on."
          icon="bell"
        />
      </>
    );
  return (
    <>
      <PageHead
        title="Notifications"
        sub="Your iPhone gets a ping when an agent asks you something or waits for approval, and when a chat you started finishes a longer run."
        right={
          <>
            <ActButton label="Send test" icon="send" variant="primary" url="/api/notify/test" />
            <ActButton label={d.settings.muted ? 'Unmute' : 'Mute'} icon="bell" url="/api/notify/mute" />
          </>
        }
      />
      <Grid2>
        <Setup d={d} />
        <Encryption settings={d.settings} />
      </Grid2>
      <FeedSection title="Recent pushes" events={d.recent} />
    </>
  );
}

function Setup({ d }: { d: Data }) {
  const act = useAct();
  const s = d.settings;
  return (
    <Card>
      <CardBody roomy>
        <Inline gap="xs">
          <Pill tone={d.barkUp ? 'ok' : 'bad'} dot>
            {d.barkUp ? 'Bark server running' : 'Bark server not answering'}
          </Pill>
          <Pill tone={s.deviceKey ? 'ok' : 'warn'}>{s.deviceKey ? 'iPhone linked' : 'No iPhone yet'}</Pill>
          <Pill tone={d.watching === d.agents ? 'ok' : 'warn'}>
            Watching {d.watching} of {d.agents} {d.agents === 1 ? 'agent' : 'agents'}
          </Pill>
          {s.muted && <Pill tone="warn">Muted</Pill>}
        </Inline>
        <SubmitField
          initial={s.deviceKey}
          placeholder="Bark device key"
          button="Save"
          keep
          primary={false}
          onSubmit={(deviceKey) => act('/api/notify/key', { deviceKey })}
        />
        <Inline>
          <Text tone="muted">&quot;Done&quot; ping when a chat took longer than</Text>
          <SubmitField
            type="number"
            initial={String(s.minMinutes)}
            button="Set"
            keep
            primary={false}
            onSubmit={(minutes) => act('/api/notify/minutes', { minutes })}
          />
          <Text tone="muted">minutes</Text>
        </Inline>
        <HelpSteps
          steps={[
            <>
              Install <b>Bark</b> from the App Store.
            </>,
            <>
              Servers → + → <Mono>{d.barkPublic || 'your Bark server address'}</Mono>.
            </>,
            'Copy the device key it shows, paste it above, then Send test.',
          ]}
        />
      </CardBody>
    </Card>
  );
}

function Encryption({ settings: s }: { settings: Data['settings'] }) {
  const act = useAct();
  return (
    <Card>
      <CardBody>
        <Split>
          <b>Encryption</b>
          <Pill tone={s.encrypt ? 'ok' : 'idle'}>{s.encrypt ? 'On' : 'Off'}</Pill>
        </Split>
        <Text tone="muted" size="md" block>
          Pushes pass through Apple. With encryption on, Apple only sees scrambled text. In Bark: Settings → Push encryption,
          enter these, save.
        </Text>
        <KeyValues
          items={[
            ['Algorithm', 'AES128 · CBC · pkcs7'],
            ['Key', <Mono key="key">{s.encKey}</Mono>],
            ['IV', 'leave empty'],
          ]}
        />
        <SubmitField
          placeholder="Or paste Bark's own 16-character key"
          button="Use"
          primary={false}
          onSubmit={(key) => act('/api/notify/enckey', { key })}
        />
        <div>
          <ActButton label={`Turn encryption ${s.encrypt ? 'off' : 'on'}`} small url="/api/notify/encrypt" />
        </div>
      </CardBody>
    </Card>
  );
}

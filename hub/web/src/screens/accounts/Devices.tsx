import { useState } from 'react';
import { api } from '../../api/client';
import { useDevices } from '../../api/queries';
import type { Device, PairLink } from '../../api/types';
import { CopyButton } from '../../ui/actions';
import { Button } from '../../ui/Button';
import { Card, CardBody } from '../../ui/Card';
import { Countdown } from '../../ui/Countdown';
import { useAct, useFeedback } from '../../ui/feedback';
import { SubmitField } from '../../ui/inputs';
import { Inline, Stack } from '../../ui/layout';
import { Empty, Section } from '../../ui/page';
import { Qr } from '../../ui/Qr';
import { List, Row } from '../../ui/Row';
import { Pill } from '../../ui/status';
import { HelpSteps, Mono, Note, Text } from '../../ui/text';
import { When } from '../../ui/When';

const seconds = (iso: string) => (iso ? Date.parse(iso) / 1000 : null);

/** Pair the T3 desktop or phone app with this agent (a one-time link, also as a QR code), and the devices that are. */
export function Devices({ agent }: { agent: string }) {
  const devices = useDevices(agent);
  const [link, setLink] = useState<PairLink | null>(null);
  const { toast } = useFeedback();
  const make = async (label: string) => {
    try {
      setLink(await api.pair(agent, 'app', label));
    } catch (e) {
      toast((e as Error).message, true);
    }
  };
  return (
    <Section title="Devices" sub="The T3 app on your phone or computer, and the browsers signed in to this agent's chat.">
      <Card>
        <CardBody>
          <SubmitField placeholder="Device name, e.g. iPhone" button="Pair the T3 app" onSubmit={make} />
          {link && (
            <NewLink
              link={link}
              onDone={() => {
                setLink(null);
              }}
            />
          )}
        </CardBody>
        {devices.data && <DeviceList agent={agent} devices={devices.data.devices} />}
      </Card>
    </Section>
  );
}

function NewLink({ link, onDone }: { link: PairLink; onDone: () => void }) {
  if (!link.available)
    return (
      <Card accent="warn">
        <CardBody>
          <Text block>{link.reason}</Text>
          <div>
            <Button label="OK" small onClick={onDone} />
          </div>
        </CardBody>
      </Card>
    );
  return (
    <Inline gap="lg" top>
      <Qr text={link.url} size={168} label="Pairing code for the T3 app" />
      <Stack gap="sm">
        <HelpSteps
          steps={[
            'Phone: in T3, Settings → Environments → Add, then scan this code.',
            'Computer: Settings → Connections → Add environment, then paste the link.',
          ]}
        />
        <Mono>{link.url}</Mono>
        <Inline>
          <CopyButton text={link.url} label="Copy link" />
          <Button label="Done" variant="quiet" small onClick={onDone} />
        </Inline>
        <Countdown until={link.expires} />
        <Note>Works once. Anyone with it can open this agent&apos;s chat until it is used or expires.</Note>
      </Stack>
    </Inline>
  );
}

function DeviceList({ agent, devices }: { agent: string; devices: Device[] }) {
  const act = useAct();
  if (!devices.length)
    return (
      <CardBody divided>
        <Empty title="No devices yet" text="Pair the T3 app above, or open the chat once in a browser." icon="phone" />
      </CardBody>
    );
  return (
    <List>
      {devices.map((d) => (
        <Row
          key={d.id}
          icon={/iphone|android|ios|mobile/i.test(`${d.label} ${d.userAgent}`) ? 'phone' : 'browser'}
          title={
            <>
              {d.label || 'Unnamed device'}{' '}
              {d.connected && (
                <Pill tone="ok" dot>
                  Connected
                </Pill>
              )}
            </>
          }
          detail={[d.userAgent, d.ip].filter(Boolean).join(' · ')}
          meta={<When t={seconds(d.lastSeen) ?? seconds(d.created)} />}
          actions={
            <Button
              label="Sign out"
              variant="quiet"
              small
              onClick={() =>
                act(
                  `/api/agents/${agent}/devices/revoke`,
                  { id: d.id },
                  { confirm: `Sign ${d.label || 'this device'} out of ${agent}'s chat?` },
                )
              }
            />
          }
        />
      ))}
    </List>
  );
}

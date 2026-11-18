import * as stylex from '@stylexjs/stylex';
import { useEffect, useRef, useState } from 'react';
import { useLocation } from 'react-router';
import { api } from '../../api/client';
import { useDevices } from '../../api/queries';
import type { Device, PairLink } from '../../api/types';
import { hueTheme } from '../../theme/hues';
import { colors, font, media, radius, space, text } from '../../theme/tokens.stylex';
import { CopyButton } from '../../ui/actions';
import { Button } from '../../ui/Button';
import { Card, CardBody } from '../../ui/Card';
import { Countdown } from '../../ui/Countdown';
import { useAct, useFeedback } from '../../ui/feedback';
import { Icon } from '../../ui/Icon';
import { SubmitField } from '../../ui/inputs';
import { Appear } from '../../ui/motion';
import { Empty, Section } from '../../ui/page';
import { Qr } from '../../ui/Qr';
import { IconBox, List, Row } from '../../ui/Row';
import { Pill } from '../../ui/status';
import { Eyebrow, Note } from '../../ui/text';
import { When } from '../../ui/When';
import { Callout } from './flow';

const seconds = (iso: string) => (iso ? Date.parse(iso) / 1000 : null);
const count = (n: number) => (n === 1 ? '1 device' : `${n} devices`);

const styles = stylex.create({
  // carries the agent's colour without adding a box (this also shows on the agent page)
  hue: { display: 'contents' },
  pair: { display: 'flex', alignItems: 'center', gap: space.xl, flexWrap: 'wrap' },
  pairIcon: {
    width: 36,
    height: 36,
    flexShrink: 0,
    display: 'grid',
    placeItems: 'center',
    borderRadius: radius.xs,
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: colors.line2,
    backgroundColor: colors.sunk,
    color: colors.muted,
  },
  pairText: { flexGrow: 1, flexShrink: 1, flexBasis: '220px', minWidth: 0 },
  pairTitle: { fontFamily: font.display, fontWeight: 600, fontSize: text.body },
  pairSub: { color: colors.muted, fontSize: text.md },
  pairForm: { flexGrow: 999, flexShrink: 1, flexBasis: '340px', minWidth: 0 },
  // the new link: the code on white beside the ways to use it
  link: {
    display: 'grid',
    gridTemplateColumns: { default: 'auto minmax(0, 1fr)', [media.phone]: '1fr' },
    gap: { default: space.huge, [media.phone]: space.xl },
    alignItems: 'center',
    padding: { default: space.xxl, [media.phone]: space.lg },
    borderRadius: radius.xs,
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: colors.line,
    backgroundColor: colors.raised,
  },
  stage: { display: 'grid', placeItems: 'center', justifySelf: { default: 'start', [media.phone]: 'center' } },
  qr: {
    padding: space.sm,
    borderRadius: radius.xs,
    backgroundColor: colors.paper,
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: colors.line2,
  },
  how: { display: 'grid', gap: space.lg, minWidth: 0 },
  // two cells on one hairline
  ways: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fit, minmax(min(200px, 100%), 1fr))',
    gap: 1,
    backgroundColor: colors.line,
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: colors.line,
  },
  way: {
    display: 'grid',
    gap: space.xxs,
    alignContent: 'start',
    padding: space.lg,
    backgroundColor: colors.panel,
    fontSize: text.md,
    color: colors.muted,
  },
  wayHead: {
    display: 'flex',
    alignItems: 'center',
    gap: space.xs,
    fontSize: text.xxs,
    fontWeight: 600,
    color: colors.fg,
  },
  wayIcon: { color: colors.faint, display: 'flex' },
  url: {
    fontFamily: font.mono,
    fontSize: text.sm,
    paddingBlock: space.sm,
    paddingInline: space.md,
    borderRadius: radius.xs,
    backgroundColor: colors.sunk,
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: colors.line,
    overflowWrap: 'anywhere',
    userSelect: 'all',
  },
  bar: { display: 'flex', alignItems: 'center', gap: space.sm, flexWrap: 'wrap' },
  timer: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: space.xs,
    marginInlineStart: 'auto',
    color: colors.warn,
    fontFamily: font.mono,
    fontVariantNumeric: 'tabular-nums',
  },
  listHead: {
    display: 'flex',
    alignItems: 'center',
    gap: space.sm,
    paddingTop: space.lg,
    paddingBottom: space.xxs,
    paddingInline: space.xxl,
    borderTopWidth: 1,
    borderTopStyle: 'solid',
    borderTopColor: colors.line,
  },
  name: { display: 'inline-flex', alignItems: 'center', gap: space.sm, flexWrap: 'wrap' },
  mono: { fontFamily: font.mono, fontSize: text.xs, fontVariantNumeric: 'tabular-nums' },
});

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
  const list = devices.data?.devices;
  const here = useRef<HTMLDivElement>(null);
  const { hash } = useLocation();
  useEffect(() => {
    if (hash !== '#devices' || !here.current) return;
    here.current.scrollIntoView({ block: 'start' });
    here.current.querySelector('input')?.focus({ preventScroll: true });
  }, [hash]);
  return (
    <div ref={here} {...stylex.props(hueTheme(agent), styles.hue)}>
      <Section
        id="devices"
        title="Devices"
        icon="phone"
        sub="The T3 app on your phone or computer, and the browsers signed in to this agent's chat."
        right={!!list?.length && <Pill tone={list.some((d) => d.connected) ? 'ok' : 'idle'}>{count(list.length)}</Pill>}
      >
        <Card>
          <CardBody roomy>
            <div {...stylex.props(styles.pair)}>
              <span {...stylex.props(styles.pairIcon)}>
                <Icon name="phone" size={22} />
              </span>
              <div {...stylex.props(styles.pairText)}>
                <div {...stylex.props(styles.pairTitle)}>Add a device</div>
                <div {...stylex.props(styles.pairSub)}>Name it, then scan the code with the T3 app or paste the link.</div>
              </div>
              <div {...stylex.props(styles.pairForm)}>
                <SubmitField placeholder="Device name, e.g. iPhone" button="Pair the T3 app" onSubmit={make} />
              </div>
            </div>
            {link && (
              <NewLink
                link={link}
                onDone={() => {
                  setLink(null);
                }}
              />
            )}
          </CardBody>
          {list && <DeviceList agent={agent} devices={list} />}
        </Card>
      </Section>
    </div>
  );
}

function NewLink({ link, onDone }: { link: PairLink; onDone: () => void }) {
  if (!link.available)
    return <Callout tone="warn" icon="alert" title={link.reason} action={<Button label="OK" small onClick={onDone} />} />;
  return (
    <Appear>
      <div {...stylex.props(styles.link)}>
        <div {...stylex.props(styles.stage)}>
          <div {...stylex.props(styles.qr)}>
            <Qr text={link.url} size={176} label="Pairing code for the T3 app" />
          </div>
        </div>
        <div {...stylex.props(styles.how)}>
          <div {...stylex.props(styles.ways)}>
            <div {...stylex.props(styles.way)}>
              <span {...stylex.props(styles.wayHead)}>
                <span {...stylex.props(styles.wayIcon)}>
                  <Icon name="phone" size={14} />
                </span>
                Phone
              </span>
              <span>In T3, Settings → Environments → Add, then scan this code.</span>
            </div>
            <div {...stylex.props(styles.way)}>
              <span {...stylex.props(styles.wayHead)}>
                <span {...stylex.props(styles.wayIcon)}>
                  <Icon name="browser" size={14} />
                </span>
                Computer
              </span>
              <span>Settings → Connections → Add environment, then paste the link.</span>
            </div>
          </div>
          <div {...stylex.props(styles.url)}>{link.url}</div>
          <div {...stylex.props(styles.bar)}>
            <CopyButton text={link.url} label="Copy link" />
            <Button label="Done" variant="quiet" small onClick={onDone} />
            <div {...stylex.props(styles.timer)}>
              <Icon name="clock" size={14} />
              <Countdown until={link.expires} />
            </div>
          </div>
          <Note>Works once. Anyone with it can open this agent&apos;s chat until it is used or expires.</Note>
        </div>
      </div>
    </Appear>
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
    <>
      <div {...stylex.props(styles.listHead)}>
        <Eyebrow>Signed in</Eyebrow>
      </div>
      <List>
        {devices.map((d) => (
          <Row
            key={d.id}
            lead={
              <IconBox
                icon={/iphone|android|ios|mobile/i.test(`${d.label} ${d.userAgent}`) ? 'phone' : 'browser'}
                tone={d.connected ? 'ok' : 'idle'}
              />
            }
            title={
              <span {...stylex.props(styles.name)}>
                {d.label || 'Unnamed device'}
                {d.connected && (
                  <Pill tone="ok" dot>
                    Connected
                  </Pill>
                )}
              </span>
            }
            detail={<span {...stylex.props(styles.mono)}>{[d.userAgent, d.ip].filter(Boolean).join(' · ')}</span>}
            meta={
              <span {...stylex.props(styles.mono)}>
                <When t={seconds(d.lastSeen) ?? seconds(d.created)} />
              </span>
            }
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
    </>
  );
}

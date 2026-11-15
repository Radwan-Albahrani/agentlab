import * as stylex from '@stylexjs/stylex';
import type { ReactNode } from 'react';
import { useNotifications } from '../api/queries';
import type { Notifications as Data } from '../api/types';
import { Screen } from '../app/Screen';
import { plural } from '../lib/format';
import { colors, font, media, radius, space, text } from '../theme/tokens.stylex';
import { ActButton } from '../ui/actions';
import { Card } from '../ui/Card';
import { Switch } from '../ui/controls';
import { useAct } from '../ui/feedback';
import { FeedSection } from '../ui/Feed';
import { Icon } from '../ui/Icon';
import { SubmitField } from '../ui/inputs';
import { EmptyCard, PageHead, Section } from '../ui/page';
import { Setting, Settings } from '../ui/Settings';
import { KeyValues, Mono, Text } from '../ui/text';

const styles = stylex.create({
  top: {
    display: 'grid',
    gridTemplateColumns: { default: 'minmax(0, 1.1fr) minmax(0, 1fr)', [media.narrow]: '1fr' },
    gap: space.xxl,
    alignItems: 'stretch',
  },
  // a lock screen with what a push looks like, drawn as a plain sunk panel
  screen: {
    position: 'relative',
    overflow: 'hidden',
    display: 'grid',
    alignContent: 'start',
    gap: space.md,
    minHeight: 300,
    paddingBlock: space.xxxl,
    paddingInline: { default: space.huge, [media.phone]: space.lg },
    borderRadius: radius.xl,
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: colors.line,
    backgroundColor: colors.sunk,
  },
  screenLabel: {
    fontSize: text.xxs,
    fontWeight: 500,
    color: colors.faint,
  },
  clock: {
    justifySelf: 'center',
    fontFamily: font.mono,
    fontSize: '48px',
    fontWeight: 400,
    letterSpacing: '-.04em',
    lineHeight: 1,
    fontVariantNumeric: 'tabular-nums',
    color: colors.fg,
    marginBlockEnd: space.md,
  },
  push: {
    display: 'grid',
    gridTemplateColumns: '32px minmax(0, 1fr) auto',
    gap: space.md,
    alignItems: 'start',
    paddingBlock: space.md,
    paddingInline: space.lg,
    borderRadius: radius.lg,
    backgroundColor: colors.raised,
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: colors.line,
  },
  pushBack: { opacity: 0.6 },
  app: {
    width: 32,
    height: 32,
    display: 'grid',
    placeItems: 'center',
    borderRadius: radius.md,
    color: colors.accentFg,
    backgroundColor: colors.accent,
  },
  pushTitle: { fontWeight: 600, fontSize: text.base },
  pushBody: { fontSize: text.md, color: colors.muted },
  pushWhen: { fontFamily: font.mono, fontSize: text.xxs, color: colors.faint, fontVariantNumeric: 'tabular-nums' },
  scramble: { fontFamily: font.mono, fontSize: text.xs, color: colors.faint, overflowWrap: 'anywhere' },
  muted: {
    position: 'absolute',
    inset: 0,
    display: 'grid',
    placeItems: 'center',
    alignContent: 'center',
    gap: space.sm,
    fontSize: text.xs,
    color: colors.warn,
    backgroundColor: `color-mix(in srgb, ${colors.sunk} 88%, transparent)`,
  },
  // what has to be true for pushes to arrive
  checks: { display: 'grid', alignContent: 'start' },
  check: {
    display: 'flex',
    alignItems: 'center',
    gap: space.lg,
    paddingBlock: space.lg,
    paddingInline: space.xxl,
    borderTopWidth: { default: 1, ':first-child': 0 },
    borderTopStyle: 'solid',
    borderTopColor: colors.line,
  },
  mark: {
    width: 28,
    height: 28,
    flexShrink: 0,
    display: 'grid',
    placeItems: 'center',
    borderRadius: radius.md,
    borderWidth: 1,
    borderStyle: 'solid',
  },
  ok: { color: colors.ok, backgroundColor: colors.okSoft, borderColor: `color-mix(in srgb, ${colors.ok} 30%, transparent)` },
  warn: {
    color: colors.warn,
    backgroundColor: colors.warnSoft,
    borderColor: `color-mix(in srgb, ${colors.warn} 35%, transparent)`,
  },
  bad: { color: colors.bad, backgroundColor: colors.badSoft, borderColor: `color-mix(in srgb, ${colors.bad} 35%, transparent)` },
  checkText: { flex: '1', minWidth: 0 },
  checkTitle: { fontWeight: 600 },
  checkSub: { fontSize: text.md, color: colors.muted },
  inline: { display: 'flex', alignItems: 'center', gap: space.sm, flexWrap: 'wrap' },
  stack: { display: 'grid', gap: space.lg, minWidth: 0 },
  steps: { display: 'grid', gap: space.lg, margin: 0, padding: 0, listStyle: 'none' },
  step: { display: 'flex', alignItems: 'baseline', gap: space.lg, color: colors.muted, fontSize: text.base },
  num: {
    width: 22,
    height: 22,
    flexShrink: 0,
    display: 'inline-grid',
    placeItems: 'center',
    borderRadius: radius.xs,
    fontFamily: font.mono,
    fontSize: text.xs,
    fontWeight: 600,
    color: colors.muted,
    backgroundColor: colors.sunk,
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: colors.line2,
  },
  stepsBody: { paddingBlock: space.xl, paddingInline: space.xxl },
});

export function Notifications() {
  const query = useNotifications();
  return (
    <Screen title="Notifications" query={query}>
      {(d) => <NotificationsView d={d} />}
    </Screen>
  );
}

function NotificationsView({ d }: { d: Data }) {
  const act = useAct();
  if (!d.configured)
    return (
      <>
        <PageHead
          eyebrow="bark · off"
          title="Notifications"
          sub="Phone pings when an agent asks you something or a long chat finishes."
        />
        <EmptyCard
          title="Phone pushes are off"
          text="They go through a Bark server (an iPhone app with a small push server). Run one and give the hub its address in BARK_URL (and BARK_PUBLIC for the phone) to turn them on."
          icon="bell"
        />
      </>
    );
  const s = d.settings;
  return (
    <>
      <PageHead
        eyebrow={`bark · ${d.barkUp ? 'up' : 'down'} · ${s.muted ? 'muted' : `watching ${d.watching}/${d.agents}`}`}
        title="Notifications"
        sub="Your iPhone gets a ping when an agent asks you something or waits for approval, and when a chat you started finishes a longer run."
        right={
          <>
            <ActButton label="Send test" icon="send" variant="primary" url="/api/notify/test" />
            <ActButton label={s.muted ? 'Unmute' : 'Mute'} icon="bell" url="/api/notify/mute" />
          </>
        }
      />
      <div {...stylex.props(styles.top)}>
        <Preview d={d} />
        <Card>
          <div {...stylex.props(styles.checks)}>
            <Check
              tone={d.barkUp ? 'ok' : 'bad'}
              title={d.barkUp ? 'Bark server running' : 'Bark server not answering'}
              sub={
                d.barkUp ? 'Pushes leave the server as soon as something happens.' : 'Nothing can be sent until it answers again.'
              }
            />
            <Check
              tone={s.deviceKey ? 'ok' : 'warn'}
              title={s.deviceKey ? 'iPhone linked' : 'No iPhone yet'}
              sub={s.deviceKey ? 'Its device key is saved below.' : 'Paste the device key from the Bark app below.'}
            />
            <Check
              tone={d.watching === d.agents ? 'ok' : 'warn'}
              title={`Watching ${d.watching} of ${plural(d.agents, 'agent')}`}
              sub={
                d.watching === d.agents
                  ? 'Every agent can reach you.'
                  : 'Some agents are not watched yet; they ping once they are up.'
              }
            />
            <Check
              tone={s.muted ? 'warn' : 'ok'}
              title={s.muted ? 'Muted' : 'Not muted'}
              sub={
                s.muted
                  ? 'Nothing is sent until you unmute.'
                  : `"Done" pings after chats longer than ${plural(s.minMinutes, 'minute')}.`
              }
            />
          </div>
        </Card>
      </div>
      <Section title="Settings" icon="sliders">
        <Card>
          <Settings>
            <Setting label="iPhone" help="The device key the Bark app shows. One phone per hub.">
              <SubmitField
                initial={s.deviceKey}
                placeholder="Bark device key"
                button="Save"
                keep
                primary={false}
                onSubmit={(deviceKey) => act('/api/notify/key', { deviceKey })}
              />
            </Setting>
            <Setting label='"Done" ping' help="When a chat you started finishes after a longer run.">
              <div {...stylex.props(styles.inline)}>
                <Text tone="muted">After</Text>
                <SubmitField
                  type="number"
                  initial={String(s.minMinutes)}
                  button="Set"
                  keep
                  primary={false}
                  onSubmit={(minutes) => act('/api/notify/minutes', { minutes })}
                />
                <Text tone="muted">minutes or more</Text>
              </div>
            </Setting>
            <Setting
              label="Encryption"
              help="Pushes pass through Apple. With encryption on, Apple only sees scrambled text. In Bark: Settings → Push encryption, enter these, save."
            >
              <div {...stylex.props(styles.stack)}>
                <div {...stylex.props(styles.inline)}>
                  <Switch on={s.encrypt} label="Encryption" onToggle={() => act('/api/notify/encrypt')} />
                  <Text tone={s.encrypt ? 'ok' : 'muted'} weight="semibold">
                    {s.encrypt ? 'On' : 'Off'}
                  </Text>
                </div>
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
              </div>
            </Setting>
          </Settings>
        </Card>
      </Section>
      <Section title="Set up the iPhone" icon="phone" sub="Three steps, once.">
        <Card>
          <div {...stylex.props(styles.stepsBody)}>
            <ol {...stylex.props(styles.steps)}>
              <Step n={1}>
                Install <b>Bark</b> from the App Store.
              </Step>
              <Step n={2}>
                Servers → + → <Mono>{d.barkPublic || 'your Bark server address'}</Mono>.
              </Step>
              <Step n={3}>Copy the device key it shows, paste it under Settings, then Send test.</Step>
            </ol>
          </div>
        </Card>
      </Section>
      <FeedSection title="Recent pushes" events={d.recent} />
    </>
  );
}

const Step = ({ n, children }: { n: number; children: ReactNode }) => (
  <li {...stylex.props(styles.step)}>
    <span {...stylex.props(styles.num)}>{n}</span>
    <span>{children}</span>
  </li>
);

function Check({ tone, title, sub }: { tone: 'ok' | 'warn' | 'bad'; title: string; sub: string }) {
  return (
    <div {...stylex.props(styles.check)}>
      <span {...stylex.props(styles.mark, styles[tone])}>
        <Icon name={tone === 'ok' ? 'check' : 'alert'} size={16} />
      </span>
      <div {...stylex.props(styles.checkText)}>
        <div {...stylex.props(styles.checkTitle)}>{title}</div>
        <div {...stylex.props(styles.checkSub)}>{sub}</div>
      </div>
    </div>
  );
}

/** What lands on the phone, with the current settings applied. */
function Preview({ d }: { d: Data }) {
  const s = d.settings;
  return (
    <section {...stylex.props(styles.screen)} aria-label="Preview">
      <span {...stylex.props(styles.screenLabel)}>Preview</span>
      <span {...stylex.props(styles.clock)}>9:41</span>
      <div {...stylex.props(styles.push)}>
        <span {...stylex.props(styles.app)}>
          <Icon name="bell" size={17} />
        </span>
        <div>
          <div {...stylex.props(styles.pushTitle)}>Your agent has a question</div>
          <div {...stylex.props(styles.pushBody)}>Which branch should the release go out from?</div>
          {s.encrypt && <div {...stylex.props(styles.scramble)}>Apple sees: 9f2c41e07ab3…</div>}
        </div>
        <span {...stylex.props(styles.pushWhen)}>now</span>
      </div>
      <div {...stylex.props(styles.push, styles.pushBack)}>
        <span {...stylex.props(styles.app)}>
          <Icon name="check" size={17} />
        </span>
        <div>
          <div {...stylex.props(styles.pushTitle)}>Chat finished</div>
          <div {...stylex.props(styles.pushBody)}>Took {s.minMinutes + 6} min · ready for you</div>
        </div>
        <span {...stylex.props(styles.pushWhen)}>12m ago</span>
      </div>
      {s.muted && (
        <div {...stylex.props(styles.muted)}>
          <Icon name="bell" size={18} />
          Muted: nothing is sent
        </div>
      )}
    </section>
  );
}

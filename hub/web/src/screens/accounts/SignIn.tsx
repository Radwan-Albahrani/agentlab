import * as stylex from '@stylexjs/stylex';
import type { ReactNode } from 'react';
import type { AccountsPage, Flow } from '../../api/types';
import { colors, font, media, radius, space, text } from '../../theme/tokens.stylex';
import { CopyButton } from '../../ui/actions';
import { Button } from '../../ui/Button';
import { Icon } from '../../ui/Icon';
import { SubmitField } from '../../ui/inputs';
import { Inline } from '../../ui/layout';
import { Pill } from '../../ui/status';
import { Note } from '../../ui/text';
import { BrandMark, DeviceCode, FlowBox, FlowEnd, LiveEdge, OpenSignInStep, Result, Step, Steps, Terminal } from './flow';
import { useAccountAct } from './useAccountAct';

type Keys = AccountsPage['keys'];

const styles = stylex.create({
  // cells share hairlines: the grid draws the top and left edge, each card its right and bottom
  grid: {
    display: 'grid',
    gridTemplateColumns: { default: 'repeat(2, minmax(0, 1fr))', [media.narrow]: 'minmax(0, 1fr)' },
    borderTopWidth: 1,
    borderTopStyle: 'solid',
    borderTopColor: colors.line,
    borderLeftWidth: 1,
    borderLeftStyle: 'solid',
    borderLeftColor: colors.line,
  },
  card: {
    position: 'relative',
    display: 'flex',
    flexDirection: 'column',
    gap: space.lg,
    padding: { default: space.xxl, [media.phone]: space.lg },
    borderRightWidth: 1,
    borderRightStyle: 'solid',
    borderRightColor: colors.line,
    borderBottomWidth: 1,
    borderBottomStyle: 'solid',
    borderBottomColor: colors.line,
    backgroundColor: colors.panel,
    minWidth: 0,
  },
  // a sign-in in progress takes the whole row
  active: { gridColumnStart: 1, gridColumnEnd: -1, backgroundColor: colors.raised },
  head: { display: 'flex', alignItems: 'flex-start', gap: space.lg, minWidth: 0 },
  who: { flex: '1', minWidth: 0, display: 'grid', gap: space.xxxs },
  nameLine: { display: 'flex', alignItems: 'center', gap: space.sm, flexWrap: 'wrap', minHeight: 24 },
  name: { fontFamily: font.display, fontSize: text.lg, fontWeight: 600 },
  detail: { color: colors.muted, fontSize: text.md, overflowWrap: 'anywhere' },
  detailOk: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: space.xs,
    color: colors.fg,
    fontFamily: font.mono,
    fontSize: text.sm,
  },
  check: { color: colors.ok, display: 'flex' },
  tags: { display: 'flex', gap: space.xxs, flexWrap: 'wrap', marginTop: space.xxs },
  tag: {
    fontSize: text.xxs,
    fontWeight: 500,
    paddingBlock: 1,
    paddingInline: space.xs,
    borderRadius: radius.xs,
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: `color-mix(in srgb, ${colors.ok} 30%, transparent)`,
    color: colors.ok,
    backgroundColor: colors.okSoft,
  },
  foot: {
    display: 'flex',
    alignItems: 'center',
    gap: space.sm,
    flexWrap: 'wrap',
    marginTop: 'auto',
    paddingTop: space.md,
    borderTopWidth: 1,
    borderTopStyle: 'solid',
    borderTopColor: colors.line,
  },
  footNote: { flexBasis: '100%', color: colors.faint, fontSize: text.sm },
  spacer: { flex: '1' },
});

const BLURB: Record<string, string> = {
  claude: 'Claude Code, with your Claude account.',
  codex: 'Codex, with your ChatGPT account.',
  github: 'Clone, push and open pull requests as you.',
  expo: 'Build and publish apps with your Expo account.',
};

/** Provider cards side by side on shared hairlines; one signing in spans the row. */
export const ProviderGrid = ({ children }: { children: ReactNode }) => <div {...stylex.props(styles.grid)}>{children}</div>;

/** `next`: signing in here is the next thing to do, so its button is the amber one. */
export function SignIn({ agent, f, keys, next }: { agent: string; f: Flow; keys: Keys; next?: boolean }) {
  const run = useAccountAct(agent);
  const start = (how?: string) => run({ action: 'start', p: f.key, how });
  const github = f.key === 'github';
  let state: ReactNode;
  let actions: ReactNode;
  if (f.active) {
    state = <Pill tone="info">Signing in…</Pill>;
  } else if (f.signedIn) {
    state = <Pill tone="ok">Signed in</Pill>;
    actions = (
      <>
        <Button label="Switch" icon="refresh" variant="quiet" small onClick={() => start()} />
        <span {...stylex.props(styles.spacer)} />
        <Button
          label="Sign out"
          variant="quiet"
          small
          onClick={() => run({ action: 'logout', p: f.key }, `Sign ${agent} out of ${f.name}?`)}
        />
      </>
    );
  } else {
    state = <Pill>Not signed in</Pill>;
    actions = (
      <>
        <Button label="Sign in" variant={next ? 'primary' : 'default'} onClick={() => start()} />
        {f.key === 'codex' && <Button label="Browser link" variant="quiet" small onClick={() => start('browser')} />}
        {f.key === 'codex' && (
          <span {...stylex.props(styles.footNote)}>Use Browser link if your ChatGPT workspace has device-code login off.</span>
        )}
      </>
    );
  }
  return (
    <article {...stylex.props(styles.card, f.active && styles.active)} aria-label={f.name}>
      {f.active && <LiveEdge />}
      <div {...stylex.props(styles.head)}>
        <BrandMark name={f.key} label={f.name} size="lg" />
        <div {...stylex.props(styles.who)}>
          <div {...stylex.props(styles.nameLine)}>
            <span {...stylex.props(styles.name)}>{f.name}</span>
            {state}
          </div>
          {f.signedIn && f.detail ? (
            <span {...stylex.props(styles.detail, styles.detailOk)}>
              <span {...stylex.props(styles.check)}>
                <Icon name="check" size={15} />
              </span>
              {f.detail}
            </span>
          ) : (
            <span {...stylex.props(styles.detail)}>{BLURB[f.key] ?? f.hint}</span>
          )}
          {github && f.signedIn && f.mcpReady && (
            <span {...stylex.props(styles.tags)}>
              {['git', 'gh', 'MCP'].map((t) => (
                <span key={t} {...stylex.props(styles.tag)}>
                  {t}
                </span>
              ))}
            </span>
          )}
        </div>
      </div>
      {f.active && <SignInSteps agent={agent} f={f} keys={keys} />}
      {github && f.signedIn && !f.mcpReady && !f.active && <GithubToken agent={agent} />}
      {actions && <div {...stylex.props(styles.foot)}>{actions}</div>}
    </article>
  );
}

function SecondStep({ f, send }: { f: Flow; send: (text: string) => unknown }) {
  const now = !!f.url && !f.done;
  if (f.key === 'pool-claude')
    return (
      <Step n={2} done={f.done} now={now} title="Paste the code" sub="Claude shows it after you approve.">
        <SubmitField placeholder="Paste code" button="Submit" onSubmit={send} />
      </Step>
    );
  if ((f.key === 'codex' && f.mode === 'browser') || f.key === 'pool-codex')
    return (
      <Step
        n={2}
        now={now}
        title="Paste the address that fails to load"
        sub={
          <>
            After signing in, ChatGPT sends you to <b>localhost:1455</b> or <b>127.0.0.1:1455</b>, which won&apos;t open. Copy
            that whole address here.
          </>
        }
      >
        <SubmitField placeholder="127.0.0.1:1455/auth/callback?…" button="Finish" onSubmit={send} />
      </Step>
    );
  if (f.key === 'codex' || f.key === 'github' || f.key === 'expo')
    return (
      <Step
        n={2}
        done={f.done}
        now={now}
        title={f.key === 'expo' ? 'Approve if the page shows this code' : 'Enter this code'}
        sub={
          f.key === 'expo'
            ? 'If it then shows a number, pick the same one in the terminal below with ↑ ↓ and Enter.'
            : 'On the page that opens.'
        }
      >
        {f.code ? (
          <Inline gap="md">
            <DeviceCode code={f.code} />
            <CopyButton text={f.code} />
          </Inline>
        ) : (
          <Note>Waiting for the code…</Note>
        )}
      </Step>
    );
  return (
    <Step n={2} now={now} title="Paste the code (if shown)" sub="Some browsers show a code instead of returning.">
      <SubmitField placeholder="Paste code" button="Submit" onSubmit={send} />
    </Step>
  );
}

export function SignInSteps({ agent, f, keys }: { agent: string; f: Flow; keys: Keys }) {
  const run = useAccountAct(agent);
  return (
    <FlowBox>
      <Steps>
        <OpenSignInStep provider={f.name} url={f.url} sub={f.hint} />
        <SecondStep f={f} send={(text) => run({ action: 'send', p: f.key, text })} />
        <Step n={3} done={f.done} last title="Done" sub={`This updates by itself when ${f.name} confirms.`} />
      </Steps>
      <Terminal screen={f.screen}>
        <Inline gap="xs">
          {keys.map((k) => (
            <Button
              key={k.value}
              label={k.label}
              variant="quiet"
              small
              onClick={() => run({ action: 'key', p: f.key, key: k.value })}
            />
          ))}
        </Inline>
      </Terminal>
      <FlowEnd finished={f.done} ok={f.done && <Result ok>Signed in.</Result>} onEnd={() => run({ action: 'stop', p: f.key })} />
    </FlowBox>
  );
}

function GithubToken({ agent }: { agent: string }) {
  const run = useAccountAct(agent);
  return (
    <FlowBox>
      <Note>
        git and gh are signed in. For the GitHub MCP tools, paste a{' '}
        <a
          href={`https://github.com/settings/tokens/new?scopes=repo,read:org,workflow&description=agent-${agent}`}
          target="_blank"
          rel="noopener"
        >
          <u>personal access token</u>
        </a>
        :
      </Note>
      <SubmitField placeholder="ghp_…" button="Save" onSubmit={(token) => run({ action: 'token', p: 'github', token })} />
    </FlowBox>
  );
}

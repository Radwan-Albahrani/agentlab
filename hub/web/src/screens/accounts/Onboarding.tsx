import * as stylex from '@stylexjs/stylex';
import { useState, type ReactNode } from 'react';
import { useParams } from 'react-router';
import { api } from '../../api/client';
import { useAccounts } from '../../api/queries';
import type { AccountsPage } from '../../api/types';
import { Screen } from '../../app/Screen';
import { hueTheme } from '../../theme/hues';
import { agent as agentVars, colors, radius, space, text } from '../../theme/tokens.stylex';
import { Button } from '../../ui/Button';
import { Card } from '../../ui/Card';
import { useAct, useFeedback } from '../../ui/feedback';
import { Icon } from '../../ui/Icon';
import { List } from '../../ui/Row';
import { Badge } from '../../ui/status';
import { AddConnector, ConnectorRow } from './Connectors';
import { SignIn } from './SignIn';

const settle = 'cubic-bezier(0.32, 0.72, 0, 1)';
const still = '@media (prefers-reduced-motion: reduce)';
const rise = stylex.keyframes({ from: { opacity: 0, transform: 'translateY(8px)' }, to: { opacity: 1, transform: 'none' } });
const pop = stylex.keyframes({ from: { transform: 'scale(.6)', opacity: 0 }, to: { transform: 'none', opacity: 1 } });

const styles = stylex.create({
  page: { display: 'grid', gap: space.huge, maxWidth: 720, width: '100%', marginInline: 'auto', minWidth: 0 },
  head: { display: 'grid', justifyItems: 'center', gap: space.md, textAlign: 'center', paddingBlock: space.huge },
  title: { margin: 0, fontSize: text.display, fontWeight: 700, letterSpacing: '-0.02em', textWrap: 'balance' },
  lede: { margin: 0, color: colors.muted, fontSize: text.lg, maxWidth: 520, textWrap: 'pretty' },
  step: {
    display: 'grid',
    gridTemplateColumns: 'auto 1fr',
    gap: space.xxl,
    alignItems: 'start',
    animationName: { default: rise, [still]: 'none' },
    animationDuration: '420ms',
    animationTimingFunction: settle,
    animationFillMode: 'both',
  },
  delay: (n: number) => ({ animationDelay: `${n * 70}ms` }),
  mark: {
    width: 32,
    height: 32,
    borderRadius: radius.pill,
    display: 'grid',
    placeItems: 'center',
    fontWeight: 700,
    fontSize: text.md,
    borderWidth: 1.5,
    borderStyle: 'solid',
    borderColor: colors.line2,
    color: colors.muted,
    backgroundColor: colors.panel,
    transitionProperty: 'background-color, border-color, color',
    transitionDuration: '240ms',
    transitionTimingFunction: settle,
  },
  markDone: {
    backgroundColor: colors.ok,
    borderColor: colors.ok,
    color: colors.onFill,
    animationName: { default: pop, [still]: 'none' },
    animationDuration: '320ms',
    animationTimingFunction: settle,
  },
  body: { display: 'grid', gap: space.md, minWidth: 0 },
  stepHead: { display: 'flex', alignItems: 'baseline', gap: space.sm, flexWrap: 'wrap', paddingTop: space.xs },
  stepTitle: { margin: 0, fontSize: text.lg, fontWeight: 650 },
  optional: { fontSize: text.xs, color: colors.faint, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.06em' },
  stepSub: { margin: 0, color: colors.muted, fontSize: text.base },
  finish: {
    display: 'grid',
    justifyItems: 'center',
    gap: space.md,
    textAlign: 'center',
    paddingBlock: space.huge,
    borderRadius: radius.xxl,
    backgroundColor: `color-mix(in srgb, ${agentVars.hue} 8%, ${colors.panel})`,
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: `color-mix(in srgb, ${agentVars.hue} 22%, transparent)`,
    animationName: { default: rise, [still]: 'none' },
    animationDuration: '420ms',
    animationTimingFunction: settle,
  },
  finishText: { margin: 0, color: colors.muted, maxWidth: 460, textWrap: 'pretty' },
});

export function Onboarding() {
  const { name = '' } = useParams();
  const query = useAccounts(name);
  return (
    <Screen title={`Set up ${name}`} query={query}>
      {(d) => <OnboardingView agent={name} d={d} />}
    </Screen>
  );
}

function Step({
  n,
  done,
  title,
  sub,
  optional,
  children,
}: {
  n: number;
  done: boolean;
  title: string;
  sub: ReactNode;
  optional?: boolean;
  children: ReactNode;
}) {
  return (
    <section {...stylex.props(styles.step, styles.delay(n))} aria-label={title}>
      <span {...stylex.props(styles.mark, done && styles.markDone)} aria-label={done ? 'done' : `step ${n}`}>
        {done ? <Icon name="check" size={16} /> : n}
      </span>
      <div {...stylex.props(styles.body)}>
        <div {...stylex.props(styles.stepHead)}>
          <h2 {...stylex.props(styles.stepTitle)}>{title}</h2>
          {optional && <span {...stylex.props(styles.optional)}>Optional</span>}
        </div>
        <p {...stylex.props(styles.stepSub)}>{sub}</p>
        {children}
      </div>
    </section>
  );
}

function OnboardingView({ agent, d }: { agent: string; d: AccountsPage }) {
  const done = (id: string) => d.onboarding.steps.some((s) => s.id === id && s.done);
  return (
    <div {...stylex.props(hueTheme(agent), styles.page)}>
      <header {...stylex.props(styles.head)}>
        <Badge name={agent} size="xl" />
        <h1 {...stylex.props(styles.title)}>{d.onboarding.done ? `${agent} is ready` : `Set up ${agent}`}</h1>
        <p {...stylex.props(styles.lede)}>
          Your own agent, with your own accounts. Nothing here is shared with anyone else&apos;s agent.
        </p>
      </header>
      <Step
        n={1}
        done={done('claude') || done('codex')}
        title="Sign in to an AI"
        sub="Claude Code or Codex, with your own account. One is enough; add the other any time."
      >
        <Card>
          <List>
            {d.ai.map((f) => (
              <SignIn key={f.key} agent={agent} f={f} keys={d.keys} />
            ))}
          </List>
        </Card>
      </Step>
      <Step
        n={2}
        done={done('connectors')}
        optional
        title="Connect your tools"
        sub="Each connector becomes a tool for both Claude and Codex, like Linear or Notion. One sign-in each."
      >
        <Card>
          <List>
            {d.connectors.map((c) => (
              <ConnectorRow key={c.key} agent={agent} c={c} />
            ))}
            <AddConnector agent={agent} />
          </List>
        </Card>
      </Step>
      <Step n={3} done={done('github')} optional title="GitHub" sub="So the agent can clone, push and open pull requests as you.">
        <Card>
          <List>
            <SignIn agent={agent} f={d.github} keys={d.keys} />
          </List>
        </Card>
      </Step>
      <Finish agent={agent} d={d} />
    </div>
  );
}

function Finish({ agent, d }: { agent: string; d: AccountsPage }) {
  const act = useAct();
  const { toast } = useFeedback();
  const [opening, setOpening] = useState(false);
  const openT3 = async () => {
    setOpening(true);
    try {
      const link = await api.pair(agent, 'browser', 'Browser');
      if (link.available) {
        window.location.assign(link.url);
        return;
      }
      toast(link.reason, true);
    } catch (e) {
      toast((e as Error).message, true);
    }
    setOpening(false);
  };
  if (d.onboarding.done)
    return (
      <div {...stylex.props(styles.finish)}>
        <Icon name="check" size={28} />
        <p {...stylex.props(styles.finishText)}>All set. Open your chat: this browser signs in to it on the way.</p>
        <Button label="Open T3" icon="chat" variant="primary" busy={opening} onClick={openT3} />
      </div>
    );
  return (
    <div {...stylex.props(styles.finish)}>
      <p {...stylex.props(styles.finishText)}>
        {d.onboarding.ready
          ? 'That is all it needs. You can change any of this later.'
          : 'Sign in to Claude Code or Codex to finish.'}
      </p>
      <Button
        label="Finish setup"
        variant="primary"
        disabled={!d.onboarding.ready}
        hint={d.onboarding.ready ? undefined : 'Sign in to an AI first'}
        onClick={() => act(`/api/agents/${agent}/onboarding/finish`)}
      />
    </div>
  );
}

import * as stylex from '@stylexjs/stylex';
import { useState, type ReactNode } from 'react';
import { useParams } from 'react-router';
import { api } from '../../api/client';
import { useAccounts } from '../../api/queries';
import type { AccountsPage } from '../../api/types';
import { Screen } from '../../app/Screen';
import { hueTheme } from '../../theme/hues';
import { colors, font, media, radius, space, text } from '../../theme/tokens.stylex';
import { Button } from '../../ui/Button';
import { useAct, useFeedback } from '../../ui/feedback';
import { Icon } from '../../ui/Icon';
import { Badge } from '../../ui/status';
import { AddConnector, ConnectorGrid, ConnectorTile } from './Connectors';
import { ProviderGrid, SignIn } from './SignIn';

const STEPS = ['AI account', 'Tools', 'GitHub'];

const code = (n: number) => String(n).padStart(2, '0');

const styles = stylex.create({
  page: { display: 'grid', gap: space.giant, maxWidth: 820, width: '100%', marginInline: 'auto', minWidth: 0 },
  head: { display: 'grid', gap: space.xxl },
  headMain: { display: 'flex', alignItems: 'center', gap: space.xl, minWidth: 0 },
  kicker: {
    fontSize: text.xs,
    color: colors.faint,
    fontVariantNumeric: 'tabular-nums',
  },
  title: {
    marginBlockStart: space.xxs,
    marginBlockEnd: space.xs,
    marginInline: 0,
    fontFamily: font.display,
    fontSize: { default: text.display, [media.phone]: text.xxl },
    fontWeight: 600,
    lineHeight: 1.1,
    letterSpacing: '-.01em',
    textWrap: 'balance',
  },
  lede: { margin: 0, color: colors.muted, fontSize: text.body, maxWidth: '62ch', textWrap: 'pretty' },
  // one cell per step on a hairline strip, a 2px edge in its state's colour
  strip: {
    display: 'grid',
    gridTemplateColumns: 'repeat(3, minmax(0, 1fr))',
    gap: 1,
    backgroundColor: colors.line,
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: colors.line,
  },
  cell: {
    display: 'flex',
    alignItems: 'baseline',
    gap: space.sm,
    paddingBlock: space.md,
    paddingInline: space.lg,
    backgroundColor: colors.panel,
    boxShadow: `inset 0 2px 0 ${colors.line2}`,
    fontSize: text.md,
    color: colors.muted,
    minWidth: 0,
  },
  cellNow: { boxShadow: `inset 0 2px 0 ${colors.accent}`, color: colors.fg },
  cellDone: { boxShadow: `inset 0 2px 0 ${colors.ok}` },
  cellCode: { fontFamily: font.mono, fontSize: text.xs, fontWeight: 600, color: colors.faint },
  cellCodeNow: { color: colors.accent },
  cellCodeDone: { color: colors.ok },
  cellLabel: { overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' },

  steps: { display: 'grid' },
  step: {
    display: 'grid',
    gridTemplateColumns: 'auto minmax(0, 1fr)',
    columnGap: { default: space.xxl, [media.phone]: space.lg },
  },
  rail: { display: 'flex', flexDirection: 'column', alignItems: 'center' },
  line: { flex: '1', width: 1, marginBlock: space.sm, backgroundColor: colors.line2 },
  lineDone: { backgroundColor: `color-mix(in srgb, ${colors.ok} 60%, ${colors.line2})` },
  mark: {
    width: 32,
    height: 32,
    flexShrink: 0,
    borderRadius: radius.xs,
    display: 'grid',
    placeItems: 'center',
    fontFamily: font.mono,
    fontWeight: 600,
    fontSize: text.sm,
    fontVariantNumeric: 'tabular-nums',
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: colors.line2,
    color: colors.faint,
    backgroundColor: colors.panel,
    transitionProperty: 'background-color, border-color, color',
    transitionDuration: '140ms',
  },
  // amber: the step to do next
  markNow: { color: colors.accentFg, borderColor: colors.accent, backgroundColor: colors.accent },
  markDone: {
    color: colors.ok,
    borderColor: `color-mix(in srgb, ${colors.ok} 40%, transparent)`,
    backgroundColor: colors.okSoft,
  },
  body: { display: 'grid', gap: space.lg, minWidth: 0, paddingBottom: space.giant },
  bodyLast: { paddingBottom: 0 },
  stepHead: { display: 'grid', gap: space.xxs, paddingTop: space.xxs },
  stepTitleLine: { display: 'flex', alignItems: 'center', gap: space.sm, flexWrap: 'wrap' },
  stepTitle: { margin: 0, fontFamily: font.display, fontSize: text.xl, fontWeight: 600 },
  optional: {
    fontSize: text.xxs,
    color: colors.faint,
    fontWeight: 500,
    paddingBlock: 1,
    paddingInline: space.xs,
    borderRadius: radius.xs,
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: colors.line2,
  },
  stepSub: { margin: 0, color: colors.muted, fontSize: text.base, textWrap: 'pretty' },

  finish: {
    display: 'flex',
    alignItems: 'center',
    gap: space.xl,
    flexWrap: 'wrap',
    paddingBlock: space.xl,
    paddingInline: { default: space.xxl, [media.phone]: space.lg },
    borderRadius: radius.xs,
    backgroundColor: colors.panel,
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: colors.line,
  },
  // ready to finish: the one panel that asks for the person's click
  finishReady: {
    borderColor: `color-mix(in srgb, ${colors.accent} 55%, ${colors.line})`,
    backgroundColor: colors.accentSoft,
  },
  finishWaiting: { borderStyle: 'dashed', borderColor: colors.line2, backgroundColor: 'transparent' },
  finishIcon: {
    width: 36,
    height: 36,
    flexShrink: 0,
    display: 'grid',
    placeItems: 'center',
    borderRadius: radius.xs,
    color: colors.onFill,
    backgroundColor: colors.ok,
  },
  finishMain: { flex: '1', minWidth: 200, display: 'grid', gap: space.xxxs },
  finishTitle: { margin: 0, fontFamily: font.display, fontSize: text.xl, fontWeight: 600 },
  finishText: { margin: 0, color: colors.muted, textWrap: 'pretty' },
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
  now,
  last,
  title,
  sub,
  optional,
  children,
}: {
  n: number;
  done: boolean;
  now: boolean;
  last?: boolean;
  title: string;
  sub: ReactNode;
  optional?: boolean;
  children: ReactNode;
}) {
  return (
    <section {...stylex.props(styles.step)} aria-label={title}>
      <div {...stylex.props(styles.rail)}>
        <span
          {...stylex.props(styles.mark, now && !done && styles.markNow, done && styles.markDone)}
          aria-label={done ? 'done' : `step ${n}`}
        >
          {done ? <Icon name="check" size={16} /> : code(n)}
        </span>
        {!last && <span {...stylex.props(styles.line, done && styles.lineDone)} />}
      </div>
      <div {...stylex.props(styles.body, last && styles.bodyLast)}>
        <div {...stylex.props(styles.stepHead)}>
          <div {...stylex.props(styles.stepTitleLine)}>
            <h2 {...stylex.props(styles.stepTitle)}>{title}</h2>
            {optional && <span {...stylex.props(styles.optional)}>Optional</span>}
          </div>
          <p {...stylex.props(styles.stepSub)}>{sub}</p>
        </div>
        {children}
      </div>
    </section>
  );
}

// its own component: StyleX's compiler can't follow flags computed by a call (marks.indexOf) inside props
function StepCell({ n, now, done }: { n: number; now: boolean; done: boolean }) {
  return (
    <span {...stylex.props(styles.cell, now && styles.cellNow, done && styles.cellDone)}>
      <span {...stylex.props(styles.cellCode, now && styles.cellCodeNow, done && styles.cellCodeDone)}>{code(n + 1)}</span>
      <span {...stylex.props(styles.cellLabel)}>{STEPS[n]}</span>
    </span>
  );
}

function OnboardingView({ agent, d }: { agent: string; d: AccountsPage }) {
  const done = (id: string) => d.onboarding.steps.some((s) => s.id === id && s.done);
  const marks: [boolean, boolean, boolean] = [done('claude') || done('codex'), done('connectors'), done('github')];
  const now = marks.indexOf(false); // the first step still open
  const count = marks.filter(Boolean).length;
  return (
    <div {...stylex.props(hueTheme(agent), styles.page)}>
      <header {...stylex.props(styles.head)}>
        <div {...stylex.props(styles.headMain)}>
          <Badge name={agent} size="xl" />
          <div>
            <div {...stylex.props(styles.kicker)}>
              {`Setup · ${agent} · `}
              {count === marks.length ? 'Every step complete' : `${count} of ${marks.length} steps complete`}
            </div>
            <h1 {...stylex.props(styles.title)}>{d.onboarding.done ? `${agent} is ready` : `Set up ${agent}`}</h1>
            <p {...stylex.props(styles.lede)}>
              Your own agent, with your own accounts. Nothing here is shared with anyone else&apos;s agent.
            </p>
          </div>
        </div>
        <div {...stylex.props(styles.strip)} aria-hidden="true">
          {marks.map((m, i) => (
            <StepCell key={STEPS[i]} n={i} now={now === i} done={m} />
          ))}
        </div>
      </header>
      <div {...stylex.props(styles.steps)}>
        <Step
          n={1}
          done={marks[0]}
          now={now === 0}
          title="Sign in to an AI"
          sub="Claude Code or Codex, with your own account. One is enough; add the other any time."
        >
          <ProviderGrid>
            {d.ai.map((f) => (
              <SignIn key={f.key} agent={agent} f={f} keys={d.keys} next={now === 0} />
            ))}
          </ProviderGrid>
        </Step>
        <Step
          n={2}
          done={marks[1]}
          now={now === 1}
          optional
          title="Connect your tools"
          sub="Each connector becomes a tool for both Claude and Codex, like Linear or Notion. One sign-in each."
        >
          <ConnectorGrid>
            {d.connectors.map((c) => (
              <ConnectorTile key={c.key} agent={agent} c={c} />
            ))}
            <AddConnector agent={agent} />
          </ConnectorGrid>
        </Step>
        <Step
          n={3}
          done={marks[2]}
          now={now === 2}
          last
          optional
          title="GitHub"
          sub="So the agent can clone, push and open pull requests as you."
        >
          <ProviderGrid>
            <SignIn agent={agent} f={d.github} keys={d.keys} next={now === 2} />
          </ProviderGrid>
        </Step>
      </div>
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
        <span {...stylex.props(styles.finishIcon)}>
          <Icon name="check" size={20} />
        </span>
        <div {...stylex.props(styles.finishMain)}>
          <h2 {...stylex.props(styles.finishTitle)}>All set</h2>
          <p {...stylex.props(styles.finishText)}>Open your chat: this browser signs in to it on the way.</p>
        </div>
        <Button label="Open T3" icon="chat" variant="primary" busy={opening} onClick={openT3} />
      </div>
    );
  return (
    <div {...stylex.props(styles.finish, d.onboarding.ready ? styles.finishReady : styles.finishWaiting)}>
      <p {...stylex.props(styles.finishMain, styles.finishText)}>
        {d.onboarding.ready
          ? 'That is all it needs. You can change any of this later.'
          : 'Sign in to Claude Code or Codex to finish.'}
      </p>
      <Button
        label="Finish setup"
        icon="check"
        variant="primary"
        disabled={!d.onboarding.ready}
        hint={d.onboarding.ready ? undefined : 'Sign in to an AI first'}
        onClick={() => act(`/api/agents/${agent}/onboarding/finish`)}
      />
    </div>
  );
}

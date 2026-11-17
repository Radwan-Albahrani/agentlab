import * as stylex from '@stylexjs/stylex';
import type { AccountPool, AccountsPage, PoolAccount, PoolWindow } from '../../api/types';
import { span } from '../../lib/format';
import { useNow } from '../../lib/useNow';
import { colors, font, media, space, text } from '../../theme/tokens.stylex';
import { Button } from '../../ui/Button';
import { MoreMenu } from '../../ui/Menu';
import { Meter, Pill } from '../../ui/status';
import { Note } from '../../ui/text';
import { BrandMark, LiveEdge } from './flow';
import { SignInSteps } from './SignIn';
import { useAccountAct } from './useAccountAct';

const styles = stylex.create({
  // the same shared-hairline grid as the sign-ins above
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
  wide: { gridColumnStart: 1, gridColumnEnd: -1, backgroundColor: colors.raised },
  head: { display: 'flex', alignItems: 'flex-start', gap: space.lg, minWidth: 0 },
  who: { flex: '1', minWidth: 0, display: 'grid', gap: space.xxxs },
  nameLine: { display: 'flex', alignItems: 'center', gap: space.sm, flexWrap: 'wrap', minHeight: 24 },
  name: { fontFamily: font.display, fontSize: text.lg, fontWeight: 600, overflowWrap: 'anywhere' },
  detail: { color: colors.muted, fontSize: text.md, overflowWrap: 'anywhere' },
  problem: { color: colors.bad, fontSize: text.md, overflowWrap: 'anywhere' },
  windows: { display: 'grid', gap: space.md },
  window: { display: 'grid', gap: space.xxs },
  windowLine: { display: 'flex', justifyContent: 'space-between', gap: space.md, fontSize: text.sm },
  windowLabel: { color: colors.fg, fontWeight: 500 },
  windowNote: { color: colors.muted, fontVariantNumeric: 'tabular-nums', textAlign: 'end' },
  intro: { display: 'grid', gap: space.sm, maxWidth: '64ch' },
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
  spacer: { flex: '1' },
});

const PROVIDER = { claude: 'Claude', codex: 'Codex' };

function Window({ w }: { w: PoolWindow }) {
  const now = useNow(30_000);
  const left = w.resetsAt ? w.resetsAt - now : 0;
  return (
    <div {...stylex.props(styles.window)}>
      <div {...stylex.props(styles.windowLine)}>
        <span {...stylex.props(styles.windowLabel)}>{w.label}</span>
        <span {...stylex.props(styles.windowNote)}>
          {`${Math.round(w.used)}% used`}
          {left > 0 && ` · resets in ${span(left)}`}
        </span>
      </div>
      <Meter pct={w.used} label={`${w.label} used`} />
    </div>
  );
}

function AccountCard({ agent, a }: { agent: string; a: PoolAccount }) {
  const run = useAccountAct(agent);
  const act = (action: string, confirm?: string) => run({ action, p: a.name }, confirm);
  let state;
  if (a.problem) state = <Pill tone="bad">Sign in again</Pill>;
  else if (a.disabled) state = <Pill>Paused</Pill>;
  else if (a.current) state = <Pill tone="ok">In use</Pill>;
  else if (a.resting) state = <Pill tone="warn">Resting</Pill>;
  return (
    <article {...stylex.props(styles.card)} aria-label={a.name}>
      <div {...stylex.props(styles.head)}>
        <BrandMark name={a.provider} label={PROVIDER[a.provider]} size="md" />
        <div {...stylex.props(styles.who)}>
          <div {...stylex.props(styles.nameLine)}>
            <span {...stylex.props(styles.name)}>{a.name}</span>
            {state}
          </div>
          {a.problem ? (
            <span {...stylex.props(styles.problem)}>{a.problem}</span>
          ) : (
            <span {...stylex.props(styles.detail)}>{a.resting || PROVIDER[a.provider]}</span>
          )}
        </div>
        <MoreMenu
          label={`${a.name} options`}
          entries={[
            { label: 'Use first', icon: 'arrow', disabled: a.disabled, onSelect: () => act('pool-first') },
            a.disabled
              ? { label: 'Resume', icon: 'power', onSelect: () => act('pool-enable') }
              : { label: 'Pause', icon: 'power', onSelect: () => act('pool-disable') },
          ]}
        />
      </div>
      {a.windows.length > 0 ? (
        <div {...stylex.props(styles.windows)}>
          {a.windows.map((w) => (
            <Window key={w.label} w={w} />
          ))}
        </div>
      ) : (
        !a.problem && <Note>Quota shows after its first use or the next check (every 5 minutes).</Note>
      )}
      <div {...stylex.props(styles.foot)}>
        {a.problem && (
          <Button
            label="Sign in again"
            variant="primary"
            small
            onClick={() => run({ action: 'pool-add', p: `pool-${a.provider}` })}
          />
        )}
        <span {...stylex.props(styles.spacer)} />
        <Button
          label="Sign out"
          variant="quiet"
          small
          onClick={() => act('pool-remove', `Sign ${a.name} out of ${agent}'s account pool?`)}
        />
      </div>
    </article>
  );
}

export function PoolSection({ agent, pool, keys }: { agent: string; pool: AccountPool; keys: AccountsPage['keys'] }) {
  const run = useAccountAct(agent);
  const signing = pool.flows.find((f) => f.active);
  return (
    <>
      <div {...stylex.props(styles.intro)}>
        <Note>
          Extra accounts for this agent only. Before one runs out, T3 and the terminal move to the next without a pause. Claude
          Code still starts on the sign-in above, so keep it; add that same account here too if its quota should count.
        </Note>
      </div>
      <div {...stylex.props(styles.grid)}>
        {pool.accounts.map((a) => (
          <AccountCard key={`${a.provider}:${a.name}`} agent={agent} a={a} />
        ))}
        {signing ? (
          <article {...stylex.props(styles.card, styles.wide)} aria-label={`Add a ${signing.name} account`}>
            <LiveEdge />
            <div {...stylex.props(styles.nameLine)}>
              <BrandMark name={signing.key.replace('pool-', '')} label={signing.name} size="md" />
              <span {...stylex.props(styles.name)}>{`Add a ${signing.name} account`}</span>
              <Pill tone="info">Signing in…</Pill>
            </div>
            <SignInSteps agent={agent} f={signing} keys={keys} />
          </article>
        ) : (
          <article {...stylex.props(styles.card, pool.accounts.length > 0 && styles.wide)} aria-label="Add an account">
            <div {...stylex.props(styles.nameLine)}>
              <Button label="Add Claude account" icon="plus" onClick={() => run({ action: 'pool-add', p: 'pool-claude' })} />
              <Button label="Add Codex account" icon="plus" onClick={() => run({ action: 'pool-add', p: 'pool-codex' })} />
            </div>
          </article>
        )}
      </div>
    </>
  );
}

/** "2 Claude + 1 Codex", or '' when empty. */
export function poolSummary(pool: AccountPool | undefined) {
  const n = (p: string) => pool?.accounts.filter((a) => a.provider === p).length ?? 0;
  return [n('claude') && `${n('claude')} Claude`, n('codex') && `${n('codex')} Codex`].filter(Boolean).join(' + ');
}

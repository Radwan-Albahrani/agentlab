import * as stylex from '@stylexjs/stylex';
import { Link } from 'react-router';
import type { AgentCard as Data } from '../api/types';
import { capitalize, pct } from '../lib/format';
import { hueTheme } from '../theme/hues';
import { agent, colors, motion, radius, space, text } from '../theme/tokens.stylex';
import { LinkButton } from '../ui/Button';
import { Brand, Icon } from '../ui/Icon';
import { Inline, Split, Stack } from '../ui/layout';
import { IconBox, List, Row } from '../ui/Row';
import { Badge, Chip, CompanionAvatar, Dot, Meter, Pill } from '../ui/status';
import { Eyebrow, Text } from '../ui/text';

const styles = stylex.create({
  card: {
    overflow: 'hidden',
    borderRadius: radius.xxl,
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: `color-mix(in srgb, ${agent.hue} 22%, ${colors.line})`,
    backgroundColor: colors.panel,
    boxShadow: colors.shadow,
    minWidth: 0,
  },
  off: { borderColor: colors.line, opacity: 0.75 },
  head: {
    display: 'flex',
    alignItems: 'center',
    gap: space.lg,
    paddingBlock: space.xxl,
    paddingInline: space.xxxl,
    backgroundImage: `linear-gradient(120deg, color-mix(in srgb, ${agent.hue} 20%, transparent), transparent 70%)`,
  },
  name: { fontSize: text.lg, fontWeight: 700, letterSpacing: '-.01em' },
  note: { fontSize: text.sm, color: colors.muted },
  open: { marginInlineStart: 'auto', color: colors.faint, display: 'flex' },
  body: { display: 'grid', gap: space.xxl, paddingBlock: space.xxl, paddingInline: space.xxxl },
  // the four ways into the agent, as equal tiles
  launch: { display: 'grid', gridTemplateColumns: 'repeat(4, minmax(0, 1fr))', gap: space.sm },
  tile: {
    display: 'grid',
    justifyItems: 'center',
    gap: space.xxs,
    paddingBlock: space.md,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: colors.line,
    backgroundColor: { default: colors.raised, ':hover': `color-mix(in srgb, ${agent.hue} 12%, ${colors.raised})` },
    color: { default: colors.fg, ':hover': agent.hue },
    fontSize: text.sm,
    fontWeight: 600,
    transitionProperty: 'background-color, color, transform, border-color',
    transitionDuration: '200ms',
    transitionTimingFunction: motion.settle,
    transform: { default: null, ':hover': 'translateY(-2px)', ':active': 'scale(.96)' },
  },
  tileOff: { opacity: 0.45, cursor: 'not-allowed', transform: 'none', font: 'inherit', fontSize: text.sm, fontWeight: 600 },
});

function readiness(a: Data): string {
  const signed = (k: string) => a.accounts?.find((x) => x.key === k)?.signedIn;
  const ai = ['claude', 'codex'].filter(signed).map(capitalize);
  return ai.length ? `Ready · ${ai.join(' + ')}${signed('github') ? '' : ' · no GitHub'}` : 'No AI account yet';
}

function Tile({ to, icon, label }: { to: string | null; icon: string; label: string }) {
  if (!to)
    return (
      <button
        type="button"
        disabled
        {...stylex.props(styles.tile, styles.tileOff)}
        title="No browser open: the view starts when the agent opens one"
      >
        <Icon name={icon} />
        {label}
      </button>
    );
  return (
    <a href={to} target="_blank" rel="noopener" {...stylex.props(styles.tile)}>
      <Icon name={icon} />
      {label}
    </a>
  );
}

/** The ways into an agent: chat, terminal, files and the live browser view. */
export function Launch({ links }: { links: NonNullable<Data['links']> }) {
  return (
    <div {...stylex.props(styles.launch)}>
      <Tile to={links.chat} icon="chat" label="Chat" />
      <Tile to={links.terminal} icon="terminal" label="Terminal" />
      <Tile to={links.files} icon="files" label="Files" />
      <Tile to={links.browser} icon="browser" label="Browser" />
    </div>
  );
}

/** An agent at a glance. `linked`: the header opens the agent's page; on that page itself the hero takes its place. */
export function AgentCard({ a, linked = true }: { a: Data; linked?: boolean }) {
  const head = (
    <>
      <Badge name={a.name} />
      <div>
        <div {...stylex.props(styles.name)}>{a.name}</div>
        <div {...stylex.props(styles.note)}>{a.online ? readiness(a) : 'Offline: starting or stopped'}</div>
      </div>
      <span {...stylex.props(styles.open)}>
        {a.online ? linked && <Icon name="arrow" size={18} /> : <Pill tone="bad">Offline</Pill>}
      </span>
    </>
  );
  return (
    <div {...stylex.props(hueTheme(a.name), styles.card, !a.online && styles.off)}>
      {linked ? (
        <Link to={`/agents/${a.name}`} {...stylex.props(styles.head)}>
          {head}
        </Link>
      ) : (
        !a.online && <div {...stylex.props(styles.head)}>{head}</div>
      )}
      {a.online && <Details a={a} full={linked} />}
    </div>
  );
}

/** full: also the launch tiles, memory and companions (the agent's own page shows those on their own). */
function Details({ a, full }: { a: Data; full: boolean }) {
  const accounts = `/agents/${a.name}/accounts`;
  const r = a.resources;
  const jobs = r
    ? [r.running.length && `${r.running.length} heavy running`, r.waiting.length && `${r.waiting.length} waiting`]
        .filter(Boolean)
        .join(' · ') || 'idle'
    : '';
  return (
    <div {...stylex.props(styles.body)}>
      {full && a.links && <Launch links={a.links} />}
      {full && r && (
        <Stack gap="xs">
          <Split>
            <Text tone="muted" size="md">
              <b>{(r.usedMB / 1024).toFixed(1)}</b> of {((r.limitMB || 0) / 1024).toFixed(0)} GB memory
            </Text>
            <Text tone="faint" size="md">
              {jobs}
            </Text>
          </Split>
          <Meter pct={pct(r.usedMB, r.limitMB || 1)} />
        </Stack>
      )}
      {full && !!a.companions?.length && (
        <Stack gap="xs">
          <Eyebrow>Companions</Eyebrow>
          <Inline gap="xs">
            {a.companions.map((c) => (
              <Chip key={c.name} avatar to={`/agents/${a.name}/${c.name}`}>
                <CompanionAvatar profile={a.name} size="sm" />
                {c.display}
                <Dot ok={c.live} />
              </Chip>
            ))}
          </Inline>
        </Stack>
      )}
      <Stack gap="xxs">
        <Eyebrow>Accounts</Eyebrow>
        <List>
          {a.accounts?.map((x) => (
            <Row
              key={x.key}
              flat
              lead={
                <IconBox>
                  <Brand name={x.key} />
                </IconBox>
              }
              title={x.label}
              detail={x.signedIn ? x.detail : x.active ? 'Sign-in in progress' : 'Not signed in'}
              actions={
                x.signedIn ? (
                  <Pill tone="ok">Signed in</Pill>
                ) : (
                  <LinkButton
                    label={x.active ? 'Finish' : 'Sign in'}
                    variant={x.active ? 'default' : 'primary'}
                    small
                    to={accounts}
                  />
                )
              }
            />
          ))}
        </List>
      </Stack>
      <Stack gap="xs">
        <Eyebrow>Connectors</Eyebrow>
        <Inline gap="xs">
          {a.connectors?.map((c) =>
            c.signedIn ? (
              <Pill key={c.key} tone="ok">
                <Icon name="check" size={13} />
                {c.name}
              </Pill>
            ) : (
              <Chip key={c.key} warn={c.added} to={accounts}>
                {c.added ? `${c.name} · sign in` : `+ ${c.name}`}
              </Chip>
            ),
          )}
        </Inline>
      </Stack>
    </div>
  );
}

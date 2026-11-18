import * as stylex from '@stylexjs/stylex';
import { Link } from 'react-router';
import type { AgentCard as Data } from '../api/types';
import { capitalize, pct } from '../lib/format';
import { hueTheme } from '../theme/hues';
import { colors, font, radius, space, text } from '../theme/tokens.stylex';
import { LinkButton, Pressable } from '../ui/Button';
import { Brand, Icon } from '../ui/Icon';
import { Inline, Split, Stack } from '../ui/layout';
import { IconBox, List, Row } from '../ui/Row';
import { Badge, Chip, CompanionAvatar, Dot, Meter, Pill } from '../ui/status';
import { Eyebrow, Text } from '../ui/text';

const styles = stylex.create({
  card: {
    overflow: 'hidden',
    borderRadius: radius.xl,
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: colors.line,
    backgroundColor: colors.panel,
    minWidth: 0,
  },
  off: { opacity: 0.7 },
  head: {
    display: 'flex',
    alignItems: 'center',
    gap: space.md,
    paddingBlock: space.md,
    paddingInline: space.xxl,
    backgroundColor: { default: colors.raised, ':hover': colors.hover },
    borderBottomWidth: 1,
    borderBottomStyle: 'solid',
    borderBottomColor: colors.line,

    transitionProperty: 'background-color',
    transitionDuration: '120ms',
  },
  name: { fontFamily: font.display, fontSize: text.lg, fontWeight: 600 },
  note: { fontFamily: font.mono, fontSize: text.xs, color: colors.faint },
  open: { marginInlineStart: 'auto', color: colors.faint, display: 'flex' },
  body: { display: 'grid', gap: space.xl, paddingBlock: space.xl, paddingInline: space.xxl },
  // the four ways into the agent, as one segmented strip
  launch: {
    display: 'grid',
    gridTemplateColumns: 'repeat(4, minmax(0, 1fr))',
    gap: 1,
    backgroundColor: colors.line,
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: colors.line,
    borderRadius: radius.md,
    overflow: 'hidden',
  },
  tile: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: space.xs,
    minHeight: 34,
    borderWidth: 0,
    backgroundColor: { default: colors.raised, ':hover': colors.hover },
    color: { default: colors.fg, ':hover': colors.accent },
    fontFamily: 'inherit',
    fontSize: text.sm,
    fontWeight: 500,
    transitionProperty: 'background-color, color',
    transitionDuration: '120ms',
    outline: { default: 'none', ':focus-visible': `2px solid ${colors.accent}` },
    outlineOffset: -2,
  },
  tileOff: { color: { default: colors.faint, ':hover': colors.faint }, cursor: 'not-allowed' },
  // what most people come for: the T3 app on their phone or computer
  pairTile: { gridColumnStart: 1, gridColumnEnd: -1, minHeight: 40, fontWeight: 600 },
});

function readiness(a: Data): string {
  const signed = (k: string) => a.accounts?.find((x) => x.key === k)?.signedIn;
  const ai = ['claude', 'codex'].filter(signed).map(capitalize);
  return ai.length ? `Ready · ${ai.join(' + ')}${signed('github') ? '' : ' · no GitHub'}` : 'No AI account yet';
}

function Tile({ to, icon, label }: { to: string | null; icon: string; label: string }) {
  if (!to)
    return (
      <Pressable look={[styles.tile, styles.tileOff]} disabled title="No browser open: the view starts when the agent opens one">
        <Icon name={icon} size={15} />
        {label}
      </Pressable>
    );
  return (
    <a href={to} target="_blank" rel="noopener" {...stylex.props(styles.tile)}>
      <Icon name={icon} size={15} />
      {label}
    </a>
  );
}

/** The ways into an agent: pairing the T3 app first (what most people want), then the web chat, terminal, files and
 *  the live browser view. */
export function Launch({ agent, links }: { agent: string; links: NonNullable<Data['links']> }) {
  return (
    <div {...stylex.props(styles.launch)}>
      <Link to={`/agents/${agent}#devices`} {...stylex.props(styles.tile, styles.pairTile)}>
        <Icon name="phone" size={15} />
        Pair a device
      </Link>
      <Tile to={links.chat} icon="chat" label="Web chat" />
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
      {full && a.links && <Launch agent={a.name} links={a.links} />}
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

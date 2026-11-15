import * as stylex from '@stylexjs/stylex';
import type { ReactNode } from 'react';
import type { Container, Stack } from '../api/types';
import { capitalize, plural } from '../lib/format';
import { hueTheme } from '../theme/hues';
import { colors, font, radius, space, text } from '../theme/tokens.stylex';
import { ActButton } from '../ui/actions';
import { Button, LinkButton } from '../ui/Button';
import { Card, DomainHead } from '../ui/Card';
import { EmptyCard } from '../ui/page';
import { IconBox, List, Row } from '../ui/Row';
import { Badge, CompanionAvatar, Tag } from '../ui/status';
import { Mono, Text } from '../ui/text';
import { useLogs } from './logs';
import { useCanSee } from './useCanSee';

const blink = stylex.keyframes({ '50%': { opacity: 0.3 } });

const styles = stylex.create({
  head: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: space.md,
    paddingBlock: space.lg,
    paddingInline: space.xxl,
    flexWrap: 'wrap',
    borderTopWidth: { default: 1, ':first-child': 0 },
    borderTopStyle: 'solid',
    borderTopColor: colors.line,
  },
  companion: {
    marginInlineStart: space.xxl,
    paddingInlineStart: space.xxl,
    borderLeftWidth: 1,
    borderLeftStyle: 'solid',
    borderLeftColor: colors.line,
  },
  who: { display: 'flex', alignItems: 'center', gap: space.md, minWidth: 0 },
  grow: { flex: '1', minWidth: 0 },
  acts: { display: 'flex', gap: space.xs, flexWrap: 'wrap', alignItems: 'center' },
  status: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: space.xs,
    fontFamily: font.mono,
    fontSize: text.xs,
    fontVariantNumeric: 'tabular-nums',
    color: colors.faint,
  },
  uptime: { fontFamily: font.mono, fontSize: text.xs, fontVariantNumeric: 'tabular-nums' },
  // a square status light in a one-step well; a blinking coral block when down
  well: {
    width: 28,
    height: 28,
    flexShrink: 0,
    display: 'grid',
    placeItems: 'center',
    borderRadius: radius.md,
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: colors.line,
    backgroundColor: colors.raised,
  },
  wellBad: { backgroundColor: colors.badSoft, borderColor: `color-mix(in srgb, ${colors.bad} 40%, ${colors.line})` },
  light: { width: 8, height: 8, backgroundColor: colors.ok },
  lightBad: {
    backgroundColor: colors.bad,
    animationName: blink,
    animationDuration: '1.2s',
    animationTimingFunction: 'steps(1)',
    animationIterationCount: 'infinite',
  },
  health: {
    marginInlineStart: space.sm,
    fontFamily: font.mono,
    fontSize: text.xxs,
    fontWeight: 500,
    letterSpacing: '.05em',
    textTransform: 'uppercase',
    paddingBlock: 0,
    paddingInline: space.xs,
    borderRadius: radius.xs,
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: `color-mix(in srgb, ${colors.ok} 30%, transparent)`,
    verticalAlign: 1,
    backgroundColor: colors.okSoft,
    color: colors.ok,
  },
  healthBad: {
    backgroundColor: colors.badSoft,
    color: colors.bad,
    borderColor: `color-mix(in srgb, ${colors.bad} 35%, transparent)`,
  },
  healthIdle: { backgroundColor: colors.idleSoft, color: colors.muted, borderColor: colors.line2 },
  name: { fontFamily: font.display, fontWeight: 600, fontSize: text.body },
});

const isCompanion = (s: { role: string | null }) => !!s.role && s.role !== 'agent';

/** Docker's "Up 2 hours (healthy)" as "up 2 hours" and "healthy"; anything else (Exited (1) …) as it is. */
export function readStatus(c: Container): { uptime: string; health: string } {
  const m = /^Up (.+?)(?: \((?:health: )?([^)]+)\))?$/.exec(c.status);
  if (!m) return { uptime: c.status, health: '' };
  return { uptime: `up ${(m[1] ?? '').toLowerCase()}`, health: m[2] ?? '' };
}

/** Shown until the host watcher has reported container health once. */
export const WATCHER_PENDING = {
  title: 'Waiting for the watcher',
  text: 'Service health appears within a minute.',
  icon: 'clock',
};
export const WatcherPending = () => <EmptyCard {...WATCHER_PENDING} />;

export function StackLead({ stack }: { stack: { profile: string | null; role: string | null } }) {
  if (stack.profile && isCompanion(stack)) return <CompanionAvatar profile={stack.profile} size="sm" />;
  if (stack.profile) return <Badge name={stack.profile} size="sm" />;
  return <IconBox icon="layers" />;
}

export function StackName({ stack }: { stack: { label: string; profile: string | null; role: string | null } }) {
  if (stack.profile && stack.role && isCompanion(stack))
    return (
      <>
        <b {...stylex.props(styles.name)}>{capitalize(stack.role)}</b>
        <Tag>companion</Tag>
      </>
    );
  if (stack.profile)
    return (
      <>
        <b {...stylex.props(styles.name)}>{stack.profile}</b>
        <Tag>agent</Tag>
      </>
    );
  return <b {...stylex.props(styles.name)}>{stack.label}</b>;
}

export const StatusLight = ({ ok }: { ok: boolean }) => (
  <span {...stylex.props(styles.well, !ok && styles.wellBad)}>
    <i {...stylex.props(styles.light, !ok && styles.lightBad)} />
  </span>
);

export function HealthTag({ c }: { c: Container }) {
  const { health } = readStatus(c);
  const word = health || (c.healthy ? '' : c.state);
  if (!word) return null;
  return (
    <span
      {...stylex.props(styles.health, !c.healthy && styles.healthBad, c.healthy && health !== 'healthy' && styles.healthIdle)}
    >
      {word}
    </span>
  );
}

const Status = ({ c }: { c: Container }) => (
  <span {...stylex.props(styles.status)}>
    {readStatus(c).uptime}
    <HealthTag c={c} />
  </span>
);

export function StackHead({
  stack,
  detail,
  actions,
}: {
  stack: { profile: string | null; role: string | null; label: string };
  detail: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <div {...stylex.props(hueTheme(stack.profile), styles.head, isCompanion(stack) && styles.companion)}>
      <div {...stylex.props(styles.who)}>
        <StackLead stack={stack} />
        <div>
          <StackName stack={stack} />
          <div>{detail}</div>
        </div>
      </div>
      {actions && <div {...stylex.props(styles.acts)}>{actions}</div>}
    </div>
  );
}

/** Logs, and Restart (asks first) for anything but Coolify itself. */
export function ContainerActions({ stack, c }: { stack: Stack; c: Container }) {
  const openLogs = useLogs();
  const warn = `Restart ${c.service}? ${
    stack.role === 'agent' ? 'Running agent chats are interrupted (they can be continued).' : 'It is back in a few seconds.'
  }`;
  return (
    <>
      <Button
        label="Logs"
        icon="log"
        small
        onClick={() => {
          openLogs(c.name);
        }}
      />
      {stack.id !== 'coolify' && (
        <ActButton label="Restart" icon="power" small url="/api/services/restart" body={{ name: c.name }} confirm={warn} />
      )}
    </>
  );
}

export function ConfigLink({ stack, iconOnly }: { stack: { id: string }; iconOnly?: boolean }) {
  const canSee = useCanSee();
  if (stack.id === 'coolify' || stack.id === 'other' || !canSee('/config')) return null;
  return <LinkButton label="Config" icon="sliders" variant="quiet" small iconOnly={iconOnly} to={`/config/${stack.id}`} />;
}

export function StackBlock({ stack }: { stack: Stack }) {
  const only = stack.containers.length === 1 ? stack.containers[0] : undefined;
  return (
    <>
      <StackHead
        stack={stack}
        detail={only ? <Status c={only} /> : <Mono>{stack.id}</Mono>}
        actions={
          <>
            {only && <ContainerActions stack={stack} c={only} />}
            <ConfigLink stack={stack} />
          </>
        }
      />
      {!only && <ContainerRows stack={stack} />}
    </>
  );
}

export function ContainerRows({ stack }: { stack: Stack }) {
  return (
    <List>
      {stack.containers.map((c) => (
        <Row
          key={c.name}
          lead={<StatusLight ok={c.healthy} />}
          accent={c.healthy ? undefined : 'bad'}
          title={
            <>
              {c.service}
              <HealthTag c={c} />
            </>
          }
          nestedUnder={isCompanion(stack) ? stack.profile : null}
          detail={
            <>
              <span {...stylex.props(styles.uptime)}>{readStatus(c).uptime}</span>
              {c.image && (
                <>
                  {' · '}
                  <Mono>{c.image}</Mono>
                </>
              )}
            </>
          }
          actions={<ContainerActions stack={stack} c={c} />}
        />
      ))}
    </List>
  );
}

export function DomainCard({
  profile,
  sub,
  actions,
  children,
}: {
  profile: string;
  sub: ReactNode;
  actions?: ReactNode;
  children?: ReactNode;
}) {
  return (
    <Card>
      <DomainHead>
        <Badge name={profile} />
        <div {...stylex.props(styles.grow)}>
          <b {...stylex.props(styles.name)}>{profile}</b>
          <Text block tone="faint" size="md">
            {sub}
          </Text>
        </div>
        <div {...stylex.props(styles.acts)}>
          {actions ?? <LinkButton label="Open" icon="arrow" variant="quiet" small to={`/agents/${profile}`} />}
        </div>
      </DomainHead>
      {children}
    </Card>
  );
}

export const domainSub = (stacks: number) => (stacks > 1 ? `agent + ${plural(stacks - 1, 'companion')}` : 'agent');

/** With one stack of one container, the header carries its actions. */
export function DomainServices({ profile, stacks }: { profile: string; stacks: Stack[] }) {
  const [alone] = stacks;
  const [c] = alone?.containers ?? [];
  if (stacks.length === 1 && alone?.containers.length === 1 && c) {
    return (
      <DomainCard
        profile={profile}
        sub={
          <>
            agent · <Status c={c} />
          </>
        }
        actions={
          <>
            <ContainerActions stack={alone} c={c} />
            <ConfigLink stack={alone} />
            <LinkButton label="Open" icon="arrow" variant="quiet" small to={`/agents/${profile}`} />
          </>
        }
      />
    );
  }
  return (
    <DomainCard profile={profile} sub={domainSub(stacks.length)}>
      {stacks.map((s) => (
        <StackBlock key={s.id} stack={s} />
      ))}
    </DomainCard>
  );
}

import * as stylex from '@stylexjs/stylex';
import type { ReactNode } from 'react';
import type { Container, Stack } from '../api/types';
import { capitalize, plural } from '../lib/format';
import { hueTheme } from '../theme/hues';
import { agent, colors, space, text } from '../theme/tokens.stylex';
import { ActButton } from '../ui/actions';
import { Button, LinkButton } from '../ui/Button';
import { Card, DomainHead } from '../ui/Card';
import { EmptyCard } from '../ui/page';
import { IconBox, List, Row } from '../ui/Row';
import { Badge, CompanionAvatar, Dot, Tag } from '../ui/status';
import { Mono, Text } from '../ui/text';
import { useLogs } from './logs';
import { useCanSee } from './useCanSee';

// Stacks the way Coolify groups them: an agent's domain card holds its own stack and its companions' stacks.

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
    borderLeftWidth: 2,
    borderLeftStyle: 'solid',
    borderLeftColor: `color-mix(in srgb, ${agent.hue} 60%, transparent)`,
  },
  who: { display: 'flex', alignItems: 'center', gap: space.md, minWidth: 0 },
  grow: { flex: '1', minWidth: 0 },
  acts: { display: 'flex', gap: space.xs, flexWrap: 'wrap', alignItems: 'center' },
  status: { display: 'inline-flex', alignItems: 'center', gap: space.xs, fontSize: text.sm, color: colors.faint },
});

const isCompanion = (s: { role: string | null }) => !!s.role && s.role !== 'agent';

/** Shown until the host watcher has reported container health once. */
export const WATCHER_PENDING = {
  title: 'Waiting for the watcher',
  text: 'Service health appears within a minute.',
  icon: 'clock',
};
export const WatcherPending = () => <EmptyCard {...WATCHER_PENDING} />;

/** The face of a stack: agent badge, companion avatar (in the agent's colour), or a plain stack icon. */
export function StackLead({ stack }: { stack: { profile: string | null; role: string | null } }) {
  if (stack.profile && isCompanion(stack)) return <CompanionAvatar profile={stack.profile} size="sm" />;
  if (stack.profile) return <Badge name={stack.profile} size="sm" />;
  return <IconBox icon="layers" />;
}

export function StackName({ stack }: { stack: { label: string; profile: string | null; role: string | null } }) {
  if (stack.profile && stack.role && isCompanion(stack))
    return (
      <>
        <b>{capitalize(stack.role)}</b>
        <Tag>companion</Tag>
      </>
    );
  if (stack.profile)
    return (
      <>
        <b>{stack.profile}</b>
        <Tag>agent</Tag>
      </>
    );
  return <b>{stack.label}</b>;
}

const Status = ({ c }: { c: Container }) => (
  <span {...stylex.props(styles.status)}>
    <Dot ok={c.healthy} />
    {c.status}
  </span>
);

/** A stack's line inside a domain card: who it is, a detail line, and its actions. */
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

function ContainerActions({ stack, c }: { stack: Stack; c: Container }) {
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

export function ConfigLink({ stack }: { stack: { id: string } }) {
  const canSee = useCanSee();
  if (stack.id === 'coolify' || stack.id === 'other' || !canSee('/config')) return null;
  return <LinkButton label="Config" icon="sliders" variant="quiet" small to={`/config/${stack.id}`} />;
}

/** One stack inside a domain card: a single container is one line; bigger stacks list their containers. */
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
          icon="power"
          tone={c.healthy ? 'ok' : 'bad'}
          title={c.service}
          nestedUnder={isCompanion(stack) ? stack.profile : null}
          detail={
            <>
              {c.status} · <Mono>{c.image}</Mono>
            </>
          }
          actions={<ContainerActions stack={stack} c={c} />}
        />
      ))}
    </List>
  );
}

/** An agent's domain: tinted header with its badge, then its stacks. */
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
    <Card agentTop={profile}>
      <DomainHead>
        <Badge name={profile} />
        <div {...stylex.props(styles.grow)}>
          <b>{profile}</b>
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

/** An agent's domain on the Services screen. Alone (one stack, one container) the header carries its actions. */
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

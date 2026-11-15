import * as stylex from '@stylexjs/stylex';
import type { ReactNode } from 'react';
import { Link } from 'react-router';
import { hueTheme } from '../theme/hues';
import { agent, colors, motion, radius, space } from '../theme/tokens.stylex';

const styles = stylex.create({
  card: {
    backgroundColor: colors.panel,
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: colors.line,
    borderRadius: radius.xl,
    boxShadow: colors.shadow,
    minWidth: 0,
    overflow: 'hidden',
  },
  open: { overflow: 'visible' },
  warn: { borderLeftWidth: 3, borderLeftColor: colors.warn },
  bad: { borderLeftWidth: 3, borderLeftColor: colors.bad },
  info: { borderLeftWidth: 3, borderLeftColor: colors.accent },
  agentTop: { borderTopWidth: 3, borderTopColor: agent.hue },
  agentLeft: {
    display: 'flex',
    alignItems: 'center',
    gap: space.lg,
    paddingBlock: space.xl,
    paddingInline: space.xxl,
    backgroundImage: `linear-gradient(100deg, color-mix(in srgb, ${agent.hue} 12%, transparent), transparent 45%)`,
    borderColor: { default: `color-mix(in srgb, ${agent.hue} 25%, ${colors.line})`, ':hover': agent.hue },
    transform: { default: null, ':hover': 'translateY(-2px)', ':active': 'scale(.99)' },
    boxShadow: { default: colors.shadow, ':hover': colors.hoverShadow },
    transitionProperty: 'transform, box-shadow, border-color',
    transitionDuration: '260ms',
    transitionTimingFunction: motion.settle,
  },
  body: { padding: space.xxl, display: 'grid', gap: space.md },
  bodyRoomy: { gap: space.xl },
  domHead: {
    display: 'flex',
    alignItems: 'center',
    gap: space.lg,
    paddingBlock: space.xl,
    paddingInline: space.xxl,
    flexWrap: 'wrap',
    backgroundColor: `color-mix(in srgb, ${agent.hue} 9%, ${colors.panel})`,
  },
  divided: { borderTopWidth: 1, borderTopStyle: 'solid', borderTopColor: colors.line },
});

/** `accent` adds a coloured left edge; `overflow` lets popovers out. */
export function Card({
  accent,
  agentTop,
  overflow,
  children,
}: {
  accent?: 'warn' | 'bad' | 'info';
  agentTop?: string;
  overflow?: boolean;
  children: ReactNode;
}) {
  return (
    <div
      {...stylex.props(
        hueTheme(agentTop),
        styles.card,
        accent && styles[accent],
        !!agentTop && styles.agentTop,
        overflow && styles.open,
      )}
    >
      {children}
    </div>
  );
}

export const CardBody = ({ roomy, divided, children }: { roomy?: boolean; divided?: boolean; children: ReactNode }) => (
  <div {...stylex.props(styles.body, roomy && styles.bodyRoomy, divided && styles.divided)}>{children}</div>
);

export const DomainHead = ({ children }: { children: ReactNode }) => <div {...stylex.props(styles.domHead)}>{children}</div>;

export const AgentLinkCard = ({ profile, to, children }: { profile: string; to: string; children: ReactNode }) => (
  <Link {...stylex.props(hueTheme(profile), styles.card, styles.agentLeft)} to={to}>
    {children}
  </Link>
);

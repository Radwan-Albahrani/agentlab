import * as stylex from '@stylexjs/stylex';
import type { ReactNode } from 'react';
import { Link } from 'react-router';
import { hueTheme } from '../theme/hues';
import { colors, radius, space } from '../theme/tokens.stylex';

const styles = stylex.create({
  card: {
    backgroundColor: colors.panel,
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: colors.line,
    borderRadius: radius.xl,
    minWidth: 0,
    overflow: 'hidden',
  },
  open: { overflow: 'visible' },
  // a whole border in the tone, not a stripe down one edge
  warn: { borderColor: `color-mix(in srgb, ${colors.warn} 55%, ${colors.line})`, backgroundColor: colors.warnSoft },
  bad: { borderColor: `color-mix(in srgb, ${colors.bad} 55%, ${colors.line})`, backgroundColor: colors.badSoft },
  info: { borderColor: `color-mix(in srgb, ${colors.info} 45%, ${colors.line})` },
  agentTop: {},
  agentLeft: {
    display: 'flex',
    alignItems: 'center',
    gap: space.lg,
    paddingBlock: space.lg,
    paddingInline: space.xxl,
    backgroundColor: { default: colors.panel, ':hover': colors.hover },
    borderColor: { default: colors.line, ':hover': colors.line2 },
    transitionProperty: 'background-color, border-color',
    transitionDuration: '140ms',
  },
  body: { padding: space.xxl, display: 'grid', gap: space.md },
  bodyRoomy: { gap: space.xl },
  domHead: {
    display: 'flex',
    alignItems: 'center',
    gap: space.lg,
    paddingBlock: space.lg,
    paddingInline: space.xxl,
    flexWrap: 'wrap',
    backgroundColor: colors.raised,
    borderBottomWidth: 1,
    borderBottomStyle: 'solid',
    borderBottomColor: colors.line,
  },
  divided: { borderTopWidth: 1, borderTopStyle: 'solid', borderTopColor: colors.line },
});

/** A panel on a hairline. `accent` tints it for attention; `overflow` lets popovers out. */
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

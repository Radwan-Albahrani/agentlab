import * as stylex from '@stylexjs/stylex';
import { Fragment, type ReactNode } from 'react';
import { colors, font, space, text } from '../theme/tokens.stylex';

const styles = stylex.create({
  base: { margin: 0, overflowWrap: 'anywhere' },
  muted: { color: colors.muted },
  faint: { color: colors.faint },
  ok: { color: colors.ok },
  bad: { color: colors.bad },
  warn: { color: colors.warn },
  fg: { color: colors.fg },
  xs: { fontSize: text.xs },
  md: { fontSize: text.md },
  body: { fontSize: text.body },
  lg: { fontSize: text.lg },
  semibold: { fontWeight: 600 },
  bold: { fontWeight: 700 },
  mono: { fontFamily: font.mono, fontSize: text.sm },
  eyebrow: {
    fontSize: text.xs,
    fontWeight: 600,
    letterSpacing: '.07em',
    textTransform: 'uppercase',
    color: colors.faint,
    margin: 0,
  },
  big: { fontSize: text.display, fontWeight: 650, letterSpacing: '-.02em', lineHeight: 1.2 },
  mid: { fontSize: text.xl, fontWeight: 600 },
  right: { textAlign: 'right' },
  block: { display: 'block' },
  steps: { margin: 0, paddingInlineStart: space.xxl, color: colors.faint, fontSize: text.md },
  keyValues: {
    display: 'grid',
    gridTemplateColumns: 'auto 1fr',
    rowGap: space.xs,
    columnGap: space.xl,
    fontSize: text.md,
    margin: 0,
  },
  key: { color: colors.faint },
  value: { margin: 0, overflowWrap: 'anywhere' },
});

interface TextProps {
  tone?: 'muted' | 'faint' | 'ok' | 'bad' | 'warn' | 'fg';
  size?: 'xs' | 'md' | 'body' | 'lg';
  weight?: 'semibold' | 'bold';
  mono?: boolean;
  block?: boolean;
  right?: boolean;
  children: ReactNode;
}

/** Inline text. Use block for a paragraph-like line. */
export function Text({ tone, size, weight, mono, block, right, children }: TextProps) {
  const Tag = block ? 'div' : 'span';
  return (
    <Tag
      {...stylex.props(
        styles.base,
        tone && styles[tone],
        size && styles[size],
        weight && styles[weight],
        mono && styles.mono,
        block && styles.block,
        right && styles.right,
      )}
    >
      {children}
    </Tag>
  );
}

export const Note = ({ children }: { children: ReactNode }) => (
  <Text tone="faint" size="md">
    {children}
  </Text>
);
export const Mono = ({ children }: { children: ReactNode }) => <Text mono>{children}</Text>;
export const Eyebrow = ({ children }: { children: ReactNode }) => <div {...stylex.props(styles.eyebrow)}>{children}</div>;
export const BigNumber = ({ children }: { children: ReactNode }) => <div {...stylex.props(styles.big)}>{children}</div>;
export const MidNumber = ({ children }: { children: ReactNode }) => <div {...stylex.props(styles.mid)}>{children}</div>;

/** Numbered how-to steps in small print. */
export const HelpSteps = ({ steps }: { steps: ReactNode[] }) => (
  <ol {...stylex.props(styles.steps)}>
    {steps.map((s, i) => (
      <li key={i}>{s}</li>
    ))}
  </ol>
);

/** Label / value pairs in two columns. */
export const KeyValues = ({ items }: { items: [string, ReactNode][] }) => (
  <dl {...stylex.props(styles.keyValues)}>
    {items.map(([k, v]) => (
      <Fragment key={k}>
        <dt {...stylex.props(styles.key)}>{k}</dt>
        <dd {...stylex.props(styles.value)}>{v}</dd>
      </Fragment>
    ))}
  </dl>
);

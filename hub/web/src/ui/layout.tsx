import * as stylex from '@stylexjs/stylex';
import type { ReactNode } from 'react';
import { space } from '../theme/tokens.stylex';

type Gap = 'xxs' | 'xs' | 'sm' | 'md' | 'lg' | 'xxl';

const gaps = stylex.create({
  xxs: { gap: space.xxs },
  xs: { gap: space.xs },
  sm: { gap: space.sm },
  md: { gap: space.md },
  lg: { gap: space.lg },
  xxl: { gap: space.xxl },
});

const styles = stylex.create({
  stack: { display: 'grid', minWidth: 0 },
  inline: { display: 'flex', alignItems: 'center', flexWrap: 'wrap', minWidth: 0 },
  nowrap: { flexWrap: 'nowrap' },
  end: { justifyContent: 'flex-end' },
  top: { alignItems: 'flex-start' },
  split: { display: 'flex', justifyContent: 'space-between', gap: space.md, alignItems: 'center', flexWrap: 'wrap' },
  baseline: { alignItems: 'baseline' },
  grid2: { display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: space.xxl, alignItems: 'start' },
  stats: { display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: space.lg },
  grow: { flex: '1', minWidth: 0 },
  scroll: { overflowX: 'auto' },
});

export const Stack = ({ gap = 'md', children }: { gap?: Gap; children: ReactNode }) => (
  <div {...stylex.props(styles.stack, gaps[gap])}>{children}</div>
);

export const Inline = ({
  gap = 'sm',
  nowrap,
  end,
  top,
  children,
}: {
  gap?: Gap;
  nowrap?: boolean;
  end?: boolean;
  top?: boolean; // align to the top instead of the middle (a tall item beside text)
  children: ReactNode;
}) => (
  <div {...stylex.props(styles.inline, gaps[gap], nowrap && styles.nowrap, end && styles.end, top && styles.top)}>{children}</div>
);

/** Two ends of a line: title on the left, actions or a number on the right. */
export const Split = ({ baseline, children }: { baseline?: boolean; children: ReactNode }) => (
  <div {...stylex.props(styles.split, baseline && styles.baseline)}>{children}</div>
);

export const Grid2 = ({ children }: { children: ReactNode }) => <div {...stylex.props(styles.grid2)}>{children}</div>;
export const StatGrid = ({ children }: { children: ReactNode }) => <div {...stylex.props(styles.stats)}>{children}</div>;
export const Grow = ({ children }: { children: ReactNode }) => <div {...stylex.props(styles.grow)}>{children}</div>;
export const HScroll = ({ children }: { children: ReactNode }) => <div {...stylex.props(styles.scroll)}>{children}</div>;
/** Pushes what follows to the end of a row. */
export const Spacer = () => <span {...stylex.props(styles.grow)} />;

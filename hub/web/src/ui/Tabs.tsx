import * as stylex from '@stylexjs/stylex';
import { Tabs as Root, TabsIndicator, TabsList, TabsPanel, TabsTab } from '@ui-sdk/react/tabs';
import type { ReactNode } from 'react';
import { colors, font, motion, radius, space, text } from '../theme/tokens.stylex';
import { Icon } from './Icon';

const styles = stylex.create({
  // minWidth 0: on phones the tab list scrolls instead of widening the page
  root: { display: 'grid', gap: space.lg, minWidth: 0 },
  bar: { minWidth: 0, position: 'sticky', top: 0, zIndex: 20, paddingBlock: space.sm, backgroundColor: colors.bg },
  list: {
    position: 'relative',
    display: 'inline-flex',
    maxWidth: '100%',
    overflowX: 'auto',
    scrollbarWidth: 'none',
    gap: space.xxxs,
    padding: space.xxxs,
    borderRadius: radius.md,
    backgroundColor: colors.sunk,
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: colors.line,
  },
  // a fill step behind the selected tab, measured by UI SDK into --active-tab-*
  indicator: {
    position: 'absolute',
    zIndex: 0,
    top: 'var(--active-tab-top)',
    left: 'var(--active-tab-left)',
    width: 'var(--active-tab-width)',
    height: 'var(--active-tab-height)',
    borderRadius: radius.sm,
    backgroundColor: colors.raised,
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: colors.line2,
    transitionProperty: { default: 'left, width', [motion.still]: 'none' },
    transitionDuration: '160ms',
    transitionTimingFunction: motion.settle,
  },
  tab: {
    position: 'relative',
    zIndex: 1,
    appearance: 'none',
    borderWidth: 0,
    backgroundColor: 'transparent',
    display: 'inline-flex',
    alignItems: 'center',
    gap: space.sm,
    paddingBlock: space.xs,
    paddingInline: space.lg,
    borderRadius: radius.sm,
    fontSize: text.base,
    fontWeight: { default: 500, ':is([data-selected])': 600 },
    whiteSpace: 'nowrap',
    cursor: 'pointer',
    color: { default: colors.muted, ':hover': colors.fg, ':is([data-selected])': colors.fg },
    transitionProperty: 'color',
    transitionDuration: '120ms',
    outline: { default: 'none', ':focus-visible': `2px solid ${colors.accent}` },
    outlineOffset: 2,
  },
  count: { fontFamily: font.mono, fontSize: text.xs, color: colors.faint, fontVariantNumeric: 'tabular-nums' },
  alert: {
    minWidth: 18,
    height: 18,
    paddingInline: space.xxs,
    borderRadius: radius.pill,
    display: 'inline-grid',
    placeItems: 'center',
    fontFamily: font.mono,
    fontSize: text.xxs,
    fontWeight: 600,
    color: colors.accentFg,
    backgroundColor: colors.accent,
  },
  panel: {
    display: 'grid',
    gap: space.huge,
    minWidth: 0,
    outline: 'none',
    transitionProperty: 'opacity',
    transitionDuration: '140ms',
    opacity: { default: 1, ':is([data-starting-style])': 0 },
  },
});

export interface TabItem {
  value: string;
  label: string;
  icon?: string;
  count?: number;
  alert?: boolean; // shows the count as a red badge
  content: ReactNode;
}

export function Tabs({
  items,
  value,
  onChange,
  label,
}: {
  items: TabItem[];
  value: string;
  onChange: (value: string) => void;
  label: string;
}) {
  return (
    <Root
      value={value}
      onValueChange={(v) => {
        if (v !== null) onChange(v);
      }}
      {...stylex.props(styles.root)}
    >
      <div {...stylex.props(styles.bar)}>
        <TabsList {...stylex.props(styles.list)} aria-label={label}>
          <TabsIndicator {...stylex.props(styles.indicator)} />
          {items.map((t) => (
            <TabsTab key={t.value} value={t.value} {...stylex.props(styles.tab)}>
              {t.icon && <Icon name={t.icon} size={16} />}
              <span>{t.label}</span>
              {!!t.count && <span {...stylex.props(t.alert ? styles.alert : styles.count)}>{t.count}</span>}
            </TabsTab>
          ))}
        </TabsList>
      </div>
      {items.map((t) => (
        <TabsPanel key={t.value} value={t.value} {...stylex.props(styles.panel)}>
          {t.content}
        </TabsPanel>
      ))}
    </Root>
  );
}

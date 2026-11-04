import * as stylex from '@stylexjs/stylex';
import { Tabs as Base } from '@base-ui/react/tabs';
import type { ReactNode } from 'react';
import { colors, radius, space, text } from '../theme/tokens.stylex';
import { Icon } from './Icon';

const cls = (...s: stylex.StyleXStyles[]) => stylex.props(...s).className ?? '';

const settle = 'cubic-bezier(0.32, 0.72, 0, 1)';
const still = '@media (prefers-reduced-motion: reduce)';
const rise = stylex.keyframes({ from: { opacity: 0, transform: 'translateY(6px)' }, to: { opacity: 1, transform: 'none' } });

const styles = stylex.create({
  // minWidth 0: on phones the tab list scrolls instead of widening the page
  root: { display: 'grid', gap: space.lg, minWidth: 0 },
  bar: {
    minWidth: 0,
    position: 'sticky',
    top: 0,
    zIndex: 20,
    paddingBlock: space.sm,
    backgroundColor: `color-mix(in srgb, ${colors.bg} 78%, transparent)`,
    backdropFilter: 'saturate(180%) blur(14px)',
  },
  list: {
    position: 'relative',
    display: 'inline-flex',
    maxWidth: '100%',
    overflowX: 'auto',
    scrollbarWidth: 'none',
    gap: 2,
    padding: 3,
    borderRadius: radius.lg,
    backgroundColor: colors.sunk,
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: colors.line,
  },
  indicator: {
    position: 'absolute',
    zIndex: 0,
    top: 'var(--active-tab-top)',
    left: 'var(--active-tab-left)',
    width: 'var(--active-tab-width)',
    height: 'var(--active-tab-height)',
    borderRadius: radius.md,
    backgroundColor: colors.panel,
    boxShadow: colors.liftShadow,
    transitionProperty: { default: 'left, width', [still]: 'none' },
    transitionDuration: '320ms',
    transitionTimingFunction: settle,
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
    paddingBlock: space.sm,
    paddingInline: space.lg,
    borderRadius: radius.md,
    fontSize: text.base,
    fontWeight: 550,
    whiteSpace: 'nowrap',
    cursor: 'pointer',
    color: { default: colors.muted, ':hover': colors.fg },
    transition: 'color .2s',
    outline: { default: 'none', ':focus-visible': `2px solid color-mix(in srgb, ${colors.accent} 55%, transparent)` },
  },
  selected: { color: colors.fg, fontWeight: 650 },
  count: { fontSize: text.xs, fontWeight: 600, color: colors.faint, fontVariantNumeric: 'tabular-nums' },
  alert: {
    minWidth: 18,
    height: 18,
    paddingInline: 5,
    borderRadius: radius.pill,
    display: 'inline-grid',
    placeItems: 'center',
    fontSize: text.xxs,
    fontWeight: 700,
    color: colors.onFill,
    backgroundColor: colors.bad,
  },
  panel: {
    display: 'grid',
    gap: space.huge,
    minWidth: 0,
    outline: 'none',
    animationName: { default: rise, [still]: 'none' },
    animationDuration: '280ms',
    animationTimingFunction: settle,
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
    <Base.Root
      value={value}
      onValueChange={(v) => {
        onChange(String(v));
      }}
      {...stylex.props(styles.root)}
    >
      <div {...stylex.props(styles.bar)}>
        <Base.List {...stylex.props(styles.list)} aria-label={label}>
          {items.map((t) => (
            <Base.Tab key={t.value} value={t.value} className={(s) => cls(styles.tab, s.active && styles.selected)}>
              {t.icon && <Icon name={t.icon} size={16} />}
              <span>{t.label}</span>
              {!!t.count && <span {...stylex.props(t.alert ? styles.alert : styles.count)}>{t.count}</span>}
            </Base.Tab>
          ))}
          <Base.Indicator {...stylex.props(styles.indicator)} />
        </Base.List>
      </div>
      {items.map((t) => (
        <Base.Panel key={t.value} value={t.value} {...stylex.props(styles.panel)}>
          {t.content}
        </Base.Panel>
      ))}
    </Base.Root>
  );
}

import * as stylex from '@stylexjs/stylex';
import { Link, useLocation } from 'react-router';
import { colors, media, radius, space, text } from '../theme/tokens.stylex';
import { Count } from '../ui/status';
import { isActive, type Menu } from './menu';
import { ThemeToggle } from './ThemeToggle';

const styles = stylex.create({
  bar: {
    display: { default: 'none', [media.nav]: 'flex' },
    alignItems: 'center',
    position: 'sticky',
    top: 0,
    zIndex: 20,
    gap: space.xs,
    backgroundColor: `color-mix(in srgb, ${colors.bg} 88%, transparent)`,
    backdropFilter: 'blur(12px)',
    borderBottomWidth: 1,
    borderBottomStyle: 'solid',
    borderBottomColor: colors.line,
    paddingBlock: space.md,
    paddingInline: `max(${space.lg}, env(safe-area-inset-left))`,
  },
  pills: { display: 'flex', gap: space.xs, flexGrow: 1, minWidth: 0, overflowX: 'auto', scrollbarWidth: 'none' },
  pill: {
    display: 'flex',
    alignItems: 'center',
    gap: space.xs,
    paddingBlock: space.sm,
    paddingInline: space.lg,
    borderRadius: radius.pill,
    whiteSpace: 'nowrap',
    color: colors.muted,
    fontWeight: 600,
    fontSize: text.base,
  },
  on: { backgroundColor: colors.fg, color: colors.bg },
});

/** The phone top bar: one scrollable row of menu pills, then the theme toggle. */
export function PhoneNav({ menu }: { menu: Menu }) {
  const { pathname } = useLocation();
  return (
    <div {...stylex.props(styles.bar)}>
      <nav {...stylex.props(styles.pills)} aria-label="Main">
        {[...menu.main, ...menu.agents, ...menu.system].map((i) => (
          <Link key={i.to} to={i.to} {...stylex.props(styles.pill, isActive(i, pathname) && styles.on)}>
            {i.short ?? i.label}
            {i.count ? <Count n={i.count} /> : null}
          </Link>
        ))}
      </nav>
      <ThemeToggle />
    </div>
  );
}

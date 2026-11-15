import * as stylex from '@stylexjs/stylex';
import { useState } from 'react';
import { Link, useLocation } from 'react-router';
import { hueTheme } from '../theme/hues';
import { colors, media, motion, radius, space, text } from '../theme/tokens.stylex';
import { Overlay } from '../ui/Dialog';
import { Icon } from '../ui/Icon';
import { Badge, Count, Dot } from '../ui/status';
import { isActive, type Menu, type MenuItem } from './menu';
import { openPalette } from './Palette';
import { ThemeToggle } from './ThemeToggle';

const rise = stylex.keyframes({ from: { transform: 'translateY(100%)' }, to: { transform: 'none' } });
const fade = stylex.keyframes({ from: { opacity: 0 } });

const styles = stylex.create({
  top: {
    display: { default: 'none', [media.nav]: 'flex' },
    alignItems: 'center',
    gap: space.sm,
    position: 'sticky',
    top: 0,
    zIndex: 20,
    backgroundColor: `color-mix(in srgb, ${colors.bg} 80%, transparent)`,
    backdropFilter: 'saturate(180%) blur(16px)',
    borderBottomWidth: 1,
    borderBottomStyle: 'solid',
    borderBottomColor: colors.line,
    paddingBlock: space.sm,
    paddingInline: `max(${space.lg}, env(safe-area-inset-left))`,
  },
  brand: { fontWeight: 700, fontSize: text.lg, letterSpacing: '-.02em', marginInlineEnd: 'auto' },
  iconBtn: {
    display: 'grid',
    placeItems: 'center',
    width: 36,
    height: 36,
    borderRadius: radius.md,
    borderWidth: 0,
    backgroundColor: { default: 'transparent', ':active': colors.hover },
    color: colors.muted,
    cursor: 'pointer',
  },
  tabs: {
    display: { default: 'none', [media.nav]: 'grid' },
    gridTemplateColumns: 'repeat(4, 1fr)',
    position: 'fixed',
    insetInline: 0,
    bottom: 0,
    zIndex: 30,
    paddingBlockStart: space.xs,
    paddingBlockEnd: `max(${space.xs}, env(safe-area-inset-bottom))`,
    backgroundColor: `color-mix(in srgb, ${colors.panel} 82%, transparent)`,
    backdropFilter: 'saturate(180%) blur(20px)',
    borderTopWidth: 1,
    borderTopStyle: 'solid',
    borderTopColor: colors.line,
  },
  tab: {
    position: 'relative',
    display: 'grid',
    justifyItems: 'center',
    gap: 2,
    paddingBlock: space.xs,
    borderWidth: 0,
    backgroundColor: 'transparent',
    color: colors.faint,
    font: 'inherit',
    fontSize: text.xxs,
    fontWeight: 600,
    cursor: 'pointer',
    transitionProperty: 'color, transform',
    transitionDuration: '160ms',
    transform: { default: null, ':active': 'scale(.92)' },
  },
  tabOn: { color: colors.accent },
  badge: { position: 'absolute', top: 0, insetInlineStart: 'calc(50% + 6px)' },
  backdrop: {
    position: 'fixed',
    inset: 0,
    zIndex: 40,
    backgroundColor: colors.overlay,
    animationName: fade,
    animationDuration: '200ms',
  },
  sheet: {
    position: 'fixed',
    insetInline: 0,
    bottom: 0,
    zIndex: 41,
    maxHeight: '82vh',
    overflowY: 'auto',
    paddingBlockStart: space.sm,
    paddingBlockEnd: `max(${space.xxl}, env(safe-area-inset-bottom))`,
    paddingInline: space.lg,
    borderStartStartRadius: radius.xxl,
    borderStartEndRadius: radius.xxl,
    backgroundColor: colors.panel,
    boxShadow: colors.popShadow,
    outline: 'none',
    animationName: rise,
    animationDuration: '320ms',
    animationTimingFunction: motion.settle,
  },
  grabber: {
    width: 40,
    height: 5,
    borderRadius: radius.pill,
    backgroundColor: colors.line2,
    marginInline: 'auto',
    marginBlockEnd: space.md,
  },
  group: {
    paddingBlockStart: space.lg,
    paddingBlockEnd: space.xs,
    paddingInline: space.md,
    fontSize: text.xxs,
    fontWeight: 650,
    letterSpacing: '.07em',
    textTransform: 'uppercase',
    color: colors.faint,
  },
  item: {
    display: 'flex',
    alignItems: 'center',
    gap: space.md,
    paddingBlock: space.md,
    paddingInline: space.md,
    borderRadius: radius.lg,
    fontWeight: 550,
    backgroundColor: { default: 'transparent', ':active': colors.hover },
  },
  itemOn: { backgroundColor: colors.accentSoft, color: colors.accent },
  nested: { paddingInlineStart: space.huge },
  end: { marginInlineStart: 'auto', display: 'flex' },
  mark: { display: 'flex', color: colors.muted },
});

function Mark({ item }: { item: MenuItem }) {
  const m = item.mark;
  if ('agent' in m) return <Badge name={m.agent} size="sm" />;
  return (
    <span {...stylex.props(hueTheme('companionOf' in m ? m.companionOf : null), styles.mark)}>
      <Icon name={'icon' in m ? m.icon : 'bot'} />
    </span>
  );
}

/** Phones: a slim bar on top, and tabs at the bottom where a thumb reaches (Overview, Agents, Search, Menu). */
export function PhoneNav({ menu }: { menu: Menu }) {
  const { pathname } = useLocation();
  const [sheet, setSheet] = useState(false);
  const home = menu.main[0];
  const agents = menu.agents[0];
  const all = [...menu.main, ...menu.agents, ...menu.system];
  const waiting = all.reduce((n, i) => n + (i.count ?? 0), 0) - (home?.count ?? 0);
  return (
    <>
      <div {...stylex.props(styles.top)}>
        <Link to="/" {...stylex.props(styles.brand)}>
          Agents
        </Link>
        <button type="button" {...stylex.props(styles.iconBtn)} onClick={openPalette} aria-label="Search">
          <Icon name="search" />
        </button>
        <ThemeToggle />
      </div>
      <nav {...stylex.props(styles.tabs)} aria-label="Main">
        {home && (
          <Link to={home.to} {...stylex.props(styles.tab, isActive(home, pathname) && styles.tabOn)}>
            <Icon name="home" size={22} />
            Overview
            {!!home.count && (
              <span {...stylex.props(styles.badge)}>
                <Count n={home.count} />
              </span>
            )}
          </Link>
        )}
        {agents && (
          <Link to={agents.to} {...stylex.props(styles.tab, pathname.startsWith('/agents') && !sheet && styles.tabOn)}>
            <Icon name="agents" size={22} />
            Agents
          </Link>
        )}
        <button type="button" {...stylex.props(styles.tab)} onClick={openPalette}>
          <Icon name="search" size={22} />
          Search
        </button>
        <button
          type="button"
          {...stylex.props(styles.tab, sheet && styles.tabOn)}
          onClick={() => {
            setSheet(true);
          }}
        >
          <Icon name="more" size={22} />
          Menu
          {waiting > 0 && (
            <span {...stylex.props(styles.badge)}>
              <Count n={waiting} />
            </span>
          )}
        </button>
      </nav>
      <Overlay open={sheet} onOpenChange={setSheet} label="Menu" backdrop={styles.backdrop} popup={styles.sheet}>
        <div {...stylex.props(styles.grabber)} />
        {(
          [
            ['', menu.main],
            ['Agents', menu.agents],
            ['System', menu.system],
          ] as const
        ).map(
          ([title, items]) =>
            items.length > 0 && (
              <div key={title}>
                {title && <div {...stylex.props(styles.group)}>{title}</div>}
                {items.map((i) => (
                  <Link
                    key={i.to}
                    to={i.to}
                    onClick={() => {
                      setSheet(false);
                    }}
                    {...stylex.props(
                      styles.item,
                      'companionOf' in i.mark && styles.nested,
                      isActive(i, pathname) && styles.itemOn,
                    )}
                  >
                    <Mark item={i} />
                    {i.label}
                    <span {...stylex.props(styles.end)}>
                      {i.count ? <Count n={i.count} /> : i.dot !== undefined ? <Dot ok={i.dot} /> : null}
                    </span>
                  </Link>
                ))}
              </div>
            ),
        )}
      </Overlay>
    </>
  );
}

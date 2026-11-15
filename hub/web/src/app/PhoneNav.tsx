import * as stylex from '@stylexjs/stylex';
import { useState } from 'react';
import { Link, useLocation } from 'react-router';
import { hueTheme } from '../theme/hues';
import { colors, media, radius, space, text } from '../theme/tokens.stylex';
import { Sheet } from '../ui/Dialog';
import { Icon } from '../ui/Icon';
import { Badge, Count, Dot } from '../ui/status';
import { isActive, type Menu, type MenuItem } from './menu';
import { openPalette } from './Palette';
import { ThemeToggle } from './ThemeToggle';
import { Pressable } from '../ui/Button';

const styles = stylex.create({
  top: {
    display: { default: 'none', [media.nav]: 'flex' },
    alignItems: 'center',
    gap: space.sm,
    position: 'sticky',
    top: 0,
    zIndex: 20,
    backgroundColor: colors.bg,
    borderBottomWidth: 1,
    borderBottomStyle: 'solid',
    borderBottomColor: colors.line,
    paddingBlock: space.sm,
    paddingInline: `max(${space.lg}, env(safe-area-inset-left))`,
  },
  brand: {
    fontSize: text.xs,
    fontWeight: 600,
    marginInlineEnd: 'auto',
  },
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
    backgroundColor: colors.panel,
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
  group: {
    paddingBlockStart: space.lg,
    paddingBlockEnd: space.xs,
    paddingInline: space.md,
    fontSize: text.xxs,
    fontWeight: 650,
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
        <Pressable look={styles.iconBtn} onClick={openPalette} label="Search">
          <Icon name="search" />
        </Pressable>
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
        <Pressable look={styles.tab} onClick={openPalette}>
          <Icon name="search" size={22} />
          Search
        </Pressable>
        <Pressable
          look={[styles.tab, sheet && styles.tabOn]}
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
        </Pressable>
      </nav>
      <Sheet open={sheet} onOpenChange={setSheet} label="Menu">
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
      </Sheet>
    </>
  );
}

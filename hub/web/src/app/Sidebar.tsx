import * as stylex from '@stylexjs/stylex';
import type { MouseEvent } from 'react';
import { Link, useLocation } from 'react-router';
import { useNav, useNowBoard } from '../api/queries';
import { useNow } from '../lib/useNow';
import { hueTheme } from '../theme/hues';
import { agent, colors, font, media, radius, space, text } from '../theme/tokens.stylex';
import { Icon } from '../ui/Icon';
import { Badge, Count, Dot } from '../ui/status';
import { isActive, type Menu, type MenuItem } from './menu';
import { openPalette } from './Palette';
import { ThemeToggle } from './ThemeToggle';

const blink = stylex.keyframes({ '50%': { opacity: 0.2 } });

const styles = stylex.create({
  side: {
    position: 'sticky',
    top: 0,
    height: '100vh',
    paddingBlock: space.xxl,
    paddingInline: space.md,
    backgroundColor: colors.panel,
    overflow: 'auto',
    borderRightWidth: 1,
    borderRightStyle: 'solid',
    borderRightColor: colors.line,
    display: { default: 'flex', [media.nav]: 'none' },
    flexDirection: 'column',
    gap: space.lg,
  },
  brand: {
    display: 'flex',
    alignItems: 'center',
    gap: space.sm,
    paddingInline: space.sm,
    paddingBlockEnd: space.xs,
    fontSize: text.xs,
    color: colors.faint,
  },
  logo: {
    width: 22,
    height: 22,
    borderRadius: radius.sm,
    backgroundColor: colors.accent,
    color: colors.accentFg,
    display: 'grid',
    placeItems: 'center',
    userSelect: 'none',
    cursor: 'default',
  },
  brandName: { color: colors.fg, fontWeight: 600 },
  nav: { display: 'grid', gap: 1 },
  group: {
    fontSize: text.xxs,
    color: colors.faint,
    paddingBlockStart: space.xl,
    paddingBlockEnd: space.xs,
    paddingInline: space.md,
  },
  link: {
    position: 'relative',
    display: 'flex',
    alignItems: 'center',
    gap: space.md,
    paddingBlock: space.xs,
    paddingInline: space.md,
    minHeight: 32,
    borderRadius: radius.sm,
    fontSize: text.base,
    color: { default: colors.muted, ':hover': colors.fg },
    backgroundColor: { default: null, ':hover': colors.hover },
    transitionProperty: 'background-color, color',
    transitionDuration: '120ms',
    outline: { default: 'none', ':focus-visible': `2px solid ${colors.accent}` },
    outlineOffset: -2,
  },
  // the current page: one fill step and a heavier weight
  on: {
    color: { default: colors.fg, ':hover': colors.fg },
    backgroundColor: { default: colors.raised, ':hover': colors.raised },
    fontWeight: 600,
  },
  nested: { paddingInlineStart: 36 },
  companionIcon: { color: agent.hue, display: 'flex' },
  end: { marginInlineStart: 'auto', display: 'flex', alignItems: 'center' },
  note: { fontFamily: font.mono, fontSize: text.xs, color: colors.faint },
  bottom: {
    marginTop: 'auto',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: space.md,
    paddingBlockStart: space.md,
    borderTopWidth: 1,
    borderTopStyle: 'solid',
    borderTopColor: colors.line,
  },
  foot: {
    fontSize: text.xxs,
    color: colors.faint,
    paddingInline: space.sm,
    display: 'flex',
    alignItems: 'center',
    gap: space.sm,
  },
  liveDot: {
    width: 7,
    height: 7,
    backgroundColor: colors.ok,
    animationName: blink,
    animationDuration: '2s',
    animationIterationCount: 'infinite',
  },
  lostDot: { backgroundColor: colors.warn, animationName: 'none' },
  search: {
    display: 'flex',
    alignItems: 'center',
    gap: space.sm,
    width: '100%',
    minHeight: 32,
    paddingInline: space.md,
    borderRadius: radius.md,
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: { default: colors.line, ':hover': colors.line2 },
    backgroundColor: { default: colors.sunk, ':hover': colors.hover },
    color: colors.faint,
    fontFamily: 'inherit',
    fontSize: text.base,
    cursor: 'pointer',
    transitionProperty: 'background-color, border-color',
    transitionDuration: '120ms',
    outline: { default: 'none', ':focus-visible': `2px solid ${colors.accent}` },
  },
  kbd: {
    marginInlineStart: 'auto',
    fontFamily: font.mono,
    fontSize: text.xxs,
    paddingBlock: 1,
    paddingInline: space.xs,
    borderRadius: radius.xs,
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: colors.line2,
    backgroundColor: colors.panel,
  },
  // running: a steel count beside a blinking block; waiting on you: an amber count
  busy: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: space.xs,
    fontFamily: font.mono,
    fontSize: text.xs,
    color: colors.info,
  },
  block: {
    width: 6,
    height: 10,
    backgroundColor: colors.info,
    animationName: blink,
    animationDuration: '1s',
    animationIterationCount: 'infinite',
  },
});

type Activity = Partial<Record<string, { running: number; waiting: number }>>;

/** Whether the page still hears from the hub: a blinking block, or a warning once answers stop. */
function Live() {
  const { isError, dataUpdatedAt } = useNav();
  const now = useNow(10_000);
  const lost = isError || (dataUpdatedAt > 0 && now * 1000 - dataUpdatedAt > 60_000);
  return (
    <output {...stylex.props(styles.foot)}>
      <i {...stylex.props(styles.liveDot, lost && styles.lostDot)} />
      <span>{lost ? 'Reconnecting…' : 'Live'}</span>
    </output>
  );
}

function MarkIcon({ item }: { item: MenuItem }) {
  const m = item.mark;
  if ('agent' in m) return <Badge name={m.agent} size="xs" />;
  if ('companionOf' in m)
    return (
      <span {...stylex.props(styles.companionIcon)}>
        <Icon name="bot" size={16} />
      </span>
    );
  return <Icon name={m.icon} size={16} />;
}

function Trailing({ item, live }: { item: MenuItem; live?: { running: number; waiting: number } }) {
  if (live?.waiting)
    return (
      <span {...stylex.props(styles.end)} title={`${live.waiting} waiting on you`}>
        <Count n={live.waiting} />
      </span>
    );
  if (live?.running)
    return (
      <span {...stylex.props(styles.end)} title={`${live.running} running`}>
        <span {...stylex.props(styles.busy)}>
          <i {...stylex.props(styles.block)} />
          {live.running}
        </span>
      </span>
    );
  if (item.count)
    return (
      <span {...stylex.props(styles.end)}>
        <Count n={item.count} />
      </span>
    );
  if (item.dot !== undefined)
    return (
      <span {...stylex.props(styles.end)}>
        <Dot ok={item.dot} />
      </span>
    );
  if (item.note) return <span {...stylex.props(styles.end, styles.note)}>{item.note}</span>;
  return null;
}

function SideLink({ item, activity }: { item: MenuItem; activity: Activity }) {
  const { pathname } = useLocation();
  const owner = 'companionOf' in item.mark ? item.mark.companionOf : 'agent' in item.mark ? item.mark.agent : undefined;
  return (
    <Link
      to={item.to}
      {...stylex.props(
        hueTheme(owner),
        styles.link,
        'companionOf' in item.mark && styles.nested,
        isActive(item, pathname) && styles.on,
      )}
    >
      <MarkIcon item={item} />
      <span>{item.label}</span>
      <Trailing item={item} live={'agent' in item.mark ? activity[item.mark.agent] : undefined} />
    </Link>
  );
}

const Group = ({ title, items, activity }: { title?: string; items: MenuItem[]; activity: Activity }) =>
  items.length > 0 && (
    <>
      {title && <div {...stylex.props(styles.group)}>{title}</div>}
      {items.map((i) => (
        <SideLink key={i.to} item={i} activity={activity} />
      ))}
    </>
  );

export function Sidebar({ menu, onLogo }: { menu: Menu; onLogo: (e: MouseEvent) => void }) {
  const activity: Activity = Object.fromEntries(
    (useNowBoard().data?.agents ?? []).map((a) => [a.name, { running: a.running + a.background, waiting: a.waiting }]),
  );
  return (
    <aside {...stylex.props(styles.side)}>
      <div {...stylex.props(styles.brand)}>
        {/* Not a control on purpose: hidden presenting switch; Alt+Shift+P is its keyboard twin. */}
        <span {...stylex.props(styles.logo)} role="presentation" onClick={onLogo}>
          <Icon name="agents" size={14} />
        </span>
        <Link to="/">
          <span {...stylex.props(styles.brandName)}>Agents</span>
        </Link>
      </div>
      <button type="button" {...stylex.props(styles.search)} onClick={openPalette}>
        <Icon name="search" size={15} />
        Search
        <kbd {...stylex.props(styles.kbd)}>Ctrl K</kbd>
      </button>
      <nav {...stylex.props(styles.nav)} aria-label="Main">
        <Group items={menu.main} activity={activity} />
        <Group title="Agents" items={menu.agents} activity={activity} />
        <Group title="System" items={menu.system} activity={activity} />
      </nav>
      <div {...stylex.props(styles.bottom)}>
        <Live />
        <ThemeToggle />
      </div>
    </aside>
  );
}

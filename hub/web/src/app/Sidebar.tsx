import * as stylex from '@stylexjs/stylex';
import type { MouseEvent } from 'react';
import { Link, useLocation } from 'react-router';
import { useNav, useNowBoard } from '../api/queries';
import { useNow } from '../lib/useNow';
import { hueTheme } from '../theme/hues';
import { agent, colors, media, motion, radius, space, text } from '../theme/tokens.stylex';
import { Icon } from '../ui/Icon';
import { Badge, Count, Dot } from '../ui/status';
import { isActive, type Menu, type MenuItem } from './menu';
import { openPalette } from './Palette';
import { ThemeToggle } from './ThemeToggle';

const bounce = stylex.keyframes({ '0%, 100%': { transform: 'scaleY(.35)' }, '50%': { transform: 'scaleY(1)' } });

const breathe = stylex.keyframes({
  '0%': { boxShadow: `0 0 0 0 color-mix(in srgb, ${colors.ok} 55%, transparent)` },
  '70%': { boxShadow: '0 0 0 7px transparent' },
  '100%': { boxShadow: '0 0 0 0 transparent' },
});

const styles = stylex.create({
  side: {
    position: 'sticky',
    top: 0,
    height: '100vh',
    paddingBlock: space.xxxl,
    paddingInline: space.xl,
    backgroundColor: `color-mix(in srgb, ${colors.panel} 72%, transparent)`,
    backdropFilter: 'saturate(160%) blur(18px)',
    overflow: 'auto',
    borderRightWidth: 1,
    borderRightStyle: 'solid',
    borderRightColor: colors.line,
    display: { default: 'flex', [media.nav]: 'none' },
    flexDirection: 'column',
    gap: space.xxl,
  },
  brand: { display: 'flex', alignItems: 'center', gap: space.md, paddingBlock: space.xxxs, paddingInline: space.sm },
  logo: {
    width: 34,
    height: 34,
    borderRadius: radius.md,
    backgroundColor: colors.fg,
    backgroundImage: `linear-gradient(140deg, ${colors.accent}, color-mix(in srgb, ${colors.accent} 40%, #a855f7))`,
    boxShadow: `0 6px 18px -6px color-mix(in srgb, ${colors.accent} 70%, transparent), inset 0 1px 0 rgba(255,255,255,.25)`,
    color: colors.onFill,
    display: 'grid',
    placeItems: 'center',
    userSelect: 'none',
    cursor: 'default',
  },
  brandName: { display: 'block', fontSize: text.lg, fontWeight: 700, letterSpacing: '-.01em' },
  brandSub: { display: 'block', color: colors.faint, fontSize: text.xs, lineHeight: 1.2 },
  nav: { display: 'grid', gap: space.xxxs },
  group: {
    fontSize: text.xxs,
    fontWeight: 600,
    letterSpacing: '.07em',
    textTransform: 'uppercase',
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
    paddingBlock: space.sm,
    paddingInline: space.md,
    borderRadius: radius.md,
    fontWeight: 500,
    color: { default: colors.muted, ':hover': colors.fg },
    backgroundColor: { default: null, ':hover': colors.hover },
    transitionProperty: 'background-color, color, transform, box-shadow',
    transitionDuration: '200ms',
    transitionTimingFunction: motion.settle,
    transform: { default: null, ':active': 'scale(.97)' },
  },
  on: {
    backgroundColor: { default: colors.panel, ':hover': colors.panel },
    color: { default: colors.fg, ':hover': colors.fg },
    fontWeight: 600,
    boxShadow: colors.shadow,
  },
  // the selected item's accent bar, in the agent's colour under an agent
  onBar: {
    position: 'absolute',
    insetInlineStart: -7,
    top: 9,
    bottom: 9,
    width: 3,
    borderRadius: radius.pill,
    backgroundColor: colors.accent,
  },
  onBarHue: { backgroundColor: agent.hue },
  nested: {
    marginInlineStart: space.xxxl,
    paddingInlineStart: space.lg,
    borderStartStartRadius: 0,
    borderEndStartRadius: 0,
    borderLeftWidth: 2,
    borderLeftStyle: 'solid',
    borderLeftColor: `color-mix(in srgb, ${agent.hue} 70%, transparent)`,
  },
  companionIcon: { color: agent.hue, display: 'flex' },
  end: { marginInlineStart: 'auto', display: 'flex', alignItems: 'center' },
  note: { fontSize: text.sm, color: colors.faint },
  bottom: { marginTop: 'auto', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: space.md },
  foot: { fontSize: text.xs, color: colors.faint, paddingInline: space.sm, display: 'flex', alignItems: 'center', gap: space.sm },
  liveDot: {
    width: 8,
    height: 8,
    borderRadius: '50%',
    backgroundColor: colors.ok,
    animationName: breathe,
    animationDuration: '2.4s',
    animationIterationCount: 'infinite',
  },
  lostDot: { backgroundColor: colors.warn, animationName: 'none' },
  search: {
    display: 'flex',
    alignItems: 'center',
    gap: space.md,
    width: '100%',
    paddingBlock: space.sm,
    paddingInline: space.md,
    borderRadius: radius.md,
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: { default: colors.line, ':hover': colors.line2 },
    backgroundColor: { default: colors.sunk, ':hover': colors.hover },
    color: colors.faint,
    font: 'inherit',
    fontSize: text.base,
    cursor: 'pointer',
    transitionProperty: 'background-color, border-color',
    transitionDuration: '160ms',
  },
  kbd: {
    marginInlineStart: 'auto',
    fontSize: text.xxs,
    fontWeight: 600,
    paddingBlock: 1,
    paddingInline: space.xs,
    borderRadius: radius.xs,
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: colors.line2,
    backgroundColor: colors.panel,
  },
  // three bars bouncing out of step: this agent is working right now
  bars: { display: 'inline-flex', alignItems: 'flex-end', gap: 2, height: 12 },
  bar: (delay: string) => ({
    width: 2.5,
    height: 12,
    borderRadius: 2,
    backgroundColor: agent.hue,
    transformOrigin: 'bottom',
    animationName: bounce,
    animationDuration: '1s',
    animationDelay: delay,
    animationIterationCount: 'infinite',
    animationTimingFunction: 'ease-in-out',
  }),
  busy: { display: 'inline-flex', alignItems: 'center', gap: space.xs, fontSize: text.xs, fontWeight: 650, color: agent.hue },
  wait: {
    display: 'inline-grid',
    placeItems: 'center',
    minWidth: 20,
    height: 20,
    paddingInline: space.xs,
    borderRadius: radius.pill,
    fontSize: text.xxs,
    fontWeight: 700,
    backgroundColor: colors.warn,
    color: colors.onFill,
  },
});

type Activity = Partial<Record<string, { running: number; waiting: number }>>;

/** Whether the page still hears from the hub: a breathing dot, or a warning once answers stop. */
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
        <Icon name="bot" />
      </span>
    );
  return <Icon name={m.icon} />;
}

function Trailing({ item, live }: { item: MenuItem; live?: { running: number; waiting: number } }) {
  if (live?.waiting)
    return (
      <span {...stylex.props(styles.end)} title={`${live.waiting} waiting on you`}>
        <span {...stylex.props(styles.wait)}>{live.waiting}</span>
      </span>
    );
  if (live?.running)
    return (
      <span {...stylex.props(styles.end)} title={`${live.running} running`}>
        <span {...stylex.props(styles.busy)}>
          <span {...stylex.props(styles.bars)}>
            {['0s', '.25s', '.5s'].map((d) => (
              <i key={d} {...stylex.props(styles.bar(d))} />
            ))}
          </span>
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
  const nested = 'companionOf' in item.mark;
  const on = isActive(item, pathname);
  return (
    <Link to={item.to} {...stylex.props(hueTheme(owner), styles.link, nested && styles.nested, on && styles.on)}>
      {on && !nested && <i {...stylex.props(styles.onBar, !!owner && styles.onBarHue)} />}
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
    (useNowBoard().data?.agents ?? []).map((a) => [a.name, { running: a.running.length, waiting: a.waiting.length }]),
  );
  return (
    <aside {...stylex.props(styles.side)}>
      <div {...stylex.props(styles.brand)}>
        {/* Not a control on purpose: hidden presenting switch; Alt+Shift+P is its keyboard twin. */}
        <span {...stylex.props(styles.logo)} role="presentation" onClick={onLogo}>
          <Icon name="agents" size={17} />
        </span>
        <Link to="/">
          <b {...stylex.props(styles.brandName)}>Agents</b>
          <small {...stylex.props(styles.brandSub)}>Cluster control</small>
        </Link>
      </div>
      <button type="button" {...stylex.props(styles.search)} onClick={openPalette}>
        <Icon name="search" size={16} />
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

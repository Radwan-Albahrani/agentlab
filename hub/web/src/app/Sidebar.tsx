import * as stylex from '@stylexjs/stylex';
import type { MouseEvent } from 'react';
import { Link, useLocation } from 'react-router';
import { hueTheme } from '../theme/hues';
import { agent, colors, media, radius, space, text } from '../theme/tokens.stylex';
import { Icon } from '../ui/Icon';
import { Badge, Count, Dot } from '../ui/status';
import { isActive, type Menu, type MenuItem } from './menu';
import { ThemeToggle } from './ThemeToggle';

const styles = stylex.create({
  side: {
    position: 'sticky',
    top: 0,
    height: '100vh',
    paddingBlock: space.xxxl,
    paddingInline: space.xl,
    backgroundColor: colors.panel,
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
    width: 30,
    height: 30,
    borderRadius: radius.sm,
    backgroundColor: colors.fg,
    color: colors.bg,
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
    display: 'flex',
    alignItems: 'center',
    gap: space.md,
    paddingBlock: space.sm,
    paddingInline: space.md,
    borderRadius: radius.sm,
    fontWeight: 500,
    color: { default: colors.muted, ':hover': colors.fg },
    backgroundColor: { default: null, ':hover': colors.hover },
  },
  on: {
    backgroundColor: { default: colors.accentSoft, ':hover': colors.accentSoft },
    color: { default: colors.accent, ':hover': colors.accent },
  },
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
  foot: { fontSize: text.xs, color: colors.faint, paddingInline: space.sm, display: 'flex', alignItems: 'center', gap: space.xs },
});

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

function Trailing({ item }: { item: MenuItem }) {
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

function SideLink({ item }: { item: MenuItem }) {
  const { pathname } = useLocation();
  const owner = 'companionOf' in item.mark ? item.mark.companionOf : undefined;
  return (
    <Link
      to={item.to}
      {...stylex.props(hueTheme(owner), styles.link, !!owner && styles.nested, isActive(item, pathname) && styles.on)}
    >
      <MarkIcon item={item} />
      <span>{item.label}</span>
      <Trailing item={item} />
    </Link>
  );
}

const Group = ({ title, items }: { title?: string; items: MenuItem[] }) =>
  items.length > 0 && (
    <>
      {title && <div {...stylex.props(styles.group)}>{title}</div>}
      {items.map((i) => (
        <SideLink key={i.to} item={i} />
      ))}
    </>
  );

/** The desktop menu: brand (its logo is the silent presenting switch), menu groups, theme and a live note. */
export function Sidebar({ menu, onLogo }: { menu: Menu; onLogo: (e: MouseEvent) => void }) {
  return (
    <aside {...stylex.props(styles.side)}>
      <div {...stylex.props(styles.brand)}>
        <span {...stylex.props(styles.logo)} onClick={onLogo}>
          <Icon name="agents" size={17} />
        </span>
        <Link to="/">
          <b {...stylex.props(styles.brandName)}>Agents</b>
          <small {...stylex.props(styles.brandSub)}>Cluster control</small>
        </Link>
      </div>
      <nav {...stylex.props(styles.nav)} aria-label="Main">
        <Group items={menu.main} />
        <Group title="Agents" items={menu.agents} />
        <Group title="System" items={menu.system} />
      </nav>
      <div {...stylex.props(styles.bottom)}>
        <div {...stylex.props(styles.foot)}>
          <Icon name="clock" size={16} />
          <span>Live · updates by itself</span>
        </div>
        <ThemeToggle />
      </div>
    </aside>
  );
}

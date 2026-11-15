import * as stylex from '@stylexjs/stylex';
import {
  Menu,
  MenuContent,
  MenuItem,
  MenuItemIcon,
  MenuItemIndicator,
  MenuRadioGroup,
  MenuRadioItem,
  MenuTrigger,
} from '@ui-sdk/react/menu';
import { colors, font, motion, radius, space, text } from '../theme/tokens.stylex';
import { Hint, look } from './Button';
import { Icon } from './Icon';

const fading = ':is([data-starting-style], [data-ending-style])';
const lit = ':is([data-highlighted])';
const off = ':is([data-disabled])';

const styles = stylex.create({
  popup: {
    minWidth: 200,
    maxHeight: 'var(--available-height)',
    overflowY: 'auto',
    margin: 0,
    padding: space.xxs,
    borderRadius: radius.lg,
    backgroundColor: colors.raised,
    color: colors.fg,
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: colors.line2,
    boxShadow: colors.popShadow,
    outline: 'none',
    display: 'grid',
    transformOrigin: 'var(--transform-origin)',
    transitionProperty: 'opacity, transform',
    transitionDuration: '160ms',
    transitionTimingFunction: motion.settle,
    opacity: { default: 1, [fading]: 0 },
    transform: { default: 'none', [fading]: 'scale(.97)' },
  },
  item: {
    display: 'flex',
    alignItems: 'center',
    gap: space.sm,
    paddingBlock: space.xs,
    paddingInline: space.md,
    borderRadius: radius.sm,
    fontSize: text.base,
    fontWeight: 500,
    color: { default: colors.fg, [off]: colors.faint },
    backgroundColor: { default: 'transparent', [lit]: colors.hover },
    cursor: { default: 'pointer', [off]: 'default' },
    outline: 'none',
    userSelect: 'none',
  },
  danger: {
    color: { default: colors.bad, [off]: colors.faint },
    backgroundColor: { default: 'transparent', [lit]: colors.badSoft },
  },
  icon: { display: 'flex' },
  hint: {
    marginInlineStart: 'auto',
    paddingInlineStart: space.lg,
    fontFamily: font.mono,
    fontSize: text.xs,
    color: colors.faint,
  },
  tick: { width: 16, display: 'inline-flex', color: colors.accent },
});

export interface MenuEntry {
  label: string;
  icon?: string;
  hint?: string;
  danger?: boolean;
  disabled?: boolean;
  onSelect: () => unknown;
}

export function PickMenu<V extends string>({
  label,
  icon,
  value,
  options,
  onChange,
}: {
  label: string;
  icon: string;
  value: V;
  options: { value: V; label: string }[];
  onChange: (v: V) => void;
}) {
  const current = options.find((o) => o.value === value);
  return (
    <Menu>
      <Hint tip={current ? `${label}: ${current.label}` : label} names={false} render={<MenuTrigger {...look({ label })} />}>
        <Icon name={icon} size={17} />
        <span>{label}</span>
      </Hint>
      <MenuContent sideOffset={6} align="end" {...stylex.props(styles.popup)}>
        <MenuRadioGroup value={value} onValueChange={onChange}>
          {options.map((o) => (
            <MenuRadioItem key={o.value} value={o.value} closeOnSelect {...stylex.props(styles.item)}>
              <span {...stylex.props(styles.tick)}>
                <MenuItemIndicator>
                  <Icon name="check" size={16} />
                </MenuItemIndicator>
              </span>
              <span>{o.label}</span>
            </MenuRadioItem>
          ))}
        </MenuRadioGroup>
      </MenuContent>
    </Menu>
  );
}

export function MoreMenu({ label, entries }: { label: string; entries: MenuEntry[] }) {
  return (
    <Menu>
      <Hint
        tip={label}
        names
        render={<MenuTrigger {...look({ label, variant: 'quiet', small: true, iconOnly: true })} aria-label={label} />}
      >
        <Icon name="more" size={16} />
      </Hint>
      <MenuContent sideOffset={6} align="end" {...stylex.props(styles.popup)}>
        {entries.map((e) => (
          <MenuItem
            key={e.label}
            disabled={e.disabled}
            destructive={e.danger}
            // fire and forget: a returned promise would keep the menu open until it settles
            onSelect={() => {
              void e.onSelect();
            }}
            {...stylex.props(styles.item, e.danger && styles.danger)}
          >
            {e.icon && (
              <MenuItemIcon {...stylex.props(styles.icon)}>
                <Icon name={e.icon} size={16} />
              </MenuItemIcon>
            )}
            <span>{e.label}</span>
            {e.hint && <span {...stylex.props(styles.hint)}>{e.hint}</span>}
          </MenuItem>
        ))}
      </MenuContent>
    </Menu>
  );
}

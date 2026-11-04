import * as stylex from '@stylexjs/stylex';
import { Menu } from '@base-ui/react/menu';
import { colors, radius, space, text } from '../theme/tokens.stylex';
import { look } from './Button';
import { Icon } from './Icon';

const cls = (...s: stylex.StyleXStyles[]) => stylex.props(...s).className ?? '';

const styles = stylex.create({
  positioner: { zIndex: 30, outline: 'none' },
  popup: {
    minWidth: 200,
    padding: space.xxs,
    borderRadius: radius.lg,
    backgroundColor: colors.panel,
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: colors.line2,
    boxShadow: colors.popShadow,
    outline: 'none',
    display: 'grid',
  },
  item: {
    display: 'flex',
    alignItems: 'center',
    gap: space.sm,
    paddingBlock: space.sm,
    paddingInline: space.md,
    borderRadius: radius.sm,
    fontSize: text.base,
    fontWeight: 500,
    color: colors.fg,
    cursor: 'pointer',
    outline: 'none',
    userSelect: 'none',
  },
  highlighted: { backgroundColor: colors.hover },
  danger: { color: colors.bad },
  dangerHighlighted: { backgroundColor: colors.badSoft },
  disabled: { color: colors.faint, cursor: 'default' },
  hint: { marginInlineStart: 'auto', paddingInlineStart: space.lg, fontSize: text.sm, color: colors.faint },
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
    <Menu.Root>
      <Menu.Trigger {...look({ label })} title={current ? `${label}: ${current.label}` : label}>
        <Icon name={icon} size={17} />
        <span>{label}</span>
      </Menu.Trigger>
      <Menu.Portal>
        <Menu.Positioner sideOffset={6} align="end" {...stylex.props(styles.positioner)}>
          <Menu.Popup {...stylex.props(styles.popup)}>
            {options.map((o) => (
              <Menu.Item
                key={o.value}
                onClick={() => {
                  onChange(o.value);
                }}
                className={(s) => cls(styles.item, s.highlighted && styles.highlighted)}
              >
                <span {...stylex.props(styles.tick)}>{o.value === value && <Icon name="check" size={16} />}</span>
                <span>{o.label}</span>
              </Menu.Item>
            ))}
          </Menu.Popup>
        </Menu.Positioner>
      </Menu.Portal>
    </Menu.Root>
  );
}

export function MoreMenu({ label, entries }: { label: string; entries: MenuEntry[] }) {
  return (
    <Menu.Root>
      <Menu.Trigger {...look({ label, variant: 'quiet', small: true, iconOnly: true })} aria-label={label} title={label}>
        <Icon name="more" size={16} />
      </Menu.Trigger>
      <Menu.Portal>
        <Menu.Positioner sideOffset={6} align="end" {...stylex.props(styles.positioner)}>
          <Menu.Popup {...stylex.props(styles.popup)}>
            {entries.map((e) => (
              <Menu.Item
                key={e.label}
                disabled={e.disabled}
                onClick={() => void e.onSelect()}
                className={(s) =>
                  cls(
                    styles.item,
                    s.highlighted && (e.danger ? styles.dangerHighlighted : styles.highlighted),
                    !!e.danger && styles.danger,
                    s.disabled && styles.disabled,
                  )
                }
              >
                {e.icon && <Icon name={e.icon} size={16} />}
                <span>{e.label}</span>
                {e.hint && <span {...stylex.props(styles.hint)}>{e.hint}</span>}
              </Menu.Item>
            ))}
          </Menu.Popup>
        </Menu.Positioner>
      </Menu.Portal>
    </Menu.Root>
  );
}

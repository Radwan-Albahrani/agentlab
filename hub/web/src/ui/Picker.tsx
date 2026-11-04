import * as stylex from '@stylexjs/stylex';
import { Combobox } from '@base-ui/react/combobox';
import { colors, radius, space, text } from '../theme/tokens.stylex';
import { Icon } from './Icon';

const cls = (...s: stylex.StyleXStyles[]) => stylex.props(...s).className ?? '';

const styles = stylex.create({
  group: {
    position: 'relative',
    display: 'flex',
    alignItems: 'center',
    flexGrow: '1',
    flexShrink: '1',
    flexBasis: '240px',
    minWidth: 0,
  },
  input: {
    width: '100%',
    minWidth: 0,
    paddingBlock: space.md,
    paddingInlineStart: space.lg,
    paddingInlineEnd: 64,
    borderRadius: radius.md,
    fontSize: text.body,
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: { default: colors.line2, ':focus': colors.accent },
    backgroundColor: colors.sunk,
    color: colors.fg,
    outline: { default: 'none', ':focus': `2px solid color-mix(in srgb, ${colors.accent} 45%, transparent)` },
    outlineOffset: 1,
    '::placeholder': { color: colors.faint },
  },
  buttons: { position: 'absolute', insetInlineEnd: space.sm, display: 'flex', gap: space.xxs },
  iconBtn: {
    appearance: 'none',
    borderWidth: 0,
    backgroundColor: { default: 'transparent', ':hover': colors.hover },
    color: { default: colors.faint, ':hover': colors.fg },
    borderRadius: radius.sm,
    padding: space.xxs,
    display: 'flex',
    cursor: 'pointer',
  },
  positioner: { zIndex: 30, outline: 'none' },
  popup: {
    width: 'var(--anchor-width)',
    maxHeight: 'min(320px, var(--available-height))',
    overflowY: 'auto',
    padding: space.xxs,
    borderRadius: radius.lg,
    backgroundColor: colors.panel,
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: colors.line2,
    boxShadow: colors.popShadow,
    outline: 'none',
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
  selected: { color: colors.accent },
  disabled: { color: colors.faint, cursor: 'default' },
  hint: { marginInlineStart: 'auto', paddingInlineStart: space.lg, fontSize: text.sm, color: colors.faint },
  empty: { paddingBlock: space.md, paddingInline: space.md, fontSize: text.base, color: colors.faint },
});

export interface PickItem {
  value: string;
  label: string;
  hint?: string;
  disabled?: boolean;
}

/** Type-to-filter single pick; '' means none picked. */
export function Picker({
  items,
  value,
  onChange,
  label,
  placeholder,
  empty = 'Nothing matches',
}: {
  items: PickItem[];
  value: string;
  onChange: (v: string) => void;
  label: string;
  placeholder: string;
  empty?: string;
}) {
  return (
    <Combobox.Root
      items={items}
      value={items.find((i) => i.value === value) ?? null}
      onValueChange={(i) => {
        onChange(i?.value ?? '');
      }}
      itemToStringLabel={(i: PickItem) => i.label}
      isItemEqualToValue={(a: PickItem, b: PickItem) => a.value === b.value}
    >
      <Combobox.InputGroup {...stylex.props(styles.group)}>
        <Combobox.Input {...stylex.props(styles.input)} placeholder={placeholder} aria-label={label} />
        <span {...stylex.props(styles.buttons)}>
          {value && (
            <Combobox.Clear {...stylex.props(styles.iconBtn)} aria-label="Clear">
              <Icon name="x" size={15} />
            </Combobox.Clear>
          )}
          <Combobox.Trigger {...stylex.props(styles.iconBtn)} aria-label={`Show ${label.toLowerCase()}`}>
            <Icon name="chevron" size={15} />
          </Combobox.Trigger>
        </span>
      </Combobox.InputGroup>
      <Combobox.Portal>
        <Combobox.Positioner sideOffset={6} {...stylex.props(styles.positioner)}>
          <Combobox.Popup {...stylex.props(styles.popup)}>
            <Combobox.Empty {...stylex.props(styles.empty)}>{empty}</Combobox.Empty>
            <Combobox.List>
              {(i: PickItem) => (
                <Combobox.Item
                  key={i.value}
                  value={i}
                  disabled={i.disabled}
                  className={(s) =>
                    cls(
                      styles.item,
                      s.highlighted && styles.highlighted,
                      s.selected && styles.selected,
                      s.disabled && styles.disabled,
                    )
                  }
                >
                  <span>{i.label}</span>
                  {i.hint && <span {...stylex.props(styles.hint)}>{i.hint}</span>}
                </Combobox.Item>
              )}
            </Combobox.List>
          </Combobox.Popup>
        </Combobox.Positioner>
      </Combobox.Portal>
    </Combobox.Root>
  );
}

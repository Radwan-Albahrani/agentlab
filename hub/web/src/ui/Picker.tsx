import * as stylex from '@stylexjs/stylex';
import {
  Combobox,
  ComboboxClear,
  ComboboxContent,
  ComboboxEmpty,
  ComboboxInput,
  ComboboxItem,
  ComboboxList,
  ComboboxTrigger,
} from '@ui-sdk/react/combobox';
import { colors, font, motion, radius, space, text } from '../theme/tokens.stylex';
import { Icon } from './Icon';

const fading = ':is([data-starting-style], [data-ending-style])';
const lit = ':is([data-highlighted])';
const off = ':is([data-disabled])';

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
    paddingBlock: space.sm,
    paddingInlineStart: space.lg,
    paddingInlineEnd: 64,
    borderRadius: radius.md,
    fontSize: text.body,
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: { default: colors.line2, ':focus': colors.accent },
    backgroundColor: colors.sunk,
    color: colors.fg,
    outline: { default: 'none', ':focus-visible': `2px solid ${colors.accent}` },
    outlineOffset: 2,
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
    outline: { default: 'none', ':focus-visible': `2px solid ${colors.accent}` },
  },
  popup: {
    width: 'var(--anchor-width)',
    maxHeight: 'min(320px, var(--available-height))',
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
    fontWeight: { default: 500, ':is([data-selected])': 600 },
    color: { default: colors.fg, ':is([data-selected])': colors.accent, [off]: colors.faint },
    backgroundColor: { default: 'transparent', [lit]: colors.hover },
    cursor: { default: 'pointer', [off]: 'default' },
    outline: 'none',
    userSelect: 'none',
  },
  hint: {
    marginInlineStart: 'auto',
    paddingInlineStart: space.lg,
    fontFamily: font.mono,
    fontSize: text.xs,
    color: colors.faint,
  },
  empty: {
    display: { default: 'none', ':is([data-empty])': 'block' },
    paddingBlock: space.md,
    paddingInline: space.md,
    fontSize: text.base,
    color: colors.faint,
  },
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
  onMiss,
}: {
  items: PickItem[];
  value: string;
  onChange: (v: string) => void;
  label: string;
  placeholder: string;
  empty?: string;
  /** Called when the typed text matches nothing (e.g. to ask for a fresher list). */
  onMiss?: () => void;
}) {
  return (
    <Combobox
      items={items}
      value={value || null}
      onValueChange={(v) => {
        onChange(v ?? '');
      }}
    >
      <div {...stylex.props(styles.group)}>
        <ComboboxInput
          {...stylex.props(styles.input)}
          placeholder={placeholder}
          aria-label={label}
          onInput={(e) => {
            const q = e.currentTarget.value.trim().toLowerCase();
            if (onMiss && q && !items.some((i) => i.label.toLowerCase().includes(q))) onMiss();
          }}
        />
        <span {...stylex.props(styles.buttons)}>
          <ComboboxClear {...stylex.props(styles.iconBtn)} aria-label="Clear">
            <Icon name="x" size={15} />
          </ComboboxClear>
          <ComboboxTrigger {...stylex.props(styles.iconBtn)} aria-label={`Show ${label.toLowerCase()}`}>
            <Icon name="chevron" size={15} />
          </ComboboxTrigger>
        </span>
      </div>
      <ComboboxContent sideOffset={6} {...stylex.props(styles.popup)}>
        <ComboboxEmpty {...stylex.props(styles.empty)}>{empty}</ComboboxEmpty>
        <ComboboxList>
          {/* the list's own state.items: only what matches the typed text (mapping `items` would show them all) */}
          {(state) =>
            (state.items as PickItem[]).map((i) => (
              <ComboboxItem key={i.value} value={i.value} label={i.label} disabled={i.disabled} {...stylex.props(styles.item)}>
                <span>{i.label}</span>
                {i.hint && <span {...stylex.props(styles.hint)}>{i.hint}</span>}
              </ComboboxItem>
            ))
          }
        </ComboboxList>
      </ComboboxContent>
    </Combobox>
  );
}

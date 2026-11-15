import * as stylex from '@stylexjs/stylex';
import { Select as Root, SelectContent, SelectItem, SelectItemIndicator, SelectTrigger, SelectValue } from '@ui-sdk/react/select';
import { colors, motion, radius, space, text } from '../theme/tokens.stylex';
import { Icon } from './Icon';

const fading = ':is([data-starting-style], [data-ending-style])';
const lit = ':is([data-highlighted])';
const picked = ':is([data-selected])';

const styles = stylex.create({
  trigger: {
    appearance: 'none',
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: space.md,
    minWidth: 200,
    maxWidth: '100%',
    paddingBlock: space.sm,
    paddingInlineStart: space.lg,
    paddingInlineEnd: space.md,
    borderRadius: radius.md,
    fontSize: text.body,
    textAlign: 'start',
    cursor: 'pointer',
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: { default: colors.line2, ':hover': colors.faint, ':is([data-open])': colors.accent },
    backgroundColor: colors.sunk,
    color: colors.fg,
    outline: { default: 'none', ':focus-visible': `2px solid ${colors.accent}` },
    outlineOffset: 2,
  },
  value: { minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' },
  chevron: { display: 'flex', color: colors.faint },
  popup: {
    minWidth: 'var(--anchor-width)',
    maxWidth: 'min(420px, calc(100vw - 32px))',
    maxHeight: 'min(360px, var(--available-height))',
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
    display: 'grid',
    gridTemplateColumns: 'minmax(0, 1fr) 16px',
    alignItems: 'center',
    columnGap: space.md,
    paddingBlock: space.xs,
    paddingInline: space.md,
    borderRadius: radius.sm,
    fontSize: text.base,
    fontWeight: { default: 500, [picked]: 600 },
    color: { default: colors.fg, [picked]: colors.accent },
    backgroundColor: { default: 'transparent', [lit]: colors.hover },
    cursor: 'pointer',
    outline: 'none',
    userSelect: 'none',
  },
  text: { display: 'grid', gap: space.xxxs, minWidth: 0 },
  help: { fontSize: text.sm, fontWeight: 400, color: colors.muted, lineHeight: 1.4 },
  tick: { display: 'flex', color: colors.accent },
});

export interface SelectOption {
  value: string;
  label: string;
  help?: string; // one line under the label, in the list only
}

/** A dropdown of a few choices; the trigger shows the chosen one. */
export function Select({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: SelectOption[];
  onChange: (v: string) => unknown;
}) {
  return (
    <Root
      items={options}
      value={value || null}
      onValueChange={(v) => {
        if (v !== null) void onChange(v);
      }}
    >
      <SelectTrigger aria-label={label} {...stylex.props(styles.trigger)}>
        <SelectValue {...stylex.props(styles.value)} />
        <span {...stylex.props(styles.chevron)}>
          <Icon name="chevron" size={15} />
        </span>
      </SelectTrigger>
      <SelectContent sideOffset={6} {...stylex.props(styles.popup)}>
        {options.map((o) => (
          <SelectItem key={o.value} value={o.value} label={o.label} {...stylex.props(styles.item)}>
            <span {...stylex.props(styles.text)}>
              <span>{o.label}</span>
              {o.help && <span {...stylex.props(styles.help)}>{o.help}</span>}
            </span>
            <SelectItemIndicator {...stylex.props(styles.tick)}>
              <Icon name="check" size={16} />
            </SelectItemIndicator>
          </SelectItem>
        ))}
      </SelectContent>
    </Root>
  );
}

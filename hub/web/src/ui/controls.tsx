import * as stylex from '@stylexjs/stylex';
import { Collapsible, CollapsiblePanel, CollapsibleTrigger } from '@ui-sdk/react/collapsible';
import { Popover, PopoverContent, PopoverTrigger } from '@ui-sdk/react/popover';
import { Radio, RadioGroup, RadioIndicator } from '@ui-sdk/react/radio';
import { Switch as SwitchRoot, SwitchThumb } from '@ui-sdk/react/switch';
import { Toggle, ToggleGroup } from '@ui-sdk/react/toggle';
import type { ReactNode } from 'react';
import { colors, font, motion, radius, space, text } from '../theme/tokens.stylex';
import { Hint } from './Button';
import { Icon } from './Icon';

const cls = (...s: stylex.StyleXStyles[]) => stylex.props(...s).className ?? '';

const fading = ':is([data-starting-style], [data-ending-style])';
const checked = ':is([data-checked])';
const opened = ':is([data-open])';

const styles = stylex.create({
  segments: {
    display: 'inline-flex',
    gap: space.xxxs,
    padding: space.xxxs,
    borderRadius: radius.md,
    backgroundColor: colors.sunk,
    flexWrap: 'wrap',
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: colors.line,
  },
  segment: {
    borderWidth: 0,
    backgroundColor: { default: 'transparent', ':hover': colors.hover },
    paddingBlock: space.xs,
    paddingInline: space.lg,
    borderRadius: radius.sm,
    fontSize: text.md,
    fontWeight: 500,
    color: { default: colors.muted, ':hover': colors.fg },
    cursor: 'pointer',
    transitionProperty: 'background-color, color',
    transitionDuration: '120ms',
    outline: { default: 'none', ':focus-visible': `2px solid ${colors.accent}` },
    outlineOffset: 2,
  },
  segmentOn: {
    backgroundColor: { default: colors.accentSoft, ':hover': colors.accentSoft },
    color: { default: colors.accent, ':hover': colors.accent },
    fontWeight: 600,
  },
  switch: {
    width: 36,
    height: 20,
    borderRadius: radius.sm,
    borderWidth: 0,
    backgroundColor: { default: colors.line2, [checked]: colors.accent },
    position: 'relative',
    cursor: 'pointer',
    padding: 0,
    flexShrink: 0,
    justifySelf: 'start',
    transition: 'background-color .14s',
    outline: { default: 'none', ':focus-visible': `2px solid ${colors.accent}` },
    outlineOffset: 2,
  },
  thumb: {
    position: 'absolute',
    top: 3,
    left: { default: 3, [checked]: 19 },
    width: 14,
    height: 14,
    borderRadius: radius.xs,
    backgroundColor: colors.onFill,
    transition: 'left .14s',
  },
  cards: { display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(170px, 1fr))', gap: space.sm },
  card: {
    display: 'grid',
    gap: space.xxs,
    textAlign: 'left',
    alignContent: 'start',
    paddingBlock: space.lg,
    paddingInline: space.lg,
    borderRadius: radius.lg,
    cursor: 'pointer',
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: { default: colors.line2, ':hover': colors.faint },
    backgroundColor: { default: colors.panel, ':hover': colors.hover },
    color: colors.fg,
    transitionProperty: 'background-color, border-color',
    transitionDuration: '120ms',
    outline: { default: 'none', ':focus-visible': `2px solid ${colors.accent}` },
    outlineOffset: 2,
  },
  cardOn: {
    borderColor: { default: colors.accent, ':hover': colors.accent },
    backgroundColor: { default: colors.accentSoft, ':hover': colors.accentSoft },
    color: colors.accent,
  },
  cardTitle: { fontSize: text.base, fontWeight: 600 },
  cardHelp: { fontSize: text.sm, color: colors.muted, lineHeight: 1.4 },
  infoTrigger: {
    width: 18,
    height: 18,
    borderRadius: radius.xs,
    display: 'inline-grid',
    placeItems: 'center',
    padding: 0,
    cursor: 'pointer',
    fontFamily: font.mono,
    fontWeight: 600,
    fontSize: text.xxs,
    lineHeight: 1,
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: { default: colors.line2, ':hover': colors.accent, [opened]: colors.accent },
    backgroundColor: { default: 'transparent', ':hover': colors.accent, [opened]: colors.accent },
    color: { default: colors.muted, ':hover': colors.accentFg, [opened]: colors.accentFg },
    outline: { default: 'none', ':focus-visible': `2px solid ${colors.accent}` },
    outlineOffset: 2,
  },
  infoPopup: {
    width: 'min(420px, calc(100vw - 40px))',
    maxHeight: 'var(--available-height)',
    overflowY: 'auto',
    margin: 0,
    paddingBlock: space.lg,
    paddingInline: space.xl,
    borderRadius: radius.lg,
    backgroundColor: colors.raised,
    color: colors.fg,
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: colors.line2,
    boxShadow: colors.popShadow,
    fontSize: text.md,
    lineHeight: 1.5,
    display: 'grid',
    gap: space.sm,
    outline: 'none',
    transformOrigin: 'var(--transform-origin)',
    transitionProperty: 'opacity, transform',
    transitionDuration: '160ms',
    transitionTimingFunction: motion.settle,
    opacity: { default: 1, [fading]: 0 },
    transform: { default: 'none', [fading]: 'scale(.97)' },
  },
  disclosure: {
    cursor: 'pointer',
    color: { default: colors.muted, ':hover': colors.fg },
    fontSize: text.md,
    backgroundColor: 'transparent',
    borderWidth: 0,
    padding: 0,
    display: 'inline-flex',
    alignItems: 'center',
    gap: space.xs,
    outline: { default: 'none', ':focus-visible': `2px solid ${colors.accent}` },
    outlineOffset: 2,
  },
  count: {
    marginInlineStart: space.xs,
    fontFamily: font.mono,
    color: colors.faint,
    fontWeight: 500,
    fontVariantNumeric: 'tabular-nums',
  },
  chips: { display: 'flex', flexWrap: 'wrap', gap: space.xs },
  chip: {
    display: 'inline-flex',
    alignItems: 'center',
    paddingBlock: space.xxxs,
    paddingInline: space.sm,
    borderRadius: radius.pill,
    fontSize: text.sm,
    fontWeight: 500,
    cursor: 'pointer',
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: { default: colors.line2, ':hover': colors.faint },
    backgroundColor: { default: colors.sunk, ':hover': colors.hover },
    color: colors.muted,
    transitionProperty: 'background-color, border-color, color',
    transitionDuration: '120ms',
    outline: { default: 'none', ':focus-visible': `2px solid ${colors.accent}` },
    outlineOffset: 2,
  },
  chipOn: {
    borderColor: { default: colors.accent, ':hover': colors.accent },
    backgroundColor: { default: colors.accentSoft, ':hover': colors.accentSoft },
    color: colors.accent,
  },
  caret: { transition: 'transform .14s', display: 'inline-block', fontSize: text.xxs },
  caretOpen: { transform: 'rotate(90deg)' },
  panel: { marginTop: space.sm },
  choices: { display: 'grid', gap: space.sm },
  choice: {
    display: 'grid',
    gridTemplateColumns: '18px minmax(0, 1fr)',
    gap: space.md,
    alignItems: 'start',
    paddingBlock: space.lg,
    paddingInline: space.xl,
    borderRadius: radius.md,
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: { default: colors.line2, ':hover': colors.faint },
    backgroundColor: colors.panel,
    cursor: 'pointer',
    transitionProperty: 'border-color, background-color',
    transitionDuration: '140ms',
  },
  choiceOn: {
    borderColor: { default: colors.accent, ':hover': colors.accent },
    backgroundColor: colors.accentSoft,
  },
  choiceOnDanger: {
    borderColor: { default: colors.bad, ':hover': colors.bad },
    backgroundColor: colors.badSoft,
  },
  radio: {
    width: 16,
    height: 16,
    marginBlockStart: 3,
    padding: 0,
    display: 'grid',
    placeItems: 'center',
    borderRadius: '50%',
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: { default: colors.faint, [checked]: colors.accent },
    backgroundColor: colors.panel,
    cursor: 'pointer',
    outline: { default: 'none', ':focus-visible': `2px solid ${colors.accent}` },
    outlineOffset: 2,
  },
  radioDanger: { borderColor: { default: colors.faint, [checked]: colors.bad } },
  dot: { width: 8, height: 8, borderRadius: '50%', backgroundColor: colors.accent },
  dotDanger: { backgroundColor: colors.bad },
  choiceTitle: { fontWeight: 600 },
  choiceHelp: { display: 'block', fontSize: text.md, color: colors.muted, marginBlockStart: space.xxxs },
  contents: { display: 'contents' },
});

const segmentLook = (s: { pressed: boolean }) => cls(styles.segment, s.pressed && styles.segmentOn);

/** An option with an icon shows just the icon; its label becomes the tooltip. */
export function Segments<V extends string>({
  value,
  options,
  onChange,
  label,
}: {
  value: V;
  options: { value: V; label: string; count?: number; icon?: string }[];
  onChange: (v: V) => unknown;
  label: string;
}) {
  return (
    <ToggleGroup
      value={[value]}
      onValueChange={(v) => {
        if (v[0]) void onChange(v[0]);
      }}
      deselectable={false}
      aria-label={label}
      {...stylex.props(styles.segments)}
    >
      {options.map((o) => {
        const count = o.count !== undefined && <span {...stylex.props(styles.count)}>{o.count}</span>;
        return o.icon ? (
          <Hint
            key={o.value}
            tip={o.label}
            names
            render={<Toggle value={o.value} aria-label={o.label} className={segmentLook} />}
          >
            <Icon name={o.icon} size={17} />
            {count}
          </Hint>
        ) : (
          <Toggle key={o.value} value={o.value} className={segmentLook}>
            {o.label}
            {count}
          </Toggle>
        );
      })}
    </ToggleGroup>
  );
}

/** Clicking the selected chip clears it. */
export function ChipFilter({
  value,
  options,
  onChange,
  label,
}: {
  value: string;
  options: { value: string; count: number }[];
  onChange: (v: string) => unknown;
  label: string;
}) {
  return (
    <ToggleGroup
      value={value ? [value] : []}
      onValueChange={(v) => void onChange(v[0] ?? '')}
      aria-label={label}
      {...stylex.props(styles.chips)}
    >
      {options.map((o) => (
        <Toggle key={o.value} value={o.value} className={(s) => cls(styles.chip, s.pressed && styles.chipOn)}>
          {o.value}
          <span {...stylex.props(styles.count)}>{o.count}</span>
        </Toggle>
      ))}
    </ToggleGroup>
  );
}

export function ChoiceCards({
  value,
  options,
  onChange,
  label,
}: {
  value: string;
  options: { value: string; label: string; help?: string }[];
  onChange: (v: string) => unknown;
  label: string;
}) {
  return (
    <ToggleGroup
      value={[value]}
      onValueChange={(v) => {
        if (v[0]) void onChange(v[0]);
      }}
      deselectable={false}
      aria-label={label}
      {...stylex.props(styles.cards)}
    >
      {options.map((o) => (
        <Toggle key={o.value} value={o.value} className={(s) => cls(styles.card, s.pressed && styles.cardOn)}>
          <span {...stylex.props(styles.cardTitle)}>{o.label}</span>
          {o.help && <span {...stylex.props(styles.cardHelp)}>{o.help}</span>}
        </Toggle>
      ))}
    </ToggleGroup>
  );
}

export function Switch({ on, label, onToggle }: { on: boolean; label: string; onToggle: () => unknown }) {
  return (
    <SwitchRoot
      checked={on}
      onCheckedChange={() => {
        void onToggle();
      }}
      aria-label={label}
      {...stylex.props(styles.switch)}
    >
      <SwitchThumb {...stylex.props(styles.thumb)} />
    </SwitchRoot>
  );
}

export function InfoTip({ label, children }: { label: string; children: ReactNode }) {
  return (
    <Popover>
      <PopoverTrigger aria-label={label} {...stylex.props(styles.infoTrigger)}>
        i
      </PopoverTrigger>
      <PopoverContent sideOffset={8} align="start" aria-label={label} {...stylex.props(styles.infoPopup)}>
        {children}
      </PopoverContent>
    </Popover>
  );
}

export function Disclosure({ label, children }: { label: string; children: ReactNode }) {
  return (
    <Collapsible>
      <CollapsibleTrigger {...stylex.props(styles.disclosure)}>
        {(s) => (
          <>
            <span {...stylex.props(styles.caret, s.open && styles.caretOpen)}>▶</span>
            {label}
          </>
        )}
      </CollapsibleTrigger>
      <CollapsiblePanel {...stylex.props(styles.panel)}>{children}</CollapsiblePanel>
    </Collapsible>
  );
}

/** Radios as selectable cards; the whole card picks. */
export function RadioCards<V extends string>({
  value,
  options,
  onChange,
  label,
}: {
  value: V;
  options: { value: V; title: string; help?: ReactNode; danger?: boolean }[];
  onChange: (v: V) => unknown;
  label: string;
}) {
  return (
    <RadioGroup
      value={value}
      onValueChange={(v) => {
        if (v !== null) void onChange(v);
      }}
      aria-label={label}
      {...stylex.props(styles.choices)}
    >
      {options.map((o) => (
        <label
          key={o.value}
          {...stylex.props(styles.choice, o.value === value && (o.danger ? styles.choiceOnDanger : styles.choiceOn))}
        >
          <Radio value={o.value} {...stylex.props(styles.radio, o.danger && styles.radioDanger)}>
            <RadioIndicator {...stylex.props(styles.dot, o.danger && styles.dotDanger)} />
          </Radio>
          <span>
            <span {...stylex.props(styles.choiceTitle)}>{o.title}</span>
            {o.help && <span {...stylex.props(styles.choiceHelp)}>{o.help}</span>}
          </span>
        </label>
      ))}
    </RadioGroup>
  );
}

/** A controlled disclosure whose trigger and panel sit apart; it adds no box of its own. */
export function Fold({
  open,
  onOpenChange,
  children,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  children: ReactNode;
}) {
  return (
    <Collapsible
      open={open}
      onOpenChange={(o) => {
        onOpenChange(o);
      }}
      {...stylex.props(styles.contents)}
    >
      {children}
    </Collapsible>
  );
}

export function FoldTrigger({ look, children }: { look: stylex.StyleXStyles; children: ReactNode }) {
  return <CollapsibleTrigger {...stylex.props(look)}>{children}</CollapsibleTrigger>;
}

export function FoldPanel({ look, children }: { look: stylex.StyleXStyles; children: ReactNode }) {
  return <CollapsiblePanel {...stylex.props(look)}>{children}</CollapsiblePanel>;
}

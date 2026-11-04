import * as stylex from '@stylexjs/stylex';
import { Collapsible } from '@base-ui/react/collapsible';
import { Popover } from '@base-ui/react/popover';
import { Switch as BaseSwitch } from '@base-ui/react/switch';
import { Toggle } from '@base-ui/react/toggle';
import { ToggleGroup } from '@base-ui/react/toggle-group';
import { useState, type ReactNode } from 'react';
import { colors, radius, space, text } from '../theme/tokens.stylex';
import { Icon } from './Icon';

const cls = (...s: stylex.StyleXStyles[]) => stylex.props(...s).className ?? '';

const styles = stylex.create({
  segments: {
    display: 'inline-flex',
    gap: space.xxxs,
    padding: space.xxs,
    borderRadius: radius.md,
    backgroundColor: colors.sunk,
    flexWrap: 'wrap',
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: colors.line,
  },
  segment: {
    borderWidth: 0,
    backgroundColor: 'transparent',
    paddingBlock: space.xs,
    paddingInline: space.lg,
    borderRadius: radius.sm,
    fontSize: text.md,
    fontWeight: 600,
    color: { default: colors.muted, ':hover': colors.fg },
    cursor: 'pointer',
  },
  segmentOn: { backgroundColor: colors.panel, color: colors.fg, boxShadow: colors.liftShadow },
  switch: {
    width: 44,
    height: 26,
    borderRadius: radius.pill,
    borderWidth: 0,
    backgroundColor: colors.line2,
    position: 'relative',
    cursor: 'pointer',
    padding: 0,
    flexShrink: 0,
    justifySelf: 'start',
    transition: 'background-color .15s',
  },
  switchOn: { backgroundColor: colors.accent },
  thumb: {
    position: 'absolute',
    top: 3,
    left: 3,
    width: 20,
    height: 20,
    borderRadius: '50%',
    backgroundColor: colors.onFill,
    transition: 'left .15s',
    boxShadow: colors.liftShadow,
  },
  thumbOn: { left: 21 },
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
    backgroundColor: colors.panel,
    color: colors.fg,
  },
  cardOn: {
    borderColor: { default: colors.accent, ':hover': colors.accent },
    backgroundColor: colors.accentSoft,
    boxShadow: `inset 0 0 0 1px ${colors.accent}`,
    color: colors.accent,
  },
  cardTitle: { fontSize: text.base, fontWeight: 700 },
  cardHelp: { fontSize: text.sm, color: colors.muted, lineHeight: 1.4 },
  infoTrigger: {
    width: 18,
    height: 18,
    borderRadius: '50%',
    display: 'inline-grid',
    placeItems: 'center',
    padding: 0,
    cursor: 'pointer',
    fontFamily: 'Georgia, serif',
    fontStyle: 'italic',
    fontWeight: 600,
    fontSize: text.xxs,
    lineHeight: 1,
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: { default: colors.line2, ':hover': colors.accent },
    backgroundColor: { default: 'transparent', ':hover': colors.accent },
    color: { default: colors.muted, ':hover': colors.accentFg },
  },
  infoOpen: { backgroundColor: colors.accent, borderColor: colors.accent, color: colors.accentFg },
  infoPopup: {
    width: 'min(420px, calc(100vw - 40px))',
    paddingBlock: space.lg,
    paddingInline: space.xl,
    borderRadius: radius.lg,
    backgroundColor: colors.panel,
    color: colors.fg,
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: colors.line2,
    boxShadow: colors.popShadow,
    fontSize: text.md,
    lineHeight: 1.5,
    display: 'grid',
    gap: space.sm,
    zIndex: 30,
    outline: 'none',
  },
  positioner: { zIndex: 30 },
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
  },
  count: { marginInlineStart: space.xs, color: colors.faint, fontWeight: 500, fontVariantNumeric: 'tabular-nums' },
  chips: { display: 'flex', flexWrap: 'wrap', gap: space.xs },
  chip: {
    display: 'inline-flex',
    alignItems: 'center',
    paddingBlock: space.xxs,
    paddingInline: space.md,
    borderRadius: radius.pill,
    fontSize: text.sm,
    fontWeight: 600,
    cursor: 'pointer',
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: { default: colors.line2, ':hover': colors.faint },
    backgroundColor: { default: colors.sunk, ':hover': colors.hover },
    color: colors.muted,
  },
  chipOn: {
    borderColor: { default: colors.accent, ':hover': colors.accent },
    backgroundColor: { default: colors.accentSoft, ':hover': colors.accentSoft },
    color: colors.accent,
  },
  caret: { transition: 'transform .15s', display: 'inline-block', fontSize: text.xxs },
  caretOpen: { transform: 'rotate(90deg)' },
  panel: { marginTop: space.sm },
});

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
      aria-label={label}
      {...stylex.props(styles.segments)}
    >
      {options.map((o) => (
        <Toggle
          key={o.value}
          value={o.value}
          aria-label={o.icon ? o.label : undefined}
          title={o.icon ? o.label : undefined}
          className={(s) => cls(styles.segment, s.pressed && styles.segmentOn)}
        >
          {o.icon ? <Icon name={o.icon} size={17} /> : o.label}
          {o.count !== undefined && <span {...stylex.props(styles.count)}>{o.count}</span>}
        </Toggle>
      ))}
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
    <BaseSwitch.Root
      checked={on}
      onCheckedChange={() => {
        void onToggle();
      }}
      aria-label={label}
      className={(s) => cls(styles.switch, s.checked && styles.switchOn)}
    >
      <BaseSwitch.Thumb className={(s) => cls(styles.thumb, s.checked && styles.thumbOn)} />
    </BaseSwitch.Root>
  );
}

export function InfoTip({ label, children }: { label: string; children: ReactNode }) {
  return (
    <Popover.Root>
      <Popover.Trigger aria-label={label} className={(s) => cls(styles.infoTrigger, s.open && styles.infoOpen)}>
        i
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Positioner sideOffset={8} align="start" {...stylex.props(styles.positioner)}>
          <Popover.Popup {...stylex.props(styles.infoPopup)}>{children}</Popover.Popup>
        </Popover.Positioner>
      </Popover.Portal>
    </Popover.Root>
  );
}

export function Disclosure({ label, children }: { label: string; children: ReactNode }) {
  const [open, setOpen] = useState(false);
  return (
    <Collapsible.Root open={open} onOpenChange={setOpen}>
      <Collapsible.Trigger {...stylex.props(styles.disclosure)}>
        <span {...stylex.props(styles.caret, open && styles.caretOpen)}>▶</span>
        {label}
      </Collapsible.Trigger>
      <Collapsible.Panel {...stylex.props(styles.panel)}>{children}</Collapsible.Panel>
    </Collapsible.Root>
  );
}

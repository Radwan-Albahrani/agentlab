import * as stylex from '@stylexjs/stylex';
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandGroupLabel,
  CommandInput,
  CommandItem,
  CommandList,
  type CommandData,
  type CommandDataItem,
} from '@ui-sdk/react/command';
import { Dialog, DialogBackdrop, DialogContent } from '@ui-sdk/react/dialog';
import { useMemo, type ReactNode } from 'react';
import { hueTheme } from '../theme/hues';
import { colors, font, media, motion, radius, space, text } from '../theme/tokens.stylex';
import { Icon } from './Icon';

const fading = ':is([data-starting-style], [data-ending-style])';

const styles = stylex.create({
  backdrop: {
    position: 'fixed',
    inset: 0,
    backgroundColor: colors.overlay,
    transitionProperty: 'opacity',
    transitionDuration: '160ms',
    opacity: { default: 1, [fading]: 0 },
  },
  popup: {
    position: 'fixed',
    top: { default: '14vh', [media.phone]: space.xxl },
    left: 0,
    right: 0,
    bottom: 'auto',
    marginBlock: 0,
    marginInline: 'auto',
    padding: 0,
    width: 'min(640px, calc(100vw - 24px))',
    overflow: 'hidden',
    borderRadius: radius.xxl,
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: colors.line2,
    backgroundColor: colors.panel,
    color: colors.fg,
    boxShadow: colors.popShadow,
    outline: 'none',
    transformOrigin: 'top center',
    transitionProperty: 'opacity, transform',
    transitionDuration: '160ms',
    transitionTimingFunction: motion.settle,
    opacity: { default: 1, [fading]: 0 },
    transform: { default: 'none', [fading]: 'scale(.97)' },
  },
  field: {
    display: 'flex',
    alignItems: 'center',
    gap: space.md,
    paddingBlock: space.lg,
    paddingInline: space.xxl,
    borderBottomWidth: 1,
    borderBottomStyle: 'solid',
    borderBottomColor: colors.line,
    color: colors.faint,
  },
  input: {
    flex: '1',
    minWidth: 0,
    borderWidth: 0,
    outline: 'none',
    backgroundColor: 'transparent',
    fontSize: text.lg,
    color: colors.fg,
    '::placeholder': { color: colors.faint },
  },
  kbd: {
    fontFamily: font.mono,
    fontSize: text.xxs,
    fontWeight: 500,
    color: colors.faint,
    paddingBlock: 1,
    paddingInline: space.xs,
    borderRadius: radius.xs,
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: colors.line2,
    backgroundColor: colors.sunk,
  },
  list: { maxHeight: 'min(60vh, 460px)', overflowY: 'auto', padding: space.xs, scrollPaddingBlock: space.xs },
  group: {
    paddingBlockStart: space.md,
    paddingBlockEnd: space.xxs,
    paddingInline: space.md,
    fontSize: text.xxs,
    fontWeight: 500,
    color: colors.faint,
  },
  item: {
    display: 'flex',
    alignItems: 'center',
    gap: space.lg,
    paddingBlock: space.sm,
    paddingInline: space.md,
    borderRadius: radius.md,
    backgroundColor: { default: 'transparent', ':is([data-highlighted])': colors.accentSoft },
    color: colors.fg,
    cursor: 'pointer',
    userSelect: 'none',
  },
  icon: {
    width: 28,
    height: 28,
    flexShrink: 0,
    display: 'grid',
    placeItems: 'center',
    borderRadius: radius.sm,
    backgroundColor: colors.sunk,
    color: colors.muted,
  },
  iconActive: { backgroundColor: colors.accent, color: colors.accentFg },
  label: { flex: '1', minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', fontWeight: 500 },
  hint: { fontFamily: font.mono, fontSize: text.xs, color: colors.faint, whiteSpace: 'nowrap' },
  enter: { color: colors.accent, display: 'flex' },
  empty: {
    display: { default: 'none', ':is([data-empty])': 'block' },
    paddingBlock: space.huge,
    textAlign: 'center',
    color: colors.faint,
  },
  foot: {
    display: 'flex',
    gap: space.xxl,
    paddingBlock: space.sm,
    paddingInline: space.xxl,
    borderTopWidth: 1,
    borderTopStyle: 'solid',
    borderTopColor: colors.line,
    fontSize: text.xs,
    color: colors.faint,
  },
  footItem: { display: 'flex', alignItems: 'center', gap: space.xs },
});

export interface CommandEntry {
  id: string;
  group: string;
  label: string;
  hint?: string;
  icon: ReactNode;
  hue?: string; // an agent's colour around the icon, which then keeps its own fill when highlighted
}

const toItem = (e: CommandEntry): CommandDataItem => ({ value: e.id, label: e.label });

/** Groups in order of first appearance, so the list never repeats a heading. */
function byGroup(entries: CommandEntry[]): CommandData {
  const groups = new Map<string, CommandDataItem[]>();
  for (const e of entries) groups.set(e.group, [...(groups.get(e.group) ?? []), toItem(e)]);
  return [...groups].map(([label, items]) => ({ type: 'group', label, items }));
}

interface SearchProps<E extends CommandEntry> {
  label: string;
  placeholder: string;
  entries: E[];
  rank: (entries: E[], query: string) => E[];
  onRun: (entry: E) => void;
}

/** A modal search over commands: type to rank them, arrows to move, Enter to run, Esc to clear and then close. */
export function CommandPalette<E extends CommandEntry>({
  open,
  onOpenChange,
  ...search
}: SearchProps<E> & { open: boolean; onOpenChange: (open: boolean) => void }) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogBackdrop {...stylex.props(styles.backdrop)} />
      <DialogContent {...stylex.props(styles.popup)} aria-label={search.label}>
        <Search {...search} />
      </DialogContent>
    </Dialog>
  );
}

// mounts with the dialog's content, so every opening starts from an empty search
function Search<E extends CommandEntry>({ label, placeholder, entries, rank, onRun }: SearchProps<E>) {
  const byId = useMemo(() => new Map(entries.map((e) => [e.id, e])), [entries]);
  const all = useMemo(() => entries.map(toItem), [entries]);
  const grouped = useMemo(() => byGroup(entries), [entries]);
  // the caller's ranking scores each command: earlier hits score higher, a miss scores 0 and hides
  const filter = (item: { value: string }, query: string) => {
    const hits = rank(entries, query);
    const at = hits.findIndex((e) => e.id === item.value);
    return at < 0 ? 0 : hits.length - at;
  };

  const item = (c: CommandDataItem) => {
    const e = byId.get(c.value);
    if (!e) return null;
    return (
      <CommandItem key={e.id} value={e.id} label={e.label} {...stylex.props(styles.item)}>
        {(s) => (
          <>
            <span {...stylex.props(hueTheme(e.hue), styles.icon, s.highlighted && !e.hue && styles.iconActive)}>{e.icon}</span>
            <span {...stylex.props(styles.label)}>{e.label}</span>
            {e.hint && <span {...stylex.props(styles.hint)}>{e.hint}</span>}
            {s.highlighted && (
              <span {...stylex.props(styles.enter)}>
                <Icon name="arrow" size={16} />
              </span>
            )}
          </>
        )}
      </CommandItem>
    );
  };

  return (
    <Command
      items={all}
      emptyItems={grouped}
      filter={filter}
      onAction={(id) => {
        const e = byId.get(id);
        if (e) onRun(e);
      }}
    >
      <div {...stylex.props(styles.field)}>
        <Icon name="search" size={20} />
        <CommandInput {...stylex.props(styles.input)} placeholder={placeholder} aria-label={label} />
        <kbd {...stylex.props(styles.kbd)}>Esc</kbd>
      </div>
      <CommandEmpty {...stylex.props(styles.empty)}>{(s) => `Nothing matches “${s.query}”.`}</CommandEmpty>
      {/* the list's own state.items: the ranked hits, or the groups while nothing is typed */}
      <CommandList {...stylex.props(styles.list)}>
        {(s) =>
          s.items.map((entry) =>
            typeof entry !== 'string' && 'type' in entry
              ? entry.type === 'group' && (
                  <CommandGroup key={entry.label}>
                    <CommandGroupLabel {...stylex.props(styles.group)}>{entry.label}</CommandGroupLabel>
                    {entry.items.map((c) => (typeof c === 'string' ? null : item(c)))}
                  </CommandGroup>
                )
              : typeof entry === 'string'
                ? null
                : item(entry),
          )
        }
      </CommandList>
      <div {...stylex.props(styles.foot)}>
        <span {...stylex.props(styles.footItem)}>
          <kbd {...stylex.props(styles.kbd)}>↑</kbd>
          <kbd {...stylex.props(styles.kbd)}>↓</kbd> move
        </span>
        <span {...stylex.props(styles.footItem)}>
          <kbd {...stylex.props(styles.kbd)}>Enter</kbd> open
        </span>
        <span {...stylex.props(styles.footItem)}>
          <kbd {...stylex.props(styles.kbd)}>Ctrl K</kbd> anywhere
        </span>
      </div>
    </Command>
  );
}

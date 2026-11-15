import * as stylex from '@stylexjs/stylex';
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandGroupLabel,
  CommandInput,
  CommandItem,
  CommandList,
} from '@ui-sdk/react/command';
import { Dialog, DialogBackdrop, DialogContent } from '@ui-sdk/react/dialog';
import { useMemo, useState, type ReactNode } from 'react';
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
    fontFamily: font.mono,
    fontSize: text.xxs,
    fontWeight: 500,
    letterSpacing: '.12em',
    textTransform: 'uppercase',
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
  // the empty part stays in the page and only fills in when nothing matches
  empty: { display: { default: 'block', ':empty': 'none' }, paddingBlock: space.huge, textAlign: 'center', color: colors.faint },
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

/** Groups in order of first appearance, so the list never repeats a heading. */
function byGroup<E extends CommandEntry>(entries: E[]): [string, E[]][] {
  const groups = new Map<string, E[]>();
  for (const e of entries) groups.set(e.group, [...(groups.get(e.group) ?? []), e]);
  return [...groups];
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
  const [query, setQuery] = useState('');
  const [picked, setPicked] = useState<string | null>(null);
  const hits = useMemo(() => rank(entries, query), [rank, entries, query]);
  const groups = query.trim() ? null : byGroup(hits);
  const shown = groups ? groups.flatMap(([, list]) => list) : hits;
  // the ranking owns the highlight: the best hit unless the person moved it
  const highlighted = shown.some((e) => e.id === picked) ? picked : (shown[0]?.id ?? null);

  const item = (e: E) => (
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

  return (
    <Command
      filter={false}
      query={query}
      onQueryChange={(q) => {
        setQuery(q);
        setPicked(null);
      }}
      value={highlighted}
      onValueChange={(v, d) => {
        if (d.reason === 'list-navigation' || d.reason === 'item-hover') setPicked(v);
      }}
      onAction={(id) => {
        const e = shown.find((x) => x.id === id);
        if (e) onRun(e);
      }}
    >
      <div {...stylex.props(styles.field)}>
        <Icon name="search" size={20} />
        <CommandInput {...stylex.props(styles.input)} placeholder={placeholder} aria-label={label} />
        <kbd {...stylex.props(styles.kbd)}>Esc</kbd>
      </div>
      <CommandEmpty {...stylex.props(styles.empty)}>Nothing matches “{query}”.</CommandEmpty>
      <CommandList {...stylex.props(styles.list)}>
        {groups
          ? groups.map(([name, list]) => (
              <CommandGroup key={name}>
                <CommandGroupLabel {...stylex.props(styles.group)}>{name}</CommandGroupLabel>
                {list.map(item)}
              </CommandGroup>
            ))
          : hits.map(item)}
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

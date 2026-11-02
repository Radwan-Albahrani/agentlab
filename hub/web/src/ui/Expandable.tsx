import * as stylex from '@stylexjs/stylex';
import { Collapsible } from '@base-ui/react/collapsible';
import { useState, type ReactNode } from 'react';
import { colors, radius, space } from '../theme/tokens.stylex';
import { Card } from './Card';
import { Icon } from './Icon';

const styles = stylex.create({
  head: {
    appearance: 'none',
    width: '100%',
    display: 'flex',
    alignItems: 'center',
    gap: space.lg,
    paddingBlock: space.lg,
    paddingInline: space.xl,
    borderWidth: 0,
    borderRadius: radius.lg,
    backgroundColor: { default: 'transparent', ':hover': colors.hover },
    color: colors.fg,
    textAlign: 'start',
    cursor: 'pointer',
    outline: { default: 'none', ':focus-visible': `2px solid color-mix(in srgb, ${colors.accent} 55%, transparent)` },
  },
  summary: { flexGrow: 1, minWidth: 0 },
  caret: { display: 'flex', color: colors.faint, transition: 'transform .15s', transform: 'rotate(-90deg)' },
  caretOpen: { transform: 'rotate(0deg)' },
  body: { display: 'grid', gap: space.lg, paddingInline: space.xl, paddingBottom: space.xl },
});

/** A card that shows one summary row and opens to its details when the row is clicked. */
export function Expandable({
  summary,
  aside,
  children,
}: {
  summary: ReactNode; // the always-visible text (title and status line)
  aside?: ReactNode; // tags or pills at the right of the row
  children: ReactNode;
}) {
  const [open, setOpen] = useState(false);
  return (
    <Card>
      <Collapsible.Root open={open} onOpenChange={setOpen}>
        <Collapsible.Trigger {...stylex.props(styles.head)}>
          <span {...stylex.props(styles.caret, open && styles.caretOpen)}>
            <Icon name="chevron" size={16} />
          </span>
          <span {...stylex.props(styles.summary)}>{summary}</span>
          {aside}
        </Collapsible.Trigger>
        <Collapsible.Panel {...stylex.props(styles.body)}>{children}</Collapsible.Panel>
      </Collapsible.Root>
    </Card>
  );
}

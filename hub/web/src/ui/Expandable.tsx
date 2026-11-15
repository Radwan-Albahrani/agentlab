import * as stylex from '@stylexjs/stylex';
import { Collapsible, CollapsiblePanel, CollapsibleTrigger } from '@ui-sdk/react/collapsible';
import type { ReactNode } from 'react';
import { colors, radius, space } from '../theme/tokens.stylex';
import { Card } from './Card';
import { Icon } from './Icon';

const styles = stylex.create({
  // the aside sits beside the trigger, not in it: a button can't hold other controls
  bar: { display: 'flex', alignItems: 'center' },
  aside: { display: 'flex', alignItems: 'center', paddingInlineEnd: space.xl },
  head: {
    appearance: 'none',
    flexGrow: 1,
    minWidth: 0,
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
    outline: { default: 'none', ':focus-visible': `2px solid ${colors.accent}` },
    outlineOffset: 2,
  },
  summary: { flexGrow: 1, minWidth: 0 },
  caret: { display: 'flex', color: colors.faint, transition: 'transform .14s', transform: 'rotate(-90deg)' },
  caretOpen: { transform: 'rotate(0deg)' },
  body: { display: 'grid', gap: space.lg, paddingInline: space.xl, paddingBottom: space.xl },
});

export function Expandable({ summary, aside, children }: { summary: ReactNode; aside?: ReactNode; children: ReactNode }) {
  return (
    <Card>
      <Collapsible>
        <div {...stylex.props(styles.bar)}>
          <CollapsibleTrigger {...stylex.props(styles.head)}>
            {(s) => (
              <>
                <span {...stylex.props(styles.caret, s.open && styles.caretOpen)}>
                  <Icon name="chevron" size={16} />
                </span>
                <span {...stylex.props(styles.summary)}>{summary}</span>
              </>
            )}
          </CollapsibleTrigger>
          {aside && <span {...stylex.props(styles.aside)}>{aside}</span>}
        </div>
        <CollapsiblePanel {...stylex.props(styles.body)}>{children}</CollapsiblePanel>
      </Collapsible>
    </Card>
  );
}

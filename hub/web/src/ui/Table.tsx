import * as stylex from '@stylexjs/stylex';
import type { ReactNode } from 'react';
import { colors, font, media, space, text } from '../theme/tokens.stylex';

// A table that becomes one stacked block per row on phones (columns marked `wide` hide there).

const styles = stylex.create({
  table: { width: '100%', borderCollapse: 'collapse', fontSize: text.base },
  head: { display: { default: null, [media.table]: 'none' } },
  th: {
    textAlign: 'left',
    fontSize: text.xs,
    fontWeight: 600,
    color: colors.faint,
    paddingBlock: space.md,
    paddingInline: space.xxl,
    borderBottomWidth: 1,
    borderBottomStyle: 'solid',
    borderBottomColor: colors.line,
  },
  tr: {
    backgroundColor: { default: null, ':hover': colors.hover },
    display: { default: null, [media.table]: 'grid' },
    gridTemplateColumns: '1fr auto',
    rowGap: space.xxs,
    columnGap: space.md,
    paddingBlock: { default: 0, [media.table]: space.lg },
    paddingInline: { default: 0, [media.table]: space.xxl },
    borderTopWidth: { default: 1, ':first-child': 0 },
    borderTopStyle: 'solid',
    borderTopColor: colors.line,
  },
  td: {
    paddingBlock: { default: space.lg, [media.table]: 0 },
    paddingInline: { default: space.xxl, [media.table]: 0 },
    verticalAlign: 'middle',
  },
  num: { textAlign: { default: 'right', [media.table]: 'left' }, fontVariantNumeric: 'tabular-nums', whiteSpace: 'nowrap' },
  span: { gridColumn: { default: null, [media.table]: '1 / -1' } },
  wide: { display: { default: null, [media.table]: 'none' } },
  fit: { width: { default: '1%', [media.table]: 'auto' }, whiteSpace: 'nowrap' },
  muted: { color: colors.muted, fontSize: text.sm },
  mono: { fontFamily: font.mono, fontSize: text.sm },
});

export const Table = ({ head, children }: { head?: ReactNode; children: ReactNode }) => (
  <table {...stylex.props(styles.table)}>
    {head && (
      <thead {...stylex.props(styles.head)}>
        <tr>{head}</tr>
      </thead>
    )}
    <tbody>{children}</tbody>
  </table>
);

export const Th = ({ num, wide, fit, children }: { num?: boolean; wide?: boolean; fit?: boolean; children?: ReactNode }) => (
  <th {...stylex.props(styles.th, num && styles.num, wide && styles.wide, fit && styles.fit)}>{children}</th>
);

export const Tr = ({ children }: { children: ReactNode }) => <tr {...stylex.props(styles.tr)}>{children}</tr>;

/** num: right-aligned (on phones it spans the row); wide: hidden on phones; fit: as narrow as its content;
 * muted / mono: secondary text. */
export const Td = ({
  num,
  wide,
  fit,
  muted,
  mono,
  colSpan,
  children,
}: {
  num?: boolean;
  wide?: boolean;
  fit?: boolean;
  muted?: boolean;
  mono?: boolean;
  colSpan?: number;
  children?: ReactNode;
}) => (
  <td
    {...stylex.props(
      styles.td,
      num && styles.num,
      num && styles.span,
      wide && styles.wide,
      fit && styles.fit,
      muted && styles.muted,
      mono && styles.mono,
    )}
    colSpan={colSpan}
  >
    {children}
  </td>
);

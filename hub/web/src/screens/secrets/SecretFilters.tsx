import * as stylex from '@stylexjs/stylex';
import type { Secret } from '../../api/types';
import { KIND_LABELS, kindCounts, users, type KindFilter, type SecretFilter } from '../../lib/secretFilter';
import { colors, media, radius, space, text } from '../../theme/tokens.stylex';
import { ChipFilter, Segments } from '../../ui/controls';
import { SearchInput } from '../../ui/inputs';

const styles = stylex.create({
  bar: {
    display: 'grid',
    gap: space.lg,
    paddingBlock: space.lg,
    paddingInline: space.xxl,
    borderRadius: radius.xl,
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: colors.line,
    backgroundColor: colors.panel,
  },
  row: {
    display: 'grid',
    gridTemplateColumns: { default: '88px minmax(0, 1fr)', [media.phone]: '1fr' },
    gap: { default: space.lg, [media.phone]: space.xs },
    alignItems: 'center',
  },
  label: {
    fontSize: text.xxs,
    fontWeight: 500,
    color: colors.faint,
  },
});

interface Props {
  items: Secret[];
  filter: SecretFilter;
  onChange: (change: Partial<SecretFilter>) => void;
}

export function SecretFilters({ items, filter, onChange }: Props) {
  const counts = kindCounts(items, filter);
  const kinds = (Object.keys(KIND_LABELS) as KindFilter[]).map((k) => ({ value: k, label: KIND_LABELS[k], count: counts[k] }));
  const usedBy = users(items, filter);
  return (
    <div {...stylex.props(styles.bar)}>
      <SearchInput
        label="Search secrets"
        value={filter.q}
        onChange={(q) => {
          onChange({ q });
        }}
      />
      <div {...stylex.props(styles.row)}>
        <span {...stylex.props(styles.label)}>On change</span>
        <div>
          <Segments
            label="On change"
            value={filter.kind}
            options={kinds}
            onChange={(kind) => {
              onChange({ kind });
            }}
          />
        </div>
      </div>
      {usedBy.length > 0 && (
        <div {...stylex.props(styles.row)}>
          <span {...stylex.props(styles.label)}>Used by</span>
          <ChipFilter
            label="Used by"
            value={filter.usedBy}
            options={usedBy.map((u) => ({ value: u.name, count: u.count }))}
            onChange={(next) => {
              onChange({ usedBy: next });
            }}
          />
        </div>
      )}
    </div>
  );
}

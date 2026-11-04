import type { Secret } from '../../api/types';
import { KIND_LABELS, kindCounts, users, type KindFilter, type SecretFilter } from '../../lib/secretFilter';
import { ChipFilter, Segments } from '../../ui/controls';
import { SearchInput } from '../../ui/inputs';
import { Stack } from '../../ui/layout';

interface Props {
  items: Secret[];
  filter: SecretFilter;
  onChange: (change: Partial<SecretFilter>) => void;
}

export function SecretFilters({ items, filter, onChange }: Props) {
  const counts = kindCounts(items, filter);
  const kinds = (Object.keys(KIND_LABELS) as KindFilter[]).map((k) => ({ value: k, label: KIND_LABELS[k], count: counts[k] }));
  return (
    <Stack gap="md">
      <SearchInput
        label="Search secrets"
        value={filter.q}
        onChange={(q) => {
          onChange({ q });
        }}
      />
      <Segments
        label="On change"
        value={filter.kind}
        options={kinds}
        onChange={(kind) => {
          onChange({ kind });
        }}
      />
      <ChipFilter
        label="Used by"
        value={filter.usedBy}
        options={users(items, filter).map((u) => ({ value: u.name, count: u.count }))}
        onChange={(usedBy) => {
          onChange({ usedBy });
        }}
      />
    </Stack>
  );
}

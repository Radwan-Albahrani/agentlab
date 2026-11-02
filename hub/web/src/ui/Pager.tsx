import { Button } from './Button';
import { Inline } from './layout';
import { Text } from './text';

/** ‹ 2 / 5 ›, for a section's header; nothing when everything fits on one page. */
export function Pager({ page, pages, setPage }: { page: number; pages: number; setPage: (p: number) => void }) {
  if (pages < 2) return null;
  return (
    <Inline gap="xs" nowrap>
      <Button
        label="Newer"
        icon="back"
        variant="quiet"
        small
        iconOnly
        disabled={page === 0}
        onClick={() => {
          setPage(page - 1);
        }}
      />
      <Text tone="muted" size="md">
        {page + 1} / {pages}
      </Text>
      <Button
        label="Older"
        icon="arrow"
        variant="quiet"
        small
        iconOnly
        disabled={page === pages - 1}
        onClick={() => {
          setPage(page + 1);
        }}
      />
    </Inline>
  );
}

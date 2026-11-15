import * as stylex from '@stylexjs/stylex';
import { Pagination, PaginationItem, PaginationList, PaginationNext, PaginationPrevious } from '@ui-sdk/react/pagination';
import { space } from '../theme/tokens.stylex';
import { Hint, look } from './Button';
import { Icon } from './Icon';
import { Text } from './text';

const styles = stylex.create({
  list: { display: 'flex', alignItems: 'center', gap: space.xs, margin: 0, padding: 0, listStyle: 'none', minWidth: 0 },
});

const step = (label: string) => look({ label, variant: 'quiet', small: true, iconOnly: true });

/** Renders nothing when everything fits on one page. `page` counts from 0. */
export function Pager({ page, pages, setPage }: { page: number; pages: number; setPage: (p: number) => void }) {
  if (pages < 2) return null;
  return (
    <Pagination
      aria-label="Pages"
      pageCount={pages}
      page={page + 1}
      onPageChange={(p) => {
        setPage(p - 1);
      }}
    >
      <PaginationList {...stylex.props(styles.list)}>
        {(s) => (
          <>
            <PaginationItem>
              <Hint tip="Newer" names render={<PaginationPrevious {...step('Newer')} aria-label="Newer" />}>
                <Icon name="back" size={16} />
              </Hint>
            </PaginationItem>
            <PaginationItem>
              <Text tone="muted" size="md">
                {s.page} / {s.pageCount}
              </Text>
            </PaginationItem>
            <PaginationItem>
              <Hint tip="Older" names render={<PaginationNext {...step('Older')} aria-label="Older" />}>
                <Icon name="arrow" size={16} />
              </Hint>
            </PaginationItem>
          </>
        )}
      </PaginationList>
    </Pagination>
  );
}

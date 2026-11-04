import { useState } from 'react';

/** One page of a list; the page stays in range when the list shrinks. */
export function usePages<T>(items: T[], size: number) {
  const [page, setPage] = useState(0);
  const pages = Math.max(1, Math.ceil(items.length / size));
  const at = Math.min(page, pages - 1);
  return { shown: items.slice(at * size, (at + 1) * size), page: at, pages, setPage };
}

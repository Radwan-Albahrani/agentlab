import { useEffect, type ReactNode } from 'react';
import { useLocation } from 'react-router-dom';
import type { UseQueryResult } from '@tanstack/react-query';
import { ApiError } from '../api/client';
import { Card } from '../ui/Card';
import { Empty, Loading, PageHead } from '../ui/page';

/** A screen's states: loading, not found (hidden or unknown), failed, or the screen itself. */
export function Screen<T>({
  title,
  query,
  children,
}: {
  title: string;
  query: UseQueryResult<T>;
  children: (data: T) => ReactNode;
}) {
  const { hash } = useLocation();
  const loaded = query.data !== undefined;
  useEffect(() => {
    document.title = `${title} · Agents`;
  }, [title]);
  useEffect(() => {
    if (loaded && hash) document.getElementById(hash.slice(1))?.scrollIntoView({ behavior: 'smooth' });
  }, [loaded, hash]);

  if (loaded) return <>{children(query.data as T)}</>;
  if (query.error instanceof ApiError && query.error.status === 404) return <NotFound />;
  if (query.error)
    return (
      <>
        <PageHead title={title} />
        <Card>
          <Empty title="Could not load this" text={query.error.message} icon="alert" />
        </Card>
      </>
    );
  return <Loading />;
}

export function NotFound() {
  return (
    <>
      <PageHead title="Not found" />
      <Card>
        <Empty title="There's nothing here" text="Check the address, or pick a page in the menu." icon="alert" />
      </Card>
    </>
  );
}

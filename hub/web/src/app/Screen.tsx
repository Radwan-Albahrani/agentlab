import { useEffect, useRef, type ReactNode } from 'react';
import { useLocation } from 'react-router';
import type { UseQueryResult } from '@tanstack/react-query';
import { ApiError } from '../api/client';
import { Card } from '../ui/Card';
import { Empty, Loading, PageHead } from '../ui/page';

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
  // only an opened link scrolls to its #section: switching tabs changes the hash too, and must not move the page
  const jumped = useRef(false);
  useEffect(() => {
    if (!loaded || jumped.current) return;
    jumped.current = true;
    if (hash) document.getElementById(hash.slice(1))?.scrollIntoView({ behavior: 'smooth' });
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

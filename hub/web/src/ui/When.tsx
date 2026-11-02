import { ago, exact } from '../lib/format';

/** "5 min ago", with the exact time on hover. */
export function When({ t }: { t: number | null | undefined }) {
  if (!t) return null;
  return <time title={exact(t)}>{ago(t)}</time>;
}

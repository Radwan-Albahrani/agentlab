import { ago, exact } from '../lib/format';

export function When({ t }: { t: number | null | undefined }) {
  if (!t) return null;
  return <time title={exact(t)}>{ago(t)}</time>;
}

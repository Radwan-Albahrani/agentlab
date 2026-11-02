import { useSearchParams } from 'react-router-dom';
import { isKind, type SecretFilter } from '../../lib/secretFilter';

/** The Secrets screen's search and filters, kept in the URL (?q=&effect=&usedBy=) so a view can be linked or reloaded. */
export function useSecretFilter(): [SecretFilter, (change: Partial<SecretFilter>) => void] {
  const [params, setParams] = useSearchParams();
  const effect = params.get('effect');
  const filter: SecretFilter = {
    q: params.get('q') ?? '',
    kind: isKind(effect) ? effect : 'all',
    usedBy: params.get('usedBy') ?? '',
  };
  const update = (change: Partial<SecretFilter>) => {
    const next = { ...filter, ...change };
    const query: Record<string, string> = {};
    if (next.q) query.q = next.q;
    if (next.kind !== 'all') query.effect = next.kind;
    if (next.usedBy) query.usedBy = next.usedBy;
    setParams(query, { replace: true });
  };
  return [filter, update];
}

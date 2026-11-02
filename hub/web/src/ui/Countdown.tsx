import { useNow } from '../lib/useNow';
import { Text } from './text';

/** "expires in 4 min", ticking every second; "expired" once `until` (an ISO time) has passed. */
export function Countdown({ until }: { until: string }) {
  const now = useNow(1000);
  const ms = Date.parse(until) - now * 1000;
  if (Number.isNaN(ms)) return null;
  const left = ms < 60_000 ? `${Math.ceil(ms / 1000)} s` : `${Math.ceil(ms / 60_000)} min`;
  return (
    <Text tone="warn" size="md" weight="semibold" block>
      {ms <= 0 ? 'expired' : `expires in ${left}`}
    </Text>
  );
}

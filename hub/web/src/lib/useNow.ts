import { useEffect, useState } from 'react';

/** The current time in epoch seconds, refreshed every `everyMs`, so components showing "x ago" stay pure. */
export function useNow(everyMs = 60_000): number {
  const [now, setNow] = useState(() => Date.now() / 1000);
  useEffect(() => {
    const t = setInterval(() => {
      setNow(Date.now() / 1000);
    }, everyMs);
    return () => {
      clearInterval(t);
    };
  }, [everyMs]);
  return now;
}

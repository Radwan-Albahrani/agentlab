import { useLocation, useNavigate } from 'react-router';

/** The open tab in the URL's #hash; the first tab has none, and an unknown hash opens it. */
export function useHashTab(tabs: string[]): [string, (tab: string) => void] {
  const { hash } = useLocation();
  const navigate = useNavigate();
  const first = tabs[0] ?? '';
  const wanted = decodeURIComponent(hash.slice(1));
  const value = tabs.includes(wanted) ? wanted : first;
  return [
    value,
    (tab) => {
      void navigate({ hash: tab === first ? '' : tab }, { preventScrollReset: true });
    },
  ];
}

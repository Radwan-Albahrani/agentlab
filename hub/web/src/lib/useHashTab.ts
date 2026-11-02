import { useLocation, useNavigate } from 'react-router-dom';

/** The open tab lives in the URL's #hash, so a link can open a tab and Back returns to the previous one. The first
 * tab has no hash. An unknown hash (a tab that is hidden now) opens the first tab. */
export function useHashTab(tabs: string[]): [string, (tab: string) => void] {
  const { hash } = useLocation();
  const navigate = useNavigate();
  const first = tabs[0] ?? '';
  const wanted = decodeURIComponent(hash.slice(1));
  const value = tabs.includes(wanted) ? wanted : first;
  return [
    value,
    (tab) => {
      navigate({ hash: tab === first ? '' : tab }, { preventScrollReset: true });
    },
  ];
}

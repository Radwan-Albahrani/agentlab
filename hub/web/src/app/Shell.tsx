import * as stylex from '@stylexjs/stylex';
import type { ReactNode } from 'react';
import { useLocation } from 'react-router';
import { useNav } from '../api/queries';
import { setAgentColors } from '../theme/hues';
import { media, motion, space } from '../theme/tokens.stylex';
import { Loading } from '../ui/page';
import { buildMenu } from './menu';
import { Palette } from './Palette';
import { PhoneNav } from './PhoneNav';
import { Sidebar } from './Sidebar';
import { StatusLine } from './StatusLine';
import { usePresentingSwitch } from './usePresentingSwitch';

const enter = stylex.keyframes({ from: { opacity: 0, transform: 'translateY(3px)' } });

const styles = stylex.create({
  app: { display: 'grid', gridTemplateColumns: { default: '236px minmax(0, 1fr)', [media.nav]: '1fr' }, minHeight: '100vh' },
  column: { minWidth: 0 },
  main: {
    minWidth: 0,
    paddingTop: { default: 28, [media.nav]: space.xxl },
    // room for the phone's tab bar
    paddingBottom: { default: 72, [media.nav]: 'calc(96px + env(safe-area-inset-bottom))' },
    paddingInline: {
      default: `max(${space.giant}, env(safe-area-inset-left))`,
      [media.nav]: `max(${space.xxl}, env(safe-area-inset-left))`,
    },
  },
  // keyed by the page: each page change eases in
  inner: {
    maxWidth: 1280,
    marginInline: 'auto',
    display: 'grid',
    gap: space.huge,
    animationName: enter,
    animationDuration: '180ms',
    animationTimingFunction: motion.settle,
  },
});

export function Shell({ children }: { children: ReactNode }) {
  const { data: nav } = useNav();
  const { pathname } = useLocation();
  const onLogo = usePresentingSwitch();
  setAgentColors(nav?.colors); // must run before children render
  const menu = nav ? buildMenu(nav) : { main: [], agents: [], system: [] };
  return (
    <div {...stylex.props(styles.app)}>
      <Sidebar menu={menu} onLogo={onLogo} />
      <div {...stylex.props(styles.column)}>
        <PhoneNav menu={menu} />
        <StatusLine />
        <main {...stylex.props(styles.main)}>
          {/* pages wait for the menu: it carries the agents' colours, which pages read as they render */}
          <div key={pathname} {...stylex.props(styles.inner)}>
            {nav ? children : <Loading />}
          </div>
        </main>
      </div>
      <Palette menu={menu} />
    </div>
  );
}

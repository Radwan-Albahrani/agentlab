import * as stylex from '@stylexjs/stylex';
import type { ReactNode } from 'react';
import { useNav } from '../api/queries';
import { setAgentColors } from '../theme/hues';
import { media, space } from '../theme/tokens.stylex';
import { buildMenu } from './menu';
import { PhoneNav } from './PhoneNav';
import { Sidebar } from './Sidebar';
import { usePresentingSwitch } from './usePresentingSwitch';

const styles = stylex.create({
  app: { display: 'grid', gridTemplateColumns: { default: '244px minmax(0, 1fr)', [media.nav]: '1fr' }, minHeight: '100vh' },
  column: { minWidth: 0 },
  main: {
    minWidth: 0,
    paddingTop: { default: 28, [media.nav]: space.xxl },
    paddingBottom: 64,
    paddingInline: `max(${space.xxl}, env(safe-area-inset-left))`,
  },
  inner: { maxWidth: 1120, marginInline: 'auto', display: 'grid', gap: space.huge },
});

/** The frame around every screen: the sidebar on desktop, a pill bar on phones. */
export function Shell({ children }: { children: ReactNode }) {
  const { data: nav } = useNav();
  const onLogo = usePresentingSwitch();
  setAgentColors(nav?.colors); // before anything below paints an agent's colour
  const menu = nav ? buildMenu(nav) : { main: [], agents: [], system: [] };
  return (
    <div {...stylex.props(styles.app)}>
      <Sidebar menu={menu} onLogo={onLogo} />
      <div {...stylex.props(styles.column)}>
        <PhoneNav menu={menu} />
        <main {...stylex.props(styles.main)}>
          <div {...stylex.props(styles.inner)}>{children}</div>
        </main>
      </div>
    </div>
  );
}

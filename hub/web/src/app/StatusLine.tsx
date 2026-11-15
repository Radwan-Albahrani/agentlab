import * as stylex from '@stylexjs/stylex';
import { Link } from 'react-router';
import { useNav, useNowBoard } from '../api/queries';
import { plural } from '../lib/format';
import { useNow } from '../lib/useNow';
import { colors, font, media, space, text } from '../theme/tokens.stylex';
import { openPalette } from './Palette';
import { Pressable } from '../ui/Button';

const blink = stylex.keyframes({ '50%': { opacity: 0.2 } });

const styles = stylex.create({
  bar: {
    position: 'sticky',
    top: 0,
    zIndex: 15,
    display: { default: 'flex', [media.nav]: 'none' },
    alignItems: 'center',
    gap: space.xl,
    minHeight: 34,
    paddingInline: space.giant,
    backgroundColor: colors.bg,
    borderBottomWidth: 1,
    borderBottomStyle: 'solid',
    borderBottomColor: colors.line,
    fontFamily: font.mono,
    fontSize: text.xxs,
    color: colors.faint,
    fontVariantNumeric: 'tabular-nums',
    whiteSpace: 'nowrap',
    overflow: 'hidden',
  },
  item: { display: 'inline-flex', alignItems: 'center', gap: space.xs },
  dot: {
    width: 6,
    height: 6,
    backgroundColor: colors.ok,
    animationName: blink,
    animationDuration: '2s',
    animationIterationCount: 'infinite',
  },
  lost: { backgroundColor: colors.warn, animationName: 'none' },
  run: { color: colors.info },
  act: { color: colors.accent },
  link: { color: { default: 'inherit', ':hover': colors.fg } },
  end: { marginInlineStart: 'auto' },
  kbd: {
    appearance: 'none',
    fontFamily: 'inherit',
    fontSize: 'inherit',
    letterSpacing: 'inherit',
    textTransform: 'inherit',
    color: { default: colors.faint, ':hover': colors.fg },
    backgroundColor: 'transparent',
    borderWidth: 0,
    padding: 0,
    cursor: 'pointer',
  },
});

/** The console's heartbeat on every page: connection, clock, what's running and what waits on you. */
export function StatusLine() {
  const nav = useNav();
  const agents = useNowBoard().data?.agents ?? [];
  const now = useNow(1000);
  const lost = nav.isError || (nav.dataUpdatedAt > 0 && now * 1000 - nav.dataUpdatedAt > 60_000);
  const running = agents.reduce((n, a) => n + a.running + a.background, 0);
  // things literally waiting on an answer: chats asking a question, companion tasks awaiting approval
  const companions = nav.data?.agents.reduce((n, a) => n + a.companions.reduce((m, c) => m + c.waiting, 0), 0) ?? 0;
  const waiting = agents.reduce((n, a) => n + a.waiting, 0) + companions;
  const date = new Date(now * 1000);
  return (
    <div {...stylex.props(styles.bar)} aria-label="Status">
      <span {...stylex.props(styles.item)}>
        <i {...stylex.props(styles.dot, lost && styles.lost)} />
        {lost ? 'reconnecting' : 'live'}
      </span>
      <span>
        {date.toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short' })}{' '}
        {date.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
      </span>
      <span {...stylex.props(running > 0 && styles.run)}>{plural(running, 'chat')} running</span>
      <Link to="/" {...stylex.props(styles.link, waiting > 0 && styles.act)}>
        {waiting} waiting on you
      </Link>
      <span {...stylex.props(styles.end)}>
        <Pressable look={styles.kbd} onClick={openPalette}>
          Ctrl K · search
        </Pressable>
      </span>
    </div>
  );
}

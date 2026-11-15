import * as stylex from '@stylexjs/stylex';
import type { ReactNode } from 'react';
import { colors, font, media, radius, space, text } from '../../theme/tokens.stylex';
import { Button, LinkButton } from '../../ui/Button';
import { Disclosure } from '../../ui/controls';
import { Brand, Icon } from '../../ui/Icon';
import { Note } from '../../ui/text';

const run = stylex.keyframes({ to: { backgroundPosition: '20px 0' } });

const styles = stylex.create({
  // the brand's mark on a square tile
  mark: {
    display: 'grid',
    placeItems: 'center',
    flexShrink: 0,
    borderRadius: radius.xs,
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: colors.line2,
    backgroundColor: colors.sunk,
    color: colors.fg,
  },
  markMd: { width: 36, height: 36 },
  markLg: { width: 44, height: 44 },
  glyph: { display: 'grid', placeItems: 'center' },
  glyphMd: { transform: 'scale(1.05)' },
  glyphLg: { transform: 'scale(1.3)' },

  box: {
    display: 'grid',
    gap: space.xl,
    padding: { default: space.xxl, [media.phone]: space.lg },
    borderRadius: radius.xs,
    backgroundColor: colors.raised,
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: colors.line,
    minWidth: 0,
  },
  steps: { listStyle: 'none', margin: 0, padding: 0, display: 'grid' },
  step: { display: 'grid', gridTemplateColumns: '28px minmax(0, 1fr)', columnGap: space.lg },
  rail: { display: 'flex', flexDirection: 'column', alignItems: 'center' },
  line: { flex: '1', width: 1, minHeight: space.lg, marginBlock: space.xxs, backgroundColor: colors.line2 },
  lineDone: { backgroundColor: `color-mix(in srgb, ${colors.ok} 60%, ${colors.line2})` },
  num: {
    width: 28,
    height: 28,
    borderRadius: radius.xs,
    display: 'grid',
    placeItems: 'center',
    fontFamily: font.mono,
    fontSize: text.xs,
    fontWeight: 600,
    fontVariantNumeric: 'tabular-nums',
    color: colors.faint,
    backgroundColor: colors.panel,
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: colors.line2,
    transitionProperty: 'background-color, border-color, color',
    transitionDuration: '140ms',
  },
  // amber: the one step waiting on the person
  numNow: { color: colors.accentFg, borderColor: colors.accent, backgroundColor: colors.accent },
  numDone: { color: colors.ok, borderColor: `color-mix(in srgb, ${colors.ok} 40%, transparent)`, backgroundColor: colors.okSoft },
  stepBody: { display: 'grid', gap: space.sm, minWidth: 0, paddingTop: 4, paddingBottom: space.xxl },
  stepBodyLast: { paddingBottom: 0 },
  title: { fontWeight: 600, fontSize: text.body, lineHeight: 1.35 },
  titleTodo: { color: colors.muted, fontWeight: 500 },
  sub: { color: colors.muted, fontSize: text.md, marginTop: -2 },
  code: {
    fontFamily: font.mono,
    fontSize: text.xxl,
    fontWeight: 600,
    fontVariantNumeric: 'tabular-nums',
    lineHeight: 1,
    letterSpacing: '.18em',
    paddingBlock: space.lg,
    paddingInlineStart: space.xxl,
    paddingInlineEnd: `calc(${space.xxl} - .18em)`,
    borderRadius: radius.xs,
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: colors.line2,
    backgroundColor: colors.sunk,
    display: 'inline-block',
    userSelect: 'all',
  },
  term: {
    whiteSpace: 'pre-wrap',
    overflowWrap: 'anywhere',
    backgroundColor: colors.sunk,
    color: colors.fg,
    borderRadius: radius.xs,
    padding: space.lg,
    fontFamily: font.mono,
    fontSize: text.xs,
    lineHeight: 1.5,
    maxHeight: 240,
    overflow: 'auto',
    marginBlockStart: 0,
    marginBlockEnd: space.sm,
    marginInline: 0,
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: colors.line,
  },
  end: { display: 'flex', alignItems: 'center', gap: space.md, flexWrap: 'wrap' },
  result: { display: 'inline-flex', alignItems: 'center', gap: space.xs, fontWeight: 600, fontSize: text.md },
  resultOk: { color: colors.ok },
  resultBad: { color: colors.bad },

  // the running dashed line from Row: work in progress
  live: {
    position: 'absolute',
    insetInline: 0,
    top: 0,
    height: 2,
    backgroundImage: `repeating-linear-gradient(90deg, ${colors.info} 0 6px, transparent 6px 10px)`,
    backgroundSize: '20px 2px',
    animationName: run,
    animationDuration: '1s',
    animationTimingFunction: 'linear',
    animationIterationCount: 'infinite',
    pointerEvents: 'none',
  },

  callout: {
    display: 'flex',
    alignItems: 'center',
    gap: space.xl,
    flexWrap: { default: 'nowrap', [media.phone]: 'wrap' },
    paddingBlock: space.lg,
    paddingInline: space.xxl,
    borderRadius: radius.xs,
    borderWidth: 1,
    borderStyle: 'solid',
    minWidth: 0,
  },
  calloutWarn: { borderColor: `color-mix(in srgb, ${colors.warn} 55%, ${colors.line})`, backgroundColor: colors.warnSoft },
  calloutInfo: { borderColor: `color-mix(in srgb, ${colors.info} 45%, ${colors.line})`, backgroundColor: colors.panel },
  calloutIcon: {
    width: 32,
    height: 32,
    flexShrink: 0,
    display: 'grid',
    placeItems: 'center',
    borderRadius: radius.xs,
    borderWidth: 1,
    borderStyle: 'solid',
  },
  calloutIconWarn: { color: colors.warn, borderColor: `color-mix(in srgb, ${colors.warn} 45%, transparent)` },
  calloutIconInfo: { color: colors.info, borderColor: `color-mix(in srgb, ${colors.info} 40%, transparent)` },
  calloutText: { flex: '1', minWidth: 0, display: 'grid', gap: space.xxxs },
  calloutTitle: { fontWeight: 600 },
  calloutBody: { color: colors.muted, fontSize: text.md },
  calloutAction: { display: 'flex', gap: space.sm, flexWrap: 'wrap' },
});

/** A provider's logo on a square tile. */
export function BrandMark({ name, label, size = 'md' }: { name: string; label?: string; size?: 'md' | 'lg' }) {
  return (
    <span {...stylex.props(styles.mark, size === 'lg' ? styles.markLg : styles.markMd)}>
      <span {...stylex.props(styles.glyph, size === 'lg' ? styles.glyphLg : styles.glyphMd)}>
        <Brand name={name} label={label} />
      </span>
    </span>
  );
}

/** A dashed line running along the top edge of its (relatively positioned) parent. */
export const LiveEdge = () => <span {...stylex.props(styles.live)} aria-hidden="true" />;

export const FlowBox = ({ children }: { children: ReactNode }) => <div {...stylex.props(styles.box)}>{children}</div>;

export const Steps = ({ children }: { children: ReactNode }) => <ol {...stylex.props(styles.steps)}>{children}</ol>;

const code = (n: number) => String(n).padStart(2, '0');

/** `now`: the step waiting on the person, in amber. */
export function Step({
  n,
  done,
  now,
  last,
  title,
  sub,
  children,
}: {
  n: number;
  done?: boolean;
  now?: boolean;
  last?: boolean;
  title: string;
  sub?: ReactNode;
  children?: ReactNode;
}) {
  return (
    <li {...stylex.props(styles.step)}>
      <div {...stylex.props(styles.rail)}>
        <span {...stylex.props(styles.num, now && !done && styles.numNow, done && styles.numDone)}>
          {done ? <Icon name="check" size={14} /> : code(n)}
        </span>
        {!last && <span {...stylex.props(styles.line, done && styles.lineDone)} />}
      </div>
      <div {...stylex.props(styles.stepBody, last && styles.stepBodyLast)}>
        <div {...stylex.props(styles.title, !done && !now && styles.titleTodo)}>{title}</div>
        {sub && <div {...stylex.props(styles.sub)}>{sub}</div>}
        {children}
      </div>
    </li>
  );
}

export const DeviceCode = ({ code: c }: { code: string }) => <span {...stylex.props(styles.code)}>{c}</span>;

export function Terminal({ screen, children }: { screen: string; children?: ReactNode }) {
  return (
    <Disclosure label="Terminal">
      <pre {...stylex.props(styles.term)}>{screen}</pre>
      {children}
    </Disclosure>
  );
}

export function OpenSignInStep({
  provider,
  url,
  title = 'Open the sign-in page',
  sub,
}: {
  provider: string;
  url?: string | null;
  title?: string;
  sub?: ReactNode;
}) {
  return (
    <Step n={1} done={!!url} now={!url} title={title} sub={sub}>
      {url ? (
        <div>
          <LinkButton label={`Open ${provider} sign-in`} icon="ext" variant="primary" to={url} />
        </div>
      ) : (
        <Note>Waiting for the sign-in link…</Note>
      )}
    </Step>
  );
}

/** The flow's outcome (when known) beside its Cancel / Close button. */
export function FlowEnd({ finished, ok, onEnd }: { finished: boolean; ok?: ReactNode; onEnd: () => unknown }) {
  return (
    <div {...stylex.props(styles.end)}>
      <Button label={finished ? 'Close' : 'Cancel'} small onClick={onEnd} />
      {ok}
    </div>
  );
}

export function Result({ ok, children }: { ok: boolean; children: ReactNode }) {
  return (
    <span {...stylex.props(styles.result, ok ? styles.resultOk : styles.resultBad)}>
      <Icon name={ok ? 'check' : 'alert'} size={16} />
      {children}
    </span>
  );
}

/** A toned panel for what needs the person's attention, with its action. */
export function Callout({
  tone,
  icon,
  title,
  children,
  action,
}: {
  tone: 'warn' | 'info';
  icon: string;
  title: ReactNode;
  children?: ReactNode;
  action?: ReactNode;
}) {
  const warn = tone === 'warn';
  return (
    <div {...stylex.props(styles.callout, warn ? styles.calloutWarn : styles.calloutInfo)}>
      <span {...stylex.props(styles.calloutIcon, warn ? styles.calloutIconWarn : styles.calloutIconInfo)}>
        <Icon name={icon} size={17} />
      </span>
      <div {...stylex.props(styles.calloutText)}>
        <div {...stylex.props(styles.calloutTitle)}>{title}</div>
        {children && <div {...stylex.props(styles.calloutBody)}>{children}</div>}
      </div>
      {action && <div {...stylex.props(styles.calloutAction)}>{action}</div>}
    </div>
  );
}

import * as stylex from '@stylexjs/stylex';
import type { ReactNode } from 'react';
import { colors, font, media, radius, space, text } from '../../theme/tokens.stylex';
import { Button, LinkButton } from '../../ui/Button';
import { Disclosure } from '../../ui/controls';
import { Note } from '../../ui/text';

const styles = stylex.create({
  box: {
    marginInlineStart: { default: 62, [media.phone]: space.xxl },
    marginInlineEnd: space.xxl,
    marginBottom: space.xl,
    padding: space.xl,
    borderRadius: radius.lg,
    backgroundColor: colors.sunk,
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: colors.line,
    display: 'grid',
    gap: space.lg,
  },
  steps: { listStyle: 'none', margin: 0, padding: 0, display: 'grid', gap: space.lg },
  step: { display: 'grid', gridTemplateColumns: '24px 1fr', gap: space.md },
  num: {
    width: 24,
    height: 24,
    borderRadius: '50%',
    display: 'grid',
    placeItems: 'center',
    fontSize: text.xs,
    fontWeight: 700,
    backgroundColor: colors.panel,
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: colors.line2,
  },
  done: { color: colors.ok, backgroundColor: colors.okSoft, borderColor: 'transparent' },
  title: { fontWeight: 600 },
  sub: { color: colors.muted, fontSize: text.md, marginBlockStart: space.xxxs, marginBlockEnd: space.sm },
  code: {
    fontFamily: font.mono,
    fontSize: text.xxl,
    fontWeight: 600,
    lineHeight: 1,
    letterSpacing: '.12em',
    paddingBlock: space.md,
    paddingInline: space.lg,
    borderRadius: radius.md,
    borderWidth: 1,
    borderStyle: 'dashed',
    borderColor: colors.line2,
    backgroundColor: colors.panel,
    display: 'inline-block',
  },
  term: {
    whiteSpace: 'pre-wrap',
    overflowWrap: 'anywhere',
    backgroundColor: colors.panel,
    color: colors.fg,
    borderRadius: radius.md,
    padding: space.md,
    fontFamily: font.mono,
    fontSize: text.xs,
    maxHeight: 240,
    overflow: 'auto',
    marginBlockStart: '0',
    marginBlockEnd: space.sm,
    marginInline: 0,
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: colors.line,
  },
});

export const FlowBox = ({ children }: { children: ReactNode }) => <div {...stylex.props(styles.box)}>{children}</div>;

export const Steps = ({ children }: { children: ReactNode }) => <ol {...stylex.props(styles.steps)}>{children}</ol>;

export function Step({
  n,
  done,
  title,
  sub,
  children,
}: {
  n: number;
  done?: boolean;
  title: string;
  sub?: ReactNode;
  children?: ReactNode;
}) {
  return (
    <li {...stylex.props(styles.step)}>
      <span {...stylex.props(styles.num, done && styles.done)}>{done ? '✓' : n}</span>
      <div>
        <div {...stylex.props(styles.title)}>{title}</div>
        {sub && <div {...stylex.props(styles.sub)}>{sub}</div>}
        {children}
      </div>
    </li>
  );
}

export const DeviceCode = ({ code }: { code: string }) => <span {...stylex.props(styles.code)}>{code}</span>;

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
    <Step n={1} done={!!url} title={title} sub={sub}>
      {url ? (
        <LinkButton label={`Open ${provider} sign-in`} icon="ext" variant="primary" to={url} />
      ) : (
        <Note>Waiting for the sign-in link…</Note>
      )}
    </Step>
  );
}

export const FlowEnd = ({ finished, onEnd }: { finished: boolean; onEnd: () => unknown }) => (
  <div>
    <Button label={finished ? 'Close' : 'Cancel'} small onClick={onEnd} />
  </div>
);

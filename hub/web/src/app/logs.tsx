import * as stylex from '@stylexjs/stylex';
import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from 'react';
import { useLogsTail } from '../api/queries';
import { containerLabel } from '../lib/format';
import { colors, font, radius, space, text } from '../theme/tokens.stylex';
import { Button } from '../ui/Button';
import { Dialog, DialogActions } from '../ui/Dialog';
import { useAct } from '../ui/feedback';
import { Icon } from '../ui/Icon';
import { Spacer } from '../ui/layout';
import { When } from '../ui/When';

const GIVE_UP_MS = 45_000;

const run = stylex.keyframes({ to: { backgroundPosition: '20px 0' } });

const styles = stylex.create({
  console: {
    position: 'relative',
    display: 'grid',
    minWidth: 0,
    overflow: 'hidden',
    borderRadius: radius.md,
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: colors.line,
    backgroundColor: colors.sunk,
  },
  bar: {
    position: 'relative',
    display: 'flex',
    alignItems: 'center',
    gap: space.sm,
    paddingBlock: space.sm,
    paddingInline: space.lg,
    fontSize: text.xxs,
    fontVariantNumeric: 'tabular-nums',
    color: colors.faint,
    borderBottomWidth: 1,
    borderBottomStyle: 'solid',
    borderBottomColor: colors.line,
    backgroundColor: colors.raised,
  },
  name: {
    fontSize: text.xs,
    textTransform: 'none',
    letterSpacing: 0,
    color: colors.muted,
    fontWeight: 600,
    overflow: 'hidden',
    textOverflow: 'ellipsis',
  },
  dot: { width: 7, height: 7, flexShrink: 0, backgroundColor: colors.faint },
  dotOk: { backgroundColor: colors.ok },
  dotBad: { backgroundColor: colors.bad },
  pre: {
    margin: 0,
    maxHeight: '62vh',
    overflow: 'auto',
    whiteSpace: 'pre-wrap',
    overflowWrap: 'anywhere',
    fontFamily: font.mono,
    fontSize: text.xs,
    lineHeight: 1.6,
    paddingBlock: space.lg,
    paddingInline: space.xl,
    color: colors.fg,
  },
  waiting: { color: colors.faint },
  // the running dashed line under the bar while the watcher fetches
  live: {
    position: 'absolute',
    insetInline: 0,
    bottom: -1,
    height: 1,
    backgroundImage: `repeating-linear-gradient(90deg, ${colors.info} 0 6px, transparent 6px 10px)`,
    backgroundSize: '20px 1px',
    animationName: run,
    animationDuration: '1s',
    animationTimingFunction: 'linear',
    animationIterationCount: 'infinite',
  },
});

interface Request {
  name: string;
  since: number;
}

const Ctx = createContext<((name: string) => void) | null>(null);

export function LogsProvider({ children }: { children: ReactNode }) {
  const act = useAct();
  const [request, setRequest] = useState<Request | null>(null);
  const open = (name: string) => {
    setRequest({ name, since: Date.now() / 1000 });
    void act('/api/services/logs', { name }, { quiet: true });
  };
  return (
    <Ctx.Provider value={open}>
      {children}
      <Dialog
        open={request !== null}
        onClose={() => {
          setRequest(null);
        }}
        wide
        title={request ? containerLabel(request.name) : ''}
        text="The last 400 lines, newest at the bottom."
      >
        {request && <Tail key={request.since} request={request} />}
        <DialogActions>
          <Button
            label="Refresh"
            icon="refresh"
            small
            onClick={() => {
              if (request) open(request.name);
            }}
          />
          <Button
            label="Close"
            small
            onClick={() => {
              setRequest(null);
            }}
          />
        </DialogActions>
      </Dialog>
    </Ctx.Provider>
  );
}

function Tail({ request }: { request: Request }) {
  const { data } = useLogsTail(request.name, request.since);
  const fresh = data && data.at >= request.since - 1 ? data : undefined;
  const [gaveUp, setGaveUp] = useState(false);
  const pre = useRef<HTMLPreElement>(null);
  useEffect(() => {
    const t = setTimeout(() => {
      setGaveUp(true);
    }, GIVE_UP_MS);
    return () => {
      clearTimeout(t);
    };
  }, []);
  useEffect(() => {
    if (fresh && pre.current) pre.current.scrollTop = pre.current.scrollHeight;
  }, [fresh]);
  const shown = fresh
    ? fresh.text || '(no output)'
    : gaveUp
      ? 'The watcher did not answer in time. Try Refresh.'
      : 'Fetching the last 400 lines…';
  const lines = fresh?.text ? fresh.text.trimEnd().split('\n').length : 0;
  return (
    <div {...stylex.props(styles.console)}>
      <div {...stylex.props(styles.bar)}>
        <i {...stylex.props(styles.dot, !!fresh && styles.dotOk, !fresh && gaveUp && styles.dotBad)} />
        <Icon name="terminal" size={14} />
        <span {...stylex.props(styles.name)}>{request.name}</span>
        <Spacer />
        {fresh ? (
          <span>
            {lines} lines · <When t={fresh.at} />
          </span>
        ) : (
          <span>{gaveUp ? 'no answer' : 'fetching'}</span>
        )}
        {!fresh && !gaveUp && <span {...stylex.props(styles.live)} />}
      </div>
      <pre ref={pre} {...stylex.props(styles.pre, !fresh && styles.waiting)} data-logs>
        {shown}
      </pre>
    </div>
  );
}

export function useLogs() {
  const open = useContext(Ctx);
  if (!open) throw new Error('useLogs outside LogsProvider');
  return open;
}

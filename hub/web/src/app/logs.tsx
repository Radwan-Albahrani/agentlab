import * as stylex from '@stylexjs/stylex';
import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from 'react';
import { useLogsTail } from '../api/queries';
import { containerLabel } from '../lib/format';
import { colors, font, radius, space, text } from '../theme/tokens.stylex';
import { Button } from '../ui/Button';
import { Dialog, DialogActions } from '../ui/Dialog';
import { useAct } from '../ui/feedback';

const GIVE_UP_MS = 45_000;

const styles = stylex.create({
  pre: {
    margin: 0,
    maxHeight: '65vh',
    overflow: 'auto',
    whiteSpace: 'pre-wrap',
    overflowWrap: 'anywhere',
    fontFamily: font.mono,
    fontSize: text.xs,
    padding: space.lg,
    borderRadius: radius.md,
    backgroundColor: colors.sunk,
    color: colors.fg,
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: colors.line,
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
  return (
    <pre ref={pre} {...stylex.props(styles.pre)} data-logs>
      {shown}
    </pre>
  );
}

export function useLogs() {
  const open = useContext(Ctx);
  if (!open) throw new Error('useLogs outside LogsProvider');
  return open;
}

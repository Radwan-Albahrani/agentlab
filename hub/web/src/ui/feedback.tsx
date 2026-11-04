import * as stylex from '@stylexjs/stylex';
import { Toast } from '@base-ui/react/toast';
import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { post } from '../api/client';
import { colors, radius, space, text } from '../theme/tokens.stylex';
import { ConfirmDialog } from './Dialog';
import { Icon } from './Icon';

interface Feedback {
  toast: (msg: string, bad?: boolean) => void;
  confirm: (text: string) => Promise<boolean>;
}

const Ctx = createContext<Feedback | null>(null);

const styles = stylex.create({
  viewport: {
    position: 'fixed',
    right: 'max(20px, env(safe-area-inset-right))',
    bottom: 'max(20px, env(safe-area-inset-bottom))',
    zIndex: 50,
    display: 'grid',
    gap: space.sm,
    width: 'min(340px, calc(100vw - 32px))',
    outline: 'none',
  },
  toast: {
    display: 'flex',
    alignItems: 'center',
    gap: space.sm,
    paddingBlock: space.sm,
    paddingInlineStart: space.sm,
    paddingInlineEnd: space.xs,
    borderRadius: radius.md,
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: colors.line2,
    backgroundColor: colors.panel,
    color: colors.fg,
    boxShadow: colors.popShadow,
    transition: 'opacity .2s, transform .2s',
  },
  moving: { opacity: 0, transform: 'translateX(16px)' },
  mark: {
    flex: 'none',
    width: 20,
    height: 20,
    borderRadius: radius.pill,
    display: 'grid',
    placeItems: 'center',
    backgroundColor: colors.okSoft,
    color: colors.ok,
  },
  markBad: { backgroundColor: colors.badSoft, color: colors.bad },
  // Base UI renders the title as a heading
  title: {
    flexGrow: 1,
    minWidth: 0,
    margin: 0,
    fontSize: text.md,
    fontWeight: 500,
    lineHeight: 1.4,
    overflowWrap: 'anywhere',
  },
  close: {
    flex: 'none',
    appearance: 'none',
    borderWidth: 0,
    padding: space.xxs,
    borderRadius: radius.sm,
    display: 'flex',
    cursor: 'pointer',
    backgroundColor: { default: 'transparent', ':hover': colors.hover },
    color: { default: colors.faint, ':hover': colors.fg },
  },
});

function Toasts() {
  const { toasts } = Toast.useToastManager();
  return (
    <Toast.Portal>
      <Toast.Viewport {...stylex.props(styles.viewport)}>
        {toasts.map((t) => (
          <Toast.Root
            key={t.id}
            toast={t}
            // oxlint-disable-next-line jsx-a11y/no-redundant-roles -- required: overrides Base UI's role="dialog"
            render={<output role="status" />}
            className={(s) =>
              stylex.props(styles.toast, (s.transitionStatus === 'starting' || s.transitionStatus === 'ending') && styles.moving)
                .className ?? ''
            }
          >
            <span {...stylex.props(styles.mark, t.type === 'error' && styles.markBad)}>
              <Icon name={t.type === 'error' ? 'alert' : 'check'} size={12} />
            </span>
            <Toast.Title {...stylex.props(styles.title)} />
            <Toast.Close {...stylex.props(styles.close)} aria-label="Dismiss">
              <Icon name="x" size={14} />
            </Toast.Close>
          </Toast.Root>
        ))}
      </Toast.Viewport>
    </Toast.Portal>
  );
}

function Provider({ children }: { children: ReactNode }) {
  const manager = Toast.useToastManager();
  const [ask, setAsk] = useState<{ text: string; resolve: (ok: boolean) => void } | null>(null);
  const toast = useCallback(
    (msg: string, bad = false) => {
      manager.add({ title: msg, type: bad ? 'error' : 'info', timeout: bad ? 6000 : 3200 });
    },
    [manager],
  );
  const confirm = useCallback(
    (text: string) =>
      new Promise<boolean>((resolve) => {
        setAsk({ text, resolve });
      }),
    [],
  );
  const value = useMemo(() => ({ toast, confirm }), [toast, confirm]);
  const answer = (ok: boolean) => {
    ask?.resolve(ok);
    setAsk(null);
  };
  return (
    <Ctx.Provider value={value}>
      {children}
      <ConfirmDialog text={ask?.text ?? null} onAnswer={answer} />
      <Toasts />
    </Ctx.Provider>
  );
}

export function FeedbackProvider({ children }: { children: ReactNode }) {
  return (
    <Toast.Provider limit={3}>
      <Provider>{children}</Provider>
    </Toast.Provider>
  );
}

export function useFeedback(): Feedback {
  const f = useContext(Ctx);
  if (!f) throw new Error('useFeedback outside FeedbackProvider');
  return f;
}

/** POST with optional confirm, toast the result, refresh all data; resolves true on success. */
export function useAct() {
  const { toast, confirm } = useFeedback();
  const qc = useQueryClient();
  return useCallback(
    async (url: string, body: Record<string, unknown> = {}, opts: { confirm?: string | null; quiet?: boolean } = {}) => {
      if (opts.confirm && !(await confirm(opts.confirm))) return false;
      try {
        const msg = await post(url, body);
        if (!opts.quiet) toast(msg);
        await qc.invalidateQueries();
        return true;
      } catch (e) {
        toast((e as Error).message, true);
        return false;
      }
    },
    [toast, confirm, qc],
  );
}

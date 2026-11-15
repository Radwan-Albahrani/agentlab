import * as stylex from '@stylexjs/stylex';
import { createToaster, Toast, ToastClose, ToastRegion, ToastTitle } from '@ui-sdk/react/toast';
import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { post } from '../api/client';
import { colors, motion, radius, space, text } from '../theme/tokens.stylex';
import { ConfirmDialog } from './Dialog';
import { Icon } from './Icon';

interface Feedback {
  toast: (msg: string, bad?: boolean) => void;
  confirm: (text: string) => Promise<boolean>;
}

const Ctx = createContext<Feedback | null>(null);

const fading = ':is([data-starting-style], [data-ending-style])';

const styles = stylex.create({
  // the region is a top-layer popover: clear the UA popover box, then pin it bottom-right
  region: {
    position: 'fixed',
    top: 'auto',
    left: 'auto',
    insetInlineEnd: 'max(20px, env(safe-area-inset-right))',
    bottom: 'max(20px, env(safe-area-inset-bottom))',
    width: 'min(340px, calc(100vw - 32px))',
    margin: 0,
    padding: 0,
    borderWidth: 0,
    overflow: 'visible',
    backgroundColor: 'transparent',
    color: colors.fg,
    outline: 'none',
  },
  toast: {
    display: 'flex',
    alignItems: 'center',
    gap: space.sm,
    marginBlockStart: space.sm,
    paddingBlock: space.md,
    paddingInlineStart: space.md,
    paddingInlineEnd: space.sm,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: colors.line2,
    backgroundColor: colors.raised,
    color: colors.fg,
    boxShadow: colors.popShadow,
    outline: { default: 'none', ':focus-visible': `2px solid ${colors.accent}` },
    outlineOffset: 2,
    transitionProperty: 'opacity, transform',
    transitionDuration: '160ms',
    transitionTimingFunction: motion.settle,
    opacity: { default: 1, [fading]: 0 },
    transform: { default: 'none', [fading]: 'translateY(8px) scale(.97)' },
  },
  mark: {
    flex: 'none',
    width: 20,
    height: 20,
    borderRadius: radius.xs,
    display: 'grid',
    placeItems: 'center',
    backgroundColor: colors.okSoft,
    color: colors.ok,
  },
  markBad: { backgroundColor: colors.badSoft, color: colors.bad },
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
    outline: { default: 'none', ':focus-visible': `2px solid ${colors.accent}` },
  },
});

export function FeedbackProvider({ children }: { children: ReactNode }) {
  const [toaster] = useState(() => createToaster<string>());
  const [ask, setAsk] = useState<{ text: string; resolve: (ok: boolean) => void } | null>(null);
  const toast = useCallback(
    (msg: string, bad = false) => {
      toaster(msg, { type: bad ? 'error' : 'info', duration: bad ? 6000 : 3200 });
    },
    [toaster],
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
      <ToastRegion toaster={toaster} side="bottom" align="end" maxVisible={3} {...stylex.props(styles.region)}>
        {(t) => (
          <Toast {...stylex.props(styles.toast)}>
            <span {...stylex.props(styles.mark, t.type === 'error' && styles.markBad)}>
              <Icon name={t.type === 'error' ? 'alert' : 'check'} size={12} />
            </span>
            <ToastTitle {...stylex.props(styles.title)} />
            <ToastClose {...stylex.props(styles.close)} aria-label="Dismiss">
              <Icon name="x" size={14} />
            </ToastClose>
          </Toast>
        )}
      </ToastRegion>
    </Ctx.Provider>
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

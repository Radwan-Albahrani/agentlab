import * as stylex from '@stylexjs/stylex';
import { AlertDialog } from '@base-ui/react/alert-dialog';
import { Dialog as Base } from '@base-ui/react/dialog';
import type { ReactNode } from 'react';
import { colors, radius, space, text } from '../theme/tokens.stylex';
import { Button } from './Button';

const styles = stylex.create({
  backdrop: { position: 'fixed', inset: 0, backgroundColor: colors.overlay, backdropFilter: 'blur(2px)', zIndex: 40 },
  popup: {
    position: 'fixed',
    top: '50%',
    left: '50%',
    transform: 'translate(-50%, -50%)',
    zIndex: 41,
    width: 'min(560px, calc(100vw - 32px))',
    maxHeight: 'calc(100vh - 48px)',
    overflow: 'auto',
    backgroundColor: colors.panel,
    color: colors.fg,
    borderRadius: radius.xxl,
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: colors.line2,
    boxShadow: colors.popShadow,
    padding: space.xxxl,
    display: 'grid',
    gap: space.xl,
    outline: 'none',
  },
  wide: { width: 'min(1000px, calc(100vw - 32px))' },
  title: { margin: 0, fontSize: text.lg },
  text: { margin: 0, color: colors.muted, fontSize: text.base },
  actions: { display: 'flex', justifyContent: 'flex-end', gap: space.sm, flexWrap: 'wrap', alignItems: 'center' },
});

export function Dialog({
  open,
  onClose,
  title,
  text,
  wide,
  children,
}: {
  open: boolean;
  onClose: () => void;
  title: ReactNode;
  text?: ReactNode;
  wide?: boolean;
  children?: ReactNode;
}) {
  return (
    <Base.Root
      open={open}
      onOpenChange={(o) => {
        if (!o) onClose();
      }}
    >
      <Base.Portal>
        <Base.Backdrop {...stylex.props(styles.backdrop)} />
        <Base.Popup {...stylex.props(styles.popup, wide && styles.wide)}>
          <Base.Title {...stylex.props(styles.title)}>{title}</Base.Title>
          {text && <Base.Description {...stylex.props(styles.text)}>{text}</Base.Description>}
          {children}
        </Base.Popup>
      </Base.Portal>
    </Base.Root>
  );
}

export function ConfirmDialog({ text, onAnswer }: { text: string | null; onAnswer: (ok: boolean) => void }) {
  return (
    <AlertDialog.Root
      open={text !== null}
      onOpenChange={(o) => {
        if (!o) onAnswer(false);
      }}
    >
      <AlertDialog.Portal>
        <AlertDialog.Backdrop {...stylex.props(styles.backdrop)} />
        <AlertDialog.Popup {...stylex.props(styles.popup)}>
          <AlertDialog.Title {...stylex.props(styles.title)}>Are you sure?</AlertDialog.Title>
          <AlertDialog.Description {...stylex.props(styles.text)}>{text}</AlertDialog.Description>
          <DialogActions>
            <Button
              label="Cancel"
              onClick={() => {
                onAnswer(false);
              }}
            />
            <Button
              label="Continue"
              variant="primary"
              onClick={() => {
                onAnswer(true);
              }}
            />
          </DialogActions>
        </AlertDialog.Popup>
      </AlertDialog.Portal>
    </AlertDialog.Root>
  );
}

export const DialogActions = ({ children }: { children: ReactNode }) => <div {...stylex.props(styles.actions)}>{children}</div>;

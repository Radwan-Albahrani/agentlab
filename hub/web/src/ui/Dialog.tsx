import * as stylex from '@stylexjs/stylex';
import {
  AlertDialog,
  AlertDialogBackdrop,
  AlertDialogClose,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogTitle,
} from '@ui-sdk/react/alert-dialog';
import { Dialog as Root, DialogBackdrop, DialogContent, DialogDescription, DialogTitle } from '@ui-sdk/react/dialog';
import { Drawer, DrawerBackdrop, DrawerContent } from '@ui-sdk/react/drawer';
import type { ReactNode } from 'react';
import { colors, font, motion, radius, space, text } from '../theme/tokens.stylex';
import { look } from './Button';

const fading = ':is([data-starting-style], [data-ending-style])';

const styles = stylex.create({
  backdrop: {
    position: 'fixed',
    inset: 0,
    backgroundColor: colors.overlay,
    transitionProperty: 'opacity',
    transitionDuration: '160ms',
    opacity: { default: 1, [fading]: 0 },
  },
  // popups sit in the browser's top layer, so no z-index; inset + auto margins centre it
  popup: {
    position: 'fixed',
    inset: 0,
    margin: 'auto',
    height: 'fit-content',
    width: 'min(560px, calc(100vw - 32px))',
    maxHeight: 'calc(100dvh - 48px)',
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
    transitionProperty: 'opacity, transform',
    transitionDuration: '160ms',
    transitionTimingFunction: motion.settle,
    opacity: { default: 1, [fading]: 0 },
    transform: { default: 'none', [fading]: 'scale(.97)' },
  },
  wide: { width: 'min(1000px, calc(100vw - 32px))' },
  title: { margin: 0, fontFamily: font.display, fontSize: text.xl, fontWeight: 600, letterSpacing: '-.01em' },
  text: { margin: 0, color: colors.muted, fontSize: text.base },
  actions: { display: 'flex', justifyContent: 'flex-end', gap: space.sm, flexWrap: 'wrap', alignItems: 'center' },
  // the drawer slides the sheet and fades the backdrop itself: no translate or opacity here
  sheetBackdrop: { position: 'fixed', inset: 0, backgroundColor: colors.overlay },
  sheet: {
    display: 'flex',
    flexDirection: 'column',
    width: '100%',
    maxHeight: '82dvh',
    paddingBlockStart: space.sm,
    borderStartStartRadius: radius.xxl,
    borderStartEndRadius: radius.xxl,
    borderWidth: 1,
    borderBottomWidth: 0,
    borderStyle: 'solid',
    borderColor: colors.line2,
    backgroundColor: colors.panel,
    color: colors.fg,
    boxShadow: colors.popShadow,
    outline: 'none',
  },
  grabber: {
    flexShrink: 0,
    width: 36,
    height: 4,
    borderRadius: radius.xs,
    backgroundColor: colors.line2,
    marginInline: 'auto',
    marginBlockEnd: space.md,
  },
  sheetBody: {
    minHeight: 0,
    flexGrow: 1,
    overflowY: 'auto',
    paddingBlockEnd: `max(${space.xxl}, env(safe-area-inset-bottom))`,
    paddingInline: space.lg,
  },
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
    <Root
      open={open}
      onOpenChange={(o) => {
        if (!o) onClose();
      }}
    >
      <DialogBackdrop {...stylex.props(styles.backdrop)} />
      <DialogContent {...stylex.props(styles.popup, wide && styles.wide)}>
        <DialogTitle {...stylex.props(styles.title)}>{title}</DialogTitle>
        {text && <DialogDescription {...stylex.props(styles.text)}>{text}</DialogDescription>}
        {children}
      </DialogContent>
    </Root>
  );
}

export function ConfirmDialog({ text, onAnswer }: { text: string | null; onAnswer: (ok: boolean) => void }) {
  return (
    <AlertDialog
      open={text !== null}
      onOpenChange={(o, details) => {
        if (!o) onAnswer(details.returnValue === 'confirm');
      }}
    >
      <AlertDialogBackdrop {...stylex.props(styles.backdrop)} />
      <AlertDialogContent {...stylex.props(styles.popup)}>
        <AlertDialogTitle {...stylex.props(styles.title)}>Are you sure?</AlertDialogTitle>
        <AlertDialogDescription {...stylex.props(styles.text)}>{text}</AlertDialogDescription>
        <DialogActions>
          <AlertDialogClose {...look({ label: 'Cancel' })}>Cancel</AlertDialogClose>
          <AlertDialogClose {...look({ label: 'Continue', variant: 'primary' })} value="confirm" data-agent-confirm={text ?? ''}>
            Continue
          </AlertDialogClose>
        </DialogActions>
      </AlertDialogContent>
    </AlertDialog>
  );
}

/** A bare modal layer (focus trap, Esc, outside click) for popups styled by their caller. */
export function Overlay({
  open,
  onOpenChange,
  label,
  backdrop,
  popup,
  children,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  label: string;
  backdrop: stylex.StyleXStyles;
  popup: stylex.StyleXStyles;
  children: ReactNode;
}) {
  return (
    <Root open={open} onOpenChange={onOpenChange}>
      <DialogBackdrop {...stylex.props(backdrop)} />
      <DialogContent {...stylex.props(popup)} aria-label={label}>
        {children}
      </DialogContent>
    </Root>
  );
}

/** A modal sheet from the bottom edge (focus trap, Esc, outside press, swipe down): the phone menu. */
export function Sheet({
  open,
  onOpenChange,
  label,
  children,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  label: string;
  children: ReactNode;
}) {
  return (
    <Drawer open={open} onOpenChange={onOpenChange} side="bottom">
      <DrawerBackdrop {...stylex.props(styles.sheetBackdrop)} />
      <DrawerContent {...stylex.props(styles.sheet)} aria-label={label}>
        <div {...stylex.props(styles.grabber)} aria-hidden />
        <div {...stylex.props(styles.sheetBody)}>{children}</div>
      </DrawerContent>
    </Drawer>
  );
}

export const DialogActions = ({ children }: { children: ReactNode }) => <div {...stylex.props(styles.actions)}>{children}</div>;

import { useState } from 'react';
import type { Action } from '../api/types';
import { Button, LinkButton, type ButtonLook, type Variant } from './Button';
import { useAct, useFeedback } from './feedback';

/** A button that POSTs an action (asking first when `confirm` is set) and shows the result. */
export function ActButton({
  url,
  body,
  confirm,
  ...look
}: ButtonLook & { url: string; body?: Record<string, unknown>; confirm?: string | null }) {
  const act = useAct();
  const [busy, setBusy] = useState(false);
  const run = async () => {
    setBusy(true);
    await act(url, body, { confirm });
    setBusy(false);
  };
  return <Button {...look} busy={busy} onClick={run} />;
}

/** Buttons the server described (Needs you items). */
export function Actions({ actions }: { actions: Action[] }) {
  return (
    <>
      {actions.map((a, i) => {
        const variant: Variant = a.primary ? 'primary' : a.type === 'link' && a.icon === 'arrow' ? 'quiet' : 'default';
        return a.type === 'link' ? (
          <LinkButton key={i} label={a.label} icon={a.icon} variant={variant} small to={a.href || '/'} />
        ) : (
          <ActButton
            key={i}
            label={a.label}
            icon={a.icon}
            variant={variant}
            small
            url={a.url || ''}
            body={a.body}
            confirm={a.confirm}
          />
        );
      })}
    </>
  );
}

export function CopyButton({ text, label = 'Copy', small = true }: { text: string; label?: string; small?: boolean }) {
  const { toast } = useFeedback();
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      toast('Copied');
    } catch {
      toast('Copy failed: select the text instead', true);
    }
  };
  return <Button label={label} icon="copy" small={small} onClick={copy} />;
}

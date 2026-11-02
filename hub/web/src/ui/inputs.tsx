import * as stylex from '@stylexjs/stylex';
import { useEffect, useRef, useState, type FormEvent, type ReactNode } from 'react';
import { colors, font, radius, space, text } from '../theme/tokens.stylex';
import { Button } from './Button';
import { Icon } from './Icon';

const styles = stylex.create({
  input: {
    width: '100%',
    minWidth: 0,
    paddingBlock: space.md,
    paddingInline: space.lg,
    borderRadius: radius.md,
    fontSize: text.body,
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: { default: colors.line2, ':focus': colors.accent },
    backgroundColor: colors.sunk,
    color: colors.fg,
    outline: { default: 'none', ':focus': `2px solid color-mix(in srgb, ${colors.accent} 45%, transparent)` },
    outlineOffset: 1,
    '::placeholder': { color: colors.faint },
  },
  grow: { flexGrow: '1', flexShrink: '1', flexBasis: '160px' },
  short: { flexGrow: '0', flexShrink: '1', flexBasis: '180px' },
  datetime: { flexGrow: '0', flexShrink: '1', flexBasis: '250px' }, // room for the date, time and AM / PM
  number: { width: 84, flex: 'none' },
  mono: { fontFamily: font.mono, fontSize: text.sm },
  area: { fontFamily: font.mono, fontSize: text.sm, minHeight: 150, resize: 'vertical' },
  prose: { fontFamily: 'inherit', fontSize: text.body, minHeight: 110, lineHeight: 1.5 },
  editor: { minHeight: '58vh', tabSize: 2 },
  form: { display: 'flex', gap: space.sm, alignItems: 'center', flexWrap: 'wrap', minWidth: 0 },
  field: { display: 'grid', gap: space.xs, fontSize: text.md, fontWeight: 600 },
  search: {
    position: 'relative',
    display: 'flex',
    alignItems: 'center',
    flexGrow: '1',
    flexShrink: '1',
    flexBasis: '240px',
    minWidth: 0,
  },
  searchIcon: { position: 'absolute', insetInlineStart: space.lg, color: colors.faint, display: 'flex', pointerEvents: 'none' },
  searchInput: { paddingInlineStart: `calc(${space.lg} + 24px)` },
});

interface InputProps {
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  type?: 'text' | 'password' | 'number' | 'datetime-local';
  width?: 'grow' | 'short' | 'number' | 'datetime';
  mono?: boolean;
  readOnly?: boolean;
  min?: number;
  max?: number;
  title?: string;
  onEnter?: () => unknown; // Enter saves, without a form (date pickers don't submit one)
}

const typing = (el: Element | null) => !!el && (el.matches('input, textarea, select') || (el as HTMLElement).isContentEditable);

/** A search field: "/" focuses it from anywhere on the page, Escape clears it. */
export function SearchInput({ value, onChange, label }: { value: string; onChange: (v: string) => void; label: string }) {
  const ref = useRef<HTMLInputElement>(null);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === '/' && !typing(document.activeElement)) {
        e.preventDefault();
        ref.current?.focus();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => {
      window.removeEventListener('keydown', onKey);
    };
  }, []);
  return (
    <label {...stylex.props(styles.search)}>
      <span {...stylex.props(styles.searchIcon)}>
        <Icon name="search" size={16} />
      </span>
      <input
        ref={ref}
        {...stylex.props(styles.input, styles.searchInput)}
        type="search"
        value={value}
        placeholder={`${label}  ( / )`}
        aria-label={label}
        onChange={(e) => {
          onChange(e.target.value);
        }}
        onKeyDown={(e) => {
          if (e.key === 'Escape') onChange('');
        }}
        autoComplete="off"
        spellCheck={false}
      />
    </label>
  );
}

export function TextInput({ value, onChange, type = 'text', width = 'grow', mono, onEnter, ...rest }: InputProps) {
  return (
    <input
      {...stylex.props(styles.input, styles[width], mono && styles.mono)}
      type={type}
      value={value}
      onChange={(e) => {
        onChange(e.target.value);
      }}
      onKeyDown={(e) => {
        if (onEnter && e.key === 'Enter') {
          e.preventDefault();
          void onEnter();
        }
      }}
      autoComplete={type === 'password' ? 'new-password' : 'off'}
      spellCheck={false}
      {...rest}
    />
  );
}

export function TextArea({
  value,
  onChange,
  placeholder,
  readOnly,
  editor,
  prose,
  onKeyDown,
  areaRef,
}: {
  value: string;
  onChange?: (v: string) => void;
  placeholder?: string;
  readOnly?: boolean;
  editor?: boolean;
  prose?: boolean; // plain writing, not code
  onKeyDown?: React.KeyboardEventHandler<HTMLTextAreaElement>;
  areaRef?: React.Ref<HTMLTextAreaElement>;
}) {
  return (
    <textarea
      ref={areaRef}
      {...stylex.props(styles.input, styles.area, editor && styles.editor, prose && styles.prose)}
      value={value}
      readOnly={readOnly}
      onChange={(e) => onChange?.(e.target.value)}
      onKeyDown={onKeyDown}
      placeholder={placeholder}
      spellCheck={!!prose}
      autoComplete="off"
    />
  );
}

/** A labelled field inside a dialog or form. */
export const Field = ({ label, children }: { label: string; children: ReactNode }) => (
  <label {...stylex.props(styles.field)}>
    {label}
    {children}
  </label>
);

/** Inputs and a submit button on one line; Enter submits. */
export function InlineForm({ onSubmit, children }: { onSubmit: () => unknown; children: ReactNode }) {
  const submit = (e: FormEvent) => {
    e.preventDefault();
    void onSubmit();
  };
  return (
    <form {...stylex.props(styles.form)} onSubmit={submit}>
      {children}
    </form>
  );
}

/** One text field with its button: sends the value, then clears it unless `keep`. */
export function SubmitField({
  placeholder,
  button,
  onSubmit,
  initial = '',
  keep,
  type,
  primary = true,
}: {
  placeholder?: string;
  button: string;
  onSubmit: (v: string) => unknown;
  initial?: string;
  keep?: boolean;
  type?: 'text' | 'password' | 'number';
  primary?: boolean;
}) {
  const [v, setV] = useState(initial);
  const submit = async () => {
    await onSubmit(v);
    if (!keep) setV('');
  };
  return (
    <InlineForm onSubmit={submit}>
      <TextInput value={v} onChange={setV} placeholder={placeholder} type={type} width={type === 'number' ? 'number' : 'grow'} />
      <Button type="submit" label={button} variant={primary ? 'primary' : 'default'} />
    </InlineForm>
  );
}

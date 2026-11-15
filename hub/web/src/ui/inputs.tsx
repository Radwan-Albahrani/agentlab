import * as stylex from '@stylexjs/stylex';
import { Field as FieldRoot, FieldLabel } from '@ui-sdk/react/field';
import { Input, InputGroup } from '@ui-sdk/react/input';
import { useShortcut } from '@ui-sdk/react/shortcuts';
import { Textarea } from '@ui-sdk/react/textarea';
import { useRef, useState, type ReactNode, type SubmitEvent } from 'react';
import { colors, font, radius, space, text } from '../theme/tokens.stylex';
import { Button } from './Button';
import { Icon } from './Icon';

const styles = stylex.create({
  input: {
    width: '100%',
    minWidth: 0,
    paddingBlock: space.md,
    paddingInline: space.lg,
    borderRadius: radius.lg,
    fontSize: text.body,
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: { default: colors.line2, ':hover': colors.faint, ':focus': colors.accent },
    backgroundColor: { default: colors.sunk, ':focus': colors.panel },
    color: colors.fg,
    outline: 'none',
    // a soft iris halo on focus instead of a hard outline
    boxShadow: { default: 'none', ':focus': `0 0 0 4px color-mix(in srgb, ${colors.accent} 22%, transparent)` },
    transitionProperty: 'border-color, box-shadow, background-color',
    transitionDuration: '160ms',
    '::placeholder': { color: colors.faint },
  },
  grow: { flexGrow: '1', flexShrink: '1', flexBasis: '160px' },
  short: { flexGrow: '0', flexShrink: '1', flexBasis: '180px' },
  datetime: { flexGrow: '0', flexShrink: '1', flexBasis: '250px' },
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
  label?: string; // its name when no Field labels it; else the placeholder names it
  onChange: (v: string) => void;
  placeholder?: string;
  type?: 'text' | 'password' | 'number' | 'datetime-local';
  width?: 'grow' | 'short' | 'number' | 'datetime';
  mono?: boolean;
  readOnly?: boolean;
  min?: number;
  max?: number;
  title?: string;
  onEnter?: () => unknown; // date pickers don't submit a form
  list?: string; // a <datalist> of suggestions
}

/** "/" focuses it from anywhere; Escape clears it. */
export function SearchInput({ value, onChange, label }: { value: string; onChange: (v: string) => void; label: string }) {
  const ref = useRef<HTMLInputElement>(null);
  useShortcut(
    '/',
    () => {
      ref.current?.focus();
    },
    { description: label },
  );
  return (
    <InputGroup {...stylex.props(styles.search)}>
      <span {...stylex.props(styles.searchIcon)}>
        <Icon name="search" size={16} />
      </span>
      <Input
        ref={ref}
        {...stylex.props(styles.input, styles.searchInput)}
        type="search"
        value={value}
        onValueChange={onChange}
        placeholder={`${label}  ( / )`}
        aria-label={label}
        aria-keyshortcuts="/"
        onKeyDown={(e) => {
          if (e.key === 'Escape') onChange('');
        }}
        autoComplete="off"
        spellCheck={false}
      />
    </InputGroup>
  );
}

export function TextInput({ value, onChange, type = 'text', width = 'grow', mono, onEnter, label, ...rest }: InputProps) {
  return (
    <Input
      {...stylex.props(styles.input, styles[width], mono && styles.mono)}
      type={type}
      value={value}
      onValueChange={onChange}
      onKeyDown={(e) => {
        if (onEnter && e.key === 'Enter') {
          e.preventDefault();
          void onEnter();
        }
      }}
      autoComplete={type === 'password' ? 'new-password' : 'off'}
      spellCheck={false}
      aria-label={label ?? rest.placeholder}
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
  label,
  look,
  spellCheck,
}: {
  value: string;
  label?: string; // its name when no Field labels it
  look?: stylex.StyleXStyles; // replaces the default box
  spellCheck?: boolean;
  onChange?: (v: string) => void;
  placeholder?: string;
  readOnly?: boolean;
  editor?: boolean;
  prose?: boolean;
  onKeyDown?: React.KeyboardEventHandler<HTMLTextAreaElement>;
  areaRef?: React.Ref<HTMLTextAreaElement>;
}) {
  return (
    <Textarea
      ref={areaRef}
      {...stylex.props(...(look ? [look] : [styles.input, styles.area, editor && styles.editor, prose && styles.prose]))}
      value={value}
      readOnly={readOnly}
      onValueChange={(v) => onChange?.(v)}
      onKeyDown={onKeyDown}
      placeholder={placeholder}
      spellCheck={spellCheck ?? !!prose}
      autoComplete="off"
      aria-label={label}
    />
  );
}

/** Labels the text field inside it. */
export const Field = ({ label, children }: { label: string; children: ReactNode }) => (
  <FieldRoot {...stylex.props(styles.field)}>
    <FieldLabel>{label}</FieldLabel>
    {children}
  </FieldRoot>
);

export function InlineForm({ onSubmit, children }: { onSubmit: () => unknown; children: ReactNode }) {
  const submit = (e: SubmitEvent<HTMLFormElement>) => {
    e.preventDefault();
    void onSubmit();
  };
  return (
    <form {...stylex.props(styles.form)} onSubmit={submit}>
      {children}
    </form>
  );
}

/** Clears the value after sending unless `keep`. */
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
  const [busy, setBusy] = useState(false);
  const submit = async () => {
    if (busy) return;
    setBusy(true);
    try {
      await onSubmit(v);
      if (!keep) setV('');
    } finally {
      setBusy(false);
    }
  };
  return (
    <InlineForm onSubmit={submit}>
      <TextInput value={v} onChange={setV} placeholder={placeholder} type={type} width={type === 'number' ? 'number' : 'grow'} />
      <Button type="submit" label={button} variant={primary ? 'primary' : 'default'} busy={busy} />
    </InlineForm>
  );
}

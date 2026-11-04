import * as stylex from '@stylexjs/stylex';
import { Link } from 'react-router';
import { colors, radius, space, text } from '../theme/tokens.stylex';
import { Icon } from './Icon';

export type Variant = 'default' | 'primary' | 'quiet' | 'danger';

const styles = stylex.create({
  btn: {
    appearance: 'none',
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: colors.line2,
    backgroundColor: { default: colors.panel, ':hover': colors.hover },
    color: colors.fg,
    borderRadius: radius.md,
    paddingBlock: space.sm,
    paddingInline: space.lg,
    fontSize: text.base,
    fontWeight: 600,
    display: 'inline-flex',
    alignItems: 'center',
    gap: space.sm,
    cursor: 'pointer',
    whiteSpace: 'nowrap',
    lineHeight: 1.3,
    transition: 'background-color .12s, border-color .12s',
    outline: { default: 'none', ':focus-visible': `2px solid color-mix(in srgb, ${colors.accent} 55%, transparent)` },
    outlineOffset: 2,
  },
  primary: {
    backgroundColor: { default: colors.accent, ':hover': colors.accent },
    borderColor: colors.accent,
    color: colors.accentFg,
    filter: { default: null, ':hover': 'brightness(1.08)' },
  },
  quiet: {
    borderColor: 'transparent',
    backgroundColor: { default: 'transparent', ':hover': colors.hover },
    color: { default: colors.muted, ':hover': colors.fg },
  },
  danger: {
    color: colors.bad,
    backgroundColor: { default: 'transparent', ':hover': colors.badSoft },
    borderColor: 'transparent',
  },
  default: {},
  sm: { paddingBlock: space.xs, paddingInline: space.md, fontSize: text.sm, borderRadius: radius.sm },
  iconOnly: { paddingBlock: space.xs, paddingInline: space.xs },
  busy: { opacity: 0.55, pointerEvents: 'none' },
  disabled: { opacity: 0.45, cursor: 'not-allowed' },
});

export interface ButtonLook {
  label: string;
  icon?: string | null;
  variant?: Variant;
  small?: boolean;
  iconOnly?: boolean; // the label becomes the tooltip
}

export const look = ({ variant = 'default', small, iconOnly }: ButtonLook, busy = false, disabled = false) =>
  stylex.props(
    styles.btn,
    styles[variant],
    small && styles.sm,
    iconOnly && styles.iconOnly,
    busy && styles.busy,
    disabled && styles.disabled,
  );

const inner = ({ icon, label, iconOnly, small }: ButtonLook) => (
  <>
    {icon && <Icon name={icon} size={small ? 16 : 17} />}
    {!iconOnly && <span>{label}</span>}
  </>
);

const external = (href: string) => /^(https?:|t3code:|slack:)/.test(href);

/** In-app routes stay in the app; anything else opens a new tab. */
export function LinkButton({ to, ...l }: ButtonLook & { to: string }) {
  const title = l.iconOnly ? l.label : undefined;
  if (external(to))
    return (
      <a {...look(l)} href={to} target="_blank" rel="noopener" title={title}>
        {inner(l)}
      </a>
    );
  return (
    <Link {...look(l)} to={to} title={title}>
      {inner(l)}
    </Link>
  );
}

export function Button({
  onClick,
  busy,
  disabled,
  hint,
  type = 'button',
  ...l
}: ButtonLook & {
  onClick?: () => unknown;
  busy?: boolean;
  disabled?: boolean;
  hint?: string; // tooltip
  type?: 'button' | 'submit';
}) {
  const name = l.iconOnly ? l.label : undefined;
  return (
    <button {...look(l, busy, disabled)} type={type} onClick={onClick} disabled={disabled} title={hint ?? name} aria-label={name}>
      {inner(l)}
    </button>
  );
}

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
    borderColor: { default: colors.line2, ':hover': colors.faint },
    backgroundColor: { default: colors.raised, ':hover': colors.hover },
    color: colors.fg,
    borderRadius: radius.md,
    paddingBlock: space.xs,
    paddingInline: space.lg,
    minHeight: 32,
    fontSize: text.md,
    fontWeight: 500,
    display: 'inline-flex',
    alignItems: 'center',
    gap: space.sm,
    cursor: 'pointer',
    whiteSpace: 'nowrap',
    lineHeight: 1.3,
    transitionProperty: 'background-color, border-color, opacity',
    transitionDuration: '120ms',
    opacity: { default: 1, ':active': 0.85 },
    outline: { default: 'none', ':focus-visible': `2px solid ${colors.accent}` },
    outlineOffset: 2,
  },
  primary: {
    backgroundColor: { default: colors.accent, ':hover': `color-mix(in srgb, ${colors.accent} 88%, ${colors.fg})` },
    borderColor: { default: colors.accent, ':hover': colors.accent },
    color: colors.accentFg,
    fontWeight: 600,
  },
  quiet: {
    borderColor: { default: 'transparent', ':hover': 'transparent' },
    backgroundColor: { default: 'transparent', ':hover': colors.hover },
    color: { default: colors.muted, ':hover': colors.fg },
  },
  danger: {
    color: colors.bad,
    backgroundColor: { default: 'transparent', ':hover': colors.badSoft },
    borderColor: { default: 'transparent', ':hover': `color-mix(in srgb, ${colors.bad} 40%, transparent)` },
  },
  default: {},
  sm: { paddingBlock: space.xxs, paddingInline: space.md, minHeight: 28, fontSize: text.sm, borderRadius: radius.sm },
  iconOnly: { paddingBlock: space.xxs, paddingInline: space.xs, justifyContent: 'center', minWidth: 28 },
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
      <a {...look(l)} href={to} target="_blank" rel="noopener" title={title} aria-label={title}>
        {inner(l)}
      </a>
    );
  return (
    <Link {...look(l)} to={to} title={title} aria-label={title}>
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

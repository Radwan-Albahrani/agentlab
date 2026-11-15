import * as stylex from '@stylexjs/stylex';
import { Button as ButtonRoot } from '@ui-sdk/react/button';
import { Tooltip, TooltipContent, TooltipTrigger } from '@ui-sdk/react/tooltip';
import type { ComponentProps, ReactNode } from 'react';
import { Link } from 'react-router';
import { colors, radius, space, text } from '../theme/tokens.stylex';
import { Icon } from './Icon';

export type Variant = 'default' | 'primary' | 'quiet' | 'danger';

const fading = ':is([data-starting-style], [data-ending-style])';
// a busy button is disabled too; it shows as busy, not unavailable
const pending = ':is([data-pending], [aria-busy="true"])';
const off = ':is([data-disabled]:not([aria-busy="true"]))';

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
    cursor: { default: 'pointer', [pending]: 'default', [off]: 'not-allowed' },
    whiteSpace: 'nowrap',
    lineHeight: 1.3,
    transitionProperty: 'background-color, border-color, opacity',
    transitionDuration: '120ms',
    opacity: { default: 1, ':active': 0.85, [pending]: 0.55, [off]: 0.45 },
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
  tip: {
    margin: 0,
    maxWidth: 'min(320px, calc(100vw - 32px))',
    paddingBlock: space.xxs,
    paddingInline: space.sm,
    borderRadius: radius.sm,
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: colors.line2,
    backgroundColor: colors.raised,
    color: colors.fg,
    boxShadow: colors.popShadow,
    fontSize: text.sm,
    fontWeight: 500,
    lineHeight: 1.35,
    pointerEvents: 'none',
    transformOrigin: 'var(--transform-origin)',
    transitionProperty: 'opacity, transform',
    transitionDuration: { default: '120ms', ':is([data-instant])': '0s' },
    opacity: { default: 1, [fading]: 0 },
    transform: { default: 'none', [fading]: 'scale(.97)' },
  },
});

export interface ButtonLook {
  label: string;
  icon?: string | null;
  variant?: Variant;
  small?: boolean;
  iconOnly?: boolean; // the label becomes the tooltip
}

export const look = ({ variant = 'default', small, iconOnly }: ButtonLook) =>
  stylex.props(styles.btn, styles[variant], small && styles.sm, iconOnly && styles.iconOnly);

const inner = ({ icon, label, iconOnly, small }: ButtonLook) => (
  <>
    {icon && <Icon name={icon} size={small ? 16 : 17} />}
    {!iconOnly && <span>{label}</span>}
  </>
);

type RootProps = ComponentProps<typeof ButtonRoot>;

/** A tooltip on `render`: it names the control (`names`), or describes one that has a name. */
export function Hint({
  tip,
  names,
  render,
  children,
}: {
  tip: string;
  names: boolean;
  render: ComponentProps<typeof TooltipTrigger>['render'];
  children: ReactNode;
}) {
  return (
    <Tooltip type={names ? 'label' : 'description'}>
      <TooltipTrigger render={render}>{children}</TooltipTrigger>
      <TooltipContent sideOffset={6} {...stylex.props(styles.tip)}>
        {tip}
      </TooltipContent>
    </Tooltip>
  );
}

function WithTip({ tip, names, props, children }: { tip?: string; names: boolean; props: RootProps; children: ReactNode }) {
  if (!tip) return <ButtonRoot {...props}>{children}</ButtonRoot>;
  return (
    <Hint tip={tip} names={names} render={<ButtonRoot {...props} />}>
      {children}
    </Hint>
  );
}

const external = (href: string) => /^(https?:|t3code:|slack:)/.test(href);

/** In-app routes stay in the app; anything else opens a new tab. */
export function LinkButton({ to, ...l }: ButtonLook & { to: string }) {
  const link: RootProps['render'] = external(to)
    ? ({ children, ...props }) => (
        <a {...props} href={to} target="_blank" rel="noopener">
          {children}
        </a>
      )
    : (props) => <Link {...props} to={to} />;
  return (
    <WithTip
      tip={l.iconOnly ? l.label : undefined}
      names
      props={{ ...look(l), render: link, 'aria-label': l.iconOnly ? l.label : undefined }}
    >
      {inner(l)}
    </WithTip>
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
  const tip = hint ?? (l.iconOnly ? l.label : undefined);
  return (
    <WithTip
      tip={tip}
      names={!hint}
      props={{
        ...look(l),
        type,
        // a returned promise keeps the button pending, so it can't run twice
        onClick,
        disabled: !!disabled || !!busy,
        // stays focusable while busy, and while disabled so its hint can say why
        focusableWhenDisabled: !!busy || !!hint,
        'aria-busy': busy ? true : undefined,
        'aria-label': l.iconOnly ? l.label : undefined,
      }}
    >
      {inner(l)}
    </WithTip>
  );
}

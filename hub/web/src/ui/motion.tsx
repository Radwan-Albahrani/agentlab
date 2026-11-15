import * as stylex from '@stylexjs/stylex';
import { useEffect, useRef, useState, type ReactNode } from 'react';
import { motion } from '../theme/tokens.stylex';

const rise = stylex.keyframes({ from: { opacity: 0, transform: 'translateY(4px)' } });

const styles = stylex.create({
  appear: (delay: string) => ({
    animationName: rise,
    animationDuration: '220ms',
    animationTimingFunction: motion.settle,
    // backwards, not both: a held last frame would override the element's own hover styles
    animationFillMode: 'backwards',
    animationDelay: delay,
  }),
  contents: { minWidth: 0 },
});

/** Fades and lifts its children in on first render; `i` staggers siblings. */
export const Appear = ({ i = 0, children }: { i?: number; children: ReactNode }) => (
  <div {...stylex.props(styles.contents, styles.appear(`${Math.min(i, 12) * 30}ms`))}>{children}</div>
);

const still = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches;

/** `value`, eased towards each new value over `ms`; counts up on first show from 10 on (a 0 → 1 reads as a glitch). */
export function useTween(value: number, ms = 700): number {
  const [shown, setShown] = useState(still() || Math.abs(value) < 10 ? value : 0);
  const from = useRef(shown);
  useEffect(() => {
    if (still()) return;
    const start = performance.now();
    const a = from.current;
    let frame = 0;
    const step = (t: number) => {
      const k = Math.min(1, (t - start) / ms);
      const v = a + (value - a) * (1 - (1 - k) ** 3);
      from.current = v;
      setShown(v);
      if (k < 1) frame = requestAnimationFrame(step);
    };
    frame = requestAnimationFrame(step);
    return () => {
      cancelAnimationFrame(frame);
    };
  }, [value, ms]);
  return still() ? value : shown;
}

/** A number that counts to its value and glides between updates. */
export function Num({ value, digits = 0 }: { value: number; digits?: number }) {
  const v = useTween(value);
  return <>{v.toFixed(digits)}</>;
}

import * as stylex from '@stylexjs/stylex';
import QRCode from 'qrcode';
import { useEffect, useState } from 'react';
import { colors, radius, space } from '../theme/tokens.stylex';

const styles = stylex.create({
  frame: { backgroundColor: colors.paper, padding: space.xs, borderRadius: radius.sm, lineHeight: 0, flexShrink: 0 },
  img: (size: number) => ({ width: size, height: size }),
});

/** A scannable QR code of `text`, on white in both themes. */
export function Qr({ text, size = 96, label = '' }: { text: string; size?: number; label?: string }) {
  const [src, setSrc] = useState('');
  useEffect(() => {
    void QRCode.toDataURL(text, { width: size * 2.5, margin: 1 }).then(setSrc);
  }, [text, size]);
  return <div {...stylex.props(styles.frame)}>{src && <img {...stylex.props(styles.img(size))} src={src} alt={label} />}</div>;
}

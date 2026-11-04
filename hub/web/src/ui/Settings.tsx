import * as stylex from '@stylexjs/stylex';
import type { ReactNode } from 'react';
import { colors, media, space, text } from '../theme/tokens.stylex';

const styles = stylex.create({
  list: { display: 'grid' },
  setting: {
    display: 'grid',
    gridTemplateColumns: { default: 'minmax(0, 1fr) minmax(0, 1.6fr)', [media.narrow]: '1fr' },
    gap: { default: space.xxl, [media.narrow]: space.md },
    padding: space.xxl,
    alignItems: 'start',
    borderTopWidth: { default: 1, ':first-child': 0 },
    borderTopStyle: 'solid',
    borderTopColor: colors.line,
  },
  label: { fontWeight: 700 },
  help: { marginBlockStart: space.xxs, marginBlockEnd: '0', marginInline: 0, color: colors.muted, fontSize: text.md },
});

export const Settings = ({ children }: { children: ReactNode }) => <div {...stylex.props(styles.list)}>{children}</div>;

export function Setting({ label, help, children }: { label: string; help?: string; children: ReactNode }) {
  return (
    <div {...stylex.props(styles.setting)}>
      <div>
        <div {...stylex.props(styles.label)}>{label}</div>
        {help && <p {...stylex.props(styles.help)}>{help}</p>}
      </div>
      {children}
    </div>
  );
}

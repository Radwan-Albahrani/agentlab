import * as stylex from '@stylexjs/stylex';
import { gb, pct } from '../lib/format';
import { chart, colors, radius, space, text } from '../theme/tokens.stylex';

const PALETTE = [chart.c1, chart.c2, chart.c3, chart.c4, chart.c5, chart.c6, chart.c7, chart.c8];
const colorOf = (i: number) => PALETTE[i % PALETTE.length] ?? chart.c8;

const styles = stylex.create({
  bar: {
    display: 'flex',
    height: 12,
    borderRadius: radius.pill,
    overflow: 'hidden',
    backgroundColor: colors.sunk,
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: colors.line,
  },
  part: (width: string, color: string) => ({ display: 'block', height: '100%', width, backgroundColor: color }),
  legend: { display: 'flex', gap: space.xl, flexWrap: 'wrap', fontSize: text.sm, color: colors.muted },
  swatch: (color: string) => ({
    display: 'inline-block',
    width: 9,
    height: 9,
    borderRadius: 3,
    marginInlineEnd: space.xs,
    verticalAlign: -1,
    backgroundColor: color,
  }),
});

interface BarPart {
  label: string;
  bytes: number;
}

/** How a total splits into parts: one coloured bar plus a legend with sizes. */
export function StackedBar({ parts, total }: { parts: BarPart[]; total: number }) {
  return (
    <>
      <div {...stylex.props(styles.bar)}>
        {parts.map((p, i) => (
          <span
            key={p.label}
            title={`${p.label} · ${gb(p.bytes)}`}
            {...stylex.props(styles.part(`${pct(p.bytes, total).toFixed(2)}%`, colorOf(i)))}
          />
        ))}
      </div>
      <div {...stylex.props(styles.legend)}>
        {parts.map((p, i) => (
          <span key={p.label}>
            <i {...stylex.props(styles.swatch(colorOf(i)))} />
            {p.label} {gb(p.bytes)}
          </span>
        ))}
      </div>
    </>
  );
}

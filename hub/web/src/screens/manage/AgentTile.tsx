import * as stylex from '@stylexjs/stylex';
import type { ManagedAgent } from '../../api/types';
import { colors, radius, space, text } from '../../theme/tokens.stylex';
import { Button } from '../../ui/Button';
import { Card, CardBody } from '../../ui/Card';
import { Icon } from '../../ui/Icon';
import { Inline, Split, Stack } from '../../ui/layout';
import { MoreMenu } from '../../ui/Menu';
import { Badge, Pill } from '../../ui/status';
import { Text } from '../../ui/text';

const styles = stylex.create({
  stats: {
    display: 'grid',
    gridTemplateColumns: 'repeat(3, minmax(0, 1fr))',
    gap: space.sm,
  },
  stat: {
    backgroundColor: colors.sunk,
    borderRadius: radius.lg,
    paddingBlock: space.lg,
    paddingInline: space.xl,
    display: 'grid',
    gap: space.xxs,
    minWidth: 0,
  },
  label: { fontSize: text.xs, color: colors.faint, textTransform: 'uppercase', letterSpacing: '0.06em', fontWeight: 600 },
  value: { fontSize: text.xl, fontWeight: 650, fontVariantNumeric: 'tabular-nums', whiteSpace: 'nowrap' },
  unit: { fontSize: text.md, color: colors.muted, fontWeight: 500, marginInlineStart: space.xxxs },
  custom: { fontSize: text.xs, color: colors.accent, fontWeight: 600 },
  owner: { minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' },
  add: {
    width: '100%',
    height: '100%',
    minHeight: 180,
    display: 'grid',
    placeItems: 'center',
    alignContent: 'center',
    gap: space.sm,
    borderRadius: radius.xxl,
    borderWidth: 1.5,
    borderStyle: 'dashed',
    borderColor: { default: colors.line2, ':hover': colors.accent },
    backgroundColor: { default: 'transparent', ':hover': colors.accentSoft },
    color: { default: colors.muted, ':hover': colors.accent },
    cursor: 'pointer',
    fontSize: text.body,
    fontWeight: 600,
    fontFamily: 'inherit',
  },
  addDisabled: { cursor: 'not-allowed', opacity: 0.5 },
});

/** "12g" -> ["12", "GB"] */
function size(v: string): [string, string] {
  const m = /^([\d.]+)\s*([kmgt]?)/i.exec(v);
  if (!m) return [v, ''];
  return [m[1] ?? v, m[2] ? `${m[2].toUpperCase()}B` : 'B'];
}

function Stat({ label, value, unit, custom }: { label: string; value: string; unit?: string; custom?: boolean }) {
  return (
    <div {...stylex.props(styles.stat)}>
      <span {...stylex.props(styles.label)}>{label}</span>
      <span {...stylex.props(styles.value)}>
        {value}
        {unit && <span {...stylex.props(styles.unit)}>{unit}</span>}
      </span>
      <span {...stylex.props(styles.custom)}>{custom ? 'custom' : ' '}</span>
    </div>
  );
}

const STATE = {
  up: (
    <Pill tone="ok" dot>
      Running
    </Pill>
  ),
  starting: <Pill tone="warn">Starting</Pill>,
  down: <Pill tone="bad">Stopped</Pill>,
};

export function AgentTile({
  a,
  disabled,
  onResize,
  onRemove,
}: {
  a: ManagedAgent;
  disabled: boolean;
  onResize: () => void;
  onRemove: () => void;
}) {
  const [mem, memUnit] = size(a.memory);
  const files = a.used ? (a.used / 2 ** 30).toFixed(1) : '—';
  return (
    <Card>
      <CardBody roomy>
        <Stack gap="lg">
          <Split>
            <Inline gap="lg" nowrap>
              <Badge name={a.id} />
              <div {...stylex.props(styles.owner)}>
                <Text size="lg" weight="bold">
                  {a.id}
                </Text>
                <Text block tone="faint" size="md">
                  {a.owner}
                </Text>
              </div>
            </Inline>
            {STATE[a.state]}
          </Split>
          <div {...stylex.props(styles.stats)}>
            <Stat label="Memory" value={mem} unit={memUnit} custom={a.customMemory} />
            <Stat label="CPUs" value={String(a.cpus)} custom={a.customCpus} />
            <Stat label="Files" value={files} unit={a.used ? 'GB' : undefined} />
          </div>
          <Split>
            <Button label="Resize" icon="sliders" small disabled={disabled} onClick={onResize} />
            <MoreMenu
              label={`More for ${a.id}`}
              entries={[{ label: 'Remove agent…', icon: 'trash', danger: true, disabled, onSelect: onRemove }]}
            />
          </Split>
        </Stack>
      </CardBody>
    </Card>
  );
}

export function AddTile({ disabled, onAdd }: { disabled: boolean; onAdd: () => void }) {
  return (
    <button type="button" {...stylex.props(styles.add, disabled && styles.addDisabled)} disabled={disabled} onClick={onAdd}>
      <Icon name="plus" size={22} />
      <span>Add an agent</span>
      <Text tone="faint" size="md">
        Everything it needs is set up for you
      </Text>
    </button>
  );
}

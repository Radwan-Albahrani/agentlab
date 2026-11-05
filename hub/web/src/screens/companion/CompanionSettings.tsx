import * as stylex from '@stylexjs/stylex';
import { useState } from 'react';
import type { SettingField } from '../../api/types';
import { ChoiceCards, Switch } from '../../ui/controls';
import { useAct } from '../../ui/feedback';
import { Icon } from '../../ui/Icon';
import { SubmitField } from '../../ui/inputs';
import { Empty } from '../../ui/page';
import { Picker } from '../../ui/Picker';
import { Setting, Settings } from '../../ui/Settings';
import { Badge, Chip } from '../../ui/status';
import { colors, radius, space, text } from '../../theme/tokens.stylex';

const styles = stylex.create({
  people: { display: 'flex', flexDirection: 'column', gap: space.md, minWidth: 0, flexGrow: 1 },
  chips: { display: 'flex', flexWrap: 'wrap', gap: space.xs },
  face: { width: 22, height: 22, borderRadius: radius.pill, objectFit: 'cover' },
  remove: {
    appearance: 'none',
    borderWidth: 0,
    padding: 0,
    display: 'flex',
    cursor: 'pointer',
    backgroundColor: 'transparent',
    color: { default: colors.faint, ':hover': colors.fg },
  },
  none: { fontSize: text.sm, color: colors.faint },
});

export function CompanionSettings({ name, display, fields }: { name: string; display: string; fields: SettingField[] }) {
  const act = useAct();
  const set = (key: string, value: unknown) => act(`/api/companions/${name}/settings`, { key, value });
  if (!fields.length)
    return <Empty title="No settings published" text={`${display} shares its settings when it starts.`} icon="bot" />;
  const values = Object.fromEntries(fields.map((f) => [f.key, String(f.value)]));
  const shown = fields.filter((f) => Object.entries(f.when ?? {}).every(([k, ok]) => ok.includes(values[k] ?? '')));
  return (
    <Settings>
      {shown.map((f) => (
        <Setting key={f.key} label={f.label} help={f.help}>
          <Control field={f} onChange={(v) => set(f.key, v)} />
        </Setting>
      ))}
    </Settings>
  );
}

function Control({ field: f, onChange }: { field: SettingField; onChange: (v: unknown) => unknown }) {
  if (f.type === 'choice')
    return <ChoiceCards label={f.label} value={String(f.value)} options={f.options ?? []} onChange={onChange} />;
  if (f.type === 'bool') return <Switch on={!!f.value} label={f.label} onToggle={() => onChange(!f.value)} />;
  if (f.type === 'people') return <People field={f} onChange={onChange} />;
  return (
    <SubmitField initial={typeof f.value === 'string' ? f.value : ''} button="Save" keep primary={false} onSubmit={onChange} />
  );
}

function People({ field: f, onChange }: { field: SettingField; onChange: (v: unknown) => unknown }) {
  const [round, setRound] = useState(0); // remounts the picker so it clears after each add
  const picked = Array.isArray(f.value) ? (f.value as string[]) : [];
  const options = f.options ?? [];
  const byId = Object.fromEntries(options.map((o) => [o.value, o]));
  const items = options.filter((o) => !picked.includes(o.value)).map((o) => ({ value: o.value, label: o.label }));
  return (
    <div {...stylex.props(styles.people)}>
      <div {...stylex.props(styles.chips)}>
        {picked.length === 0 && <span {...stylex.props(styles.none)}>Only you</span>}
        {picked.map((id) => (
          <Chip key={id} avatar>
            {byId[id]?.avatar ? (
              <img src={byId[id].avatar} alt="" {...stylex.props(styles.face)} />
            ) : (
              <Badge name={byId[id]?.label ?? id} size="xs" />
            )}
            {byId[id]?.label ?? id}
            <button
              type="button"
              aria-label={`Remove ${byId[id]?.label ?? id}`}
              onClick={() => onChange(picked.filter((p) => p !== id))}
              {...stylex.props(styles.remove)}
            >
              <Icon name="x" size={14} />
            </button>
          </Chip>
        ))}
      </div>
      <Picker
        key={round}
        items={items}
        value=""
        label="Add a person"
        placeholder={options.length ? 'Add a person…' : 'Waiting for the Slack member list…'}
        empty="Nobody else matches"
        onChange={(id) => {
          if (!id) return;
          setRound((r) => r + 1);
          void onChange([...picked, id]);
        }}
      />
    </div>
  );
}

import type { SettingField } from '../../api/types';
import { ChoiceCards, Switch } from '../../ui/controls';
import { useAct } from '../../ui/feedback';
import { SubmitField } from '../../ui/inputs';
import { Empty } from '../../ui/page';
import { Setting, Settings } from '../../ui/Settings';

/** The settings a companion publishes, each with the control its type calls for; changes apply live. */
export function CompanionSettings({ name, display, fields }: { name: string; display: string; fields: SettingField[] }) {
  const act = useAct();
  const set = (key: string, value: unknown) => act(`/api/companions/${name}/settings`, { key, value });
  if (!fields.length)
    return <Empty title="No settings published" text={`${display} shares its settings when it starts.`} icon="bot" />;
  return (
    <Settings>
      {fields.map((f) => (
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
  return (
    <SubmitField initial={typeof f.value === 'string' ? f.value : ''} button="Save" keep primary={false} onSubmit={onChange} />
  );
}

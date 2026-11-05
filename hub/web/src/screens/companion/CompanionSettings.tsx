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
import { Badge } from '../../ui/status';
import { colors, radius, space, text } from '../../theme/tokens.stylex';

const styles = stylex.create({
  people: { display: 'grid', gap: space.sm, minWidth: 0 },
  search: { display: 'flex', minWidth: 0 },
  list: {
    display: 'grid',
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: colors.line,
    borderRadius: radius.md,
    overflow: 'hidden',
  },
  person: {
    display: 'flex',
    alignItems: 'center',
    gap: space.md,
    paddingBlock: space.sm,
    paddingInline: space.md,
    minWidth: 0,
    borderTopWidth: { default: 1, ':first-child': 0 },
    borderTopStyle: 'solid',
    borderTopColor: colors.line,
  },
  face: { width: 28, height: 28, borderRadius: radius.pill, objectFit: 'cover', flexShrink: 0 },
  name: { flexGrow: 1, minWidth: 0, fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' },
  remove: {
    appearance: 'none',
    borderWidth: 0,
    padding: space.xxs,
    borderRadius: radius.sm,
    display: 'flex',
    cursor: 'pointer',
    backgroundColor: { default: 'transparent', ':hover': colors.hover },
    color: { default: colors.faint, ':hover': colors.fg },
  },
  none: { fontSize: text.sm, color: colors.faint, paddingInline: space.xxs },
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
      <div {...stylex.props(styles.search)}>
        <Picker
          key={round}
          items={items}
          value=""
          label="Add a person"
          placeholder={options.length ? 'Search people to add…' : 'Waiting for the Slack member list…'}
          empty="Nobody else matches"
          onChange={(id) => {
            if (!id) return;
            setRound((r) => r + 1);
            void onChange([...picked, id]);
          }}
        />
      </div>
      {picked.length === 0 ? (
        <span {...stylex.props(styles.none)}>Only you can tag it right now.</span>
      ) : (
        <div {...stylex.props(styles.list)}>
          {picked.map((id) => {
            const label = byId[id]?.label ?? id;
            return (
              <div key={id} {...stylex.props(styles.person)}>
                {byId[id]?.avatar ? (
                  <img src={byId[id].avatar} alt="" {...stylex.props(styles.face)} />
                ) : (
                  <Badge name={label} size="sm" />
                )}
                <span {...stylex.props(styles.name)}>{label}</span>
                <button
                  type="button"
                  aria-label={`Remove ${label}`}
                  title="Remove access"
                  onClick={() => onChange(picked.filter((p) => p !== id))}
                  {...stylex.props(styles.remove)}
                >
                  <Icon name="x" size={15} />
                </button>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

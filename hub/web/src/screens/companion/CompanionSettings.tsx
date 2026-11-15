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
import { colors, radius, space, text } from '../../theme/tokens.stylex';
import { Avatar } from './parts';

const styles = stylex.create({
  people: { display: 'grid', gap: space.md, minWidth: 0 },
  search: { display: 'flex', minWidth: 0 },
  list: { display: 'flex', flexWrap: 'wrap', gap: space.sm },
  person: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: space.sm,
    maxWidth: '100%',
    paddingBlock: space.xxs,
    paddingInlineStart: space.xxs,
    paddingInlineEnd: space.xxs,
    borderRadius: radius.sm,
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: colors.line2,
    backgroundColor: colors.raised,
  },
  name: { minWidth: 0, fontWeight: 500, fontSize: text.md, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' },
  remove: {
    appearance: 'none',
    borderWidth: 0,
    padding: space.xxs,
    borderRadius: radius.xs,
    display: 'flex',
    cursor: 'pointer',
    backgroundColor: { default: 'transparent', ':hover': colors.badSoft },
    color: { default: colors.faint, ':hover': colors.bad },
    transitionProperty: 'background-color, color',
    transitionDuration: '140ms',
    opacity: { default: 1, ':active': 0.85 },
    outline: { default: 'none', ':focus-visible': `2px solid ${colors.accent}` },
    outlineOffset: 2,
  },
  none: {
    display: 'flex',
    alignItems: 'center',
    gap: space.sm,
    paddingBlock: space.md,
    paddingInline: space.lg,
    borderRadius: radius.md,
    borderWidth: 1,
    borderStyle: 'dashed',
    borderColor: colors.line2,
    fontSize: text.md,
    color: colors.muted,
  },
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
        <span {...stylex.props(styles.none)}>
          <Icon name="key" size={15} />
          Only you can tag it right now.
        </span>
      ) : (
        <div {...stylex.props(styles.list)}>
          {picked.map((id) => {
            const label = byId[id]?.label ?? id;
            return (
              <span key={id} {...stylex.props(styles.person)}>
                <Avatar name={label} src={byId[id]?.avatar} size={24} />
                <span {...stylex.props(styles.name)}>{label}</span>
                <button
                  type="button"
                  aria-label={`Remove ${label}`}
                  title="Remove access"
                  onClick={() => onChange(picked.filter((p) => p !== id))}
                  {...stylex.props(styles.remove)}
                >
                  <Icon name="x" size={14} />
                </button>
              </span>
            );
          })}
        </div>
      )}
    </div>
  );
}

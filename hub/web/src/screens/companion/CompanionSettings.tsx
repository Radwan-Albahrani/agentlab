import * as stylex from '@stylexjs/stylex';
import { useState } from 'react';
import type { GithubPerson, SettingField } from '../../api/types';
import { ChoiceCards, Disclosure, Switch } from '../../ui/controls';
import { useAct } from '../../ui/feedback';
import { Icon } from '../../ui/Icon';
import { SubmitField, TextInput } from '../../ui/inputs';
import { Button } from '../../ui/Button';
import { Empty } from '../../ui/page';
import { Picker } from '../../ui/Picker';
import { Setting, Settings } from '../../ui/Settings';
import { colors, font, radius, space, text } from '../../theme/tokens.stylex';
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
  links: { display: 'grid', gap: space.md, minWidth: 0 },
  pairs: { display: 'grid', gap: space.xs },
  pair: {
    display: 'flex',
    alignItems: 'center',
    gap: space.md,
    flexWrap: 'wrap',
    paddingBlock: space.sm,
    borderTopWidth: 1,
    borderTopStyle: 'solid',
    borderTopColor: colors.line,
    minWidth: 0,
  },
  who: { display: 'flex', alignItems: 'center', gap: space.sm, flexGrow: 1, flexShrink: 1, flexBasis: '180px', minWidth: 0 },
  whoText: { display: 'grid', minWidth: 0 },
  sub: { fontSize: text.xs, color: colors.faint },
  ok: { color: colors.ok },
  pick: { display: 'flex', flexGrow: 2, flexShrink: 1, flexBasis: '220px', minWidth: 0 },
  login: { fontFamily: font.mono, fontSize: text.md, overflowWrap: 'anywhere' },
  add: { display: 'flex', gap: space.sm, flexWrap: 'wrap', alignItems: 'center', minWidth: 0 },
  addLogin: { flexGrow: 1, flexShrink: 1, flexBasis: '160px', minWidth: 0 },
  addPerson: { flexGrow: 2, flexShrink: 1, flexBasis: '200px', minWidth: 0, display: 'flex' },
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

export function CompanionSettings({
  name,
  display,
  fields,
  authors = [],
  github = [],
}: {
  name: string;
  display: string;
  fields: SettingField[];
  authors?: Author[];
  github?: GithubPerson[];
}) {
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
          <Control field={f} onChange={(v) => set(f.key, v)} authors={authors} github={github} />
        </Setting>
      ))}
    </Settings>
  );
}

function Control({
  field: f,
  onChange,
  authors,
  github,
}: {
  field: SettingField;
  onChange: (v: unknown) => unknown;
  authors: Author[];
  github: GithubPerson[];
}) {
  if (f.type === 'choice')
    return <ChoiceCards label={f.label} value={String(f.value)} options={f.options ?? []} onChange={onChange} />;
  if (f.type === 'bool') return <Switch on={!!f.value} label={f.label} onToggle={() => onChange(!f.value)} />;
  if (f.type === 'people') return <People field={f} onChange={onChange} />;
  if (f.type === 'links') return <Links field={f} onChange={onChange} authors={authors} github={github} />;
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

interface Link {
  github: string;
  slack: string;
}

export interface Author {
  login: string;
  avatar: string;
  prs: number;
}

const norm = (v: string) => v.toLowerCase().replace(/[^a-z0-9]/g, '');

/** The Slack person whose name best matches a GitHub login, or '' when nothing is close. */
export function guessSlack(login: string, people: { value: string; label: string }[]): string {
  const l = norm(login);
  if (l.length < 3) return '';
  let best = '';
  let bestScore = 0;
  for (const p of people) {
    const name = norm(p.label);
    const first = norm(p.label.split(/\s+/)[0] ?? '');
    const score =
      name === l
        ? 4
        : name.includes(l) || (name.length >= 4 && l.includes(name))
          ? 3
          : first.length >= 4 && l.startsWith(first)
            ? 2
            : 0;
    if (score > bestScore) {
      best = p.value;
      bestScore = score;
    }
  }
  return best;
}

/** GitHub people linked to Slack: the authors of open pull requests come listed, each with a suggested Slack match. */
function Links({
  field: f,
  onChange,
  authors,
  github,
}: {
  field: SettingField;
  onChange: (v: unknown) => unknown;
  authors: Author[];
  github: GithubPerson[];
}) {
  const pairs = Array.isArray(f.value) ? (f.value as Link[]) : [];
  const options = f.options ?? [];
  const byId = Object.fromEntries(options.map((o) => [o.value, o]));
  const linked = new Map(pairs.map((p) => [p.github.toLowerCase(), p.slack]));
  const link = (github: string, slack: string) => {
    const rest = pairs.filter((p) => p.github.toLowerCase() !== github.toLowerCase());
    void onChange(slack ? [...rest, { github, slack }] : rest);
  };
  const known = new Set(authors.map((a) => a.login.toLowerCase()));
  const rows: Author[] = [
    ...authors,
    ...pairs.filter((p) => !known.has(p.github.toLowerCase())).map((p) => ({ login: p.github, avatar: '', prs: 0 })),
  ];
  return (
    <div {...stylex.props(styles.links)}>
      {rows.length === 0 ? (
        <span {...stylex.props(styles.none)}>
          <Icon name="github" size={15} />
          No pull requests yet: their authors show up here to link.
        </span>
      ) : (
        <div {...stylex.props(styles.pairs)}>
          {rows.map((a) => {
            const current = linked.get(a.login.toLowerCase()) ?? '';
            const guess = current ? '' : guessSlack(a.login, options);
            return (
              <div key={a.login} {...stylex.props(styles.pair)}>
                <div {...stylex.props(styles.who)}>
                  <Avatar name={a.login} src={a.avatar} size={24} />
                  <div {...stylex.props(styles.whoText)}>
                    <span {...stylex.props(styles.login)}>{a.login}</span>
                    <span {...stylex.props(styles.sub)}>
                      {current ? (
                        <span {...stylex.props(styles.ok)}>Gets their review results</span>
                      ) : a.prs ? (
                        `${a.prs} open pull request${a.prs === 1 ? '' : 's'}`
                      ) : (
                        'Not linked'
                      )}
                    </span>
                  </div>
                </div>
                <div {...stylex.props(styles.pick)}>
                  <Picker
                    items={options.map((o) => ({ value: o.value, label: o.label }))}
                    value={current}
                    label={`Slack person for ${a.login}`}
                    placeholder={options.length ? 'Pick their Slack account…' : 'Waiting for the Slack member list…'}
                    empty="Nobody matches"
                    onChange={(slack) => {
                      link(a.login, slack);
                    }}
                  />
                </div>
                {guess && (
                  <Button
                    label={`Link ${byId[guess]?.label ?? 'them'}`}
                    icon="check"
                    small
                    onClick={() => {
                      link(a.login, guess);
                    }}
                  />
                )}
              </div>
            );
          })}
        </div>
      )}
      <Other
        onLink={link}
        options={options}
        github={github.filter((g) => !linked.has(g.login.toLowerCase()) && !known.has(g.login.toLowerCase()))}
      />
    </div>
  );
}

/** Someone without an open pull request: pick them from the people who can work on the repos (typed only until Leafy lists them). */
function Other({
  onLink,
  options,
  github,
}: {
  onLink: (github: string, slack: string) => void;
  options: { value: string; label: string }[];
  github: GithubPerson[];
}) {
  const [login, setLogin] = useState('');
  const [person, setPerson] = useState('');
  const [round, setRound] = useState(0);
  const name = login.trim().replace(/^@/, '');
  const add = () => {
    if (!name || !person) return;
    onLink(name, person);
    setLogin('');
    setPerson('');
    setRound((r) => r + 1);
  };
  return (
    <Disclosure label="Link someone else">
      <div {...stylex.props(styles.add)}>
        <div {...stylex.props(styles.addLogin)}>
          {github.length ? (
            <Picker
              key={`gh-${round}`}
              items={github.map((g) => ({ value: g.login, label: g.login }))}
              value={login}
              label="GitHub person"
              placeholder="Search GitHub people…"
              empty="Nobody matches"
              onChange={setLogin}
            />
          ) : (
            <TextInput value={login} onChange={setLogin} placeholder="GitHub username" onEnter={add} />
          )}
        </div>
        <div {...stylex.props(styles.addPerson)}>
          <Picker
            key={round}
            items={options}
            value={person}
            label="Their Slack account"
            placeholder="Their Slack account…"
            empty="Nobody matches"
            onChange={setPerson}
          />
        </div>
        <Button label="Link" icon="plus" small onClick={add} disabled={!name || !person} />
      </div>
    </Disclosure>
  );
}

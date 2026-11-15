import * as stylex from '@stylexjs/stylex';
import type { Secret, SecretKind } from '../../api/types';
import { plural } from '../../lib/format';
import { colors, font, radius, space, text } from '../../theme/tokens.stylex';
import { Button } from '../../ui/Button';
import { InfoTip } from '../../ui/controls';
import { useAct } from '../../ui/feedback';
import { Icon } from '../../ui/Icon';
import { Inline } from '../../ui/layout';
import { MoreMenu } from '../../ui/Menu';
import { Chip } from '../../ui/status';
import { Td, Tr } from '../../ui/Table';
import { Note, Text } from '../../ui/text';
import { When } from '../../ui/When';

const styles = stylex.create({
  who: { display: 'flex', alignItems: 'center', gap: space.lg, minWidth: 0 },
  lock: {
    width: 28,
    height: 28,
    flexShrink: 0,
    display: 'grid',
    placeItems: 'center',
    borderRadius: radius.md,
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: colors.line,
    color: colors.muted,
    backgroundColor: colors.raised,
  },
  lockWarn: {
    color: colors.warn,
    backgroundColor: colors.warnSoft,
    borderColor: `color-mix(in srgb, ${colors.warn} 35%, transparent)`,
  },
  name: { minWidth: 0 },
  // a squared mono tag, tinted by what a change does
  state: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: space.xxs,
    fontFamily: font.mono,
    fontSize: text.xxs,
    fontWeight: 500,
    letterSpacing: '.05em',
    textTransform: 'uppercase',
    paddingBlock: 1,
    paddingInline: space.xs,
    borderRadius: radius.xs,
    borderWidth: 1,
    borderStyle: 'solid',
    whiteSpace: 'nowrap',
  },
  info: {
    backgroundColor: colors.infoSoft,
    color: colors.info,
    borderColor: `color-mix(in srgb, ${colors.info} 30%, transparent)`,
  },
  ok: { backgroundColor: colors.okSoft, color: colors.ok, borderColor: `color-mix(in srgb, ${colors.ok} 30%, transparent)` },
  idle: { backgroundColor: colors.idleSoft, color: colors.muted, borderColor: colors.line2 },
  warn: {
    backgroundColor: colors.warnSoft,
    color: colors.warn,
    borderColor: `color-mix(in srgb, ${colors.warn} 35%, transparent)`,
  },
  effect: { marginBlockStart: space.xxs, fontSize: text.md, color: colors.muted },
  when: { fontFamily: font.mono, fontSize: text.xs, fontVariantNumeric: 'tabular-nums' },
  versions: { display: 'block', fontFamily: font.mono, fontSize: text.xxs, color: colors.faint },
});

const TONE = { info: styles.info, ok: styles.ok, idle: styles.idle, warn: styles.warn };

/** How a change to it lands, as a small coloured chip. */
const STATE: Record<SecretKind, [label: string, icon: string, tone: keyof typeof TONE]> = {
  restart: ['restarts', 'power', 'info'],
  copy: ['copied', 'copy', 'ok'],
  read: ['read live', 'eye', 'idle'],
  unmapped: ['not mapped', 'alert', 'warn'],
};

interface Props {
  s: Secret;
  onView: () => void;
  onEdit: () => void;
  onHistory: () => void;
}

export function SecretRow({ s, onView, onEdit, onHistory }: Props) {
  const act = useAct();
  const title = s.label || s.name;
  const unmapped = s.kinds.includes('unmapped');
  return (
    <Tr>
      <Td>
        <div {...stylex.props(styles.who)}>
          <span {...stylex.props(styles.lock, unmapped && styles.lockWarn)}>
            <Icon name="key" size={15} />
          </span>
          <div {...stylex.props(styles.name)}>
            <Inline nowrap>
              <Text weight="semibold">{title}</Text>
              {s.about && (
                <InfoTip label={`About ${title}`}>
                  <Text block>{s.about}</Text>
                  {s.how && (
                    <Text block>
                      <b>How to get or replace it:</b> {s.how}
                    </Text>
                  )}
                </InfoTip>
              )}
            </Inline>
            <Text mono tone="muted" block>
              {s.name}
            </Text>
          </div>
        </div>
      </Td>
      <Td wide>
        <Inline gap="xs">
          {s.kinds.map((k) => {
            const [label, icon, tone] = STATE[k];
            return (
              <span key={k} {...stylex.props(styles.state, TONE[tone])}>
                <Icon name={icon} size={11} />
                {label}
              </span>
            );
          })}
          {s.used_by.length ? s.used_by.map((u) => <Chip key={u}>{u}</Chip>) : <Note>nothing yet</Note>}
        </Inline>
        <div {...stylex.props(styles.effect)}>{s.effect}</div>
      </Td>
      <Td wide fit muted>
        <span {...stylex.props(styles.when)}>
          <When t={s.modified} />
        </span>
        {s.versions > 0 && <span {...stylex.props(styles.versions)}>{plural(s.versions, 'earlier version')}</span>}
      </Td>
      <Td num fit>
        <Inline gap="xs" nowrap end>
          <Button label="View" icon="eye" small onClick={onView} />
          <Button label="Edit" icon="edit" small onClick={onEdit} />
          <MoreMenu
            label={`More for ${title}`}
            entries={[
              {
                label: 'History',
                icon: 'history',
                hint: s.versions ? String(s.versions) : 'No earlier versions',
                disabled: !s.versions,
                onSelect: onHistory,
              },
              {
                label: 'Delete',
                icon: 'trash',
                danger: true,
                onSelect: () =>
                  act('/api/secrets/delete', { name: s.name }, { confirm: `Delete ${s.name}? A copy stays in its versions.` }),
              },
            ]}
          />
        </Inline>
      </Td>
    </Tr>
  );
}

import type { Secret } from '../../api/types';
import { Button } from '../../ui/Button';
import { InfoTip } from '../../ui/controls';
import { useAct } from '../../ui/feedback';
import { Inline } from '../../ui/layout';
import { MoreMenu } from '../../ui/Menu';
import { Chip } from '../../ui/status';
import { Td, Tr } from '../../ui/Table';
import { Note, Text } from '../../ui/text';
import { When } from '../../ui/When';

interface Props {
  s: Secret;
  onView: () => void;
  onEdit: () => void;
  onHistory: () => void;
}

/** One secret: its name with an ⓘ about how to get it, who uses it, and what you can do with it. */
export function SecretRow({ s, onView, onEdit, onHistory }: Props) {
  const act = useAct();
  const title = s.label || s.name;
  return (
    <Tr>
      <Td>
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
      </Td>
      <Td wide>
        <Inline gap="xs">{s.used_by.length ? s.used_by.map((u) => <Chip key={u}>{u}</Chip>) : <Note>nothing yet</Note>}</Inline>
        <Text tone="muted" size="md" block>
          {s.effect}
        </Text>
      </Td>
      <Td wide fit muted>
        <When t={s.modified} />
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

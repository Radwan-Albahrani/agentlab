import * as stylex from '@stylexjs/stylex';
import { useState } from 'react';
import { useCompanionLogs, useCompanionSecrets } from '../../api/queries';
import type { CompanionSecrets as Data } from '../../api/types';
import { colors, font, radius, space, text } from '../../theme/tokens.stylex';
import { Button } from '../../ui/Button';
import { Card, CardBody } from '../../ui/Card';
import { useAct } from '../../ui/feedback';
import { SubmitField } from '../../ui/inputs';
import { Empty, Section } from '../../ui/page';
import { List, Row } from '../../ui/Row';
import { Pill } from '../../ui/status';
import { Note } from '../../ui/text';
import { When } from '../../ui/When';

const styles = stylex.create({
  pre: {
    margin: 0,
    maxHeight: '60vh',
    overflow: 'auto',
    whiteSpace: 'pre-wrap',
    overflowWrap: 'anywhere',
    fontFamily: font.mono,
    fontSize: text.xs,
    padding: space.lg,
    borderRadius: radius.md,
    backgroundColor: colors.sunk,
    color: colors.fg,
  },
});

export function CompanionSecrets({ name, display }: { name: string; display: string }) {
  const query = useCompanionSecrets(name);
  return (
    <Section
      title="Secrets"
      sub={`What ${display} signs in with. Saving one restarts it with the new value; they are never shown again here.`}
    >
      <Card>{query.data ? <SecretList name={name} d={query.data} /> : <Empty title="Loading…" icon="clock" />}</Card>
    </Section>
  );
}

function SecretList({ name, d }: { name: string; d: Data }) {
  const act = useAct();
  const [open, setOpen] = useState<string | null>(null);
  return (
    <List>
      {d.items.map((s) => (
        <div key={s.file}>
          <Row
            icon="key"
            title={s.label || s.file}
            detail={s.about}
            meta={s.set ? <When t={s.modified} /> : undefined}
            actions={
              <>
                <Pill tone={s.set ? 'ok' : 'warn'}>{s.set ? 'Set' : 'Not set'}</Pill>
                <Button
                  label={s.set ? 'Replace' : 'Set'}
                  variant="quiet"
                  small
                  onClick={() => {
                    setOpen(open === s.file ? null : s.file);
                  }}
                />
              </>
            }
          />
          {open === s.file && (
            <CardBody divided>
              {s.how && <Note>{s.how}</Note>}
              <SubmitField
                type="password"
                placeholder={s.file}
                button="Save"
                onSubmit={async (value) => {
                  if (await act(`/api/companions/${name}/secret`, { file: s.file, value })) setOpen(null);
                }}
              />
            </CardBody>
          )}
        </div>
      ))}
    </List>
  );
}

export function CompanionLogs({ name }: { name: string }) {
  const query = useCompanionLogs(name);
  const logs = query.data;
  return (
    <Section title="Logs" sub={logs?.at ? <When t={logs.at} /> : 'Nothing logged yet.'}>
      <Card>
        <CardBody>
          {logs?.text ? (
            <pre {...stylex.props(styles.pre)} data-logs>
              {logs.text}
            </pre>
          ) : (
            <Empty title="No log yet" text="It appears once the companion has started." icon="log" />
          )}
        </CardBody>
      </Card>
    </Section>
  );
}

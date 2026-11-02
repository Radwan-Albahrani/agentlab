import { useDisplay } from '../api/queries';
import type { DisplayMode, DisplaySettings } from '../api/types';
import { Screen } from '../app/Screen';
import { Card, CardBody } from '../ui/Card';
import { Segments, Switch } from '../ui/controls';
import { useAct } from '../ui/feedback';
import { Split } from '../ui/layout';
import { PageHead, Section } from '../ui/page';
import { List, Row } from '../ui/Row';
import { Text } from '../ui/text';

const MODES: { value: DisplayMode; label: string }[] = [
  { value: 'show', label: 'Show' },
  { value: 'present', label: 'Hide while presenting' },
  { value: 'hide', label: 'Always hide' },
];

export function Display() {
  const query = useDisplay();
  return (
    <Screen title="Display" query={query}>
      {(d) => <DisplayView d={d} />}
    </Screen>
  );
}

function DisplayView({ d }: { d: DisplaySettings }) {
  const act = useAct();
  return (
    <>
      <PageHead
        title="Display"
        sub='Choose what this page shows. Presenting hides everything marked "Hide while presenting" in one switch (Alt+Shift+P, or triple-click the logo), menus and links included; those pages answer "not found". This page stays at /display.'
      />
      <Card>
        <CardBody>
          <Split>
            <div>
              <b>Presenting</b>
              <Text tone="muted" size="md" block>
                {d.presenting
                  ? 'On: only what you allow is visible, with nothing on screen saying so.'
                  : 'Off: everything is visible to you.'}
              </Text>
            </div>
            <Switch
              on={d.presenting}
              label="Presenting"
              onToggle={() => act('/api/display/presenting', { on: !d.presenting }, { quiet: true })}
            />
          </Split>
        </CardBody>
      </Card>
      {d.groups.map((g) => (
        <Section key={g.name} title={g.name}>
          <Card>
            <List>
              {g.items.map((i) => (
                <Row
                  key={i.key}
                  title={i.label}
                  actions={
                    <Segments
                      label={i.label}
                      value={i.mode}
                      options={MODES}
                      onChange={(v) => act('/api/display/mode', { key: i.key, value: v }, { quiet: true })}
                    />
                  }
                />
              ))}
            </List>
          </Card>
        </Section>
      ))}
    </>
  );
}

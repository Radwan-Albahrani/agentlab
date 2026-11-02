import type { AgentCard as Data } from '../api/types';
import { capitalize, pct } from '../lib/format';
import { Button, LinkButton } from '../ui/Button';
import { Card, CardBody } from '../ui/Card';
import { Brand, Icon } from '../ui/Icon';
import { Inline, Split, Stack } from '../ui/layout';
import { IconBox, List, Row } from '../ui/Row';
import { Badge, Chip, CompanionAvatar, Dot, Meter, Pill } from '../ui/status';
import { Eyebrow, Text } from '../ui/text';

function readiness(a: Data): string {
  const signed = (k: string) => a.accounts?.find((x) => x.key === k)?.signedIn;
  const ai = ['claude', 'codex'].filter(signed).map(capitalize);
  return ai.length ? `Ready · ${ai.join(' + ')}${signed('github') ? '' : ' · no GitHub'}` : 'No AI account yet';
}

function Title({ a, note }: { a: Data; note: string }) {
  return (
    <Inline gap="lg" nowrap>
      <Badge name={a.name} />
      <div>
        <Text size="lg" weight="bold">
          {a.name}
        </Text>
        <Text block tone="faint" size="md">
          {note}
        </Text>
      </div>
    </Inline>
  );
}

/**
 * One agent: readiness, memory, quick links, companions, sign-ins and connectors (both managed on its Accounts page).
 * `linked` adds an Open button to the agent's page; off on that page itself.
 */
export function AgentCard({ a, linked = true }: { a: Data; linked?: boolean }) {
  if (!a.online) {
    return (
      <Card>
        <CardBody>
          <Split>
            <Title a={a} note="Offline: starting or stopped" />
            <Pill tone="bad">Offline</Pill>
          </Split>
        </CardBody>
      </Card>
    );
  }
  const accounts = `/agents/${a.name}/accounts`;
  const r = a.resources;
  const jobs = r
    ? [r.running.length && `${r.running.length} heavy running`, r.waiting.length && `${r.waiting.length} waiting`]
        .filter(Boolean)
        .join(' · ') || 'idle'
    : '';
  return (
    <Card>
      <CardBody>
        <Stack gap="xxl">
          <Split>
            <Title a={a} note={readiness(a)} />
            {linked && <LinkButton label="Open" icon="arrow" variant="quiet" small to={`/agents/${a.name}`} />}
          </Split>
          {r && (
            <Stack gap="xs">
              <Meter pct={pct(r.usedMB, r.limitMB || 1)} />
              <Split>
                <Text tone="faint" size="md">
                  {(r.usedMB / 1024).toFixed(1)} of {((r.limitMB || 0) / 1024).toFixed(0)} GB memory
                </Text>
                <Text tone="faint" size="md">
                  {jobs}
                </Text>
              </Split>
            </Stack>
          )}
          {a.links && (
            <Inline gap="xs">
              <LinkButton label="Chat" icon="chat" small to={a.links.chat} />
              <LinkButton label="Terminal" icon="terminal" small to={a.links.terminal} />
              <LinkButton label="Files" icon="files" small to={a.links.files} />
              {a.links.browser ? (
                <LinkButton label="Browser" icon="browser" small to={a.links.browser} />
              ) : (
                <Button
                  label="Browser"
                  icon="browser"
                  small
                  disabled
                  hint="No browser open: the view starts when the agent opens one"
                />
              )}
            </Inline>
          )}
          {!!a.companions?.length && (
            <Stack gap="xs">
              <Eyebrow>Companions</Eyebrow>
              <Inline gap="xs">
                {a.companions.map((c) => (
                  <Chip key={c.name} avatar to={`/agents/${a.name}/${c.name}`}>
                    <CompanionAvatar profile={a.name} size="sm" />
                    {c.display}
                    <Dot ok={c.live} />
                  </Chip>
                ))}
              </Inline>
            </Stack>
          )}
          <Stack gap="xxs">
            <Eyebrow>Accounts</Eyebrow>
            <List>
              {a.accounts?.map((x) => (
                <Row
                  key={x.key}
                  flat
                  lead={
                    <IconBox>
                      <Brand name={x.key} />
                    </IconBox>
                  }
                  title={x.label}
                  detail={x.signedIn ? x.detail : x.active ? 'Sign-in in progress' : 'Not signed in'}
                  actions={
                    x.signedIn ? (
                      <Pill tone="ok">Signed in</Pill>
                    ) : (
                      <LinkButton
                        label={x.active ? 'Finish' : 'Sign in'}
                        variant={x.active ? 'default' : 'primary'}
                        small
                        to={accounts}
                      />
                    )
                  }
                />
              ))}
            </List>
          </Stack>
          <Stack gap="xs">
            <Eyebrow>Connectors</Eyebrow>
            <Inline gap="xs">
              {a.connectors?.map((c) =>
                c.signedIn ? (
                  <Pill key={c.key} tone="ok">
                    <Icon name="check" size={13} />
                    {c.name}
                  </Pill>
                ) : (
                  <Chip key={c.key} warn={c.added} to={accounts}>
                    {c.added ? `${c.name} · sign in` : `+ ${c.name}`}
                  </Chip>
                ),
              )}
            </Inline>
          </Stack>
        </Stack>
      </CardBody>
    </Card>
  );
}

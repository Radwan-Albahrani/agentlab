import { useLocation } from 'react-router';
import { useConfigFile, useConfigs } from '../api/queries';
import type { ConfigFile, ConfigRow, Configs as Data } from '../api/types';
import { Screen } from '../app/Screen';
import { DomainCard, domainSub, StackHead } from '../app/stacks';
import { useCanSee } from '../app/useCanSee';
import { Button, LinkButton } from '../ui/Button';
import { Card, CardBody } from '../ui/Card';
import { useAct, useFeedback } from '../ui/feedback';
import { FeedSection } from '../ui/Feed';
import { TextArea } from '../ui/inputs';
import { Split } from '../ui/layout';
import { PageHead, Section } from '../ui/page';
import { List, Row } from '../ui/Row';
import { Mono, Note } from '../ui/text';
import { When } from '../ui/When';

export function Configs() {
  const query = useConfigs();
  return (
    <Screen title="Configs" query={query}>
      {(d) => <ConfigsView d={d} />}
    </Screen>
  );
}

const Edit = ({ id }: { id: string }) => <LinkButton label="View" icon="edit" small to={`/config/${id}`} />;

function ConfigsView({ d }: { d: Data }) {
  const canSee = useCanSee();
  return (
    <>
      <PageHead
        title="Configs"
        sub="The compose file of every stack, each agent with its companions. agentctl renders them from cluster.toml; deploying one only recreates the services whose definition changed."
      />
      {d.domains.map((x) => (
        <DomainConfigs key={x.profile} profile={x.profile} stacks={x.stacks} />
      ))}
      {d.other.length > 0 && (
        <Section title="Other stacks">
          <Card>
            <List>
              {d.other.map((s) => (
                <Row
                  key={s.id}
                  icon="layers"
                  title={s.label}
                  detail={<Mono>rendered/compose/{s.id}/docker-compose.yml</Mono>}
                  meta={<When t={s.modified} />}
                  actions={<Edit id={s.id} />}
                />
              ))}
            </List>
          </Card>
        </Section>
      )}
      {(canSee('/secrets') || canSee('/notifications')) && (
        <Section title="Other settings">
          <Card>
            <List>
              {canSee('/secrets') && (
                <Row
                  icon="key"
                  title="Secrets"
                  detail="Tokens and passwords, applied where they are used"
                  actions={<LinkButton label="Open" icon="arrow" small to="/secrets" />}
                />
              )}
              {canSee('/notifications') && (
                <Row
                  icon="bell"
                  title="Notifications"
                  detail="Phone pushes through Bark (optional)"
                  actions={<LinkButton label="Open" icon="arrow" small to="/notifications" />}
                />
              )}
            </List>
          </Card>
        </Section>
      )}
    </>
  );
}

/** An agent alone is one line with its Edit button; with companions, each stack gets its own line. */
function DomainConfigs({ profile, stacks }: { profile: string; stacks: ConfigRow[] }) {
  const [only] = stacks;
  if (stacks.length === 1 && only)
    return (
      <DomainCard
        profile={profile}
        actions={<Edit id={only.id} />}
        sub={
          <>
            agent · <Mono>{only.id}</Mono> · <When t={only.modified} />
          </>
        }
      />
    );
  return (
    <DomainCard profile={profile} sub={domainSub(stacks.length)}>
      {stacks.map((s) => (
        <ConfigStack key={s.id} s={s} />
      ))}
    </DomainCard>
  );
}

function ConfigStack({ s }: { s: ConfigRow }) {
  return (
    <StackHead
      stack={s}
      detail={<Mono>{s.id}</Mono>}
      actions={
        <>
          <Note>
            <When t={s.modified} />
          </Note>
          {s.companion && (
            <LinkButton label="Settings" icon="bot" variant="quiet" small to={`/agents/${s.profile}/${s.companion}#settings`} />
          )}
          <Edit id={s.id} />
        </>
      }
    />
  );
}

export function ConfigEdit() {
  const id = useLocation().pathname.replace(/^\/config\//, '');
  const query = useConfigFile(id);
  return (
    <Screen title="Config" query={query}>
      {(d) => <Viewer d={d} />}
    </Screen>
  );
}

/** A rendered compose file, read-only: agentctl writes it from cluster.toml, so a change goes there. */
function Viewer({ d }: { d: ConfigFile }) {
  const act = useAct();
  const { confirm } = useFeedback();
  const warn =
    d.role === 'agent'
      ? 'Deploying recreates this agent: running chats are interrupted (they can be continued).'
      : 'Only services whose definition changed are recreated.';

  const deploy = async () => {
    if (await confirm(`Deploy ${d.id}? ${warn}`)) await act('/api/config/deploy', { id: d.id });
  };

  return (
    <>
      <PageHead
        eyebrow="Config"
        title={d.label}
        sub={<Mono>{d.path}</Mono>}
        right={<LinkButton label="Services" icon="layers" to="/services" />}
      />
      <Card>
        <CardBody>
          <TextArea editor readOnly value={d.text} />
          <Split>
            <Note>
              Rendered by agentctl. To change it, edit <Mono>/etc/agentlab/cluster.toml</Mono> and run <Mono>agentctl apply</Mono>
              . {warn}
            </Note>
            <Button label="Deploy" variant="primary" onClick={deploy} />
          </Split>
        </CardBody>
      </Card>
      <FeedSection title="Deploys" events={d.deploys} />
    </>
  );
}

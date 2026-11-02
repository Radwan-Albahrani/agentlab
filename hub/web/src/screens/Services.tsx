import { useServices } from '../api/queries';
import type { Services as Data } from '../api/types';
import { Screen } from '../app/Screen';
import { ConfigLink, ContainerRows, DomainServices, WatcherPending } from '../app/stacks';
import { useCanSee } from '../app/useCanSee';
import { LinkButton } from '../ui/Button';
import { Card } from '../ui/Card';
import { PageHead, Section } from '../ui/page';

export function Services() {
  const query = useServices();
  return (
    <Screen title="Services" query={query}>
      {(d) => <ServicesView d={d} />}
    </Screen>
  );
}

function ServicesView({ d }: { d: Data }) {
  const canSee = useCanSee();
  return (
    <>
      <PageHead
        title="Services"
        sub="Every container the cluster runs. Each agent comes with its companions. Restart one, read its logs, or redeploy a stack from Configs."
        right={canSee('/config') ? <LinkButton label="Configs" icon="sliders" to="/config" /> : undefined}
      />
      {!d.domains.length && !d.other.length && <WatcherPending />}
      {d.domains.map((x) => (
        <DomainServices key={x.profile} profile={x.profile} stacks={x.stacks} />
      ))}
      {d.other.map((s) => {
        const down = s.containers.filter((c) => !c.healthy).length;
        return (
          <Section
            key={s.id}
            title={s.label}
            sub={`${s.id} · ${down ? `${down} down` : 'all healthy'}`}
            right={<ConfigLink stack={s} />}
          >
            <Card>
              <ContainerRows stack={s} />
            </Card>
          </Section>
        );
      })}
    </>
  );
}

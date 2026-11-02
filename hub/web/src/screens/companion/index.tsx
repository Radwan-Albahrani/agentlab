import { useParams } from 'react-router-dom';
import { useCompanion } from '../../api/queries';
import type { Companion as Data } from '../../api/types';
import { NotFound, Screen } from '../../app/Screen';
import { STATE_PILL, weekStats } from '../../lib/companion';
import { ago, capitalize, duration } from '../../lib/format';
import { useHashTab } from '../../lib/useHashTab';
import { useNow } from '../../lib/useNow';
import { ActButton } from '../../ui/actions';
import { LinkButton } from '../../ui/Button';
import { Card, CardBody } from '../../ui/Card';
import { FeedSection } from '../../ui/Feed';
import { StatGrid } from '../../ui/layout';
import { Crumb, Hero, Section, Stat } from '../../ui/page';
import { CompanionAvatar, Pill } from '../../ui/status';
import { type TabItem, Tabs } from '../../ui/Tabs';
import { AskBox } from './AskBox';
import { CompanionSettings } from './CompanionSettings';
import { Polls } from './Polls';
import { PullRequests } from './PullRequests';
import { Delivered } from './Delivered';
import { TaskTable, WaitingTasks, WorkingTasks } from './Tasks';
import { CompanionLogs, CompanionSecrets } from './Upkeep';

export function Companion() {
  const { profile = '', name = '' } = useParams();
  const query = useCompanion(name);
  return (
    <Screen title={capitalize(name)} query={query}>
      {(d) => (d.profile === profile ? <CompanionView d={d} /> : <NotFound />)}
    </Screen>
  );
}

/** The companion's page: what needs you and what runs first (Overview), then a tab per kind of work, so no view is
 * a long scroll through everything. Tabs only appear for what this companion has (pull requests need a GitHub App,
 * polls need polls). */
function CompanionView({ d }: { d: Data }) {
  const now = useNow();
  const waiting = d.tasks.filter((t) => t.status === 'waiting').length;
  const tabs: TabItem[] = [
    {
      value: 'overview',
      label: 'Overview',
      icon: 'home',
      count: waiting,
      alert: true,
      content: (
        <>
          {d.channels && <AskBox name={d.name} display={d.display} channels={d.channels} />}
          <WeekStats d={d} now={now} />
          <WaitingTasks tasks={d.tasks} />
          <WorkingTasks tasks={d.tasks} now={now} />
          <FeedSection title="Recent activity" events={d.events} />
        </>
      ),
    },
  ];
  if (d.pulls)
    tabs.push({
      value: 'pulls',
      label: 'Pull requests',
      icon: 'pr',
      count: d.pulls.items.length,
      content: <PullRequests name={d.name} pulls={d.pulls} />,
    });
  tabs.push({
    value: 'tasks',
    label: 'Tasks',
    icon: 'log',
    count: d.tasks.length,
    content: (
      <>
        <TaskTable tasks={d.tasks} now={now} />
        {d.delivered && <Delivered events={d.delivered} />}
      </>
    ),
  });
  if (d.polls?.length)
    tabs.push({
      value: 'polls',
      label: 'Polls',
      icon: 'poll',
      count: d.polls.filter((p) => p.open).length,
      content: <Polls name={d.name} polls={d.polls} />,
    });
  if (d.settings)
    tabs.push({
      value: 'settings',
      label: 'Settings',
      icon: 'sliders',
      content: (
        <Section title="Settings" sub="Changes apply within seconds; no restart." id="settings">
          <Card>
            <CompanionSettings name={d.name} display={d.display} fields={d.settings} />
          </Card>
        </Section>
      ),
    });
  if (d.settings)
    tabs.push({
      value: 'secrets',
      label: 'Secrets',
      icon: 'key',
      content: <CompanionSecrets name={d.name} display={d.display} />,
    });
  tabs.push({ value: 'logs', label: 'Logs', icon: 'log', content: <CompanionLogs name={d.name} /> });
  const [tab, setTab] = useHashTab(tabs.map((t) => t.value));
  return (
    <>
      <Crumb profile={d.profile} here="Companion" />
      <Header d={d} now={now} />
      {d.state === 'unconfigured' && (
        <Card accent="info">
          <CardBody>
            <b>{d.display} is not set up yet.</b> Its Slack app or secrets are missing: add them under Secrets, or ask your agent
            in T3 to set it up.
          </CardBody>
        </Card>
      )}
      {d.problem && d.state !== 'live' && (
        <Card accent="bad">
          <CardBody>
            <b>Last error:</b> {d.problem}
          </CardBody>
        </Card>
      )}
      <Tabs items={tabs} value={tab} onChange={setTab} label={`${d.display} views`} />
    </>
  );
}

function Header({ d, now }: { d: Data; now: number }) {
  const [label, tone] = STATE_PILL[d.state] ?? ['Unknown', 'bad'];
  const nice = d.display;
  return (
    <Hero
      profile={d.profile}
      avatar={<CompanionAvatar profile={d.profile} size="lg" />}
      title={
        <>
          {nice}{' '}
          <Pill tone={tone} dot>
            {label}
          </Pill>
        </>
      }
      sub={
        <>
          Slack companion of the <b>{d.profile}</b> agent
          {d.mode && (
            <>
              {' '}
              · mode <b>{d.mode}</b>
            </>
          )}
          {d.state !== 'offline' && d.since ? ` · up ${duration(now - d.since)}` : ''}
          {d.state === 'offline' && d.seen ? ` · last seen ${ago(d.seen, now)}` : ''}
        </>
      }
      actions={
        <>
          <ActButton
            label="Restart"
            icon="power"
            url={`/api/companions/${d.name}/restart`}
            confirm={`Restart ${nice}? Running tasks continue in T3 and are picked up again.`}
          />
          <ActButton
            label="Remove"
            icon="trash"
            variant="danger"
            url={`/api/companions/${d.name}/remove`}
            confirm={`Remove ${nice}? The bot stops and its data (tasks, settings, secrets) is archived. Its code stays in the agent's workspace, so it can be set up again.`}
          />
          <LinkButton label={`${d.profile} agent`} icon="arrow" to={`/agents/${d.profile}`} />
        </>
      }
    />
  );
}

function WeekStats({ d, now }: { d: Data; now: number }) {
  const s = weekStats(d.tasks, d.sentThisWeek, now);
  return (
    <StatGrid>
      <Stat label="Waiting on you" value={s.waiting} sub="approvals, replies, logins" tone={s.waiting ? 'warn' : 'idle'} />
      <Stat label="Working now" value={s.working} sub="tasks in progress" tone={s.working ? 'info' : 'idle'} />
      <Stat label="Taken · 7 days" value={s.taken} sub={`${s.errands} errands · ${s.plainTasks} tasks`} />
      <Stat
        label="Completed · 7 days"
        value={s.done}
        sub={s.failed ? `${s.failed} failed` : 'none failed'}
        tone={s.failed ? 'bad' : s.done ? 'ok' : 'idle'}
      />
      <Stat label="Messages sent · 7 days" value={s.sent} sub={`to ${s.people} ${s.people === 1 ? 'person' : 'people'}`} />
    </StatGrid>
  );
}

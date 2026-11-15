import * as stylex from '@stylexjs/stylex';
import { useParams } from 'react-router';
import { useCompanion } from '../../api/queries';
import type { Companion as Data } from '../../api/types';
import { NotFound, Screen } from '../../app/Screen';
import { STATE_PILL, sentTo, weekStats } from '../../lib/companion';
import { ago, capitalize, duration } from '../../lib/format';
import { useHashTab } from '../../lib/useHashTab';
import { useNow } from '../../lib/useNow';
import { hueTheme } from '../../theme/hues';
import { colors, font, media, radius, space, text } from '../../theme/tokens.stylex';
import { ActButton } from '../../ui/actions';
import { Button, LinkButton, Pressable } from '../../ui/Button';
import { Card } from '../../ui/Card';
import { FeedSection } from '../../ui/Feed';
import { StatGrid } from '../../ui/layout';
import { Num } from '../../ui/motion';
import { Crumb, Section, Stat } from '../../ui/page';
import { CompanionAvatar, Pill } from '../../ui/status';
import { type TabItem, Tabs } from '../../ui/Tabs';
import { AskBox } from './AskBox';
import { CompanionSettings } from './CompanionSettings';
import { Delivered } from './Delivered';
import { Blink, Notice } from './parts';
import { Polls } from './Polls';
import { PullRequests } from './PullRequests';
import { TaskTable, WaitingTasks, WorkingTasks } from './Tasks';
import { CompanionLogs, CompanionSecrets } from './Upkeep';

const styles = stylex.create({
  // whose page this is as one square agent-colour edge on top; the numbers sit in a hairline strip below
  hero: {
    display: 'grid',
    overflow: 'hidden',
    borderRadius: radius.xl,
    borderWidth: 1,
    borderStyle: 'solid',
    borderColor: colors.line,
    backgroundColor: colors.panel,
  },
  top: {
    display: 'grid',
    gridTemplateColumns: { default: 'minmax(0, 1fr) auto', [media.narrow]: '1fr' },
    gap: space.xxl,
    alignItems: 'center',
    paddingBlock: space.xxxl,
    paddingInline: { default: space.huge, [media.phone]: space.xxl },
  },
  identity: { display: 'flex', alignItems: 'center', gap: space.xxl, minWidth: 0 },
  kicker: {
    fontSize: text.xs,
    color: colors.faint,
    display: 'flex',
    alignItems: 'center',
    gap: space.sm,
    flexWrap: 'wrap',
  },
  title: {
    marginBlock: space.xxs,
    marginInline: 0,
    display: 'flex',
    alignItems: 'center',
    gap: space.md,
    flexWrap: 'wrap',
    fontFamily: font.display,
    fontSize: { default: text.display, [media.phone]: text.xxl },
    fontWeight: 600,
    letterSpacing: '-.01em',
    lineHeight: 1.1,
  },
  sub: { margin: 0, color: colors.muted, fontSize: text.body },
  strong: { color: colors.fg, fontWeight: 600 },
  mono: { fontFamily: font.mono, fontSize: text.md, color: colors.fg },
  actions: {
    display: 'flex',
    gap: space.sm,
    flexWrap: 'wrap',
    justifyContent: { default: 'flex-end', [media.narrow]: 'flex-start' },
  },
  strip: {
    display: 'grid',
    gridTemplateColumns: { default: 'repeat(auto-fit, minmax(150px, 1fr))', [media.phone]: 'repeat(2, minmax(0, 1fr))' },
    gap: 1,
    backgroundColor: colors.line,
    borderTopWidth: 1,
    borderTopStyle: 'solid',
    borderTopColor: colors.line,
  },
  metric: {
    appearance: 'none',
    borderWidth: 0,
    borderRadius: 0,
    paddingBlock: space.lg,
    paddingInline: { default: space.huge, [media.phone]: space.xxl },
    font: 'inherit',
    textAlign: 'start',
    cursor: 'pointer',
    display: 'grid',
    gap: space.xxxs,
    color: colors.fg,
    backgroundColor: { default: colors.panel, ':hover': colors.hover },
    transitionProperty: 'background-color',
    transitionDuration: '140ms',
    opacity: { default: 1, ':active': 0.85 },
    outline: { default: 'none', ':focus-visible': `2px solid ${colors.accent}` },
    outlineOffset: -2,
  },
  // phones lay the cards out two by two; an odd last one takes the whole row
  lastAlone: { gridColumn: { default: 'auto', [media.phone]: '1 / -1' } },
  metricValue: {
    display: 'flex',
    alignItems: 'center',
    gap: space.sm,
    fontFamily: font.mono,
    fontSize: text.xxl,
    fontWeight: 500,
    letterSpacing: '-.03em',
    lineHeight: 1.1,
    fontVariantNumeric: 'tabular-nums',
  },
  metricLabel: {
    fontSize: text.xxs,
    color: colors.muted,
  },
  quiet: { color: colors.faint },
  warn: { color: colors.warn },
  live: { color: colors.info },
  plain: { color: colors.fg },
  split: {
    display: 'grid',
    gridTemplateColumns: { default: 'minmax(0, 1.3fr) minmax(0, 1fr)', [media.narrow]: '1fr' },
    gap: space.huge,
    alignItems: 'start',
  },
});

export function Companion() {
  const { profile = '', name = '' } = useParams();
  const query = useCompanion(name);
  return (
    <Screen title={capitalize(name)} query={query}>
      {(d) => (d.profile === profile ? <CompanionView d={d} /> : <NotFound />)}
    </Screen>
  );
}

function CompanionView({ d }: { d: Data }) {
  const now = useNow(5000);
  const waiting = d.tasks.filter((t) => t.status === 'waiting').length;
  const working = <WorkingTasks tasks={d.tasks} name={d.name} />;
  const tabs: TabItem[] = [
    {
      value: 'overview',
      label: 'Overview',
      icon: 'home',
      count: waiting,
      alert: true,
      content: (
        <>
          <WaitingTasks tasks={d.tasks} />
          {d.channels ? (
            <div {...stylex.props(styles.split)}>
              <AskBox name={d.name} display={d.display} channels={d.channels} />
              {working}
            </div>
          ) : (
            working
          )}
          <WeekStats d={d} now={now} />
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
    content: <TaskTable tasks={d.tasks} now={now} />,
  });
  if (d.delivered)
    tabs.push({
      value: 'sent',
      label: 'Sent',
      icon: 'send',
      count: d.delivered.length,
      content: <Delivered events={d.delivered} />,
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
        <Section title="Settings" icon="sliders" sub="Changes apply within seconds; no restart." id="settings">
          <Card>
            <CompanionSettings
              name={d.name}
              display={d.display}
              fields={d.settings}
              authors={authorsOf(d)}
              github={d.pulls?.github.people ?? []}
              repos={d.pulls?.github.repos ?? []}
              channels={d.channels ?? []}
            />
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
  const has = (value: string) => tabs.some((t) => t.value === value);
  return (
    <>
      <Crumb profile={d.profile} here="Companion" />
      <Header d={d} now={now} go={setTab} />
      {d.state === 'unconfigured' && (
        <Notice
          tone="warn"
          icon="key"
          action={
            has('secrets') ? (
              <Button
                label="Add secrets"
                icon="key"
                small
                variant="primary"
                onClick={() => {
                  setTab('secrets');
                }}
              />
            ) : undefined
          }
        >
          <b>{d.display} is not set up yet.</b> Its Slack app or secrets are missing: add them under Secrets, or ask your agent in
          T3 to set it up.
        </Notice>
      )}
      {d.problem && d.state !== 'live' && (
        <Notice
          tone="bad"
          icon="alert"
          action={
            <Button
              label="Open the logs"
              icon="log"
              small
              onClick={() => {
                setTab('logs');
              }}
            />
          }
        >
          <b>Last error:</b> {d.problem}
        </Notice>
      )}
      <Tabs items={tabs} value={tab} onChange={setTab} label={`${d.display} views`} />
    </>
  );
}

function Metric({
  value,
  label,
  tone,
  live,
  onClick,
  alone,
}: {
  value: number;
  label: string;
  tone?: stylex.StyleXStyles;
  live?: boolean;
  onClick: () => void;
  alone?: boolean;
}) {
  return (
    <Pressable look={[styles.metric, alone && styles.lastAlone]} onClick={onClick}>
      <span {...stylex.props(styles.metricValue, tone ?? styles.quiet)}>
        <Num value={value} />
        {live && <Blink />}
      </span>
      <span {...stylex.props(styles.metricLabel)}>{label}</span>
    </Pressable>
  );
}

/** Who it is, whether it's up, and the numbers that matter; each number opens its tab. */
function Header({ d, now, go }: { d: Data; now: number; go: (tab: string) => void }) {
  const [label, tone] = STATE_PILL[d.state] ?? ['Unknown', 'bad'];
  const nice = d.display;
  const waiting = d.tasks.filter((t) => t.status === 'waiting').length;
  const working = d.tasks.filter((t) => t.status === 'working').length;
  const reviewing = d.pulls?.items.filter(
    (p) => p.review && ['queued', 'working', 'waiting', 'paused'].includes(p.review.status),
  ).length;
  const openPolls = d.polls?.filter((p) => p.open).length ?? 0;
  const people = d.sentThisWeek.filter((e) => sentTo(e) === 'person').length;
  return (
    <header {...stylex.props(hueTheme(d.profile), styles.hero)}>
      <div {...stylex.props(styles.top)}>
        <div {...stylex.props(styles.identity)}>
          <CompanionAvatar profile={d.profile} size="lg" />
          <div>
            <div {...stylex.props(styles.kicker)}>
              <span>Slack companion · @{d.name}</span>
              {d.state !== 'offline' && d.since ? <span>· up {duration(now - d.since)}</span> : null}
              {d.state === 'offline' && d.seen ? <span>· last seen {ago(d.seen, now)}</span> : null}
            </div>
            <h1 {...stylex.props(styles.title)}>
              {nice}
              <Pill tone={tone} dot>
                {label}
              </Pill>
            </h1>
            <p {...stylex.props(styles.sub)}>
              Companion of the <b {...stylex.props(styles.strong)}>{d.profile}</b> agent
              {d.mode && (
                <>
                  {' '}
                  · mode <code {...stylex.props(styles.mono)}>{d.mode}</code>
                </>
              )}
            </p>
          </div>
        </div>
        <div {...stylex.props(styles.actions)}>
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
        </div>
      </div>
      <div {...stylex.props(styles.strip)}>
        <Metric
          value={waiting}
          label="Waiting on you"
          tone={waiting ? styles.warn : undefined}
          onClick={() => {
            go('overview');
          }}
        />
        <Metric
          value={working}
          label="Working now"
          tone={working ? styles.live : undefined}
          live={working > 0}
          onClick={() => {
            go('overview');
          }}
        />
        {d.pulls && (
          <Metric
            value={d.pulls.items.length}
            label={reviewing ? `Pull requests · ${reviewing} in review` : 'Open pull requests'}
            tone={reviewing ? styles.live : styles.plain}
            live={!!reviewing}
            onClick={() => {
              go('pulls');
            }}
          />
        )}
        {d.delivered && (
          <Metric
            alone={!d.polls?.length && !d.pulls}
            value={d.sentThisWeek.length}
            label={people ? `Sent this week · ${people} to people` : 'Sent this week'}
            tone={d.sentThisWeek.length ? styles.plain : undefined}
            onClick={() => {
              go('sent');
            }}
          />
        )}
        {!!d.polls?.length && (
          <Metric
            alone={(2 + Number(!!d.pulls) + Number(!!d.delivered)) % 2 === 0}
            value={openPolls}
            label="Open polls"
            tone={openPolls ? styles.plain : undefined}
            onClick={() => {
              go('polls');
            }}
          />
        )}
      </div>
    </header>
  );
}

function WeekStats({ d, now }: { d: Data; now: number }) {
  const s = weekStats(d.tasks, d.sentThisWeek, now);
  return (
    <Section title="Last 7 days" icon="history">
      <StatGrid>
        <Stat
          label="Taken on"
          value={s.taken}
          sub={`${s.errands} errands · ${s.plainTasks} tasks`}
          tone={s.taken ? 'info' : 'idle'}
        />
        <Stat
          label="Completed"
          value={s.done}
          sub={s.failed ? `${s.failed} failed` : 'none failed'}
          tone={s.failed ? 'bad' : s.done ? 'ok' : 'idle'}
        />
        <Stat label="Messages sent" value={s.sent} sub={`to ${s.people} ${s.people === 1 ? 'person' : 'people'}`} />
      </StatGrid>
    </Section>
  );
}

/** Who opened the pull requests the companion sees, most pull requests first. */
function authorsOf(d: Data) {
  const by = new Map<string, { login: string; avatar: string; prs: number }>();
  for (const p of d.pulls?.items ?? []) {
    const a = by.get(p.author) ?? { login: p.author, avatar: p.avatar, prs: 0 };
    a.prs += 1;
    by.set(p.author, a);
  }
  return [...by.values()].filter((a) => a.login !== d.pulls?.me).sort((a, b) => b.prs - a.prs);
}

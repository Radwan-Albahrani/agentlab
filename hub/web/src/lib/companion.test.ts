import type { Event, Poll, Task } from '../api/types';
import {
  askedBy,
  askers,
  dayLabel,
  delivery,
  sentTo,
  filterTasks,
  pollSummary,
  resumesLabel,
  slackParts,
  slackPlain,
  taskAge,
  taskWho,
  weekStats,
} from './companion';

const now = 1_800_000_000;
const task = (over: Partial<Task>): Task => ({
  id: 'x',
  title: 't',
  kind: 'task',
  requester: '',
  status: 'done',
  waiting: '',
  outcome: '',
  poll: null,
  startedAt: now - 3600,
  endedAt: now - 1800,
  slack: '',
  t3: '',
  ...over,
});

describe('companion tasks', () => {
  const tasks = [
    task({ id: 'a', kind: 'errand', status: 'done' }),
    task({ id: 'b', kind: 'task', status: 'failed' }),
    task({ id: 'c', kind: 'errand', status: 'waiting', endedAt: null }),
    task({ id: 'd', kind: 'task', status: 'done', startedAt: now - 30 * 86400 }),
  ];

  it('filters by kind and by status', () => {
    expect(filterTasks(tasks, 'all')).toHaveLength(4);
    expect(filterTasks(tasks, 'errand').map((t) => t.id)).toEqual(['a', 'c']);
    expect(filterTasks(tasks, 'done').map((t) => t.id)).toEqual(['a', 'd']);
    expect(filterTasks(tasks, 'failed').map((t) => t.id)).toEqual(['b']);
    const reviewed = [...tasks, task({ id: 'r', kind: 'review', status: 'done' })];
    expect(filterTasks(reviewed, 'review').map((t) => t.id)).toEqual(['r']);
    expect(filterTasks(reviewed, 'task').map((t) => t.id)).toEqual(['b', 'd']);
  });

  it('counts the last 7 days', () => {
    const sent: Event[] = [
      { at: now - 60, kind: 'sent', title: 'm', to: 'Heba' },
      { at: now - 90, kind: 'sent', title: 'm', to: 'Heba' },
    ];
    const s = weekStats(tasks, sent, now);
    expect(s).toMatchObject({ waiting: 1, taken: 3, errands: 2, plainTasks: 1, done: 1, failed: 1, sent: 2, people: 1 });
  });

  it('shows how long a task took, but not for old ones without an end time', () => {
    expect(taskAge(tasks[0]!, now)).toBe('30 min');
    expect(taskAge(tasks[2]!, now)).toBe('1 h 00 m');
    expect(taskAge(task({ endedAt: null, status: 'done' }), now)).toBe('');
    expect(taskAge(task({ status: 'working', startedAt: now - 660, endedAt: now - 480 }), now)).toBe('11 min');
    expect(taskAge(task({ status: 'paused', startedAt: now - 660, endedAt: null }), now)).toBe('11 min');
  });

  it('says when a task paused by a usage limit resumes', () => {
    expect(resumesLabel(null, now)).toBe('resumes when the limit resets');
    expect(resumesLabel(now + 3600, now)).toMatch(/^resumes \d{1,2}:\d\d [AP]M$/);
  });
});

describe('taskWho', () => {
  it('says who an errand is for and who started a task', () => {
    expect(taskWho(task({ kind: 'errand', requester: 'Salah' }))).toBe('for Salah');
    expect(taskWho(task({ kind: 'task', requester: 'Salah' }))).toBe('started by Salah');
    expect(taskWho(task({ kind: 'task' }))).toBe('started by you');
  });
});

describe('pollSummary', () => {
  const poll = (votes: number[], open = true): Poll => ({
    id: 'p',
    task: 't',
    open,
    closes: now,
    closed: open ? null : now,
    question: 'Where?',
    channel: '#lunch',
    link: '',
    multiple: true,
    options: votes.map((n, i) => ({
      label: `O${i}`,
      votes: n,
      voters: Array.from({ length: n }, (_, k) => ({ name: `P${k}`, avatar: '' })),
    })),
  });
  it('leads, ties, wins and no votes read as one line', () => {
    expect(pollSummary(poll([2, 1]))).toMatch(/^Leading: O0 · 2 votes · 2 people voted · closes /);
    expect(pollSummary(poll([2, 2]))).toMatch(/^Leading: O0, O1 · 2 votes each · /);
    expect(pollSummary(poll([1, 3], false))).toMatch(/^Winner: O1 · 3 votes · 3 people voted · closed /);
    expect(pollSummary(poll([0, 0]))).toMatch(/^No votes yet · closes /);
  });
});

describe('slack text and who asked', () => {
  it('turns Slack links into parts and labels', () => {
    const s = 'Review posted on <https://github.com/o/r/pull/1#c|o/r#1> · no findings';
    expect(slackParts(s)).toEqual([
      'Review posted on ',
      { url: 'https://github.com/o/r/pull/1#c', label: 'o/r#1' },
      ' · no findings',
    ]);
    expect(slackPlain(s)).toBe('Review posted on o/r#1 · no findings');
    expect(slackPlain('see <https://x.io>')).toBe('see https://x.io');
  });

  it('offers anyone, you, then each person, and filters by them', () => {
    const t = (requester: string) => ({ requester }) as Task;
    const tasks = [t(''), t('Sara'), t('Ali'), t('Sara')];
    expect(askers(tasks).map((o) => o.label)).toEqual(['Anyone · 4', 'You · 1', 'Ali · 1', 'Sara · 2']);
    expect(askedBy(tasks, '@Sara')).toHaveLength(2);
    expect(askedBy(tasks, 'me')).toHaveLength(1);
    expect(askedBy(tasks, '*')).toHaveLength(4);
  });
});

describe('deliveries', () => {
  const e = (to: string) => ({ to }) as Event;
  it('tells DMs to people from channels and pull requests', () => {
    expect(sentTo(e('Sara Ali'))).toBe('person');
    expect(sentTo(e('#general'))).toBe('channel');
    expect(sentTo(e('netzerosa/platform#6182'))).toBe('github');
    expect(sentTo(e('app#12'))).toBe('github');
  });

  it('says where once and what it was, without repeating the destination', () => {
    const d = (title: string, to: string, detail = '') => delivery({ at: 0, kind: 'sent', title, to, detail });
    expect(d('Review of netzerosa/platform#6111: no findings · QA verified', 'netzerosa/platform#6111')).toEqual({
      where: 'github',
      to: 'platform#6111',
      link: 'https://github.com/netzerosa/platform/pull/6111',
      what: 'Review',
      note: 'no findings · QA verified',
    });
    expect(d('Message sent to Ali Al-Shaikh by DM', 'Ali Al-Shaikh by DM', '\nHi Ali,\nmore')).toMatchObject({
      where: 'person',
      to: 'Ali Al-Shaikh',
      what: 'Message sent',
      note: 'Hi Ali,',
    });
    expect(d('Product update posted to #product-updates', '#product-updates', 'revision 2')).toMatchObject({
      where: 'channel',
      what: 'Product update posted',
      note: 'revision 2',
    });
    expect(d('Review result for platform#6111', 'Sara', '<https://x|Approved> · clean')).toMatchObject({
      what: 'Review result for platform#6111',
      note: 'Approved · clean',
    });
  });

  it('groups by Today, Yesterday, then the date', () => {
    const noon = new Date(2026, 10, 16, 12).getTime() / 1000;
    expect(dayLabel(noon - 3600, noon)).toBe('Today');
    expect(dayLabel(noon - 86400, noon)).toBe('Yesterday');
    expect(dayLabel(noon - 4 * 86400, noon)).not.toMatch(/Today|Yesterday/);
  });
});

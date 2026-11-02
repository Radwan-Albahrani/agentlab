import type { Event, Poll, Task } from '../api/types';
import { filterTasks, pollSummary, taskAge, weekStats } from './companion';

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
    // picked up again after an earlier turn ended: counts until now
    expect(taskAge(task({ status: 'working', startedAt: now - 660, endedAt: now - 480 }), now)).toBe('11 min');
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

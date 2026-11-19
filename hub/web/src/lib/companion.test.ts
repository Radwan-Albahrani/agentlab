import type { CaseItem, Event, Poll, Task } from '../api/types';
import {
  askedBy,
  askers,
  casesOf,
  dayLabel,
  filterCases,
  ITEM_PILL,
  itemHistory,
  lineOf,
  waitingOnYou,
  delivery,
  sentTo,
  filterTasks,
  pollSummary,
  resumesLabel,
  routeLine,
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
  party: 'owner',
  phase: 'answered',
  caseLink: '',
  items: [],
  route: null,
  ...over,
});

const item = (over: Partial<CaseItem>): CaseItem => ({ seq: 1, kind: 'in', state: 'received', at: now, history: [], ...over });

describe('cases', () => {
  const sara = task({ id: 's', party: 'colleague', requester: 'Sara', phase: 'working' });
  const waiting = task({
    id: 'w',
    party: 'colleague',
    phase: 'answered',
    items: [item({ seq: 2, kind: 'approval', state: 'awaiting_owner', action: 'Merge' })],
  });
  const errand = task({ id: 'e', party: 'errand', phase: 'answered' });
  const mine = task({ id: 'm', party: 'owner' });

  it('are every conversation with someone else, errands included', () => {
    expect(casesOf([sara, waiting, errand, mine]).map((t) => t.id)).toEqual(['s', 'w', 'e']);
  });

  it('need you while anything waits on you, whatever the phase says', () => {
    const all = casesOf([sara, waiting, errand]);
    expect(filterCases(all, 'you').map((t) => t.id)).toEqual(['w']);
    expect(filterCases(all, 'open').map((t) => t.id)).toEqual(['s', 'w']);
    expect(waitingOnYou(waiting)).toHaveLength(1);
  });

  it('read each message as who to whom, keeping your private exchange apart', () => {
    expect(lineOf(item({ label: 'Sara' }), 'Sara', 'Leafy')).toEqual({ from: 'Sara', to: 'Leafy', side: 'theirs' });
    expect(lineOf(item({ private: true }), 'Sara', 'Leafy')).toEqual({ from: 'You', to: 'Leafy', side: 'private' });
    expect(lineOf(item({ kind: 'final', to: 'case' }), 'Sara', 'Leafy')).toEqual({ from: 'Leafy', to: 'you', side: 'private' });
    const out = item({ kind: 'message', to: 'channel', label: '#incidents', state: 'awaiting_owner' });
    expect(lineOf(out, 'Sara', 'Leafy')).toEqual({ from: 'Leafy', to: '#incidents', side: 'ours' });
    expect(lineOf(item({ kind: 'approval' }), 'Sara', 'Leafy')).toBeNull();
  });

  it('say how an item got to its state', () => {
    const it = item({
      kind: 'approval',
      state: 'approved',
      history: [
        ['received', now],
        ['awaiting_owner', now],
        ['approved', now],
      ],
    });
    expect(
      itemHistory(it)
        .split(' → ')
        .map((s) => s.split(' ').slice(0, -2).join(' ')),
    ).toEqual(['received', 'waiting for you', 'approved']);
    expect(ITEM_PILL[it.state]).toEqual(['Approved', 'ok']);
  });
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

  it('reads the audit: where it came from, who approved it, who else asked', () => {
    expect(taskWho(task({ kind: 'task', startedBy: 'Ali', via: 'in a DM', requester: 'Ali' }))).toBe('started by Ali in a DM');
    expect(
      taskWho(
        task({
          kind: 'task',
          startedBy: 'Salah',
          requester: 'Salah',
          via: 'in the requests channel #leafy-requests',
          approvedBy: 'Radwan',
        }),
      ),
    ).toBe('started by Salah in the requests channel #leafy-requests · approved by Radwan');
    expect(taskWho(task({ kind: 'review', startedBy: '', via: 'from the hub', requester: 'Ali' }))).toBe(
      'started by you from the hub · for Ali',
    );
    expect(taskWho(task({ kind: 'errand', requester: 'Salah', via: 'by your tag on their message' }))).toBe(
      'for Salah · by your tag on their message',
    );
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

describe('where a chat started', () => {
  it('names the project under the workspace and why it was chosen', () => {
    const r = { project: '/workspace/netzero-platform/apps/node-api', by: 'named' as const, why: 'the ask names "node-api"' };
    expect(routeLine(r)).toBe('netzero-platform/apps/node-api · named in the ask');
    expect(routeLine({ ...r, project: '/workspace/netzero-platform', by: 'default' })).toBe(
      'netzero-platform · the default project',
    );
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

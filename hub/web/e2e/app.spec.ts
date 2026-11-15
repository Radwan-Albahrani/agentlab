import { expect, test, type Locator, type Page, type TestInfo } from '@playwright/test';

// Only reads, a logs request and display settings may reach the server; intercept anything else.

const SCREENS = [
  '/',
  '/agents',
  '/agents/admin',
  '/agents/admin/accounts',
  '/agents/sara/onboarding',
  '/agents/admin/scout',
  '/agents/sara/helper',
  '/services',
  '/config',
  '/config/agentlab-core',
  '/storage',
  '/secrets',
  '/notifications',
  '/display',
];
const MUTATIONS =
  /\/api\/(services\/restart|config\/deploy|storage\/|secrets\/(save|create|delete|restore)|companions\/[\w-]+\/(restart|remove|settings|ask|poll|pulls|review|secret)$|notify\/|agents\/[\w-]+\/(pair|onboarding\/finish|devices\/revoke)|agents\/[\w-]+\/accounts\/(act|env\/))/;
const shots = process.env.SHOTS;

async function guard(page: Page) {
  const errors: string[] = [];
  page.on('pageerror', (e) => errors.push(e.message));
  page.on('console', (m) => m.type() === 'error' && !m.text().includes('fonts.g') && errors.push(m.text()));
  await page.route(MUTATIONS, (route) => route.fulfill({ json: { ok: true, message: '(test) not sent' } }));
  return errors;
}

async function settled(page: Page) {
  // the page's loading skeleton, not a button busy with its own action (UI SDK marks those aria-busy too)
  await expect(page.locator('[aria-busy="true"][aria-label="Loading"]')).toHaveCount(0, { timeout: 20_000 });
  await expect(page.getByText('Could not load this')).toHaveCount(0);
}

const shotName = (info: TestInfo, path: string) => `${shots}/${info.project.name}${path.replace(/\//g, '_') || '_'}.png`;
const dialog = (page: Page) => page.getByRole('dialog');

test('every screen loads without errors', async ({ page }, info) => {
  const errors = await guard(page);
  for (const path of SCREENS) {
    await page.goto(path);
    await settled(page);
    await expect(page.locator('h1').first(), path).toBeVisible();
    await expect(page.getByText("There's nothing here"), path).toHaveCount(0);
    if (shots) await page.screenshot({ path: shotName(info, path), fullPage: true });
  }
  expect(errors).toEqual([]);
});

test('no button in the page links to the page it is on', async ({ page }) => {
  await guard(page);
  for (const path of SCREENS) {
    await page.goto(path);
    await settled(page);
    await expect(page.locator(`main a[href="${path}"]`), path).toHaveCount(0);
  }
});

test('an agent card offers the live browser view, enabled only while a browser is open', async ({ page }) => {
  await guard(page);
  for (const path of ['/agents', '/agents/admin']) {
    await page.goto(path);
    await settled(page);
    const browser = page
      .locator('main')
      .getByRole('link', { name: 'Browser' })
      .or(page.locator('main').getByRole('button', { name: 'Browser' }));
    await expect(browser.first(), path).toBeVisible();
    const link = page.locator('main').getByRole('link', { name: 'Browser' }).first();
    await expect(page.locator('main').getByRole('link', { name: 'Files' }).first()).toHaveAttribute(
      'href',
      /\/_agentlab\/view\/admin\?next=\/_agentlab\/files\//,
    );
    if (await link.count())
      await expect(link).toHaveAttribute('href', /\/_agentlab\/view\/admin\?next=\/_agentlab\/accounts\/browser/);
    else await expect(page.locator('main').getByRole('button', { name: 'Browser' }).first()).toBeDisabled();
  }
});

test('tell the companion: pick a channel by typing, write, send (intercepted)', async ({ page }) => {
  await guard(page);
  let sent: Record<string, unknown> | null = null;
  await page.route(/\/api\/companions\/scout\/ask/, (route) => {
    sent = route.request().postDataJSON() as Record<string, unknown>;
    return route.fulfill({ json: { ok: true, message: '(test) not sent' } });
  });
  await page.goto('/agents/admin/scout');
  await settled(page);
  const box = page.getByPlaceholder(/make a poll/);
  await expect(box).toBeVisible();
  const picker = page.getByRole('combobox', { name: 'Channel' });
  await picker.fill('gen');
  // typing narrows the list: only matching channels stay (a picker once showed everyone whatever was typed)
  await expect(page.getByRole('option')).toHaveCount(1);
  await page.getByRole('option', { name: /#general/ }).click();
  await expect(picker).toHaveValue('#general');
  await box.fill('Make a poll: pizza or sushi, ends at 2pm');
  await page.getByRole('button', { name: 'Send', exact: true }).click();
  await expect.poll(() => sent).toMatchObject({ text: 'Make a poll: pizza or sushi, ends at 2pm', review: true });
  expect((sent as Record<string, unknown> | null)?.channel).toMatch(/^C/);
  const toast = page.getByRole('region', { name: 'Notifications' }).getByRole('listitem').filter({ hasText: '(test) not sent' });
  await expect(toast).toBeVisible();
  const at = await toast.boundingBox();
  const view = page.viewportSize();
  expect(at && view && view.width - (at.x + at.width)).toBeLessThan(40);
  expect(at && view && view.height - (at.y + at.height)).toBeLessThan(40);
  await toast.hover(); // hovering holds it open
  await toast.getByRole('button', { name: 'Dismiss' }).click();
  await expect(toast).toHaveCount(0);
});

test('companion polls: results with voters, and the open ones can be changed (intercepted)', async ({ page }) => {
  await guard(page);
  const sent: Record<string, unknown>[] = [];
  await page.route(/\/api\/companions\/scout\/poll$/, (route) => {
    sent.push(route.request().postDataJSON() as Record<string, unknown>);
    return route.fulfill({ json: { ok: true, message: '(test) not sent' } });
  });
  await page.goto('/agents/admin/scout#polls');
  await settled(page);
  const polls = page.locator('#polls');
  await expect(polls.getByText(/people? voted|No votes yet/).first()).toBeVisible();
  await expect(polls.getByRole('button', { name: 'Close the poll now' })).toHaveCount(0);
  await polls.locator('[aria-expanded="false"]').first().click();
  const choice = polls.getByRole('button', { name: 'Single choice' }).first();
  if (await choice.count()) {
    const multiple = await polls.getByRole('button', { name: 'Multiple choice', pressed: true }).count();
    await polls
      .getByRole('button', { name: multiple ? 'Single choice' : 'Multiple choice' })
      .first()
      .click();
    await expect.poll(() => sent.length).toBe(1);
    expect(sent[0]).toMatchObject({ multiple: !multiple });
    const closes = polls.locator('input[type="datetime-local"]').first();
    await closes.fill('2030-01-01T12:00');
    await closes.press('Enter');
    await expect.poll(() => sent.length).toBe(2);
    expect(sent[1].closes).toBe(new Date('2030-01-01T12:00').getTime() / 1000);
  }
});

const PULL = {
  repo: 'example/app',
  url: 'https://github.com/example/app/pull/1',
  draft: false,
  avatar: '',
  additions: 12,
  deletions: 3,
  created: '2026-11-01T10:00:00Z',
  head: 'abc',
  ci: 'passing',
  review: null,
};

/** `github: null` stands for a companion without a GitHub App. */
async function withPulls(page: Page, github: Record<string, unknown>, items: Record<string, unknown>[]) {
  await page.route(/\/api\/companions\/scout$/, async (route) => {
    const response = await route.fetch();
    const json = (await response.json()) as Record<string, unknown>;
    json.pulls = { github, me: 'example-admin', items };
    await route.fulfill({ response, json });
  });
}

test('pull requests: mine first, searchable, and Review sends the agent (intercepted)', async ({ page }) => {
  await guard(page);
  const asked: Record<string, unknown>[] = [];
  let refreshed = 0;
  await page.route(/\/api\/companions\/scout\/pulls$/, (route) => {
    refreshed += 1;
    return route.fulfill({ json: { ok: true, message: 'Refreshing.' } });
  });
  await page.route(/\/api\/companions\/scout\/review$/, (route) => {
    asked.push(route.request().postDataJSON() as Record<string, unknown>);
    return route.fulfill({ json: { ok: true, message: '(test) not sent' } });
  });
  await withPulls(page, { ready: true, bot: 'scout-example', accounts: ['example'], at: Date.now() / 1000, error: '' }, [
    {
      ...PULL,
      id: 'example/app#5922',
      number: 5922,
      title: 'test(api): remove duplicate cases',
      author: 'example-admin',
      labels: [{ name: 'lane:green', color: '0e8a16' }],
      updated: '2026-11-02T10:00:00Z',
    },
    {
      ...PULL,
      id: 'example/app#5026',
      number: 5026,
      title: 'feat(tree-wallet-mobile): read HealthKit',
      author: 'example-dev',
      labels: [],
      updated: '2026-11-01T10:00:00Z',
      review: {
        status: 'done',
        outcome: '2 findings (1 blocking) · QA found problems',
        task: 't',
        head: 'old',
        at: '',
        counts: { findings: 2, blocking: 1, open: 0, qa: 'fail' },
      },
    },
  ]);
  await page.goto('/agents/admin/scout#pulls');
  await settled(page);
  const section = page.locator('#pulls');
  await expect.poll(() => refreshed).toBeGreaterThan(0);
  const rows = section.getByTestId('pull');
  await expect(rows).toHaveCount(2);
  await expect(rows.first()).toContainText('#5922');
  await expect(section.getByText('Authored')).toBeVisible();
  await expect(rows.nth(1)).toContainText('1 blocking');
  await expect(rows.nth(1)).toContainText('QA ✗');
  await expect(rows.nth(1).getByTitle('2 findings (1 blocking) · QA found problems')).toBeVisible();
  await expect(rows.nth(1).getByText('new commits', { exact: true })).toBeVisible();
  await section.getByRole('searchbox').fill('label:green');
  await expect(rows).toHaveCount(1);
  await rows.first().getByRole('button', { name: 'Review' }).click();
  await expect.poll(() => asked).toEqual([{ pr: 'example/app#5922' }]);
  await expect(rows.first().getByText('Starting…')).toBeVisible();
  await page.unrouteAll({ behavior: 'ignoreErrors' }); // the page keeps polling while it starts
});

test('pull requests: without a GitHub App the page says how to connect one', async ({ page }) => {
  await guard(page);
  await withPulls(page, { ready: false, bot: '', accounts: [], at: 0, error: 'not set up' }, []);
  await page.goto('/agents/admin/scout#pulls');
  await settled(page);
  await expect(page.locator('#pulls').getByText('Connect a GitHub App')).toBeVisible();
  await expect(page.locator('#pulls').getByText('companions/scout/github-app-id.txt', { exact: false })).toBeVisible();
});

test('companion tabs: switching tabs leaves the page where it is', async ({ page }) => {
  await guard(page);
  await page.goto('/agents/admin/scout');
  await settled(page);
  const before = await page.evaluate(() => window.scrollY);
  for (const name of [/Tasks/, /Pull requests/, /Logs/]) {
    await page.getByRole('tab', { name }).click();
    await page.waitForTimeout(400);
    expect(await page.evaluate(() => window.scrollY)).toBe(before);
  }
});

test('companion tabs: each view has its own URL and Back returns', async ({ page }) => {
  await guard(page);
  await page.goto('/agents/admin/scout');
  await settled(page);
  const tabs = page.getByRole('tablist', { name: 'Scout views' });
  await expect(tabs.getByRole('tab', { name: /Overview/, selected: true })).toBeVisible();
  await tabs.getByRole('tab', { name: /Tasks/ }).click();
  await expect(page).toHaveURL(/#tasks$/);
  await expect(page.getByRole('group', { name: 'Filter tasks' })).toBeVisible();
  await page.goBack();
  await expect(tabs.getByRole('tab', { name: /Overview/, selected: true })).toBeVisible();
  await expect(page.getByRole('group', { name: 'Filter tasks' })).toHaveCount(0);
});

test('long lists come a page at a time', async ({ page }) => {
  await guard(page);
  await page.goto('/agents/admin/scout');
  await settled(page);
  const older = page.getByRole('button', { name: 'Older' }).first();
  if (await older.count()) {
    const first = await page.locator('main').innerText();
    await older.click();
    await expect(page.getByText(/^2 \/ \d+$/).first()).toBeVisible();
    expect(await page.locator('main').innerText()).not.toEqual(first);
    await expect(page.getByRole('button', { name: 'Newer' }).first()).toBeEnabled();
  }
});

test('logs open with text', async ({ page }) => {
  await guard(page);
  await page.goto('/services');
  await settled(page);
  await page.getByRole('button', { name: 'Logs' }).first().click();
  const pre = dialog(page).locator('pre[data-logs]');
  await expect(pre).toBeVisible();
  await expect(pre).not.toHaveText(/Fetching the last/, { timeout: 30_000 });
  await dialog(page).getByRole('button', { name: 'Close' }).click();
  await expect(dialog(page)).toHaveCount(0);
});

test('a secret opens read-only and closes', async ({ page }) => {
  await guard(page);
  await page.goto('/secrets');
  await settled(page);
  await page.getByRole('button', { name: 'View', exact: true }).first().click();
  const value = dialog(page).locator('textarea');
  await expect(value).toBeVisible();
  await expect(value).toHaveAttribute('readonly', '');
  await dialog(page).getByRole('button', { name: 'Close' }).click();
  await expect(dialog(page)).toHaveCount(0);
});

test('a secret explains itself', async ({ page }) => {
  await guard(page);
  await page.goto('/secrets');
  await settled(page);
  await page
    .getByRole('button', { name: /^About / })
    .first()
    .click();
  await expect(page.getByText('How to get or replace it:').first()).toBeVisible();
  await page.keyboard.press('Escape');
});

test('task filters', async ({ page }) => {
  await guard(page);
  await page.goto('/agents/admin/scout#tasks');
  await settled(page);
  await page.getByRole('group', { name: 'Filter tasks' }).getByRole('button', { name: 'Errands' }).click();
  const rows = page.locator('tbody tr');
  expect(await rows.count()).toBeGreaterThan(0);
  for (const text of await rows.allTextContents()) expect(text).toMatch(/Errand · for/);
});

test('restart asks first and goes nowhere in tests', async ({ page }) => {
  await guard(page);
  await page.goto('/services');
  await settled(page);
  await page.getByRole('button', { name: 'Restart' }).first().click();
  const confirm = page.getByRole('alertdialog');
  await expect(confirm).toBeVisible();
  await confirm.getByRole('button', { name: 'Cancel' }).click();
  await expect(confirm).toHaveCount(0);
});

test('companion settings: the QA repository is picked from the private repos the App sees, not typed', async ({ page }) => {
  await guard(page);
  let saved: Record<string, unknown> | null = null;
  await page.route(/\/api\/companions\/scout\/settings$/, (route) => {
    saved = route.request().postDataJSON() as Record<string, unknown>;
    return route.fulfill({ json: { ok: true, message: '(test) not saved' } });
  });
  await page.goto('/agents/admin/scout#settings');
  await settled(page);
  const picker = page.getByRole('combobox', { name: 'QA screenshots repository' });
  await picker.fill('qa');
  await expect(page.getByRole('option')).toHaveCount(1);
  await page.getByRole('option', { name: 'example/qa-evidence' }).click();
  await expect.poll(() => saved).toMatchObject({ key: 'qa_evidence_repo', value: 'example/qa-evidence' });
});

test('tasks: filter by who asked, and Slack links read as links', async ({ page }) => {
  await guard(page);
  await page.goto('/agents/admin/scout#tasks');
  await settled(page);
  const tasks = page.getByRole('tabpanel');
  await expect(tasks.getByRole('link', { name: 'example/app#12' })).toHaveAttribute('href', /pull\/12/);
  await expect(tasks).not.toContainText('<https://');
  await page.getByRole('combobox', { name: 'Asked by' }).click();
  await page.getByRole('option', { name: /^Sara/ }).click();
  await expect(tasks).toContainText('Summarise the incident thread');
  await expect(tasks).not.toContainText('Review example/app#12');
});

test('display settings: three states per item', async ({ page }) => {
  await guard(page);
  await page.goto('/display');
  await settled(page);
  const modes = () => page.getByRole('group', { name: 'Recent activity' });
  await modes().getByRole('button', { name: 'Always hide' }).click();
  await expect(modes().getByRole('button', { name: 'Always hide' })).toHaveAttribute('aria-pressed', 'true');
  await page.goto('/');
  await settled(page);
  await expect(page.getByRole('heading', { name: 'Recent activity' })).toHaveCount(0);
  await page.goto('/display');
  await settled(page);
  await modes().getByRole('button', { name: 'Show', exact: true }).click();
  await expect(modes().getByRole('button', { name: 'Show', exact: true })).toHaveAttribute('aria-pressed', 'true');
});

test('presenting by shortcut hides infrastructure and leaves no trace', async ({ page, request }) => {
  await guard(page);
  await page.goto('/services');
  await settled(page);
  await page.keyboard.press('Alt+Shift+KeyP');
  await expect(page).toHaveURL(/\/$/);
  const menu = page.locator('aside nav');
  await expect(menu.getByRole('link', { name: 'Services' })).toHaveCount(0);
  await expect(menu.getByRole('link', { name: 'Display' })).toHaveCount(0);
  await expect(page.getByText(/present/i)).toHaveCount(0);
  expect((await request.get('/api/services')).status()).toBe(404);
  expect((await request.get('/api/secrets/value?name=companions/scout/owner.txt')).status()).toBe(404);
  await page.keyboard.press('Alt+Shift+KeyP');
  await expect(menu.getByRole('link', { name: 'Services' })).toBeVisible();
});

// A control pushed past the edge of its card (clipped) or the screen can't be tapped; only deliberate scrollers may.
const CLIP_PATHS = [...SCREENS, '/agents/admin/scout#pulls', '/agents/admin/scout#tasks', '/agents/admin/scout#polls'];

async function clippedControls(page: Page) {
  const found: string[] = [];
  for (const path of CLIP_PATHS) {
    await page.goto(path);
    await settled(page);
    const bad = await page.evaluate(() => {
      const out: string[] = [];
      const width = document.documentElement.clientWidth;
      for (const el of document.querySelectorAll<HTMLElement>('main a, main button')) {
        const r = el.getBoundingClientRect();
        if (!r.width || !r.height || el.closest('[hidden], [aria-hidden="true"]')) continue;
        let clip = { left: 0, right: width };
        let scroller = false;
        for (let p = el.parentElement; p && p !== document.body; p = p.parentElement) {
          const ox = getComputedStyle(p).overflowX;
          if (ox === 'auto' || ox === 'scroll') {
            scroller = true;
            break;
          }
          if (ox === 'hidden' || ox === 'clip') {
            const b = p.getBoundingClientRect();
            clip = { left: Math.max(clip.left, b.left), right: Math.min(clip.right, b.right) };
          }
        }
        if (!scroller && (r.left < clip.left - 1 || r.right > clip.right + 1))
          out.push(
            `${el.tagName.toLowerCase()} "${(el.getAttribute('aria-label') ?? el.textContent ?? '').trim().slice(0, 40)}"`,
          );
      }
      return out;
    });
    found.push(...bad.map((b) => `${path}: ${b}`));
  }
  return found;
}

test('every button and link sits fully inside the screen and its card', async ({ page }) => {
  await guard(page);
  expect(await clippedControls(page)).toEqual([]);
});

test('phone and tablet: every button and link sits fully inside the screen and its card @phone', async ({ page }) => {
  await guard(page);
  for (const width of [360, 390, 768]) {
    await page.setViewportSize({ width, height: 844 });
    expect(await clippedControls(page), `${width}px`).toEqual([]);
  }
});

test('phone layout never scrolls sideways @phone', async ({ page }, info) => {
  await guard(page);
  for (const path of SCREENS) {
    await page.goto(path);
    await settled(page);
    const wide = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(wide, path).toBeLessThanOrEqual(0);
    if (shots) await page.screenshot({ path: shotName(info, path), fullPage: true });
  }
});

// A broken token silently turns pills and hovers colourless.
const PALETTE = {
  dark: {
    bg: 'rgb(18, 20, 23)',
    hover: 'rgb(34, 39, 45)',
    ok: 'rgb(111, 207, 151)',
    okSoft: 'rgb(19, 38, 27)',
    raised: 'rgb(28, 32, 37)',
  },
  light: {
    bg: 'rgb(236, 235, 231)',
    hover: 'rgb(230, 229, 224)',
    ok: 'rgb(27, 120, 67)',
    okSoft: 'rgb(219, 237, 225)',
    raised: 'rgb(251, 250, 248)',
  },
};
const schemeOf = (info: TestInfo) => (info.project.name.includes('dark') ? 'dark' : 'light');
const css = (l: Locator, prop: 'backgroundColor' | 'color') => l.evaluate((e, p) => getComputedStyle(e)[p], prop);

test('colour tokens resolve: pills, the active menu item and hovers are coloured', async ({ page }, info) => {
  await guard(page);
  await page.goto('/agents');
  await settled(page);
  const p = PALETTE[schemeOf(info)];
  const pill = page.getByText('Signed in', { exact: true }).first();
  expect(await css(pill, 'backgroundColor')).toBe(p.okSoft);
  expect(await css(pill, 'color')).toBe(p.ok);
  const menu = page.getByRole('navigation', { name: 'Main' });
  expect(await css(menu.getByRole('link', { name: 'All agents' }), 'backgroundColor')).toBe(p.raised);
  const services = menu.getByRole('link', { name: 'Services' });
  await services.hover();
  await expect.poll(() => css(services, 'backgroundColor')).toBe(p.hover); // it eases in
});

test('the live board counts chats per agent and never shows what they are about', async ({ page }) => {
  await guard(page);
  await page.goto('/');
  await settled(page);
  const board = page.locator('section', { has: page.getByRole('heading', { name: 'Your agents, now' }) });
  const admin = board.locator('[data-agent="admin"]');
  await expect(admin.getByText('running', { exact: true }).locator('..')).toContainText('1');
  await expect(admin.getByText('asking you', { exact: true }).locator('..')).toContainText('1');
  for (const title of ['Migrate billing to the new API', 'Which region should staging use?', 'Fix the flaky login test'])
    await expect(page.getByText(title)).toHaveCount(0);
  await page.keyboard.press('Control+KeyK');
  await page.getByRole('combobox', { name: 'Search' }).fill('billing');
  await expect(page.getByRole('option', { name: /Migrate billing/ })).toHaveCount(0);
});

test('search: Ctrl+K finds a page by a few letters and Enter goes there', async ({ page }, info) => {
  await guard(page);
  await page.goto('/');
  await settled(page);
  await page.keyboard.press('Control+KeyK');
  const search = page.getByRole('dialog', { name: 'Search' });
  await expect(search).toBeVisible();
  await search.getByRole('combobox', { name: 'Search' }).fill('helpr');
  await expect(search.getByRole('option').first()).toContainText('Helper');
  await expect(search.getByRole('option', { name: /quarterly report/ })).toHaveCount(0); // scattered letters don't count
  if (shots) await page.screenshot({ path: `${shots}/${info.project.name}_search.png` });
  await page.keyboard.press('Enter');
  await expect(page).toHaveURL(/\/agents\/sara\/helper$/);
  await expect(search).toHaveCount(0);
  await page.keyboard.press('/');
  await expect(search).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(search).toHaveCount(0);
});

test('reviews: an Overview count opens the list filtered to it, and a pull request opens its review', async ({ page }) => {
  await guard(page);
  await page.goto('/');
  await settled(page);
  const reviews = page.locator('section', { has: page.getByRole('heading', { name: 'Pull request reviews' }) });
  await reviews.getByRole('link', { name: /Blocking/ }).click();
  await expect(page).toHaveURL(/\/agents\/admin\/scout\?filter=blocking#pulls$/);
  const rows = page.getByTestId('pull');
  await expect(rows).toHaveCount(1);
  await page.getByRole('group', { name: 'Filter pull requests' }).getByRole('button', { name: /All/ }).click();
  await expect(rows).toHaveCount(4);
  await expect(page).not.toHaveURL(/filter=/);
  await rows
    .filter({ hasText: 'migratedAdditionsFor' })
    .getByRole('link', { name: /refactor\(api\)/ })
    .click();
  const view = page.getByRole('dialog');
  await expect(view).toContainText('Changes requested');
  await expect(view).toContainText('Revoked grants survive the migration');
  await expect(view.getByRole('link', { name: 'api/src/migrate/inputs.ts:80-88' })).toHaveAttribute('href', /#L80-L88$/);
  await expect(view).toContainText('QA partly verified');
  await expect(page).toHaveURL(/pr=15/);
  await page.keyboard.press('Escape');
  await expect(view).toHaveCount(0);
  await expect(page).not.toHaveURL(/pr=/);
});

test('pull requests: a batch of reviews shows how far along it is', async ({ page }) => {
  await guard(page);
  await page.goto('/agents/admin/scout#pulls');
  await settled(page);
  const batch = page.getByRole('region', { name: 'Review batch' });
  await expect(batch).toContainText('Reviewing 3 pull requests');
  await expect(batch).toContainText('1 of 3 done');
  await expect(page.getByTestId('pull').filter({ hasText: 'Bump the API client' })).toContainText('3 of 3');
  await page.unrouteAll({ behavior: 'ignoreErrors' });
});

test('the theme toggle switches to the other look and is remembered', async ({ page }, info) => {
  await guard(page);
  await page.goto('/');
  await settled(page);
  const bg = () => page.evaluate(() => getComputedStyle(document.body).backgroundColor);
  const system = schemeOf(info);
  const other = system === 'dark' ? 'light' : 'dark';
  expect(await bg()).toBe(PALETTE[system].bg);
  await page.getByRole('button', { name: `Switch to ${other} theme` }).click();
  expect(await bg()).toBe(PALETTE[other].bg);
  await page.reload();
  await settled(page);
  expect(await bg()).toBe(PALETTE[other].bg);
  await expect(page.getByRole('button', { name: `Switch to ${system} theme` })).toBeVisible();
});

test('secrets: search and filters narrow the list and live in the URL', async ({ page }) => {
  await guard(page);
  await page.goto('/secrets');
  await settled(page);
  const rows = page.locator('tbody tr');
  const total = await rows.count();
  await page.getByRole('searchbox', { name: 'Search secrets' }).fill('scout');
  await expect(rows).not.toHaveCount(total);
  for (const text of await rows.allInnerTexts()) expect(text.toLowerCase()).toContain('scout');
  await page.getByRole('searchbox', { name: 'Search secrets' }).fill('');
  await page
    .getByRole('group', { name: 'On change' })
    .getByRole('button', { name: /^Restarts a service/ })
    .click();
  await expect(page).toHaveURL(/effect=restart/);
  // the list re-renders a moment after the URL changes (router transition)
  await expect(rows).not.toHaveCount(total);
  const restarts = await rows.count();
  expect(restarts).toBeGreaterThan(0);
  expect(restarts).toBeLessThan(total);
  await page.reload();
  await settled(page);
  await expect(rows).toHaveCount(restarts);
  await page.getByRole('searchbox', { name: 'Search secrets' }).fill('no-such-secret-anywhere');
  await expect(page.getByText('No secrets match')).toBeVisible();
});

test('secrets: every row has the same one-line actions and a ⋯ menu', async ({ page }) => {
  await guard(page);
  await page.goto('/secrets');
  await settled(page);
  const boxes = await page
    .locator('tbody tr td:last-child > div')
    .evaluateAll((els) => els.map((el) => Math.round(el.getBoundingClientRect().height)));
  expect(boxes.length).toBeGreaterThan(1);
  expect(new Set(boxes).size).toBe(1);
  await page
    .getByRole('button', { name: /^More for / })
    .first()
    .click();
  await expect(page.getByRole('menuitem', { name: /History/ })).toBeVisible();
  await expect(page.getByRole('menuitem', { name: /Delete/ })).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.getByRole('menu')).toHaveCount(0);
});

test('secrets: actions stay usable on phones @phone', async ({ page }) => {
  await guard(page);
  await page.goto('/secrets');
  await settled(page);
  const rows = await page.locator('tbody tr').count();
  await expect(page.getByRole('button', { name: 'View', exact: true })).toHaveCount(rows);
  for (const view of await page.getByRole('button', { name: 'View', exact: true }).all()) {
    const box = await view.boundingBox();
    expect(box && box.width).toBeGreaterThan(40);
  }
});

test('onboarding: sign-in steps, Finish, then Open T3 signs this browser in (intercepted)', async ({ page }) => {
  await guard(page);
  await page.route(/\/api\/agents\/sara\/pair$/, (route) =>
    route.fulfill({
      json: {
        ok: true,
        message: { available: true, kind: 'browser', url: 'https://agents.example.com/pair#token=t', expires: '', id: 'p' },
      },
    }),
  );
  await page.route('https://agents.example.com/**', (route) => route.fulfill({ body: 'T3', contentType: 'text/plain' }));
  await page.goto('/agents/sara/onboarding');
  await settled(page);
  await expect(page.getByRole('heading', { name: 'Set up sara' })).toBeVisible();
  for (const step of ['Sign in to an AI', 'Connect your tools', 'GitHub'])
    await expect(page.getByRole('region', { name: step })).toBeVisible();
  await expect(page.getByRole('region', { name: 'Sign in to an AI' }).getByLabel('done')).toBeVisible();
  await page.getByRole('button', { name: 'Finish setup' }).click(); // intercepted: the agent keeps its state
  await page.route(/\/api\/agents\/sara\/accounts$/, async (route) => {
    const response = await route.fetch();
    const json = (await response.json()) as { onboarding: { done: boolean } };
    json.onboarding.done = true;
    await route.fulfill({ response, json });
  });
  await page.reload();
  await settled(page);
  await page.getByRole('button', { name: 'Open T3' }).click();
  await expect(page).toHaveURL('https://agents.example.com/pair#token=t');
});

test('pair the T3 app: a QR code and link, or why it cannot (intercepted)', async ({ page }) => {
  await guard(page);
  let answer: Record<string, unknown> = {
    available: true,
    kind: 'app',
    url: 'https://admin-t3.example.com/pair#token=t',
    expires: new Date(Date.now() + 600_000).toISOString(),
    id: 'p',
  };
  await page.route(/\/api\/agents\/admin\/pair$/, (route) => route.fulfill({ json: { ok: true, message: answer } }));
  await page.goto('/agents/admin');
  await settled(page);
  const devices = page.getByRole('region', { name: 'Devices' }).or(page.locator('section', { hasText: 'Pair the T3 app' }));
  await expect(devices.getByText('iPhone').first()).toBeVisible();
  await devices.getByPlaceholder('Device name, e.g. iPhone').fill('Laptop');
  await devices.getByRole('button', { name: 'Pair the T3 app' }).click();
  await expect(devices.getByRole('img', { name: 'Pairing code for the T3 app' })).toBeVisible();
  await expect(devices.getByText('https://admin-t3.example.com/pair#token=t')).toBeVisible();
  await expect(devices.getByText(/expires in/)).toBeVisible();
  answer = { available: false, reason: 'No pair_domain on this cluster.' };
  await devices.getByRole('button', { name: 'Done' }).click();
  await devices.getByPlaceholder('Device name, e.g. iPhone').fill('Laptop');
  await devices.getByRole('button', { name: 'Pair the T3 app' }).click();
  await expect(devices.getByText('No pair_domain on this cluster.')).toBeVisible();
});

test('a person sees only their own agents and companions', async ({ browser, request }) => {
  const sara = { 'X-Agentlab-User': 'sara@example.com' };
  const nav = (await (await request.get('/api/nav', { headers: sara })).json()) as { agents: { name: string }[] };
  expect(nav.agents.map((a) => a.name)).toEqual(['sara', 'lab']);
  for (const path of [
    '/api/agents/admin',
    '/api/companions/scout',
    '/api/companions/scout/logs',
    '/api/services',
    '/api/secrets',
  ])
    expect((await request.get(path, { headers: sara })).status(), path).toBe(403);
  expect((await request.post('/api/agents/admin/pair', { headers: sara, data: { kind: 'browser' } })).status()).toBe(403);
  const context = await browser.newContext({ extraHTTPHeaders: sara });
  const page = await context.newPage();
  await page.goto('/');
  await settled(page);
  const menu = page.getByRole('navigation', { name: 'Main' });
  await expect(menu.getByRole('link', { name: /lab/ })).toBeVisible();
  await expect(menu.getByRole('link', { name: /admin/ })).toHaveCount(0);
  await expect(menu.getByRole('link', { name: 'Services' })).toHaveCount(0);
  await page.goto('/agents/sara/helper');
  await settled(page);
  await expect(page.getByText('Helper is not set up yet.')).toBeVisible();
  await context.close();
});

test('companion secrets can be set, never read back; logs show (intercepted)', async ({ page }) => {
  await guard(page);
  const sent: Record<string, unknown>[] = [];
  await page.route(/\/api\/companions\/scout\/secret$/, (route) => {
    sent.push(route.request().postDataJSON() as Record<string, unknown>);
    return route.fulfill({ json: { ok: true, message: '(test) not sent' } });
  });
  await page.goto('/agents/admin/scout#secrets');
  await settled(page);
  const secrets = page.locator('section', { hasText: 'What Scout signs in with' });
  await expect(secrets.getByText('Set', { exact: true }).first()).toBeVisible();
  await secrets.getByRole('button', { name: 'Set', exact: true }).first().click();
  await secrets.locator('input[type="password"]').fill('xapp-example');
  await secrets.getByRole('button', { name: 'Save' }).click();
  await expect.poll(() => sent.length).toBe(1);
  expect(sent[0]).toMatchObject({ value: 'xapp-example' });
  await page.goto('/agents/admin/scout#logs');
  await settled(page);
  await expect(page.locator('pre[data-logs]')).toContainText('connected to Slack');
});

import { act, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import { Button } from './Button';
import { CommandPalette, type CommandEntry } from './Command';
import { ChipFilter, Disclosure, InfoTip, RadioCards, Segments, Switch } from './controls';
import { ConfirmDialog, Dialog } from './Dialog';
import { Field, TextInput } from './inputs';
import { MoreMenu, PickMenu } from './Menu';
import { Pager } from './Pager';
import { Picker } from './Picker';
import { Select } from './Select';
import { Meter } from './status';
import { Tabs } from './Tabs';

const settle = () => act(() => new Promise((r) => setTimeout(r, 0)));

function ChannelPicker({ onPick, onMiss }: { onPick: (v: string) => void; onMiss?: () => void }) {
  const [v, setV] = useState('');
  return (
    <Picker
      onMiss={onMiss}
      label="Channel"
      placeholder="Pick a channel"
      items={[
        { value: 'C1', label: '#general' },
        { value: 'C2', label: '#random' },
        { value: 'C3', label: '#gear' },
      ]}
      value={v}
      onChange={(next) => {
        setV(next);
        onPick(next);
      }}
    />
  );
}

describe('Picker', () => {
  it('typing narrows the options and Enter picks the highlighted one', async () => {
    const user = userEvent.setup();
    const picked: string[] = [];
    render(<ChannelPicker onPick={(v) => picked.push(v)} />);
    const box = screen.getByRole('combobox', { name: 'Channel' });
    await user.click(box);
    expect(screen.getAllByRole('option')).toHaveLength(3);
    await user.keyboard('ge');
    expect(screen.getAllByRole('option').map((o) => o.textContent)).toEqual(['#general', '#gear']);
    await user.keyboard('n');
    expect(screen.getAllByRole('option').map((o) => o.textContent)).toEqual(['#general']);
    await user.keyboard('{ArrowDown}{Enter}');
    expect(picked).toEqual(['C1']);
    expect(box).toHaveProperty('value', '#general');
  });

  it('says so when nothing matches', async () => {
    const user = userEvent.setup();
    render(<ChannelPicker onPick={() => undefined} />);
    await user.click(screen.getByRole('combobox', { name: 'Channel' }));
    await user.keyboard('zzz');
    expect(screen.queryAllByRole('option')).toHaveLength(0);
    expect(screen.getByText('Nothing matches')).toBeTruthy();
  });

  it('asks for a fresher list only when the typed text matches nothing', async () => {
    const user = userEvent.setup();
    const missed: string[] = [];
    render(<ChannelPicker onPick={() => undefined} onMiss={() => missed.push('miss')} />);
    await user.click(screen.getByRole('combobox', { name: 'Channel' }));
    await user.keyboard('ge');
    expect(missed).toEqual([]);
    await user.keyboard('x');
    expect(missed).toEqual(['miss']);
  });
});

describe('Dialog', () => {
  function Opener() {
    const [open, setOpen] = useState(false);
    return (
      <>
        <Button
          label="Open details"
          onClick={() => {
            setOpen(true);
          }}
        />
        <Dialog
          open={open}
          onClose={() => {
            setOpen(false);
          }}
          title="Details"
          text="About this agent"
        >
          <Field label="Name">
            <TextInput value="" onChange={() => undefined} />
          </Field>
          <Button
            label="Close"
            onClick={() => {
              setOpen(false);
            }}
          />
        </Dialog>
      </>
    );
  }

  it('is named by its title, keeps Tab inside, and Escape closes it back to the opener', async () => {
    const user = userEvent.setup();
    render(<Opener />);
    const opener = screen.getByRole('button', { name: 'Open details' });
    await user.click(opener);
    await settle();
    const dialog = screen.getByRole('dialog', { name: 'Details' });
    expect(dialog.getAttribute('aria-modal')).toBe('true');
    expect(dialog.contains(document.activeElement)).toBe(true);
    for (let i = 0; i < 4; i++) {
      await user.tab();
      expect(dialog.contains(document.activeElement)).toBe(true);
    }
    await user.keyboard('{Escape}');
    await settle();
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(document.activeElement).toBe(opener);
  });

  it('closes from its own Close button', async () => {
    const user = userEvent.setup();
    render(<Opener />);
    await user.click(screen.getByRole('button', { name: 'Open details' }));
    await settle();
    await user.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Close' }));
    await settle();
    expect(screen.queryByRole('dialog')).toBeNull();
  });
});

describe('ConfirmDialog', () => {
  it('starts on Cancel, answers each button, and leaves Continue to a person', async () => {
    const user = userEvent.setup();
    const answers: boolean[] = [];
    const { rerender } = render(<ConfirmDialog text="Restart the hub?" onAnswer={(ok) => answers.push(ok)} />);
    await settle();
    const ask = screen.getByRole('alertdialog', { name: 'Are you sure?' });
    expect(ask.textContent).toContain('Restart the hub?');
    expect(document.activeElement).toBe(within(ask).getByRole('button', { name: 'Cancel' }));
    expect(within(ask).getByRole('button', { name: 'Continue' }).getAttribute('data-agent-confirm')).toBe('Restart the hub?');
    await user.click(within(ask).getByRole('button', { name: 'Cancel' }));
    expect(answers).toEqual([false]);
    rerender(<ConfirmDialog text={null} onAnswer={(ok) => answers.push(ok)} />);
    await settle();
    rerender(<ConfirmDialog text="Delete it?" onAnswer={(ok) => answers.push(ok)} />);
    await settle();
    await user.click(screen.getByRole('button', { name: 'Continue' }));
    expect(answers).toEqual([false, true]);
  });
});

describe('MoreMenu', () => {
  it('opens on Enter, a disabled item is reached but does nothing, Enter runs one and focus returns', async () => {
    const user = userEvent.setup();
    const ran: string[] = [];
    render(
      <MoreMenu
        label="More for scout"
        entries={[
          { label: 'History', onSelect: () => ran.push('history') },
          { label: 'Rename', disabled: true, onSelect: () => ran.push('rename') },
          { label: 'Delete', danger: true, onSelect: () => ran.push('delete') },
        ]}
      />,
    );
    const trigger = screen.getByRole('button', { name: 'More for scout' });
    trigger.focus();
    await user.keyboard('{Enter}');
    await settle();
    const menu = screen.getByRole('menu');
    expect(document.activeElement).toBe(within(menu).getByRole('menuitem', { name: 'History' }));
    expect(within(menu).getByRole('menuitem', { name: 'Rename' }).getAttribute('aria-disabled')).toBe('true');
    expect(within(menu).getByRole('menuitem', { name: 'Delete' }).hasAttribute('data-destructive')).toBe(true);
    await user.keyboard('{ArrowDown}');
    expect(document.activeElement).toBe(within(menu).getByRole('menuitem', { name: 'Rename' }));
    await user.keyboard('{Enter}');
    expect(ran).toEqual([]);
    await user.keyboard('{ArrowDown}');
    expect(document.activeElement).toBe(within(menu).getByRole('menuitem', { name: 'Delete' }));
    await user.keyboard('{Enter}');
    await settle();
    expect(ran).toEqual(['delete']);
    expect(screen.queryByRole('menu')).toBeNull();
    expect(document.activeElement).toBe(trigger);
  });

  it('Escape closes it without running anything', async () => {
    const user = userEvent.setup();
    const ran: string[] = [];
    render(<MoreMenu label="More for scout" entries={[{ label: 'History', onSelect: () => ran.push('history') }]} />);
    await user.click(screen.getByRole('button', { name: 'More for scout' }));
    await settle();
    await user.keyboard('{Escape}');
    await settle();
    expect(screen.queryByRole('menu')).toBeNull();
    expect(ran).toEqual([]);
  });
});

describe('PickMenu', () => {
  it('checks the current choice and picks another with the keyboard', async () => {
    const user = userEvent.setup();
    const picked: string[] = [];
    render(
      <PickMenu
        label="Sort"
        icon="sort"
        value="new"
        options={[
          { value: 'new', label: 'Newest' },
          { value: 'old', label: 'Oldest' },
        ]}
        onChange={(v) => picked.push(v)}
      />,
    );
    act(() => {
      screen.getByRole('button', { name: 'Sort' }).focus();
    });
    await user.keyboard('{Enter}');
    await settle();
    const newest = screen.getByRole('menuitemradio', { name: 'Newest' });
    expect(newest.getAttribute('aria-checked')).toBe('true');
    expect(screen.getByRole('menuitemradio', { name: 'Oldest' }).getAttribute('aria-checked')).toBe('false');
    expect(document.activeElement).toBe(newest);
    await user.keyboard('{ArrowDown}{Enter}');
    await settle();
    expect(picked).toEqual(['old']);
    expect(screen.queryByRole('menu')).toBeNull();
  });
});

describe('Tabs', () => {
  function Views() {
    const [v, setV] = useState('a');
    return (
      <Tabs
        label="Scout views"
        value={v}
        onChange={setV}
        items={[
          { value: 'a', label: 'Overview', content: 'All of it' },
          { value: 'b', label: 'Tasks', count: 3, content: 'The tasks' },
          { value: 'c', label: 'Logs', content: 'The logs' },
        ]}
      />
    );
  }

  it('arrows move the selection, one tab is tabbable, and the panel follows', async () => {
    const user = userEvent.setup();
    render(<Views />);
    const list = screen.getByRole('tablist', { name: 'Scout views' });
    const tabs = within(list).getAllByRole('tab');
    expect(tabs.map((t) => t.getAttribute('tabindex'))).toEqual(['0', '-1', '-1']);
    tabs[0]!.focus();
    await user.keyboard('{ArrowRight}');
    expect(screen.getByRole('tab', { name: /Tasks/ }).getAttribute('aria-selected')).toBe('true');
    expect(screen.getByRole('tabpanel').textContent).toBe('The tasks');
    await user.keyboard('{ArrowLeft}{ArrowLeft}');
    expect(screen.getByRole('tab', { name: 'Logs' }).getAttribute('aria-selected')).toBe('true');
    await user.keyboard('{Home}');
    expect(screen.getByRole('tab', { name: 'Overview' }).getAttribute('aria-selected')).toBe('true');
  });
});

describe('Segments and ChipFilter', () => {
  it('arrows move between segments and Space presses one', async () => {
    const user = userEvent.setup();
    const changed: string[] = [];
    render(
      <Segments
        label="Filter tasks"
        value="all"
        options={[
          { value: 'all', label: 'All' },
          { value: 'errands', label: 'Errands' },
          { value: 'grid', label: 'Grid view', icon: 'grid' },
        ]}
        onChange={(v) => changed.push(v)}
      />,
    );
    const group = screen.getByRole('group', { name: 'Filter tasks' });
    const all = within(group).getByRole('button', { name: 'All' });
    expect(all.getAttribute('aria-pressed')).toBe('true');
    expect(within(group).getByRole('button', { name: 'Grid view' }).getAttribute('aria-pressed')).toBe('false');
    await user.click(all);
    expect(changed).toEqual([]);
    await user.keyboard('{ArrowRight}');
    expect(document.activeElement).toBe(within(group).getByRole('button', { name: 'Errands' }));
    await user.keyboard(' ');
    expect(changed).toEqual(['errands']);
  });

  it('pressing the chosen chip clears the filter', async () => {
    const user = userEvent.setup();
    const changed: string[] = [];
    render(
      <ChipFilter
        label="Labels"
        value="bug"
        options={[
          { value: 'bug', count: 2 },
          { value: 'docs', count: 1 },
        ]}
        onChange={(v) => changed.push(v)}
      />,
    );
    const bug = screen.getByRole('button', { name: /bug/ });
    expect(bug.getAttribute('aria-pressed')).toBe('true');
    await user.click(bug);
    await user.click(screen.getByRole('button', { name: /docs/ }));
    expect(changed).toEqual(['', 'docs']);
  });
});

describe('Switch', () => {
  it('Space toggles it, and a press while saving is ignored', async () => {
    const user = userEvent.setup();
    let finish: () => void = () => undefined;
    let saves = 0;
    render(
      <Switch
        on={false}
        label="Presenting"
        onToggle={() => {
          saves++;
          return new Promise<void>((done) => {
            finish = done;
          });
        }}
      />,
    );
    const sw = screen.getByRole('switch', { name: 'Presenting' });
    expect(sw.getAttribute('aria-checked')).toBe('false');
    expect(sw.hasAttribute('aria-busy')).toBe(false);
    sw.focus();
    await user.keyboard(' ');
    expect(saves).toBe(1);
    expect(sw.getAttribute('aria-busy')).toBe('true');
    await user.keyboard(' ');
    expect(saves).toBe(1);
    await act(async () => {
      finish();
      await Promise.resolve();
    });
    expect(sw.hasAttribute('aria-busy')).toBe(false);
    await user.keyboard(' ');
    expect(saves).toBe(2);
  });
});

describe('RadioCards', () => {
  it('arrow keys check the next card and the card shows it', async () => {
    const user = userEvent.setup();
    function Files() {
      const [v, setV] = useState<'keep' | 'delete'>('keep');
      return (
        <RadioCards
          label="What happens to its files"
          value={v}
          options={[
            { value: 'keep', title: 'Keep' },
            { value: 'delete', title: 'Delete', danger: true },
          ]}
          onChange={setV}
        />
      );
    }
    render(<Files />);
    const group = screen.getByRole('radiogroup', { name: 'What happens to its files' });
    const keep = within(group).getByRole('radio', { name: 'Keep' });
    expect(keep.getAttribute('aria-checked')).toBe('true');
    keep.focus();
    await user.keyboard('{ArrowDown}');
    const del = within(group).getByRole('radio', { name: 'Delete' });
    expect(del.getAttribute('aria-checked')).toBe('true');
    expect(document.activeElement).toBe(del);
    expect(del.closest('label')?.querySelector('[data-checked]')).toBe(del);
  });
});

describe('Disclosure and InfoTip', () => {
  it('a disclosure opens with Enter', async () => {
    const user = userEvent.setup();
    render(<Disclosure label="Paste a .env file">The form</Disclosure>);
    const trigger = screen.getByRole('button', { name: /Paste a .env file/ });
    expect(trigger.getAttribute('aria-expanded')).toBe('false');
    expect(screen.queryByText('The form')).toBeNull();
    trigger.focus();
    await user.keyboard('{Enter}');
    expect(trigger.getAttribute('aria-expanded')).toBe('true');
    expect(screen.getByText('The form')).toBeTruthy();
  });

  it('an info tip opens, is named, and Escape returns focus to it', async () => {
    const user = userEvent.setup();
    render(<InfoTip label="About owner.txt">How to get or replace it: ask.</InfoTip>);
    const trigger = screen.getByRole('button', { name: 'About owner.txt' });
    await user.click(trigger);
    await settle();
    expect(screen.getByRole('dialog', { name: 'About owner.txt' }).textContent).toContain('How to get or replace it');
    await user.keyboard('{Escape}');
    await settle();
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(document.activeElement).toBe(trigger);
  });
});

describe('Select', () => {
  function Mode({ onPick }: { onPick: (v: string) => void }) {
    const [v, setV] = useState('auto');
    return (
      <Select
        label="Review mode"
        value={v}
        options={[
          { value: 'auto', label: 'Automatic', help: 'Reviews each new pull request' },
          { value: 'ask', label: 'On request' },
          { value: 'off', label: 'Off' },
        ]}
        onChange={(next) => {
          setV(next);
          onPick(next);
        }}
      />
    );
  }

  it('shows the choice, opens, arrows move, Enter picks and Escape closes', async () => {
    const user = userEvent.setup();
    const picked: string[] = [];
    render(<Mode onPick={(v) => picked.push(v)} />);
    const trigger = screen.getByRole('combobox', { name: 'Review mode' });
    expect(trigger.textContent).toBe('Automatic');
    trigger.focus();
    await user.keyboard('{ArrowDown}');
    await settle();
    const list = screen.getByRole('listbox');
    expect(within(list).getAllByRole('option')).toHaveLength(3);
    expect(
      within(list)
        .getByRole('option', { name: /Automatic/ })
        .getAttribute('aria-selected'),
    ).toBe('true');
    expect(within(list).getByText('Reviews each new pull request')).toBeTruthy();
    await user.keyboard('{ArrowDown}{Enter}');
    await settle();
    expect(picked).toEqual(['ask']);
    expect(screen.queryByRole('listbox')).toBeNull();
    expect(trigger.textContent).toBe('On request');
    expect(document.activeElement).toBe(trigger);
    await user.keyboard('{ArrowDown}');
    await settle();
    await user.keyboard('{ArrowDown}{Escape}');
    await settle();
    expect(screen.queryByRole('listbox')).toBeNull();
    expect(picked).toEqual(['ask']);
    expect(trigger.textContent).toBe('On request');
    await settle();
  });
});

describe('CommandPalette', () => {
  const entries: CommandEntry[] = [
    { id: 'go-helper', group: 'Go to', label: 'Helper', icon: null },
    { id: 'go-services', group: 'Go to', label: 'Services', icon: null },
    { id: 'theme', group: 'Actions', label: 'Switch to dark theme', icon: null },
  ];
  const rank = (list: CommandEntry[], q: string) =>
    q ? list.filter((e) => e.label.toLowerCase().includes(q.toLowerCase())).reverse() : list;

  it('groups at first, lists the ranked hits as you type, and Enter runs the best', async () => {
    const user = userEvent.setup();
    const ran: string[] = [];
    render(
      <CommandPalette
        open
        onOpenChange={() => undefined}
        label="Search"
        placeholder="Search pages"
        entries={entries}
        rank={rank}
        onRun={(e) => ran.push(e.id)}
      />,
    );
    await settle();
    const dialog = screen.getByRole('dialog', { name: 'Search' });
    expect(
      within(dialog)
        .getAllByRole('group')
        .map((g) => g.firstChild?.textContent),
    ).toEqual(['Go to', 'Actions']);
    const input = within(dialog).getByRole('combobox', { name: 'Search' });
    expect(document.activeElement).toBe(input);
    await user.keyboard('e');
    // the caller's ranking decides the order: this one puts later entries first
    expect(
      within(dialog)
        .getAllByRole('option')
        .map((o) => o.textContent),
    ).toEqual(['Switch to dark theme', 'Services', 'Helper']);
    await user.keyboard('lp');
    expect(
      within(dialog)
        .getAllByRole('option')
        .map((o) => o.textContent),
    ).toEqual(['Helper']);
    await user.keyboard('{Enter}');
    expect(ran).toEqual(['go-helper']);
  });

  it('says what found nothing', async () => {
    const user = userEvent.setup();
    render(
      <CommandPalette
        open
        onOpenChange={() => undefined}
        label="Search"
        placeholder="Search pages"
        entries={entries}
        rank={rank}
        onRun={() => undefined}
      />,
    );
    await settle();
    await user.keyboard('zzz');
    expect(screen.queryAllByRole('option')).toHaveLength(0);
    expect(screen.getByText('Nothing matches “zzz”.')).toBeTruthy();
  });
});

describe('Pager and Meter', () => {
  it('steps pages from its own state and marks the ends', async () => {
    const user = userEvent.setup();
    function Pages() {
      const [p, setP] = useState(0);
      return <Pager page={p} pages={2} setPage={setP} />;
    }
    render(<Pages />);
    const nav = screen.getByRole('navigation', { name: 'Pages' });
    expect(within(nav).getByText('1 / 2')).toBeTruthy();
    const older = within(nav).getByRole('button', { name: 'Older' });
    expect(older.hasAttribute('aria-disabled')).toBe(false);
    await user.click(older);
    expect(within(nav).getByText('2 / 2')).toBeTruthy();
    expect(older.getAttribute('aria-disabled')).toBe('true');
    expect(within(nav).getByRole('button', { name: 'Newer' }).hasAttribute('aria-disabled')).toBe(false);
  });

  it('a meter reads its value as a percent', () => {
    render(<Meter pct={91.26} label="Disk used" />);
    const meter = screen.getByRole('meter', { name: 'Disk used' });
    expect(meter.getAttribute('aria-valuenow')).toBe('91.3');
    expect(meter.getAttribute('aria-valuetext')).toMatch(/^91(\.3)?%$/);
  });
});

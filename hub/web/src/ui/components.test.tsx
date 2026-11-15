import { act, fireEvent, render, screen } from '@testing-library/react';
import { useState } from 'react';
import { Button } from './Button';
import { RadioCards, Segments } from './controls';
import { Feed } from './Feed';
import { Field, SearchInput, TextArea, TextInput } from './inputs';
import { Pager } from './Pager';
import { Meter } from './status';

const noop = () => undefined;

describe('Feed', () => {
  it('shows each event with who received it', () => {
    render(
      <Feed
        events={[{ at: Date.now() / 1000 - 30, kind: 'sent', title: 'Message to Heba', to: 'Heba', detail: 'Your login' }]}
      />,
    );
    const to = screen.getByText('Heba');
    expect(to.tagName).toBe('B');
    expect(to.parentElement?.textContent).toBe('Message to Heba → Heba');
    expect(screen.getByText('just now')).toBeTruthy();
  });

  it('says so when there is nothing yet', () => {
    render(<Feed events={[]} empty="No pushes yet." />);
    expect(screen.getByText('No pushes yet.')).toBeTruthy();
  });
});

describe('Segments', () => {
  it('marks the current choice and reports a change', () => {
    const changed: string[] = [];
    render(
      <Segments
        label="Filter"
        value="all"
        options={[
          { value: 'all', label: 'All' },
          { value: 'done', label: 'Done' },
        ]}
        onChange={(v) => changed.push(v)}
      />,
    );
    expect(screen.getByText('All').getAttribute('aria-pressed')).toBe('true');
    fireEvent.click(screen.getByText('Done'));
    expect(changed).toEqual(['done']);
  });
});

describe('Button', () => {
  it('names an icon-only button by its label', () => {
    render(<Button label="Refresh" icon="refresh" iconOnly />);
    expect(screen.getByRole('button', { name: 'Refresh' })).toBeTruthy();
  });

  it('stays pending while its action runs', async () => {
    let finish: () => void = noop;
    let runs = 0;
    render(
      <Button
        label="Save"
        onClick={() => {
          runs++;
          return new Promise<void>((done) => {
            finish = done;
          });
        }}
      />,
    );
    const button = screen.getByRole('button', { name: 'Save' });
    fireEvent.click(button);
    fireEvent.click(button);
    expect(runs).toBe(1);
    expect(button.getAttribute('aria-busy')).toBe('true');
    await act(async () => {
      finish();
      await Promise.resolve();
    });
    expect(button.getAttribute('aria-busy')).toBeNull();
  });

  it('a busy button ignores presses', () => {
    let runs = 0;
    render(<Button label="Send" busy onClick={() => runs++} />);
    fireEvent.click(screen.getByRole('button', { name: 'Send' }));
    expect(runs).toBe(0);
  });
});

describe('inputs', () => {
  it('a field names its text field', async () => {
    // the field links its label once the control mounts
    await act(async () => {
      render(
        <Field label="Name">
          <TextInput value="" onChange={noop} />
        </Field>,
      );
      await Promise.resolve();
    });
    expect(screen.getByRole('textbox', { name: 'Name' })).toBeTruthy();
  });

  it('a read-only text area stays read-only', () => {
    render(<TextArea value="secret" readOnly />);
    expect(screen.getByRole('textbox').hasAttribute('readonly')).toBe(true);
  });

  it('search reports typing and clears on Escape', () => {
    function Search() {
      const [q, setQ] = useState('');
      return <SearchInput label="Search secrets" value={q} onChange={setQ} />;
    }
    render(<Search />);
    const box = screen.getByRole<HTMLInputElement>('searchbox', { name: 'Search secrets' });
    fireEvent.input(box, { target: { value: 'scout' } });
    expect(box.value).toBe('scout');
    fireEvent.keyDown(box, { key: 'Escape' });
    expect(box.value).toBe('');
  });
});

describe('Pager', () => {
  it('steps between pages and shows where it is', () => {
    const pages: number[] = [];
    render(<Pager page={0} pages={3} setPage={(p) => pages.push(p)} />);
    expect(screen.getByText('1 / 3')).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Newer' }).getAttribute('aria-disabled')).toBe('true');
    fireEvent.click(screen.getByRole('button', { name: 'Older' }));
    expect(pages).toEqual([1]);
  });
});

describe('Meter', () => {
  it('reports its reading', () => {
    render(<Meter pct={42} label="Disk used" />);
    expect(screen.getByRole('meter', { name: 'Disk used' }).getAttribute('aria-valuenow')).toBe('42');
  });
});

describe('RadioCards', () => {
  it('picks a card', () => {
    const picked: string[] = [];
    render(
      <RadioCards
        label="Files"
        value="keep"
        options={[
          { value: 'keep', title: 'Keep' },
          { value: 'delete', title: 'Delete', danger: true },
        ]}
        onChange={(v) => picked.push(v)}
      />,
    );
    expect(screen.getByRole('radio', { name: 'Keep' }).getAttribute('aria-checked')).toBe('true');
    fireEvent.click(screen.getByRole('radio', { name: 'Delete' }));
    expect(picked).toEqual(['delete']);
  });
});

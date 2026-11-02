import { fireEvent, render, screen } from '@testing-library/react';
import { Segments } from './controls';
import { Feed } from './Feed';

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

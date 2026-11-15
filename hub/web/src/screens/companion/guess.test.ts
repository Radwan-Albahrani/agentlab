import { describe, expect, it } from 'vitest';
import { guessSlack } from './CompanionSettings';

const people = [
  { value: 'U1', label: 'Mishal Alotaibi' },
  { value: 'U2', label: 'Radwan Albahrani' },
  { value: 'U3', label: 'Sara' },
];

describe('guessSlack', () => {
  it('matches a GitHub login to the Slack person with the same name', () => {
    expect(guessSlack('Radwan-Albahrani', people)).toBe('U2');
    expect(guessSlack('mishal-dev', people)).toBe('U1');
  });

  it('suggests nobody when nothing is close, rather than guessing wrong', () => {
    expect(guessSlack('mi3lix9', people)).toBe('');
    expect(guessSlack('ab', people)).toBe('');
  });
});

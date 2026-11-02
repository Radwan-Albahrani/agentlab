import { afterEach, describe, expect, it } from 'vitest';
import { hueTheme, setAgentColors } from './hues';

describe('hueTheme', () => {
  afterEach(() => {
    setAgentColors(undefined);
  });

  it('picks the same colour for an id every time, without a chosen one', () => {
    expect(hueTheme('example')).toBe(hueTheme('example'));
    expect(hueTheme(null)).toBeUndefined();
  });

  it('uses the colour chosen in cluster.toml', () => {
    setAgentColors({ alpha: 'green', beta: 'green', gamma: 'red' });
    expect(hueTheme('alpha')).toBe(hueTheme('beta'));
    expect(hueTheme('alpha')).not.toBe(hueTheme('gamma'));
  });

  it('falls back to the picked colour for an unknown name', () => {
    const picked = hueTheme('delta');
    setAgentColors({ delta: 'chartreuse' });
    expect(hueTheme('delta')).toBe(picked);
  });
});

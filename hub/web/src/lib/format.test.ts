import { ago, containerLabel, duration, gb, toneFor, versionLabel } from './format';

describe('format', () => {
  const now = 1_800_000_000;

  it('says how long ago, briefly', () => {
    expect(ago(now - 10, now)).toBe('just now');
    expect(ago(now - 600, now)).toBe('10 min ago');
    expect(ago(now - 7200, now)).toBe('2 h ago');
    expect(ago(0, now)).toBe('');
    expect(ago(now - 3 * 86400, now)).toMatch(/^(Sun|Mon|Tue|Wed|Thu|Fri|Sat) \d\d:\d\d$/);
    expect(ago(now - 30 * 86400, now)).toMatch(/^[A-Z][a-z]{2} \d\d$/);
  });

  it('formats durations and sizes', () => {
    expect(duration(42)).toBe('42 s');
    expect(duration(600)).toBe('10 min');
    expect(duration(3 * 3600 + 5 * 60)).toBe('3 h 05 m');
    expect(gb(2 ** 30 * 1.5)).toBe('1.5 GB');
    expect(gb(null)).toBe('0.0 GB');
  });

  it('picks a tone by fill level', () => {
    expect(toneFor(50)).toBe('ok');
    expect(toneFor(80)).toBe('warn');
    expect(toneFor(95)).toBe('bad');
  });

  it('cleans labels', () => {
    expect(versionLabel('20261028-144742')).toBe('2026-10-28 14:47');
    expect(containerLabel('scout-abcdefghij0123456789klmn')).toBe('scout');
    expect(containerLabel('coolify-db')).toBe('coolify-db');
  });
});

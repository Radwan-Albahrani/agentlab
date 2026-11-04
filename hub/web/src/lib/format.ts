const pad = (n: number) => String(n).padStart(2, '0');
const DAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

export function ago(t: number | null | undefined, now = Date.now() / 1000): string {
  if (!t) return '';
  const d = now - t;
  if (d < 45) return 'just now';
  if (d < 3600) return `${Math.round(d / 60)} min ago`;
  if (d < 86400) return `${Math.round(d / 3600)} h ago`;
  const date = new Date(t * 1000);
  if (d < 7 * 86400) return `${DAYS[date.getDay()]} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
  return `${MONTHS[date.getMonth()]} ${pad(date.getDate())}`;
}

export function exact(t: number): string {
  const d = new Date(t * 1000);
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export function duration(sec: number): string {
  const s = Math.max(0, Math.floor(sec));
  if (s < 60) return `${s} s`;
  if (s < 3600) return `${Math.floor(s / 60)} min`;
  return `${Math.floor(s / 3600)} h ${pad(Math.floor((s % 3600) / 60))} m`;
}

export const gb = (bytes: number | null | undefined, digits = 1) => `${((bytes || 0) / 2 ** 30).toFixed(digits)} GB`;

export const pct = (part: number, whole: number) => (whole ? (100 * part) / whole : 0);

export const toneFor = (p: number) => (p >= 90 ? 'bad' : p >= 75 ? 'warn' : 'ok');

export const plural = (n: number, one: string, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;

export const capitalize = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);

/** 20261028-144742 -> 2026-10-28 14:47 */
export const versionLabel = (v: string) => v.replace(/^(\d{4})(\d\d)(\d\d)-(\d\d)(\d\d)\d\d$/, '$1-$2-$3 $4:$5');

/** Strips the stack uuid Coolify appends to container names. */
export const containerLabel = (name: string) => name.replace(/-[a-z0-9]{24}$/, '');

/** "Thu 2:00 PM" */
export const clock = (t: number) =>
  new Date(t * 1000).toLocaleString('en-US', { weekday: 'short', hour: 'numeric', minute: '2-digit', hour12: true });

/** Epoch seconds <-> a datetime-local input's value. */
export const toLocalInput = (t: number) => {
  const d = new Date(t * 1000);
  return new Date(d.getTime() - d.getTimezoneOffset() * 60_000).toISOString().slice(0, 16);
};
export const fromLocalInput = (v: string) => new Date(v).getTime() / 1000;

import { useSyncExternalStore } from 'react';

/** Dark or light. Until the user picks one the page follows the system; every colour token follows it through light-dark(). */
export type Scheme = 'dark' | 'light';

const KEY = 'hub-theme';
const systemDark = window.matchMedia('(prefers-color-scheme: dark)');
const listeners = new Set<() => void>();
let chosen = stored();

function stored(): Scheme | null {
  try {
    const v = localStorage.getItem(KEY);
    return v === 'dark' || v === 'light' ? v : null;
  } catch {
    return null; // storage blocked (private window): just follow the system
  }
}

export function applyScheme() {
  document.documentElement.style.colorScheme = chosen ?? 'light dark';
}

const shown = (): Scheme => chosen ?? (systemDark.matches ? 'dark' : 'light');

function subscribe(listener: () => void) {
  listeners.add(listener);
  systemDark.addEventListener('change', listener);
  return () => {
    listeners.delete(listener);
    systemDark.removeEventListener('change', listener);
  };
}

/** Switches to the opposite of what is shown now and remembers it. */
function toggle() {
  chosen = shown() === 'dark' ? 'light' : 'dark';
  applyScheme();
  try {
    localStorage.setItem(KEY, chosen);
  } catch {
    /* not remembered; still applied for this visit */
  }
  listeners.forEach((l) => {
    l();
  });
}

export function useScheme(): [Scheme, () => void] {
  return [useSyncExternalStore(subscribe, shown), toggle];
}

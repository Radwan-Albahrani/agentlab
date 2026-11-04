import { useSyncExternalStore } from 'react';

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
    return null;
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

function toggle() {
  chosen = shown() === 'dark' ? 'light' : 'dark';
  applyScheme();
  try {
    localStorage.setItem(KEY, chosen);
  } catch {
    /* storage blocked */
  }
  listeners.forEach((l) => {
    l();
  });
}

export function useScheme(): [Scheme, () => void] {
  return [useSyncExternalStore(subscribe, shown), toggle];
}

import * as stylex from '@stylexjs/stylex';
import { agent } from './tokens.stylex';

// StyleX needs each theme as its own top-level constant.
const green = stylex.createTheme(agent, { hue: '#10b981' });
const pink = stylex.createTheme(agent, { hue: '#f0628f' });
const violet = stylex.createTheme(agent, { hue: '#8b5cf6' });
const amber = stylex.createTheme(agent, { hue: '#f59e0b' });
const sky = stylex.createTheme(agent, { hue: '#0ea5e9' });
const red = stylex.createTheme(agent, { hue: '#ef4444' });
const teal = stylex.createTheme(agent, { hue: '#14b8a6' });
const indigo = stylex.createTheme(agent, { hue: '#6366f1' });
const named = { green, pink, violet, amber, sky, red, teal, indigo };
const themes = Object.values(named);
let chosen: Record<string, string> = {};

export const setAgentColors = (colors: Record<string, string> | undefined) => {
  chosen = colors ?? {};
};

const pick = (id: string) => {
  let h = 0;
  for (const ch of id) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  return themes[h % themes.length];
};

/** Spread into stylex.props(...) to give an element and its children an agent's colour. */
export const hueTheme = (profile: string | null | undefined) => {
  if (!profile) return undefined;
  const name = chosen[profile];
  return (name && (named as Partial<Record<string, typeof green>>)[name]) || pick(profile);
};

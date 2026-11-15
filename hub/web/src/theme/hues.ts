import * as stylex from '@stylexjs/stylex';
import { agent } from './tokens.stylex';

// StyleX needs each theme as its own top-level constant.
// Muted, equally light (about oklch 0.6): agents tell apart without competing with the status colours.
const green = stylex.createTheme(agent, { hue: '#3f9b6a' });
const pink = stylex.createTheme(agent, { hue: '#c2577f' });
const violet = stylex.createTheme(agent, { hue: '#8566c7' });
const amber = stylex.createTheme(agent, { hue: '#b37e2a' });
const sky = stylex.createTheme(agent, { hue: '#3f84b8' });
const red = stylex.createTheme(agent, { hue: '#c25548' });
const teal = stylex.createTheme(agent, { hue: '#2f958f' });
const indigo = stylex.createTheme(agent, { hue: '#5d6fc9' });
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

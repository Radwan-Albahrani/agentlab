import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import stylex from '@stylexjs/unplugin';
import type { PluginOption } from 'vite';

// Vitest needs the Rollup variant: the Vite one starts a CSS timer that keeps Vitest from exiting.
const stylexPlugin = (process.env.VITEST ? stylex.rollup() : stylex.vite()) as PluginOption;
const TARGETS = ['chrome123', 'edge123', 'firefox120', 'safari17.5', 'ios17.5'];

export default defineConfig({
  plugins: [stylexPlugin, react()],
  // Vite's default target rewrites light-dark() into a fallback that ignores the theme toggle.
  build: { outDir: 'dist', sourcemap: false, target: TARGETS, cssTarget: TARGETS },
  server: { proxy: { '/api': process.env.HUB_URL ?? 'http://127.0.0.1:7189' } },
  test: { environment: 'jsdom', globals: true, include: ['src/**/*.test.{ts,tsx}'] },
});

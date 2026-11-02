import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import stylex from '@stylexjs/unplugin';

// Under Vitest use StyleX's Rollup variant: the Vite one starts a dev-server CSS timer that keeps Vitest from exiting.
const stylexPlugin = process.env.VITEST ? stylex.rollup() : stylex.vite();
const TARGETS = ['chrome123', 'edge123', 'firefox120', 'safari17.5', 'ios17.5'];

export default defineConfig({
  plugins: [stylexPlugin, react()],
  // The browsers in package.json's browserslist. Vite's older default target makes its CSS minifier rewrite
  // light-dark() into a prefers-color-scheme fallback, which ignores the theme toggle's color-scheme.
  build: { outDir: 'dist', sourcemap: false, target: TARGETS, cssTarget: TARGETS },
  server: { proxy: { '/api': process.env.HUB_URL ?? 'http://127.0.0.1:7189' } }, // the throwaway hub (test.sh instance)
  test: { environment: 'jsdom', globals: true, include: ['src/**/*.test.{ts,tsx}'] },
});

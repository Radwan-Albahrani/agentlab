import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import stylex from '@stylexjs/unplugin';

// Under Vitest use StyleX's Rollup variant: the Vite one starts a dev-server CSS timer that keeps Vitest from exiting.
const stylexPlugin = process.env.VITEST ? stylex.rollup() : stylex.vite();

export default defineConfig({
  plugins: [stylexPlugin, react()],
  build: { outDir: 'dist', sourcemap: false },
  server: { proxy: { '/api': process.env.HUB_URL ?? 'http://127.0.0.1:7189' } }, // the throwaway hub (test.sh instance)
  test: { environment: 'jsdom', globals: true, include: ['src/**/*.test.{ts,tsx}'] },
});

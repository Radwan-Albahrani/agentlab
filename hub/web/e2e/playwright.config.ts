import { defineConfig } from '@playwright/test';

const desktop = { viewport: { width: 1400, height: 1000 } };
const phone = { viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true };

export default defineConfig({
  testDir: '.',
  timeout: 60_000,
  workers: 1,
  reporter: [['list']],
  outputDir: '/tmp/test-results',
  use: { baseURL: process.env.BASE_URL || 'http://127.0.0.1:7189', screenshot: 'off' },
  projects: [
    { name: 'dark', use: { ...desktop, colorScheme: 'dark' }, grepInvert: /@phone/ },
    { name: 'light', use: { ...desktop, colorScheme: 'light' }, grepInvert: /@phone/ },
    { name: 'phone-dark', use: { ...phone, colorScheme: 'dark' }, grep: /@phone/ },
    { name: 'phone-light', use: { ...phone, colorScheme: 'light' }, grep: /@phone/ },
  ],
});

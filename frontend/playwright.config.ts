import { defineConfig } from '@playwright/test';
import path from 'node:path';

const root = path.resolve(import.meta.dirname, '..');
const python = path.join(root, '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 40_000,
  reporter: [['list'], ['json', { outputFile: 'test-results/results.json' }]],
  use: { baseURL: 'http://127.0.0.1:8765', channel: 'chrome', viewport: { width: 1440, height: 1050 }, screenshot: 'only-on-failure', trace: 'retain-on-failure' },
  webServer: { command: `"${python}" -X utf8 scripts/e2e_server.py`, cwd: root, url: 'http://127.0.0.1:8765/api/health', reuseExistingServer: false, timeout: 40_000 },
});


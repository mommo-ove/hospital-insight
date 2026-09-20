import { expect, test } from '@playwright/test';
import path from 'node:path';

test('home shows real data coverage and a usable desktop layout', async ({ page }, info) => {
  const errors: string[] = [];
  page.on('pageerror', e => errors.push(e.message));
  await page.goto('/');
  await expect(page.getByRole('heading', { name: /让每一次提问/ })).toBeVisible();
  await expect(page.locator('.dataset-strip')).toContainText('224');
  await expect(page.locator('.dataset-strip')).toContainText('2026-04');
  await expect(page.getByText('离线演示模式', { exact: true })).toBeVisible();
  await page.screenshot({ path: info.outputPath('home-desktop.png'), fullPage: true });
  expect(errors).toEqual([]);
});

test('query, source drawer, follow-up, and history restore', async ({ page }) => {
  await page.goto('/');
  await page.locator('.example-card').filter({ hasText: '心内科一年的收入是多少' }).click();
  await expect(page.locator('.value-card')).toContainText('25,979,271');
  await page.getByRole('button', { name: '查看依据' }).click();
  await expect(page.locator('.ant-drawer-body')).toContainText('院管数据.xlsx');
  await page.getByRole('tab', { name: 'SQL 与参数' }).click();
  await expect(page.locator('.sql-section').first()).toContainText('SELECT');
  await expect(page.locator('.sql-section').first()).toContainText('2025-01');
  await page.locator('.ant-drawer-close').click();
  const input = page.getByRole('textbox', { name: '输入你的数据问题' });
  await input.fill('那儿科呢？');
  await input.press('Enter');
  await expect(page.locator('.answer-card')).toHaveCount(2);
  await expect(page.locator('.answer-card').last().locator('.query-tags')).toContainText('儿科');
  await expect(page.locator('.answer-card').last().locator('.query-tags')).toContainText('2025-01');
  await page.reload();
  await page.locator('.history-list button').first().click();
  await expect(page.locator('.answer-card')).toHaveCount(2);
});

test('ranking chart, table, and downloadable CSV', async ({ page }, info) => {
  await page.goto('/');
  await page.locator('.example-card').filter({ hasText: '哪个科室的收入最高' }).click();
  await expect(page.locator('.query-chart canvas')).toBeVisible();
  await expect(page.locator('.answer-text')).toContainText('神经内科');
  await page.screenshot({ path: info.outputPath('ranking-desktop.png'), fullPage: true });
  await page.getByRole('tab', { name: '结果表 · 8' }).click();
  await expect(page.locator('.ant-table-tbody')).toContainText('2,141,617');
  const downloadPromise = page.waitForEvent('download');
  await page.getByRole('link', { name: '导出 CSV' }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toMatch(/^hospital-query-.*\.csv$/);
});

test('ambiguity is clarified and unsupported question gets no invented numbers', async ({ page }) => {
  await page.goto('/');
  const input = page.getByRole('textbox', { name: '输入你的数据问题' });
  await input.fill('2025年心内科花费多少钱？');
  await input.press('Enter');
  await expect(page.locator('.answer-card').last()).toContainText('需要补充信息');
  await page.getByRole('button', { name: '合计收入', exact: true }).click();
  await expect(page.locator('.value-card')).toContainText('25,979,271');
  await input.fill('做一次CT多少钱？');
  await input.press('Enter');
  await expect(page.locator('.answer-card').last()).toContainText('超出数据范围');
  await expect(page.locator('.answer-card').last().locator('.value-card')).toHaveCount(0);
});

test('upload preview and commit are separate; duplicate upload preserves data', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('button', { name: '数据管理', exact: true }).click();
  await page.locator('input[type=file]').setInputFiles(path.resolve(import.meta.dirname, '../../院管数据.xlsx'));
  await expect(page.getByTestId('import-preview')).toContainText('重复 224');
  await expect(page.getByTestId('import-preview')).toContainText('新增 0');
  await expect(page.getByRole('button', { name: '确认导入' })).toBeEnabled();
  await page.getByRole('button', { name: '确认导入' }).click();
  await expect(page.getByTestId('import-preview')).toHaveCount(0);
  await expect(page.locator('.overview-grid')).toContainText('224');
  await expect(page.locator('.overview-grid')).toContainText('v1');
});

test('catalog and mobile layout stay usable', async ({ page }, info) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/');
  await expect(page.locator('.dataset-strip')).toContainText('224');
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
  await page.screenshot({ path: info.outputPath('home-mobile.png'), fullPage: true });
  await page.getByRole('button', { name: '指标说明', exact: true }).click();
  await expect(page.getByRole('heading', { name: '先理解指标，再读懂数字' })).toBeVisible();
  await page.getByRole('searchbox', { name: '搜索指标' }).fill('次均费用');
  await expect(page.locator('.ant-table-tbody')).toContainText('不等同于患者平均住院账单');
});

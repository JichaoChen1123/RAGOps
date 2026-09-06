import { chromium } from 'playwright-core';
import { existsSync } from 'node:fs';
import { mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import assert from 'node:assert/strict';

const repo = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const mode = process.argv[2] ?? 'mock';
const url = process.env.RAGOPS_FRONTEND_URL ?? (mode === 'api' ? 'http://127.0.0.1:15174' : 'http://127.0.0.1:15173');
const output = path.join(repo, 'docs/qa/screenshots/neumorphism');
const executablePath = [process.env.RAGOPS_BROWSER_EXECUTABLE, 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe', 'C:/Program Files/Google/Chrome/Application/chrome.exe'].find((candidate) => candidate && existsSync(candidate));
assert(executablePath, 'Set RAGOPS_BROWSER_EXECUTABLE to an installed Chromium browser.');
await mkdir(output, { recursive: true });
const browser = await chromium.launch({ executablePath, headless: true });
const results = { mode, viewports: [], interactions: [], consoleErrors: [], externalRequests: [], contrast: [] };
const context = await browser.newContext({ reducedMotion: 'reduce' });
await context.route('**/*', async (route) => {
  const requested = new URL(route.request().url());
  if (['http:', 'https:'].includes(requested.protocol) && !['127.0.0.1', 'localhost', '[::1]'].includes(requested.hostname)) {
    results.externalRequests.push(`${requested.origin}${requested.pathname}`);
    await route.abort();
  } else await route.continue();
});
const page = await context.newPage();
page.on('pageerror', (error) => results.consoleErrors.push(error.message));
page.on('console', (message) => { if (message.type() === 'error') results.consoleErrors.push(message.text()); });
page.setDefaultTimeout(15000);
const visit = async (route) => {
  await page.goto(`${url}${route}`);
  await page.locator('.content').waitFor();
  await page.locator('.loading-mark').waitFor({ state: 'hidden' });
};
async function capture(name) {
  const layout = await page.evaluate(() => ({
    width: innerWidth, height: innerHeight, clientWidth: document.documentElement.clientWidth,
    scrollWidth: document.documentElement.scrollWidth, textLength: document.body.innerText.length,
    surface: getComputedStyle(document.documentElement).backgroundColor,
  }));
  assert(layout.scrollWidth <= layout.clientWidth + 1, `${name} horizontal overflow: ${JSON.stringify(layout)}`);
  assert(layout.textLength > 20, `${name} blank page`);
  results.viewports.push({ name, ...layout });
  await page.screenshot({ path: path.join(output, `${mode}-${name}.png`), fullPage: true });
}
async function clickNav(name) {
  if (await page.getByRole('button', { name: '打开主导航' }).isVisible()) await page.getByRole('button', { name: '打开主导航' }).click();
  await page.getByRole('navigation', { name: '主导航' }).getByRole('link', { name, exact: true }).click();
  await page.locator('.loading-mark').waitFor({ state: 'hidden' });
}
try {
  if (mode === 'mock' || mode === 'capture') {
    for (const width of [1440, 820, 390]) {
      await page.setViewportSize({ width, height: 900 });
      for (const [name, route] of [
        ['overview', 'overview'], ['datasets', 'datasets'], ['evaluations', 'evaluations'],
        ['report', 'evaluations/eval-20260826/report'], ['diagnosis', 'evaluations/eval-20260826/samples/sample-042'],
      ]) {
        await visit(`/projects/demo/${route}`);
        await capture(`${name}-${width}`);
      }
      await page.goto(`${url}/not-found`);
      await page.getByRole('heading', { name: '页面不存在' }).waitFor();
      await capture(`not-found-${width}`);
    }
    if (mode === 'capture') process.exitCode = 0;
    else {
      for (const width of [1440, 390]) {
        await page.setViewportSize({ width, height: 900 });
        await visit('/projects/demo/overview');
        const stack = page.getByRole('region', { name: '最近运行卡片' });
        assert.equal(await stack.locator('.stack-sheet').count(), 3);
        await stack.focus();
        await page.keyboard.press('ArrowRight');
        assert.match(await stack.locator('.stack-count').innerText(), /2 \/ 3/);
        await page.keyboard.press('End');
        assert.match(await stack.locator('.stack-count').innerText(), /3 \/ 3/);
        await page.getByRole('button', { name: '最近运行卡片：下一项' }).click();
        assert.match(await stack.locator('.stack-count').innerText(), /1 \/ 3/);
        await clickNav('数据集');
        await page.getByRole('button', { name: '新建数据集', exact: true }).click();
        await page.getByRole('textbox', { name: '数据集名称' }).fill(`界面验收 ${width}`);
        await capture(`create-dialog-${width}`);
        await page.getByRole('button', { name: '创建 Mock 数据集' }).click();
        await page.getByRole('row').filter({ hasText: `界面验收 ${width}` }).waitFor();
        await page.getByRole('textbox', { name: '搜索数据集' }).fill(`界面验收 ${width}`);
        await page.getByRole('button', { name: `界面验收 ${width} 更多操作` }).click();
        await page.getByRole('menuitem', { name: '查看详情' }).click();
        await page.getByRole('dialog').waitFor();
        await page.keyboard.press('Escape');
        await page.getByRole('textbox', { name: '搜索数据集' }).fill('');
        await page.getByRole('button', { name: '导入数据', exact: true }).click();
        await page.getByRole('dialog').getByRole('button', { name: '导入示例 JSONL', exact: true }).click();
        await page.getByRole('row').filter({ hasText: '退款政策示例 JSONL' }).waitFor();
        await clickNav('评测任务');
        await page.getByRole('button', { name: '新建评测任务', exact: true }).click();
        await page.getByRole('button', { name: '创建评测任务', exact: true }).click();
        const created = page.getByRole('row').filter({ hasText: '模拟评测' });
        await created.waitFor();
        assert.match(await created.innerText(), /未评估/);
        assert.match(await created.innerText(), /未知/);
        await page.getByRole('textbox', { name: '搜索评测任务' }).fill('客服知识库');
        await page.getByRole('link', { name: '查看报告', exact: false }).click();
        await page.getByRole('region', { name: '样本诊断卡片' }).waitFor();
        await page.getByRole('button', { name: '样本诊断卡片：下一项' }).click();
        assert.equal(await page.locator('.stack-record').getAttribute('aria-label'), 'sample-017');
        await page.getByRole('button', { name: '表格列表', exact: true }).click();
        assert.equal(await page.getByRole('table').count(), 1);
        await capture(`sample-table-${width}`);
        await page.getByRole('button', { name: '卡片浏览', exact: true }).click();
        await page.getByRole('button', { name: '导出报告', exact: true }).click();
        const download = page.waitForEvent('download');
        await page.getByRole('dialog').getByRole('button', { name: /JSON/ }).click();
        assert.match((await download).suggestedFilename(), /report\.json$/);
        await page.getByRole('link', { name: '诊断样本 sample-042' }).click();
        await page.getByRole('button', { name: /确认故障归因/ }).click();
        await page.getByRole('button', { name: /确认故障归因/ }).isDisabled().then((value) => assert(value));
        await page.getByRole('button', { name: /\[2\].*不支持/ }).click();
        await page.getByRole('heading', { name: '订单退款通用规则', exact: true }).waitFor();
        await page.getByRole('button', { name: '打开源文档', exact: true }).click();
        await capture(`source-dialog-${width}`);
        const dialog = page.getByRole('dialog');
        const last = dialog.locator('button').last();
        await last.focus();
        await page.keyboard.press('Tab');
        assert(await dialog.evaluate((el) => el.contains(document.activeElement)), 'Dialog focus escaped');
        await page.keyboard.press('Escape');
        await page.getByRole('dialog').waitFor({ state: 'hidden' });
        results.interactions.push(`Mock ${width}: navigation, stack keyboard/wrap, create/import, search, evaluation, report/table/export, diagnosis/citation/review, dialog focus/Escape`);
      }
      await page.setViewportSize({ width: 390, height: 844 });
      for (const state of ['loading', 'empty', 'error', 'partial']) {
        await page.goto(`${url}/projects/demo/overview?state=${state}`);
        if (state === 'loading') await page.getByText('正在载入项目健康度').waitFor();
        else await page.locator('.loading-mark').waitFor({ state: 'hidden' });
        await capture(`state-${state}-390`);
      }
      await page.setViewportSize({ width: 1440, height: 900 });
      await visit('/projects/demo/overview');
      await page.emulateMedia({ reducedMotion: 'no-preference' });
      const sheet = page.locator('.stack-depth-0');
      const rear = page.locator('.stack-depth-1');
      const baselineShadow = await sheet.evaluate((el) => getComputedStyle(el).boxShadow);
      const baselineRear = await rear.evaluate((el) => getComputedStyle(el).transform);
      await sheet.hover();
      await page.waitForTimeout(350);
      assert.notEqual(await rear.evaluate((el) => getComputedStyle(el).transform), baselineRear, 'Rear cards did not fan out');
      assert.equal(await sheet.evaluate((el) => getComputedStyle(el).boxShadow), baselineShadow, 'Stack hover enlarged shadow');
      await page.locator('.recent-runs').screenshot({ path: path.join(output, 'mock-stack-hover-1440.png') });
      await page.getByRole('button', { name: '查看运行模式状态' }).focus();
      assert.equal(await page.getByRole('button', { name: '查看运行模式状态' }).evaluate((el) => getComputedStyle(el).transform), 'none', 'Button should not translate');
      await page.emulateMedia({ reducedMotion: 'reduce' });
      assert.equal(await sheet.evaluate((el) => getComputedStyle(el).transitionDuration), '0s', 'Reduced motion still transitions');
      assert.equal(await sheet.evaluate((el) => getComputedStyle(el).transform), 'none', 'Reduced motion still lifts front card');
      results.interactions.push('Motion: rear fan-out, fixed shadow, no button transform, reduced motion disables transitions and lift');

      results.contrast = await page.evaluate(() => {
        const root = getComputedStyle(document.documentElement);
        const rgb = (hex) => hex.trim().replace('#', '').match(/../g).map((part) => parseInt(part, 16) / 255);
        const luminance = (hex) => rgb(hex).map((value) => value <= .04045 ? value / 12.92 : ((value + .055) / 1.055) ** 2.4).reduce((sum, value, index) => sum + value * [.2126, .7152, .0722][index], 0);
        return ['--ink', '--muted', '--accent', '--green', '--red', '--amber'].flatMap((token) => ['--surface', '--surface-light'].map((surface) => {
          const a = luminance(root.getPropertyValue(token)); const b = luminance(root.getPropertyValue(surface));
          return { token, surface, ratio: Number(((Math.max(a, b) + .05) / (Math.min(a, b) + .05)).toFixed(2)) };
        }));
      });
      assert(results.contrast.every((entry) => entry.ratio >= 4.5), 'AA text token contrast failure');
    }
  } else if (mode === 'api') {
    await page.setViewportSize({ width: 1440, height: 900 });
    await visit('/projects/demo/datasets');
    await page.getByRole('button', { name: '查看运行模式状态' }).getByText('mock', { exact: true }).waitFor();
    const axes = await page.getByRole('button', { name: '查看运行模式状态' }).innerText();
    assert.match(axes, /API 数据/); assert.match(axes, /mock/); assert.match(axes, /未配置/); assert(!axes.includes('真实已验证'));
    const publishedExample = page.getByRole('row').filter({ hasText: '退款政策示例 JSONL' }).filter({ hasText: '可用' });
    if (await publishedExample.count() === 0) {
      await page.getByRole('button', { name: '导入数据', exact: true }).click();
      await page.getByRole('dialog').getByRole('button', { name: '导入示例 JSONL', exact: true }).click();
      await page.getByRole('dialog').waitFor({ state: 'hidden' });
      await publishedExample.first().waitFor();
    }
    await capture('datasets-1440');
    await clickNav('评测任务');
    await page.getByRole('button', { name: '新建评测任务', exact: true }).click();
    await page.getByRole('button', { name: '创建评测任务', exact: true }).click();
    await page.getByRole('dialog').waitFor({ state: 'hidden' });
    const row = page.getByRole('row').filter({ hasText: '退款政策示例 JSONL' }).first();
    for (let attempt = 0; attempt < 15; attempt += 1) {
      await page.getByRole('button', { name: '刷新任务状态' }).click();
      if (await row.getByRole('link', { name: /查看报告/ }).isVisible()) break;
      await page.waitForTimeout(300);
    }
    await row.getByRole('link', { name: /查看报告/ }).click();
    await page.getByRole('region', { name: '样本诊断卡片' }).waitFor();
    const reportRoute = new URL(page.url()).pathname;
    assert.match(await page.locator('.report-status-strip').innerText(), /执行成功/);
    assert.match(await page.locator('.report-status-strip').innerText(), /未评估/);
    assert.match(await page.locator('.report-status-strip').innerText(), /未知/);
    await capture('report-1440');
    await page.locator('.stack-record').getByRole('link', { name: /诊断样本/ }).click();
    await page.getByRole('region', { name: '本次运行元信息' }).waitFor();
    const diagnosisRoute = new URL(page.url()).pathname;
    assert.match(await page.getByRole('region', { name: '本次运行元信息' }).innerText(), /成本未知/);
    assert.match(await page.locator('.simulation-banner').innerText(), /SIMULATED/);
    await capture('diagnosis-1440');
    await page.setViewportSize({ width: 390, height: 844 });
    for (const [name, route] of [['overview', '/projects/demo/overview'], ['evaluations', '/projects/demo/evaluations'], ['report', reportRoute], ['diagnosis', diagnosisRoute]]) {
      await visit(route); await capture(`${name}-390`);
    }
    results.interactions.push('API: frontend API / backend mock / provider not configured; real localhost dataset import, task, report and diagnosis; quality/token/cost unknown retained; external calls disabled');
  } else throw new Error(`Unknown mode: ${mode}`);
  assert.deepEqual(results.consoleErrors, [], 'Unexpected browser console errors');
  assert.deepEqual(results.externalRequests, [], 'External request attempted');
  results.passed = true;
} catch (error) {
  results.passed = false; results.error = error.stack;
  await page.screenshot({ path: path.join(output, `${mode}-failure.png`), fullPage: true }).catch(() => {});
  process.exitCode = 1;
} finally {
  await writeFile(path.join(output, `${mode}-checks.json`), `${JSON.stringify(results, null, 2)}\n`);
  await browser.close();
  console.log(JSON.stringify(results, null, 2));
}

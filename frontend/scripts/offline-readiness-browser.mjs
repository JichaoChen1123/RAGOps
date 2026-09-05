import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import path from 'node:path';
import { chromium } from 'playwright-core';

const frontendUrl = (process.env.RAGOPS_FRONTEND_URL ?? 'http://127.0.0.1:15173').replace(/\/$/, '');
const phase = process.env.RAGOPS_BROWSER_PHASE ?? process.argv[2] ?? 'create';
const outputDirectory = path.resolve(
  process.env.RAGOPS_BROWSER_OUTPUT_DIR ?? '../docs/qa/screenshots/offline-readiness',
);
const statePath = path.resolve(
  process.env.RAGOPS_BROWSER_STATE ?? path.join(outputDirectory, 'browser-api-evidence.json'),
);
const browserCandidates = [
  process.env.RAGOPS_BROWSER_EXECUTABLE,
  'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
  'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
].filter(Boolean);
const executablePath = browserCandidates.find((candidate) => existsSync(candidate));

function ensure(condition, message) {
  if (!condition) throw new Error(message);
}

async function text(locator) {
  return (await locator.textContent())?.replace(/\s+/g, ' ').trim() ?? '';
}

async function waitForTaskReport(page, datasetName) {
  for (let attempt = 0; attempt < 15; attempt += 1) {
    const row = page.getByRole('row').filter({ hasText: datasetName }).first();
    const reportLink = row.getByRole('link', { name: /查看报告/ });
    if (await reportLink.isVisible().catch(() => false)) return { row, reportLink };
    await page.getByRole('button', { name: /刷新任务状态/ }).click();
    await page.waitForTimeout(300);
  }
  throw new Error('Mock task did not expose a terminal report link within the bounded browser poll.');
}

async function assertRuntimeAxes(page) {
  const axes = await text(page.getByRole('button', { name: '查看运行模式状态' }));
  ensure(axes.includes('API 数据'), `Frontend mode is not API: ${axes}`);
  ensure(axes.includes('mock'), `Backend adapter is not mock: ${axes}`);
  ensure(axes.includes('未配置') || axes.includes('已配置未验证'), `Provider state is dishonest: ${axes}`);
  ensure(!axes.includes('真实已验证'), `Offline browser run must not show a verified provider: ${axes}`);
  return axes;
}

async function createAndInspect(page) {
  const datasetName = '退款政策示例 JSONL';
  await page.goto(`${frontendUrl}/projects/demo/datasets`, { waitUntil: 'networkidle' });
  await page.getByRole('heading', { name: '数据集管理', exact: true, level: 2 }).waitFor();
  const runtimeAxes = await assertRuntimeAxes(page);

  let datasetRow = page.getByRole('row').filter({ hasText: datasetName }).first();
  if (!(await datasetRow.isVisible().catch(() => false))) {
    await page.getByRole('button', { name: '导入数据', exact: true }).click();
    await page.getByRole('button', { name: '导入示例 JSONL', exact: true }).click();
    await page.getByText('示例数据集已通过 API 创建、导入 12 条 2.0 样本并发布').waitFor();
    datasetRow = page.getByRole('row').filter({ hasText: datasetName }).first();
  }
  ensure((await text(datasetRow)).includes('12'), 'Imported sample count is not visible in the dataset row.');
  ensure((await text(datasetRow)).includes('可用'), 'Published dataset is not shown as ready.');
  await page.screenshot({ path: path.join(outputDirectory, 'api-dataset-desktop.png'), fullPage: true });

  await page.getByRole('link', { name: /^评测任务/ }).click();
  await page.getByRole('heading', { name: '评测任务', exact: true, level: 2 }).waitFor();
  await page.getByRole('button', { name: '新建评测任务', exact: true }).click();
  const datasetSelect = page.getByLabel('选择评测数据集');
  const datasetValue = await datasetSelect.locator('option').filter({ hasText: datasetName }).first().getAttribute('value');
  ensure(Boolean(datasetValue), 'Imported dataset is missing from the evaluation selector.');
  await datasetSelect.selectOption(datasetValue);
  await page.getByRole('button', { name: '创建评测任务', exact: true }).click();
  await page.getByText(/已由后端接受；执行器 mock，质量 not_evaluated/).waitFor();

  const { row: taskRow, reportLink } = await waitForTaskReport(page, datasetName);
  const taskText = await text(taskRow);
  ensure(taskText.includes('执行成功'), `Task execution outcome is not successful: ${taskText}`);
  ensure(taskText.includes('未评估'), `Task quality is not unevaluated: ${taskText}`);
  ensure(taskText.includes('未知'), `Task unknown quality score is not visible: ${taskText}`);
  ensure(taskText.includes('SIMULATED'), `Task is not visibly marked simulated: ${taskText}`);
  const taskId = (await text(taskRow.locator('td').first().locator('small').first())).trim();
  ensure(taskId.length > 0, 'Task ID is not visible.');

  await reportLink.click();
  await page.getByLabel('运行与质量状态').waitFor();
  const reportStatus = await text(page.getByLabel('运行与质量状态'));
  ensure(reportStatus.includes('执行成功'), `Report lacks successful execution state: ${reportStatus}`);
  ensure(reportStatus.includes('未评估'), `Report incorrectly evaluates quality: ${reportStatus}`);
  ensure(reportStatus.includes('未知'), `Report lacks unknown score/verdict: ${reportStatus}`);
  ensure(await page.getByText('SIMULATED REPORT', { exact: true }).isVisible(), 'Report lacks SIMULATED marker.');
  await page.screenshot({ path: path.join(outputDirectory, 'api-report-desktop.png'), fullPage: true });

  const diagnosisLink = page.getByRole('link', { name: /诊断样本/ }).first();
  await diagnosisLink.click();
  await page.getByText('SIMULATED RUN', { exact: true }).waitFor();
  const diagnosisUrl = page.url();
  const sampleId = diagnosisUrl.split('/').at(-1);
  ensure(Boolean(sampleId), 'Sample ID is missing from the diagnosis URL.');
  ensure(await page.getByText('按退款金额比例扣回。', { exact: true }).isVisible(), 'Reference answer is not displayed.');
  const generatedAnswer = await text(page.locator('.generated-answer p'));
  ensure(generatedAnswer.startsWith('[mock] '), `Current answer is not a mock run output: ${generatedAnswer}`);
  ensure((await text(page.locator('.document-list'))).includes('给定上下文'), 'Provided context origin is not displayed.');
  ensure(await page.getByText('没有引用记录', { exact: true }).isVisible(), 'Citation empty state is not displayed.');
  const usageRow = page.locator('dt').filter({ hasText: 'Token 用量' }).locator('..');
  ensure((await text(usageRow)).includes('未知'), 'Unknown token usage is not displayed honestly.');
  const diagnosisLabels = await page.locator('.diagnosis-callout h3, .secondary-diagnosis strong').allTextContents();
  const semanticFailures = diagnosisLabels.includes('unclassified')
    ? ['Backend diagnosis rule_id values are rendered as unclassified.']
    : [];

  await page.reload({ waitUntil: 'networkidle' });
  await page.getByText('SIMULATED RUN', { exact: true }).waitFor();
  ensure(await text(page.locator('.generated-answer p')) === generatedAnswer, 'Answer changed after browser refresh.');

  await page.setViewportSize({ width: 390, height: 844 });
  await page.reload({ waitUntil: 'networkidle' });
  await page.getByText('SIMULATED RUN', { exact: true }).waitFor();
  const mobileLayout = await page.evaluate(() => ({
    clientWidth: document.documentElement.clientWidth,
    scrollWidth: document.documentElement.scrollWidth,
    bodyTextLength: document.body.innerText.length,
  }));
  ensure(mobileLayout.bodyTextLength > 500, `Mobile page is unexpectedly empty: ${JSON.stringify(mobileLayout)}`);
  ensure(mobileLayout.scrollWidth <= mobileLayout.clientWidth + 1, `Mobile page overflows horizontally: ${JSON.stringify(mobileLayout)}`);
  await page.screenshot({ path: path.join(outputDirectory, 'api-diagnosis-mobile.png'), fullPage: true });

  return {
    baseline_sha: '10ef6b33c4373ee98f6e82e9a053212e5105252f',
    phase: 'create',
    frontend_url: frontendUrl,
    dataset_name: datasetName,
    task_id: taskId,
    sample_id: sampleId,
    report_url: `${frontendUrl}/projects/demo/evaluations/${taskId}/report`,
    diagnosis_url: diagnosisUrl,
    generated_answer: generatedAnswer,
    runtime_axes: runtimeAxes,
    report_status: reportStatus,
    mobile_layout: mobileLayout,
    diagnosis_labels: diagnosisLabels,
    semantic_failures: semanticFailures,
  };
}

async function recheckAfterRestart(page, previous) {
  await page.goto(previous.report_url, { waitUntil: 'networkidle' });
  const reportStatus = await text(page.getByLabel('运行与质量状态'));
  ensure(reportStatus.includes('执行成功') && reportStatus.includes('未评估'), `Report changed after backend restart: ${reportStatus}`);
  await assertRuntimeAxes(page);
  await page.goto(previous.diagnosis_url, { waitUntil: 'networkidle' });
  await page.getByText('SIMULATED RUN', { exact: true }).waitFor();
  ensure(await text(page.locator('.generated-answer p')) === previous.generated_answer, 'Persisted answer changed after backend restart.');
  ensure(await page.getByText('按退款金额比例扣回。', { exact: true }).isVisible(), 'Reference answer disappeared after restart.');
  await page.screenshot({ path: path.join(outputDirectory, 'api-diagnosis-after-restart.png'), fullPage: true });
  return { ...previous, phase: 'restart_recheck', restart_recheck: 'passed' };
}

async function checkDisconnected(page, previous) {
  await page.goto(previous.report_url, { waitUntil: 'domcontentloaded' });
  const alert = page.getByRole('alert').filter({ hasText: '数据载入失败' });
  await alert.waitFor();
  ensure(await page.getByRole('button', { name: '重新请求' }).isVisible(), 'Disconnected API state has no retry action.');
  ensure(!(await page.getByText('SIMULATED REPORT', { exact: true }).isVisible().catch(() => false)), 'Disconnected API page silently displayed fixture report.');
  await page.screenshot({ path: path.join(outputDirectory, 'api-disconnected-desktop.png'), fullPage: true });
  return {
    ...previous,
    phase: 'disconnected',
    disconnected_state: 'passed_without_mock_fallback',
    console_errors_context: 'expected local API 502 responses after the backend was deliberately stopped',
  };
}

ensure(executablePath, 'No supported local Edge/Chrome executable was found.');
await mkdir(outputDirectory, { recursive: true });
const browser = await chromium.launch({ executablePath, headless: true });
const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, locale: 'zh-CN' });
const page = await context.newPage();
const requests = [];
const failedRequests = [];
const consoleErrors = [];

await context.route('**/*', async (route) => {
  const url = new URL(route.request().url());
  if (url.protocol === 'http:' || url.protocol === 'https:') {
    requests.push(url.href);
    if (!['127.0.0.1', 'localhost'].includes(url.hostname)) {
      failedRequests.push(url.href);
      await route.abort('blockedbyclient');
      return;
    }
  }
  await route.continue();
});
page.on('console', (message) => {
  if (message.type() === 'error') consoleErrors.push(message.text());
});

let evidence;
try {
  const previous = phase === 'create' ? null : JSON.parse(await readFile(statePath, 'utf8'));
  evidence = phase === 'create'
    ? await createAndInspect(page)
    : phase === 'restart_recheck'
      ? await recheckAfterRestart(page, previous)
      : phase === 'disconnected'
        ? await checkDisconnected(page, previous)
        : (() => { throw new Error(`Unsupported RAGOPS_BROWSER_PHASE: ${phase}`); })();
  ensure(failedRequests.length === 0, `Browser attempted external requests: ${failedRequests.join(', ')}`);
  evidence.browser = 'local Chromium channel via playwright-core';
  evidence.browser_executable = path.basename(executablePath);
  evidence.request_count = requests.length;
  evidence.request_hosts = [...new Set(requests.map((url) => new URL(url).host))];
  evidence.external_requests = failedRequests;
  evidence.console_errors = consoleErrors;
  evidence.acceptance_failures = [...(evidence.semantic_failures ?? [])];
  if (phase !== 'disconnected' && consoleErrors.length > 0) {
    evidence.acceptance_failures.push('Browser console emitted errors during the API workflow.');
  }
  evidence.acceptance_status = evidence.acceptance_failures.length === 0 ? 'passed' : 'failed';
  await writeFile(statePath, `${JSON.stringify(evidence, null, 2)}\n`, 'utf8');
  process.stdout.write(`${JSON.stringify(evidence, null, 2)}\n`);
  if (evidence.acceptance_status === 'failed') process.exitCode = 1;
} finally {
  await browser.close();
}

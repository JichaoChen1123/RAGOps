import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright-core';

const scriptDirectory = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(scriptDirectory, '../..');
const frontendUrl = (process.env.RAGOPS_FRONTEND_URL ?? 'http://127.0.0.1:15173').replace(/\/$/, '');
const phase = process.env.RAGOPS_BROWSER_PHASE ?? process.argv[2] ?? 'create';
const baselineSha = execFileSync('git', ['rev-parse', 'HEAD'], { cwd: repoRoot, encoding: 'utf8' }).trim();
const expectedBaselineSha = process.env.RAGOPS_BROWSER_EXPECTED_SHA?.trim();
const scriptVersion = 'wor-68-d01-retest-v1';
const evidencePrefix = process.env.RAGOPS_BROWSER_EVIDENCE_PREFIX ?? 'd01-retest';
const expectedDiagnosisRules = [
  'retrieval.missing_evidence',
  'citation.missing',
  'rerank.no_gain_or_regression',
];
const outputDirectory = path.resolve(
  process.env.RAGOPS_BROWSER_OUTPUT_DIR ?? '../docs/qa/screenshots/offline-readiness',
);
const statePath = path.resolve(
  process.env.RAGOPS_BROWSER_STATE ?? path.join(outputDirectory, `${evidencePrefix}-state.json`),
);
const phaseEvidencePath = path.join(outputDirectory, `${evidencePrefix}-${phase}.json`);
const browserCandidates = [
  process.env.RAGOPS_BROWSER_EXECUTABLE,
  'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
  'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
].filter(Boolean);
const executablePath = browserCandidates.find((candidate) => existsSync(candidate));

function ensure(condition, message) {
  if (!condition) throw new Error(message);
}

ensure(/^[0-9a-f]{40}$/.test(baselineSha), `Unable to resolve a full git HEAD SHA: ${baselineSha}`);
if (expectedBaselineSha) {
  ensure(baselineSha === expectedBaselineSha, `Browser baseline ${baselineSha} does not match expected ${expectedBaselineSha}.`);
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

async function inspectLayout(page) {
  return page.evaluate(() => ({
    viewport: { width: window.innerWidth, height: window.innerHeight },
    clientWidth: document.documentElement.clientWidth,
    scrollWidth: document.documentElement.scrollWidth,
    bodyTextLength: document.body.innerText.length,
  }));
}

function assertLayout(layout, name) {
  ensure(layout.bodyTextLength > 500, `${name} page is unexpectedly empty: ${JSON.stringify(layout)}`);
  ensure(layout.scrollWidth <= layout.clientWidth + 1, `${name} page overflows horizontally: ${JSON.stringify(layout)}`);
}

async function inspectFailureDistribution(page) {
  return page.locator('.failure-chart .failure-row').evaluateAll((rows) => rows.map((row) => ({
    label: row.querySelector('div > span')?.textContent?.trim() ?? '',
    count: Number(row.querySelector('div > strong')?.textContent ?? '0'),
  })));
}

async function readApiSnapshot(page, taskId, sampleId) {
  return page.evaluate(async ({ taskId: currentTaskId, sampleId: currentSampleId }) => {
    const requestJson = async (url) => {
      const response = await fetch(url);
      if (!response.ok) throw new Error(`API evidence request failed: ${response.status} ${url}`);
      return response.json();
    };
    const [task, report, samples] = await Promise.all([
      requestJson(`/api/v1/evaluation-jobs/${currentTaskId}`),
      requestJson(`/api/v1/evaluation-jobs/${currentTaskId}/report`),
      requestJson(`/api/v1/evaluation-jobs/${currentTaskId}/samples`),
    ]);
    const items = Array.isArray(samples.items) ? samples.items : [];
    const sample = items.find((item) => item.id === currentSampleId || item.sample_id === currentSampleId);
    if (!sample) throw new Error(`API sample ${currentSampleId} is missing after reading current backend state.`);
    const primaryRuleCounts = {};
    for (const item of items) {
      const primaryRule = item.diagnoses?.[0]?.rule_id;
      if (typeof primaryRule === 'string') primaryRuleCounts[primaryRule] = (primaryRuleCounts[primaryRule] ?? 0) + 1;
    }
    return {
      task: {
        id: task.id,
        status: task.status,
        outcome: task.outcome,
        quality_status: task.quality_status,
        quality_score: task.quality_score,
        adapter_id: task.execution_snapshot?.adapter_id ?? null,
        is_mock: task.execution_snapshot?.adapter_id === 'mock',
      },
      report: {
        id: report.id,
        status: report.status,
        execution_outcome: report.execution_summary?.outcome,
        quality_status: report.quality_summary?.status,
        quality_verdict: report.quality_summary?.verdict,
        quality_score: report.quality_summary?.score,
      },
      sample: {
        id: sample.id,
        sample_id: sample.sample_id,
        reference_answer: sample.reference_answer,
        historical_answer: sample.historical_answer,
        answer: sample.run?.answer ?? sample.answer,
        context_origins: (sample.run?.contexts ?? sample.retrieval_results ?? []).map((context) => context.origin),
        citation_count: (sample.run?.citations ?? sample.citations ?? []).length,
        diagnosis_rule_ids: (sample.diagnoses ?? []).map((diagnosis) => diagnosis.rule_id),
      },
      primary_rule_counts: primaryRuleCounts,
    };
  }, { taskId, sampleId });
}

function assertApiSnapshot(snapshot) {
  ensure(snapshot.task.status === 'completed', `API task lifecycle is not completed: ${JSON.stringify(snapshot.task)}`);
  ensure(snapshot.task.outcome === 'succeeded', `API execution outcome is not succeeded: ${JSON.stringify(snapshot.task)}`);
  ensure(snapshot.task.quality_status === 'not_evaluated', `API task quality is not unevaluated: ${JSON.stringify(snapshot.task)}`);
  ensure(snapshot.task.quality_score === null, `API task quality score is not unknown: ${JSON.stringify(snapshot.task)}`);
  ensure(snapshot.task.adapter_id === 'mock' && snapshot.task.is_mock === true, `API task is not an explicit mock result: ${JSON.stringify(snapshot.task)}`);
  ensure(snapshot.report.execution_outcome === 'succeeded', `API report execution outcome changed: ${JSON.stringify(snapshot.report)}`);
  ensure(snapshot.report.quality_status === 'not_evaluated', `API report quality is not unevaluated: ${JSON.stringify(snapshot.report)}`);
  ensure(snapshot.report.quality_verdict === 'unknown' && snapshot.report.quality_score === null, `API report inferred a quality verdict or score: ${JSON.stringify(snapshot.report)}`);
  ensure(snapshot.sample.diagnosis_rule_ids.length === expectedDiagnosisRules.length, `API diagnosis rule count changed: ${JSON.stringify(snapshot.sample.diagnosis_rule_ids)}`);
  ensure(expectedDiagnosisRules.every((rule) => snapshot.sample.diagnosis_rule_ids.includes(rule)), `API diagnosis rules do not match the frozen sample: ${JSON.stringify(snapshot.sample.diagnosis_rule_ids)}`);
}

function assertFailureDistribution(domBuckets, apiSnapshot) {
  const domCounts = Object.fromEntries(domBuckets.map((bucket) => [bucket.label, bucket.count]));
  for (const [rule, count] of Object.entries(apiSnapshot.primary_rule_counts)) {
    ensure(domCounts[rule] === count, `Report failure distribution omitted or changed primary rule ${rule}: DOM=${JSON.stringify(domBuckets)} API=${JSON.stringify(apiSnapshot.primary_rule_counts)}`);
  }
  ensure(!Object.hasOwn(domCounts, 'unclassified'), `Report failure distribution contains unclassified: ${JSON.stringify(domBuckets)}`);
}

async function inspectDiagnosis(page, expectedAnswer) {
  await page.getByText('SIMULATED RUN', { exact: true }).waitFor();
  const referenceAnswer = await text(page.locator('.expected-answer p'));
  const generatedAnswer = await text(page.locator('.generated-answer p'));
  const historicalAnswerVisible = await page.locator('.historical-answer').isVisible().catch(() => false);
  const contextText = await text(page.locator('.document-list'));
  const citationText = await text(page.locator('.citation-list'));
  const usageText = await text(page.locator('dt').filter({ hasText: 'Token 用量' }).locator('..'));
  const diagnosisLabels = (await page.locator('.diagnosis-callout h3, .secondary-diagnosis strong').allTextContents())
    .map((label) => label.trim());
  ensure(referenceAnswer === '按退款金额比例扣回。', `Reference answer is incorrect: ${referenceAnswer}`);
  ensure(generatedAnswer.startsWith('[mock] '), `Current answer is not a mock run output: ${generatedAnswer}`);
  if (expectedAnswer !== undefined) ensure(generatedAnswer === expectedAnswer, 'Persisted answer changed after refresh or backend restart.');
  ensure(contextText.includes('给定上下文'), `Provided context origin is not displayed: ${contextText}`);
  ensure(citationText.includes('没有引用记录'), `Citation empty state is not displayed: ${citationText}`);
  ensure(usageText.includes('未知'), `Unknown token usage is not displayed honestly: ${usageText}`);
  ensure(!diagnosisLabels.includes('unclassified'), `Backend diagnosis rule_id values are rendered as unclassified: ${JSON.stringify(diagnosisLabels)}`);
  ensure(expectedDiagnosisRules.every((rule) => diagnosisLabels.includes(rule)), `DOM diagnosis rules do not match the backend contract: ${JSON.stringify(diagnosisLabels)}`);
  return {
    reference_answer: referenceAnswer,
    historical_answer_visible: historicalAnswerVisible,
    generated_answer: generatedAnswer,
    context_text: contextText,
    citation_text: citationText,
    usage_text: usageText,
    diagnosis_labels: diagnosisLabels,
  };
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
  await page.screenshot({ path: path.join(outputDirectory, `${evidencePrefix}-api-dataset-desktop.png`), fullPage: true });

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
  const desktopLayout = await inspectLayout(page);
  assertLayout(desktopLayout, 'Desktop report');
  const failureDistribution = await inspectFailureDistribution(page);
  await page.screenshot({ path: path.join(outputDirectory, `${evidencePrefix}-api-report-desktop.png`), fullPage: true });

  const diagnosisLink = page.getByRole('link', { name: /诊断样本/ }).first();
  await diagnosisLink.click();
  const diagnosisUrl = page.url();
  const sampleId = diagnosisUrl.split('/').at(-1);
  ensure(Boolean(sampleId), 'Sample ID is missing from the diagnosis URL.');
  const diagnosis = await inspectDiagnosis(page);
  const apiSnapshot = await readApiSnapshot(page, taskId, sampleId);
  assertApiSnapshot(apiSnapshot);
  assertFailureDistribution(failureDistribution, apiSnapshot);
  ensure(apiSnapshot.sample.reference_answer === diagnosis.reference_answer, 'DOM reference answer differs from the current API response.');
  ensure(apiSnapshot.sample.answer === diagnosis.generated_answer, 'DOM current answer differs from the current API response.');
  ensure((apiSnapshot.sample.historical_answer !== null) === diagnosis.historical_answer_visible, 'DOM historical-answer presence differs from the current API response.');
  ensure(apiSnapshot.sample.context_origins.includes('provided'), 'Current API sample does not preserve provided context origin.');
  ensure(apiSnapshot.sample.citation_count === 0, `Current API sample citation count is not the expected empty state: ${apiSnapshot.sample.citation_count}`);

  await page.reload({ waitUntil: 'networkidle' });
  await inspectDiagnosis(page, diagnosis.generated_answer);

  await page.setViewportSize({ width: 390, height: 844 });
  await page.reload({ waitUntil: 'networkidle' });
  await inspectDiagnosis(page, diagnosis.generated_answer);
  const mobileLayout = await inspectLayout(page);
  assertLayout(mobileLayout, 'Mobile diagnosis');
  await page.screenshot({ path: path.join(outputDirectory, `${evidencePrefix}-api-diagnosis-mobile.png`), fullPage: true });

  return {
    frontend_url: frontendUrl,
    dataset_name: datasetName,
    task_id: taskId,
    sample_id: sampleId,
    report_url: `${frontendUrl}/projects/demo/evaluations/${taskId}/report`,
    diagnosis_url: diagnosisUrl,
    generated_answer: diagnosis.generated_answer,
    runtime_axes: runtimeAxes,
    report_status: reportStatus,
    desktop_layout: desktopLayout,
    mobile_layout: mobileLayout,
    diagnosis_dom: diagnosis,
    failure_distribution_dom: failureDistribution,
    api_snapshot: apiSnapshot,
  };
}

async function recheckAfterRestart(page, previous) {
  await page.goto(previous.report_url, { waitUntil: 'networkidle' });
  const reportStatus = await text(page.getByLabel('运行与质量状态'));
  ensure(reportStatus.includes('执行成功') && reportStatus.includes('未评估'), `Report changed after backend restart: ${reportStatus}`);
  const runtimeAxes = await assertRuntimeAxes(page);
  const failureDistribution = await inspectFailureDistribution(page);
  const desktopLayout = await inspectLayout(page);
  assertLayout(desktopLayout, 'Restarted desktop report');
  await page.goto(previous.diagnosis_url, { waitUntil: 'networkidle' });
  const diagnosis = await inspectDiagnosis(page, previous.generated_answer);
  const apiSnapshot = await readApiSnapshot(page, previous.task_id, previous.sample_id);
  assertApiSnapshot(apiSnapshot);
  assertFailureDistribution(failureDistribution, apiSnapshot);
  ensure(apiSnapshot.task.id === previous.task_id && apiSnapshot.sample.id === previous.sample_id, 'Task or sample ID changed after backend restart.');
  ensure(apiSnapshot.sample.reference_answer === diagnosis.reference_answer, 'Restarted DOM reference answer differs from the current API response.');
  ensure(apiSnapshot.sample.answer === diagnosis.generated_answer, 'Restarted DOM current answer differs from the current API response.');
  ensure((apiSnapshot.sample.historical_answer !== null) === diagnosis.historical_answer_visible, 'Restarted DOM historical-answer presence differs from the current API response.');
  await page.screenshot({ path: path.join(outputDirectory, `${evidencePrefix}-api-diagnosis-after-restart.png`), fullPage: true });
  return {
    frontend_url: previous.frontend_url,
    dataset_name: previous.dataset_name,
    task_id: previous.task_id,
    sample_id: previous.sample_id,
    report_url: previous.report_url,
    diagnosis_url: previous.diagnosis_url,
    generated_answer: diagnosis.generated_answer,
    runtime_axes: runtimeAxes,
    report_status: reportStatus,
    desktop_layout: desktopLayout,
    diagnosis_dom: diagnosis,
    failure_distribution_dom: failureDistribution,
    api_snapshot: apiSnapshot,
    restart_recheck: 'passed_with_fresh_dom_and_api',
  };
}

async function checkDisconnected(page, previous) {
  await page.goto(previous.report_url, { waitUntil: 'domcontentloaded' });
  const alert = page.getByRole('alert').filter({ hasText: '数据载入失败' });
  await alert.waitFor();
  const alertText = await text(alert);
  ensure(alertText.includes('HTTP 502'), `Disconnected API state does not expose HTTP 502: ${alertText}`);
  ensure(await page.getByRole('button', { name: '重新请求' }).isVisible(), 'Disconnected API state has no retry action.');
  ensure(!(await page.getByText('SIMULATED REPORT', { exact: true }).isVisible().catch(() => false)), 'Disconnected API page silently displayed fixture report.');
  const desktopLayout = await inspectLayout(page);
  ensure(desktopLayout.bodyTextLength > 50, `Disconnected page is unexpectedly empty: ${JSON.stringify(desktopLayout)}`);
  ensure(desktopLayout.scrollWidth <= desktopLayout.clientWidth + 1, `Disconnected page overflows horizontally: ${JSON.stringify(desktopLayout)}`);
  await page.screenshot({ path: path.join(outputDirectory, `${evidencePrefix}-api-disconnected-desktop.png`), fullPage: true });
  return {
    frontend_url: previous.frontend_url,
    dataset_name: previous.dataset_name,
    task_id: previous.task_id,
    sample_id: previous.sample_id,
    report_url: previous.report_url,
    diagnosis_url: previous.diagnosis_url,
    http_error: alertText,
    desktop_layout: desktopLayout,
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
const consoleWarnings = [];

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
  if (message.type() === 'warning') consoleWarnings.push(message.text());
});

let phaseResult = {};
let previous = null;
let acceptanceFailures = [];
let unexpectedError = null;
try {
  previous = phase === 'create' ? null : JSON.parse(await readFile(statePath, 'utf8'));
  if (phase === 'create') ensure(!existsSync(statePath), `Fresh create phase requires a new state path: ${statePath}`);
  phaseResult = phase === 'create'
    ? await createAndInspect(page)
    : phase === 'restart_recheck'
      ? await recheckAfterRestart(page, previous)
      : phase === 'disconnected'
        ? await checkDisconnected(page, previous)
        : (() => { throw new Error(`Unsupported RAGOPS_BROWSER_PHASE: ${phase}`); })();
  ensure(failedRequests.length === 0, `Browser attempted external requests: ${failedRequests.join(', ')}`);
  const duplicateKeyWarnings = [...consoleErrors, ...consoleWarnings]
    .filter((message) => /same key|unique ["']key["']|Encountered two children/i.test(message));
  ensure(duplicateKeyWarnings.length === 0, `React emitted duplicate-key warnings: ${duplicateKeyWarnings.join(' | ')}`);
  if (phase !== 'disconnected' && consoleErrors.length > 0) acceptanceFailures.push('Browser console emitted errors during the API workflow.');
} catch (error) {
  unexpectedError = error instanceof Error ? { name: error.name, message: error.message, stack: error.stack } : { message: String(error) };
  acceptanceFailures.push(unexpectedError.message);
} finally {
  await browser.close();
}

const evidence = {
  baseline_sha: baselineSha,
  script_version: scriptVersion,
  phase,
  ...phaseResult,
  browser: 'local Chromium channel via playwright-core',
  browser_executable: path.basename(executablePath),
  request_count: requests.length,
  request_hosts: [...new Set(requests.map((url) => new URL(url).host))],
  external_requests: failedRequests,
  console_errors: consoleErrors,
  console_warnings: consoleWarnings,
  duplicate_key_warnings: [...consoleErrors, ...consoleWarnings]
    .filter((message) => /same key|unique ["']key["']|Encountered two children/i.test(message)),
  acceptance_failures: acceptanceFailures,
  acceptance_status: acceptanceFailures.length === 0 ? 'passed' : 'failed',
  exit_code: acceptanceFailures.length === 0 ? 0 : 1,
  error: unexpectedError,
  evidence_path: path.relative(repoRoot, phaseEvidencePath).replaceAll('\\', '/'),
};
const phaseHistory = { ...(previous?.phase_results ?? {}), [phase]: evidence };
const phaseExitCodes = Object.fromEntries(Object.entries(phaseHistory).map(([name, result]) => [name, result.exit_code]));
const overallExitCode = Object.values(phaseExitCodes).some((code) => code !== 0) ? 1 : 0;
const cumulativeState = phase === 'create'
  ? { ...evidence, phase_results: phaseHistory, phase_exit_codes: phaseExitCodes, overall_acceptance_status: overallExitCode === 0 ? 'passed' : 'failed' }
  : { ...previous, ...phaseResult, phase, phase_results: phaseHistory, phase_exit_codes: phaseExitCodes, overall_acceptance_status: overallExitCode === 0 ? 'passed' : 'failed' };
await writeFile(phaseEvidencePath, `${JSON.stringify(evidence, null, 2)}\n`, 'utf8');
await writeFile(statePath, `${JSON.stringify(cumulativeState, null, 2)}\n`, 'utf8');
process.stdout.write(`${JSON.stringify(evidence, null, 2)}\n`);
process.exitCode = evidence.exit_code;

import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { AppRoutes } from '../../frontend/src/App';
import { ApiError, apiClient } from '../../frontend/src/api/client';
import { evaluationTasks } from '../../frontend/src/api/fixtures';
import { MetricCard } from '../../frontend/src/components/MetricCard';
import type { ModelExecutionStatus } from '../../frontend/src/types';

const status: ModelExecutionStatus = {
  schemaVersion: '3.0',
  backendExecutionAdapter: 'codex_chatgpt',
  externalCallsEnabled: true,
  executionAvailable: true,
  activeAdapter: {
    adapterId: 'codex_chatgpt',
    isMock: false,
    capabilities: { externalNetwork: true, supportsSeed: false, supportsStop: false, reportsUsage: true, reportsRequestId: true },
  },
  providers: [{
    adapterId: 'codex_chatgpt',
    providerId: 'codex_chatgpt',
    configurationStatus: 'verified',
    baseUrlConfigured: true,
    credentialConfigured: true,
    defaultModelConfigured: true,
    lastVerifiedAt: '2026-09-06T01:00:00Z',
    verificationMessage: '登录状态来自 Windows 主机桥接。',
    loginStatus: 'logged_in',
    lastConnectionCheckAt: '2026-09-06T01:00:00Z',
    lastConnectionCheckStatus: 'succeeded',
    realGenerationVerified: false,
    lastGenerationVerifiedAt: null,
    codexVersion: 'codex-test-version',
    availableModels: ['gpt-codex-test'],
    quota: null,
  }, {
    adapterId: 'openai_compatible',
    providerId: 'openai_compatible',
    configurationStatus: 'configured_unverified',
    baseUrlConfigured: true,
    credentialConfigured: true,
    defaultModelConfigured: true,
    lastVerifiedAt: null,
    verificationMessage: null,
    loginStatus: 'not_applicable',
    lastConnectionCheckAt: null,
    lastConnectionCheckStatus: 'not_checked',
    realGenerationVerified: null,
    lastGenerationVerifiedAt: null,
    codexVersion: null,
    availableModels: ['provider-model'],
    quota: { remaining: null, limit: null, unit: null, resetsAt: null, message: null },
  }],
  source: 'api',
};

function route(path: string) {
  return render(<MemoryRouter initialEntries={[path]}><AppRoutes /></MemoryRouter>);
}

describe('three-channel model execution UI', () => {
  it('separates local login checks from confirmed real generation checks', async () => {
    vi.spyOn(apiClient, 'getModelExecutionStatus').mockResolvedValue(status);
    const verify = vi.spyOn(apiClient, 'verifyModelExecution').mockResolvedValue({
      adapterId: 'codex_chatgpt', check: 'login', status: 'succeeded', checkedAt: '2026-09-06T01:00:00Z',
      message: '登录有效', model: null, usage: null, requestId: null,
    });
    const user = userEvent.setup();
    route('/projects/demo/overview');
    await screen.findByText('最近评测任务');

    await user.click(screen.getByRole('button', { name: '查看运行模式状态' }));
    const dialog = screen.getByRole('dialog', { name: '模型与 Prompt · 只读快照' });
    expect(dialog).toHaveTextContent('Mock fixture（浏览器内存）');
    expect(dialog).toHaveTextContent('codex_chatgpt');
    expect(dialog).toHaveTextContent('codex-test-version');
    expect(dialog).toHaveTextContent('gpt-codex-test');
    expect(dialog).toHaveTextContent('额度');
    expect(dialog).toHaveTextContent('未知');

    await user.click(within(dialog).getByRole('button', { name: '检查 ChatGPT 登录（不生成）' }));
    await waitFor(() => expect(verify).toHaveBeenCalledWith({ adapterId: 'codex_chatgpt', check: 'login', model: undefined }));
    expect(screen.queryByRole('alertdialog', { name: '确认真实小请求检查' })).not.toBeInTheDocument();

    const codexCard = within(dialog).getByRole('region', { name: 'codex_chatgpt 状态' });
    await user.click(within(codexCard).getByRole('button', { name: '真实小请求检查' }));
    const confirmation = screen.getByRole('alertdialog', { name: '确认真实小请求检查' });
    expect(confirmation).toHaveTextContent('使用当前 ChatGPT 账号额度');
    expect(verify).toHaveBeenCalledTimes(1);
    await user.click(within(confirmation).getByRole('button', { name: '确认检查' }));
    await waitFor(() => expect(verify).toHaveBeenLastCalledWith({ adapterId: 'codex_chatgpt', check: 'generation', model: 'gpt-codex-test' }));
  });

  it('shows a concrete safe quota error and never echoes an unsafe raw message', async () => {
    vi.spyOn(apiClient, 'getModelExecutionStatus').mockResolvedValue(status);
    vi.spyOn(apiClient, 'verifyModelExecution').mockRejectedValue(new ApiError('raw upstream body with secret', 429, 'QUOTA_EXCEEDED'));
    const user = userEvent.setup();
    route('/projects/demo/overview');
    await screen.findByText('最近评测任务');
    await user.click(screen.getByRole('button', { name: '查看运行模式状态' }));
    const dialog = screen.getByRole('dialog', { name: '模型与 Prompt · 只读快照' });
    const codexCard = within(dialog).getByRole('region', { name: 'codex_chatgpt 状态' });
    await user.click(within(codexCard).getByRole('button', { name: '真实小请求检查' }));
    await user.click(screen.getByRole('button', { name: '确认检查' }));

    expect(await screen.findByText(/QUOTA_EXCEEDED/)).toHaveTextContent('账号额度不足');
    expect(dialog).not.toHaveTextContent('raw upstream body with secret');
  });

  it('creates mock, Codex ChatGPT and OpenAI-compatible tasks with explicit models', async () => {
    const getStatus = vi.spyOn(apiClient, 'getModelExecutionStatus').mockResolvedValue(status);
    const create = vi.spyOn(apiClient, 'createEvaluationTask').mockImplementation(async (_projectId, input) => ({
      ...evaluationTasks[0],
      id: `created-${input.adapterId}`,
      name: `${input.adapterId} run`,
      adapterId: input.adapterId,
      modelVersion: input.generation.model,
      isMock: input.adapterId === 'mock',
    }));
    const user = userEvent.setup();
    route('/projects/demo/evaluations');
    await screen.findByRole('heading', { level: 2, name: '评测任务' });
    await waitFor(() => expect(getStatus).toHaveBeenCalledTimes(2));

    const createTask = async (adapterId: 'mock' | 'codex_chatgpt' | 'openai_compatible', model: string) => {
      await user.click(screen.getByRole('button', { name: '新建评测任务' }));
      const dialog = screen.getByRole('dialog', { name: '新建评测任务' });
      await user.selectOptions(within(dialog).getByRole('combobox', { name: '选择后端执行通道' }), adapterId);
      const modelInput = within(dialog).getByRole('combobox', { name: '请求模型' });
      await user.clear(modelInput);
      await user.type(modelInput, model);
      await user.click(within(dialog).getByRole('button', { name: '创建评测任务' }));
      await waitFor(() => expect(screen.queryByRole('dialog', { name: '新建评测任务' })).not.toBeInTheDocument());
    };

    await createTask('mock', 'mock-ragops-v1');
    await createTask('codex_chatgpt', 'gpt-codex-test');
    await createTask('openai_compatible', 'provider-model');

    expect(create.mock.calls.map((call) => ({ adapterId: call[1].adapterId, model: call[1].generation.model }))).toEqual([
      { adapterId: 'mock', model: 'mock-ragops-v1' },
      { adapterId: 'codex_chatgpt', model: 'gpt-codex-test' },
      { adapterId: 'openai_compatible', model: 'provider-model' },
    ]);
  });

  it('labels partial metric coverage instead of presenting it as an all-sample result', () => {
    render(<MetricCard metric={{ key: 'support', label: '引用支持率', value: 100, status: 'ok', unit: '%', evaluatedCount: 1, excludedCount: 2 }} />);
    expect(screen.getByRole('article')).toHaveTextContent('已评 1 / 3 个样本（非整批）');
  });

  it('keeps channel, requested/actual model, usage, request ID and unknown cost visible in reports', async () => {
    const user = userEvent.setup();
    route('/projects/demo/evaluations/eval-20260826/report');
    await screen.findByRole('heading', { level: 2, name: /客服知识库 v3 回归评测/ });
    expect(screen.getByText('0 / 3（部分样本）')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '表格列表' }));
    const table = screen.getByRole('table');
    expect(table).toHaveTextContent('mock-ragops-v1 → mock-ragops-v1');
    expect(table).toHaveTextContent('usage 未知 · 成本未知');
    expect(table).toHaveTextContent('request ID：未知');
    expect(table).toHaveTextContent('SIMULATED');
  });
});

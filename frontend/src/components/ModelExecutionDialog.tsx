import { Bot, Database, LogIn, RefreshCw, ShieldCheck, SlidersHorizontal, Zap } from 'lucide-react';
import { useEffect, useState } from 'react';
import { ApiError, apiClient, apiMode } from '../api/client';
import { formatDateTime } from '../lib/format';
import type { ModelExecutionStatus, ProviderStatus, VerificationCheck } from '../types';
import { Dialog } from './Interaction';
import { StatusBadge } from './StatusBadge';

export type RuntimeStatusView =
  | { state: 'loading' }
  | { state: 'success'; data: ModelExecutionStatus }
  | { state: 'error'; message: string };

interface PendingVerification {
  adapterId: 'codex_chatgpt' | 'openai_compatible';
  model?: string;
}

const configurationLabel = (provider: ProviderStatus) => provider.configurationStatus === 'verified'
  ? '真实验证通过'
  : provider.configurationStatus === 'configured_unverified' ? '已配置 / 未验证'
    : provider.configurationStatus === 'not_configured' ? '未配置' : '未知';

const loginLabel = (provider: ProviderStatus) => provider.loginStatus === 'logged_in'
  ? '已登录'
  : provider.loginStatus === 'logged_out' ? '未登录'
    : provider.loginStatus === 'expired' ? '登录已失效'
      : provider.loginStatus === 'not_applicable' ? '不适用' : '未知';

const checkLabel = (provider: ProviderStatus) => provider.lastConnectionCheckStatus === 'succeeded'
  ? '通过'
  : provider.lastConnectionCheckStatus === 'failed' ? '失败'
    : provider.lastConnectionCheckStatus === 'not_checked' ? '未检查' : '未知';

const quotaLabel = (provider: ProviderStatus) => {
  if (!provider.quota) return '未知';
  if (provider.quota.message) return provider.quota.message;
  if (provider.quota.remaining === null || provider.quota.limit === null) return '未知';
  return `${provider.quota.remaining} / ${provider.quota.limit}${provider.quota.unit ? ` ${provider.quota.unit}` : ''}`;
};

const safeErrorMessage = (error: unknown) => {
  const code = error instanceof ApiError ? error.code : undefined;
  const messages: Record<string, string> = {
    CHATGPT_NOT_LOGGED_IN: 'ChatGPT 未登录；请先在 Windows 主机完成 Codex 登录。',
    CHATGPT_LOGIN_EXPIRED: 'ChatGPT 登录已失效；请在 Windows 主机重新登录。',
    ACCOUNT_NOT_LOGGED_IN: 'ChatGPT 未登录；本次没有发起生成。',
    ACCOUNT_SESSION_EXPIRED: 'ChatGPT 登录已失效；本次没有自动重试。',
    QUOTA_EXCEEDED: '账号额度不足；本次没有切换到其他通道。',
    RATE_LIMITED: '提供方限流；本次没有切换通道。',
    PROVIDER_RATE_LIMITED: 'OpenAI-compatible 提供方限流；本次没有自动切换通道。',
    AUTHENTICATION_FAILED: '提供方认证失败；请由后端管理员检查凭据配置。',
    PROVIDER_AUTHENTICATION_FAILED: 'OpenAI-compatible 认证失败；浏览器未读取任何 API Key。',
    MODEL_TIMEOUT: '小请求检查超时；Codex 通道未自动重提，避免重复消耗额度。',
    PROVIDER_TIMEOUT: 'OpenAI-compatible 小请求检查超时；未自动切换通道。',
    EXTERNAL_CALLS_DISABLED: '外部调用总开关已关闭；未发送真实请求。',
    PROVIDER_NOT_CONFIGURED: '通道尚未配置；浏览器不会要求或保存凭据。',
    VERIFICATION_UNAVAILABLE: '当前数据模式不支持真实连接检查。',
  };
  if (code && messages[code]) return `[${code}] ${messages[code]}`;
  if (error instanceof ApiError) return `[${code ?? 'VERIFICATION_FAILED'}] 连接检查失败；请查看后端返回的安全错误记录。`;
  return '连接检查失败；状态保持未验证，也没有切换到其他通道。';
};

export function ModelExecutionDialog({
  open,
  runtimeStatus,
  backendAdapterLabel,
  onClose,
  onRefresh,
}: {
  open: boolean;
  runtimeStatus: RuntimeStatusView;
  backendAdapterLabel: string;
  onClose: () => void;
  onRefresh: () => Promise<void>;
}) {
  const [verifying, setVerifying] = useState<string | null>(null);
  const [pending, setPending] = useState<PendingVerification | null>(null);
  const [result, setResult] = useState<string | null>(null);

  useEffect(() => {
    if (!open) {
      setPending(null);
      setResult(null);
    }
  }, [open]);

  const verify = async (adapterId: PendingVerification['adapterId'], check: VerificationCheck, model?: string) => {
    const key = `${adapterId}:${check}`;
    setVerifying(key);
    setPending(null);
    setResult(null);
    try {
      const response = await apiClient.verifyModelExecution({ adapterId, check, model });
      const usage = response.usage ? ` · ${response.usage.totalTokens} tokens` : '';
      setResult(`${response.message}${usage}${response.requestId ? ` · request ID ${response.requestId}` : ''}`);
      await onRefresh();
    } catch (error) {
      setResult(safeErrorMessage(error));
    } finally {
      setVerifying(null);
    }
  };

  const status = runtimeStatus.state === 'success' ? runtimeStatus.data : undefined;
  return (
    <Dialog open={open} title="模型与 Prompt · 只读快照" eyebrow="DATA SOURCE / EXECUTION / VERIFICATION" onClose={onClose}>
      <div className="configuration-snapshot">
        <div><Database size={16} /><span><small>FRONTEND DATA SOURCE</small><strong>{apiMode === 'mock' ? 'Mock fixture（浏览器内存）' : 'RAGOps API（项目数据来源）'}</strong></span><i>{apiMode.toUpperCase()}</i></div>
        <div><Bot size={16} /><span><small>BACKEND EXECUTION ADAPTER</small><strong>{backendAdapterLabel}</strong></span><i>{status?.activeAdapter?.isMock ? 'MOCK' : 'EXPLICIT'}</i></div>
        <div><SlidersHorizontal size={16} /><span><small>EXTERNAL CALLS</small><strong>{status?.externalCallsEnabled === null || status?.externalCallsEnabled === undefined ? '未知' : status.externalCallsEnabled ? '已开启' : '已关闭'}</strong></span><i>BACKEND ONLY</i></div>
      </div>

      {runtimeStatus.state === 'loading' && <p className="form-hint" role="status">正在读取后端本地状态；该读取不会探测模型或消耗额度。</p>}
      {runtimeStatus.state === 'error' && <div className="run-error" role="alert"><strong>状态 API 读取失败</strong><p>{runtimeStatus.message}</p><button className="button button-secondary" type="button" onClick={() => void onRefresh()}><RefreshCw size={14} />重试状态读取</button></div>}
      {status && (
        <>
          <dl className="detail-list runtime-detail">
            <div><dt>执行可用</dt><dd>{status.executionAvailable === null ? '未知' : status.executionAvailable ? '是' : '否'}</dd></div>
            <div><dt>状态来源</dt><dd>{status.source === 'fixture' ? '前端模拟 fixture' : '后端本地状态（不生成）'}</dd></div>
          </dl>
          <div className="provider-status-list">
            {status.providers.map((provider, index) => {
              const adapterId = provider.adapterId ?? provider.providerId;
              const isCodex = adapterId === 'codex_chatgpt';
              const isOpenAiCompatible = adapterId === 'openai_compatible';
              const model = provider.availableModels?.[0];
              return (
                <section className="provider-status-card" key={`${adapterId ?? 'unknown'}:${index}`} aria-label={`${adapterId ?? '未知通道'} 状态`}>
                  <header><div><span className="eyebrow">{isCodex ? 'CHATGPT OAUTH VIA CODEX' : isOpenAiCompatible ? 'CHAT COMPLETIONS' : 'PROVIDER'}</span><h3>{adapterId ?? '未知通道'} · {configurationLabel(provider)}</h3></div><StatusBadge value={provider.configurationStatus} /></header>
                  <dl className="detail-list">
                    <div><dt>配置状态</dt><dd>{configurationLabel(provider)}</dd></div>
                    <div><dt>ChatGPT 登录</dt><dd>{isCodex ? loginLabel(provider) : '不适用'}</dd></div>
                    <div><dt>最近连接检查</dt><dd>{checkLabel(provider)} · {formatDateTime(provider.lastConnectionCheckAt ?? undefined)}</dd></div>
                    <div><dt>真实生成验证</dt><dd>{provider.realGenerationVerified === null ? '未知' : provider.realGenerationVerified ? `已验证 · ${formatDateTime(provider.lastGenerationVerifiedAt ?? undefined)}` : '未验证'}</dd></div>
                    <div><dt>Codex 版本</dt><dd>{isCodex ? provider.codexVersion ?? '未知' : '不适用'}</dd></div>
                    <div><dt>可用模型</dt><dd>{provider.availableModels === null ? '未知' : provider.availableModels.length > 0 ? provider.availableModels.join('、') : '无可用模型'}</dd></div>
                    <div><dt>额度</dt><dd>{quotaLabel(provider)}{provider.quota?.resetsAt ? ` · 重置 ${formatDateTime(provider.quota.resetsAt)}` : ''}</dd></div>
                  </dl>
                  {provider.verificationMessage && <p className="provider-message">{provider.verificationMessage}</p>}
                  <div className="provider-actions">
                    {isCodex && <button className="button button-secondary" type="button" disabled={verifying !== null} onClick={() => void verify('codex_chatgpt', 'login')}><LogIn size={14} />{verifying === 'codex_chatgpt:login' ? '检查中' : '检查 ChatGPT 登录（不生成）'}</button>}
                    {(isCodex || isOpenAiCompatible) && <button className="button button-primary" type="button" disabled={verifying !== null} onClick={() => setPending({ adapterId: isCodex ? 'codex_chatgpt' : 'openai_compatible', model })}><Zap size={14} />真实小请求检查</button>}
                  </div>
                </section>
              );
            })}
          </div>
        </>
      )}

      {pending && <div className="verification-confirm" role="alertdialog" aria-label="确认真实小请求检查"><ShieldCheck size={20} /><div><strong>确认发起真实小请求</strong><p>{pending.adapterId === 'codex_chatgpt' ? '这会使用当前 ChatGPT 账号额度；超时不会自动重提。' : '这会调用 OpenAI-compatible 提供方，可能产生费用。'}失败时不会回退到其他通道。</p></div><div><button className="button button-secondary" type="button" onClick={() => setPending(null)}>取消</button><button className="button button-primary" type="button" onClick={() => void verify(pending.adapterId, 'generation', pending.model)}>确认检查</button></div></div>}
      {result && <p className="verification-result" role="status" aria-live="polite">{result}</p>}
      <p className="form-hint">浏览器只提交通道、检查类型和可选模型 ID；不会读取或传输密码、OAuth Token、API Key 或桥接 Token。状态未知时保持“未知”。</p>
    </Dialog>
  );
}

import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { apiClient } from '../../frontend/src/api/client';
import { report } from '../../frontend/src/api/fixtures';
import { SampleStack } from '../../frontend/src/components/SampleStack';

function renderStack(samples = report.samples.slice(0, 3)) {
  return render(<MemoryRouter><SampleStack samples={samples} projectId="demo" taskId="eval-20260826" /></MemoryRouter>);
}

describe('sample browsing persistence feedback', () => {
  it('updates rear-card status after saving the foreground card without touching review state', async () => {
    const user = userEvent.setup();
    const markViewed = vi.spyOn(apiClient, 'markSampleViewed').mockResolvedValue(undefined);
    const originalReview = report.samples[0].reviewStatus;
    renderStack();

    await waitFor(() => expect(markViewed).toHaveBeenCalledWith('demo', 'eval-20260826', report.samples[0].id, 'local-workspace-user'));
    expect(markViewed).toHaveBeenCalledTimes(1); // Rear cards are only previews, never writes.
    await user.click(screen.getByRole('button', { name: '样本诊断卡片：下一项' }));
    await waitFor(() => expect(screen.getByRole('button', { name: `翻阅：${report.samples[0].sampleId}` })).toHaveTextContent('已浏览'));
    expect(report.samples[0].reviewStatus).toBe(originalReview);
    await user.click(screen.getByRole('button', { name: `翻阅：${report.samples[0].sampleId}` }));
    expect(screen.getByRole('article', { name: report.samples[0].sampleId })).toHaveTextContent('人工复核');
  });

  it('restores the persisted service value when the report is loaded again', async () => {
    const user = userEvent.setup();
    const restored = report.samples.slice(0, 3).map((sample, index) => index === 0
      ? { ...sample, viewedAt: '2026-09-12T00:00:00Z', viewedBy: 'local-workspace-user' }
      : sample);
    const markViewed = vi.spyOn(apiClient, 'markSampleViewed').mockResolvedValue(undefined);
    renderStack(restored);

    expect(markViewed).not.toHaveBeenCalled();
    await user.click(screen.getByRole('button', { name: '样本诊断卡片：下一项' }));
    expect(screen.getByRole('button', { name: `翻阅：${restored[0].sampleId}` })).toHaveTextContent('已浏览');
  });

  it('shows a non-destructive error and retries only when requested', async () => {
    const user = userEvent.setup();
    const markViewed = vi.spyOn(apiClient, 'markSampleViewed').mockRejectedValueOnce(new Error('network')).mockResolvedValueOnce(undefined);
    renderStack();

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('浏览记录未保存');
    expect(alert).toHaveTextContent('不会改变人工复核状态');
    expect(markViewed).toHaveBeenCalledTimes(1);
    await user.click(screen.getByRole('button', { name: '重试保存浏览记录' }));
    await waitFor(() => expect(markViewed).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(screen.queryByRole('alert')).not.toBeInTheDocument());
  });
});

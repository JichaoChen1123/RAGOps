import { afterEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { AppRoutes } from '../../frontend/src/App';
import { apiClient } from '../../frontend/src/api/client';
import type { Dataset, DatasetSampleInput } from '../../frontend/src/types';

const draft: Dataset = {
  id: 'draft-recovery-1', name: '恢复草稿', description: '', sampleCount: 1,
  status: 'draft', schemaVersion: '2.0', version: 'v0.1', contentSha256: null,
  coverage: null, updatedAt: '2026-09-12T00:00:00Z', owner: 'test',
};
const samples: DatasetSampleInput[] = [{
  sampleId: 'cmrc-1', question: '中文问题',
  labels: { referenceAnswer: '主答案', referenceAnswers: ['答案一', '答案二'], goldDocumentIds: [], goldEvidenceIds: [], expectedDiagnoses: [] },
  contexts: [{ origin: 'provided', rank: 1, docId: 'doc-1', chunkId: 'chunk-1', text: '中文上下文' }],
  metadata: { source: { dataset: 'CMRC' } }, tags: [], historicalOutput: null,
}];
const file = new File([`${JSON.stringify({ schema_version: '2.0', sample_id: 'cmrc-1', question: '中文问题', labels: { reference_answer: '主答案', reference_answers: ['答案一', '答案二'], gold_document_ids: [], gold_evidence_ids: [], expected_diagnoses: [] }, contexts: [{ origin: 'provided', rank: 1, doc_id: 'doc-1', chunk_id: 'chunk-1', text: '中文上下文' }], metadata: { source: { dataset: 'CMRC' }, }, tags: [] })}\n`], 'cmrc.jsonl', { type: 'application/jsonl' });

function renderDatasets() {
  return render(<MemoryRouter initialEntries={['/projects/recovery/datasets?state=empty']}><AppRoutes /></MemoryRouter>);
}

async function selectFile(user: ReturnType<typeof userEvent.setup>) {
  await user.upload(screen.getByTestId('local-jsonl-input'), file);
  await waitFor(() => expect(screen.getByTestId('confirm-local-jsonl-import')).toBeEnabled());
}

afterEach(() => {
  vi.restoreAllMocks();
  window.localStorage.clear();
});

describe('DatasetsPage local JSONL recovery', () => {
  it('reuses the same draft after reselecting an identical file, including after reopening', async () => {
    const user = userEvent.setup();
    const create = vi.spyOn(apiClient, 'createDataset').mockResolvedValue(draft);
    const importSamples = vi.spyOn(apiClient, 'importDatasetSamples')
      .mockRejectedValueOnce(new Error('interrupted'))
      .mockResolvedValue({ accepted: 1, rejected: 0, dataset: draft });
    const read = vi.spyOn(apiClient, 'listDatasetSamples').mockResolvedValue([]);
    vi.spyOn(apiClient, 'listDatasets').mockResolvedValue([]);

    renderDatasets();
    await user.click(await screen.findByRole('button', { name: '导入数据' }));
    await selectFile(user);
    await user.click(screen.getByTestId('confirm-local-jsonl-import'));
    await waitFor(() => expect(importSamples).toHaveBeenCalledTimes(1));
    expect(create).toHaveBeenCalledTimes(1);

    await user.click(screen.getByRole('button', { name: '关闭导入本地 JSONL' }));
    await user.click(screen.getByRole('button', { name: '导入数据' }));
    await selectFile(user);
    await user.click(screen.getByTestId('confirm-local-jsonl-import'));
    await waitFor(() => expect(importSamples).toHaveBeenCalledTimes(2));
    expect(create).toHaveBeenCalledTimes(1);
    expect(read).toHaveBeenCalledWith('recovery', draft.id);
  });

  it('recognizes a lost import response from the saved API representation without a second write', async () => {
    const user = userEvent.setup();
    const create = vi.spyOn(apiClient, 'createDataset').mockResolvedValue(draft);
    const importSamples = vi.spyOn(apiClient, 'importDatasetSamples').mockRejectedValue(new Error('response lost'));
    const read = vi.spyOn(apiClient, 'listDatasetSamples').mockResolvedValue([{ ...samples[0], metadata: { ...samples[0].metadata, reference_answers: ['答案一', '答案二'] } }]);
    vi.spyOn(apiClient, 'getDataset').mockResolvedValue(draft);
    vi.spyOn(apiClient, 'listDatasets').mockResolvedValue([]);

    renderDatasets();
    await user.click(await screen.findByRole('button', { name: '导入数据' }));
    await selectFile(user);
    await user.click(screen.getByTestId('confirm-local-jsonl-import'));
    await waitFor(() => expect(screen.getByText(draft.name)).toBeInTheDocument());
    expect(create).toHaveBeenCalledTimes(1);
    expect(importSamples).toHaveBeenCalledTimes(1);
    expect(read).toHaveBeenCalledWith('recovery', draft.id);
    expect(window.localStorage.getItem('ragops.dataset-import-recovery.recovery')).toBeNull();
  });
});

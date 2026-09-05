PRAGMA foreign_keys = ON;

CREATE TABLE datasets (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    name VARCHAR(160) NOT NULL UNIQUE,
    description TEXT,
    owner VARCHAR(120) NOT NULL,
    schema_version VARCHAR(20) NOT NULL,
    version VARCHAR(40) NOT NULL,
    status VARCHAR(20) NOT NULL,
    sample_count INTEGER NOT NULL,
    content_sha256 VARCHAR(64),
    created_at DATETIME NOT NULL,
    published_at DATETIME
);

CREATE TABLE dataset_samples (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    dataset_id VARCHAR(36) NOT NULL REFERENCES datasets (id),
    ordinal INTEGER NOT NULL,
    external_id VARCHAR(200) NOT NULL,
    question TEXT NOT NULL,
    reference_answer TEXT,
    gold_document_ids JSON NOT NULL,
    gold_evidence_ids JSON NOT NULL,
    retrieved_contexts JSON NOT NULL,
    answer TEXT,
    citations JSON NOT NULL,
    tags JSON NOT NULL,
    expected_diagnoses JSON NOT NULL,
    metadata JSON NOT NULL,
    content_sha256 VARCHAR(64) NOT NULL,
    created_at DATETIME NOT NULL,
    CONSTRAINT uq_dataset_sample_external_id UNIQUE (dataset_id, external_id),
    CONSTRAINT uq_dataset_sample_ordinal UNIQUE (dataset_id, ordinal)
);

CREATE TABLE evaluation_jobs (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    dataset_id VARCHAR(36) NOT NULL REFERENCES datasets (id),
    name VARCHAR(160) NOT NULL,
    status VARCHAR(32) NOT NULL,
    outcome VARCHAR(32),
    config_version VARCHAR(120) NOT NULL,
    model_version VARCHAR(120) NOT NULL,
    prompt_version VARCHAR(120) NOT NULL,
    metric_config JSON NOT NULL,
    total_count INTEGER NOT NULL,
    queued_count INTEGER NOT NULL,
    running_count INTEGER NOT NULL,
    succeeded_count INTEGER NOT NULL,
    failed_count INTEGER NOT NULL,
    progress FLOAT NOT NULL,
    failure_code VARCHAR(80),
    failure_message TEXT,
    idempotency_key VARCHAR(128) UNIQUE,
    request_fingerprint VARCHAR(64) NOT NULL,
    created_at DATETIME NOT NULL,
    started_at DATETIME,
    finished_at DATETIME
);

CREATE TABLE evaluation_job_samples (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    job_id VARCHAR(36) NOT NULL REFERENCES evaluation_jobs (id),
    sample_id VARCHAR(36) NOT NULL REFERENCES dataset_samples (id),
    status VARCHAR(24) NOT NULL,
    answer TEXT,
    retrieval_results JSON NOT NULL,
    metric_results JSON NOT NULL,
    diagnoses JSON NOT NULL,
    review_status VARCHAR(20) NOT NULL,
    reviewed_at DATETIME,
    latency_ms INTEGER,
    failure_code VARCHAR(80),
    failure_message TEXT,
    created_at DATETIME NOT NULL,
    started_at DATETIME,
    finished_at DATETIME,
    CONSTRAINT uq_job_sample UNIQUE (job_id, sample_id)
);

CREATE TABLE evaluation_reports (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    job_id VARCHAR(36) NOT NULL UNIQUE REFERENCES evaluation_jobs (id),
    status VARCHAR(32) NOT NULL,
    outcome VARCHAR(32) NOT NULL,
    total_count INTEGER NOT NULL,
    succeeded_count INTEGER NOT NULL,
    failed_count INTEGER NOT NULL,
    metrics JSON NOT NULL,
    generated_at DATETIME NOT NULL
);

INSERT INTO datasets VALUES ('legacy-dataset-001', 'legacy offline dataset', 'synthetic migration fixture', 'qa', '1.0', 'v1', 'published', 1, 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', '2026-08-01 00:00:00', '2026-08-01 00:01:00');
INSERT INTO dataset_samples VALUES ('legacy-sample-row-001', 'legacy-dataset-001', 1, 'legacy-external-001', '旧记录迁移后是否保留？', '必须保留。', '["legacy-doc"]', '["legacy-evidence"]', '[{"rank":1,"doc_id":"legacy-doc","chunk_id":"legacy-chunk","evidence_ids":["legacy-evidence"],"text":"旧数据不可删除。","score":0.9}]', '旧历史回答', '[{"citation_id":"legacy-citation","claim_id":"legacy-claim","chunk_id":"legacy-chunk","resolved":true,"supports_claim":null}]', '["legacy"]', '[]', '{"fixture":"synthetic"}', 'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb', '2026-08-01 00:00:00');
INSERT INTO evaluation_jobs VALUES ('legacy-job-001', 'legacy-dataset-001', 'legacy completed job', 'completed', 'succeeded', 'legacy-config', 'legacy-model-label', 'legacy-prompt', '[]', 1, 0, 0, 1, 0, 1.0, NULL, NULL, 'legacy-idempotency', 'cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc', '2026-08-01 00:02:00', '2026-08-01 00:02:01', '2026-08-01 00:02:02');
INSERT INTO evaluation_job_samples VALUES ('legacy-job-sample-001', 'legacy-job-001', 'legacy-sample-row-001', 'succeeded', '旧运行回答', '[{"rank":1,"doc_id":"legacy-doc","chunk_id":"legacy-chunk","evidence_ids":["legacy-evidence"],"text":"旧数据不可删除。","score":0.9}]', '[]', '[]', 'confirmed', '2026-08-01 00:03:00', 4, NULL, NULL, '2026-08-01 00:02:00', '2026-08-01 00:02:01', '2026-08-01 00:02:02');
INSERT INTO evaluation_reports VALUES ('legacy-report-001', 'legacy-job-001', 'completed', 'succeeded', 1, 1, 0, '[{"metric_name":"execution_success_rate","metric_version":"1.0.0","status":"ok","value":1.0,"details":{}}]', '2026-08-01 00:02:02');

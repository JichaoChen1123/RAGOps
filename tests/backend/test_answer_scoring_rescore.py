from __future__ import annotations

from sqlalchemy import select

from app.evaluation.answer_scoring import answer_score_results, answer_tokens, normalized_em, strict_em
from app.persistence.models import AnswerRescore, Dataset, DatasetSample, EvaluationJob, EvaluationJobSample
from app.persistence.db import Database
from app.services.rescore import rescore_job


def test_answer_score_contract_protects_numeric_meaning_and_multireference() -> None:
    assert strict_em("答案。", ["答案。"]).value == 1
    assert strict_em("答案。", ["答案"]).value == 0
    assert normalized_em(" A  answer。", ["a answer"]).value == 1
    assert normalized_em("hello, world", ["hello world"]).value == 1
    assert answer_tokens("GPT4") == ["gpt4"]
    assert normalized_em("1.5", ["15"]).value == 0
    assert normalized_em("-2", ["2"]).value == 0
    assert normalized_em("10%", ["10"]).value == 0
    assert normalized_em("10kg", ["10g"]).value == 0
    metrics = answer_score_results("北京天气晴", ["上海天气雨", "北京天气晴"])
    assert all(metric.details["matched_reference_index"] == 1 for metric in metrics)
    assert metrics[2].value > 0
    assert answer_score_results("", [""])[2].value == 1
    assert answer_score_results("x", [""])[2].value == 0
    assert answer_score_results("x", []).pop().status == "not_applicable"


def test_rescore_is_append_only_and_offline() -> None:
    # A sentinel would be hit if this path imported/used a model adapter or executor.
    database = Database("sqlite://")
    database.migrate()
    dataset = Dataset(name="d", owner="test", status="published")
    with database.session() as session:
        session.add(dataset)
        session.flush()
        sample = DatasetSample(dataset_id=dataset.id, ordinal=1, external_id="s", question="q", reference_answer="A。", content_sha256="a" * 64)
        session.add(sample)
        session.flush()
        job = EvaluationJob(dataset_id=dataset.id, name="j", config_version="c", model_version="m", prompt_version="p", total_count=1, request_fingerprint="b" * 64)
        session.add(job)
        session.flush()
        row = EvaluationJobSample(job_id=job.id, sample_id=sample.id, status="succeeded", answer="a", metric_results=[{"metric_name":"old", "value":0}])
        session.add(row)
        session.commit()
        original = list(row.metric_results)
        summary = rescore_job(session, job.id)
        assert summary.succeeded == 1 and summary.failed == 0
        assert row.metric_results == original
        saved = session.scalar(select(AnswerRescore).where(AnswerRescore.job_sample_id == row.id))
        assert saved is not None and saved.job_id == job.id and saved.sample_id == sample.id
        assert {item["metric_name"] for item in saved.metric_results} == {"strict_em", "normalized_em", "chinese_answer_f1"}
        dry_run = rescore_job(session, job.id, dry_run=True)
        assert dry_run.succeeded == 1
        assert len(session.scalars(select(AnswerRescore)).all()) == 1
        second = rescore_job(session, job.id)
        assert second.batch_id != summary.batch_id
        assert len(session.scalars(select(AnswerRescore)).all()) == 2


def test_rescore_persists_skip_reason() -> None:
    database = Database("sqlite://")
    database.migrate()
    with database.session() as session:
        dataset = Dataset(name="skip-d", owner="test", status="published")
        session.add(dataset)
        session.flush()
        sample = DatasetSample(dataset_id=dataset.id, ordinal=1, external_id="skip", question="q", reference_answer="a", content_sha256="c" * 64)
        session.add(sample)
        session.flush()
        job = EvaluationJob(dataset_id=dataset.id, name="skip-j", config_version="c", model_version="m", prompt_version="p", total_count=1, request_fingerprint="d" * 64)
        session.add(job)
        session.flush()
        row = EvaluationJobSample(job_id=job.id, sample_id=sample.id, status="failed", answer=None)
        session.add(row); session.commit()
        summary = rescore_job(session, job.id)
        saved = session.scalar(select(AnswerRescore).where(AnswerRescore.job_sample_id == row.id))
        assert summary.skipped == 1
        assert saved is not None and saved.status == "skipped"
        assert saved.failure_reason == "stored model answer is unavailable"

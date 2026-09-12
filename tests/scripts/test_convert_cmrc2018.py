import importlib.util
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("convert_cmrc2018", ROOT / "scripts" / "convert_cmrc2018.py")
converter = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(converter)


class ConvertCmrc2018Tests(unittest.TestCase):
    def test_converter_is_deterministic_and_excludes_legacy_groups(self) -> None:
        work = ROOT / "tests" / ".cmrc-converter-test-work"
        if work.exists():
            raise RuntimeError(f"stale test directory: {work}")
        work.mkdir()
        try:
            paragraphs = []
            for number in range(55):
                context = f"上下文 {number} 含答案 {number}。"
                answer = f"答案 {number}"
                paragraphs.append({"id": f"p{number}", "context": context, "qas": [{"id": f"q{number}", "question": f"问题 {number}？", "answers": [{"text": answer, "answer_start": context.index(answer)}]}]})
            source, legacy = work / "dev.json", work / "legacy.jsonl"
            source.write_text(json.dumps({"data": [{"id": "a", "title": "title", "paragraphs": paragraphs}]}, ensure_ascii=False), encoding="utf-8")
            legacy.write_text(json.dumps({"question": "问题 0？", "contexts": [{"text": "上下文 0 含答案 0。"}]}, ensure_ascii=False) + "\n", encoding="utf-8")
            first, second = work / "one", work / "two"
            converter.convert(source, legacy, first, 20260912)
            converter.convert(source, legacy, second, 20260912)
            for name in (converter.DEBUG_NAME, converter.HOLDOUT_NAME):
                self.assertEqual((first / name).read_bytes(), (second / name).read_bytes())
            debug = [json.loads(line) for line in (first / converter.DEBUG_NAME).read_text(encoding="utf-8").splitlines()]
            holdout = [json.loads(line) for line in (first / converter.HOLDOUT_NAME).read_text(encoding="utf-8").splitlines()]
            self.assertEqual((len(debug), len(holdout)), (20, 30))
            self.assertTrue({row["contexts"][0]["text"] for row in debug}.isdisjoint({row["contexts"][0]["text"] for row in holdout}))
            self.assertTrue(all(row["contexts"][0]["origin"] == "provided" for row in debug + holdout))
            self.assertTrue(all(row["labels"]["reference_answer"] == row["metadata"]["reference_answers"][0] for row in debug + holdout))
        finally:
            for directory in (work / "one", work / "two"):
                if directory.exists():
                    for file in directory.iterdir():
                        file.unlink()
                    directory.rmdir()
            (work / "dev.json").unlink(missing_ok=True)
            (work / "legacy.jsonl").unlink(missing_ok=True)
            work.rmdir()

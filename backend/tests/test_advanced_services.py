"""Tests for advanced services."""

import pytest

from app.services.ast_service import ASTService
from app.services.content_detection_service import ContentDetectionService
from app.services.fingerprint_service import FingerprintService
from app.services.quality_guard_service import QualityGuardService
from app.services.relevance_service import RelevanceService
from app.services.specialized_compression_service import SpecializedCompressionService
from app.services.token_heatmap_service import TokenHeatmapService
from app.schemas import ContentType


class TestContentDetection:
    def test_detect_code(self):
        svc = ContentDetectionService()
        result = svc.detect("```python\ndef hello():\n    pass\n```")
        assert result.content_type == ContentType.CODE

    def test_detect_json(self):
        svc = ContentDetectionService()
        result = svc.detect('{"key": "value", "items": [1, 2]}')
        assert result.content_type == ContentType.JSON

    def test_detect_stacktrace(self):
        svc = ContentDetectionService()
        result = svc.detect("Traceback (most recent call last):\n  File test.py")
        assert result.content_type == ContentType.STACKTRACE


class TestASTService:
    def test_python_symbols(self):
        code = "import os\n\ndef hello():\n    return 1\n\nclass Foo:\n    pass"
        svc = ASTService()
        analysis = svc.analyze(code, "python")
        names = [s.name for s in analysis.symbols]
        assert "hello" in names
        assert "Foo" in names

    def test_compress_code(self):
        code = "def hello():\n    x = 1\n    y = 2\n    return x + y"
        svc = ASTService()
        compressed = svc.compress_code(code, "python")
        assert "hello" in compressed or "def" in compressed


class TestRelevanceService:
    def test_critical_system_prompt(self):
        svc = RelevanceService()
        score = svc.score_message({"role": "system", "content": "You MUST always return JSON format."})
        assert score.is_critical or score.instruction_priority > 0.5

    def test_discardable_chat(self):
        svc = RelevanceService()
        messages = [
            {"role": "user", "content": "Implement API"},
            {"role": "user", "content": "ok"},
        ]
        kept, removed = svc.filter_discardable(messages)
        assert len(kept) < len(messages)


class TestQualityGuard:
    def test_preserves_system_prompt(self):
        svc = QualityGuardService()
        original = [
            {"role": "system", "content": "You are a helpful assistant. MUST return JSON."},
            {"role": "user", "content": "Hello " * 100},
        ]
        compressed = [{"role": "user", "content": "Hello"}]
        merged, report = svc.merge_with_compressed(original, compressed)
        system_contents = [m["content"] for m in merged if m["role"] == "system"]
        assert len(system_contents) > 0


class TestFingerprint:
    def test_near_duplicate(self):
        svc = FingerprintService()
        a = "Implement a REST API with FastAPI and PostgreSQL"
        b = "Implement a REST API with FastAPI and PostgreSQL please"
        assert svc.is_near_duplicate(a, b, threshold=0.7)

    def test_different_prompts(self):
        svc = FingerprintService()
        a = "Write Python code for sorting"
        b = "What is the weather today"
        assert not svc.is_near_duplicate(a, b, threshold=0.85)

    def test_repeat_fingerprint_does_not_raise(self):
        svc = FingerprintService()
        text = "Same prompt submitted twice in the playground"
        first = svc.fingerprint(text)
        second = svc.fingerprint(text)
        assert first.fingerprint == second.fingerprint


class TestSpecializedCompression:
    def test_compress_logs(self):
        svc = SpecializedCompressionService()
        logs = "2024-01-01 INFO started\n2024-01-01 INFO started\n2024-01-01 ERROR failed"
        compressed, ops = svc.compress(logs, ContentType.LOGS)
        assert len(compressed) <= len(logs)
        assert "specialized:logs" in ops

    def test_compress_verbose_chat(self):
        svc = SpecializedCompressionService()
        text = "Please note that it is important to remember that we need the API."
        compressed, ops, ct = svc.compress_message(text)
        assert len(compressed) < len(text)


class TestTokenHeatmap:
    def test_generate_heatmap(self):
        svc = TokenHeatmapService()
        messages = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Write code:\n```python\ndef x(): pass\n```"},
        ]
        result = svc.generate(messages)
        assert result["total_tokens"] > 0
        assert len(result["segments"]) == 2

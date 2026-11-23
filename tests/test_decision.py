from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))

from docdecision.rules import Rule, RuleEngine, load_engine  # noqa: E402
from docdecision.extract import extract_fields  # noqa: E402
from docdecision.document import Document, ReadError  # noqa: E402
from docdecision.decision import decide_document  # noqa: E402


def make_engine(tmp: str | Path, rules_text: str) -> RuleEngine:
    path = Path(tmp) / "rules.yaml"
    path.write_text(rules_text, encoding="utf-8")
    return load_engine(path)


SAMPLE_RULES = """
default: needs_review
rules:
  - name: tiny-approve
    when:
      amount: { lte: 100 }
    suggest: approve
    reasons:
      - total at or below 100
    priority: 10
  - name: huge-escalate
    when:
      amount: { gt: 5000 }
    suggest: escalate
    reasons:
      - total above 5000
    priority: 20
  - name: missing-amount
    when:
      amount: { missing: true }
    suggest: request_more_info
    reasons:
      - no total found
    priority: 30
"""

FIELDS = {
    "amount": {
        "regex": r"(?i)total[:\s]+\$?\s*(?P<value>-?[\d,]+(?:\.\d+)?)",
        "cast": "float",
    },
    "invoice_number": {
        "regex": r"invoice[\s_-]*(?:number|no\.?|#)\s*[:#]?\s*(?P<value>[A-Z0-9-]+)",
        "cast": "string",
    },
}


class RuleMatchingTests(unittest.TestCase):
    def test_first_matching_rule_wins_by_priority(self):
        engine = RuleEngine([Rule("a", {"amount": {"gt": 10}}, "escalate", priority=50),
                             Rule("b", {"amount": {"gte": 0}}, "approve", priority=10)])
        decision = engine.decide({"amount": 20})
        self.assertEqual(decision.decision, "approve")
        self.assertEqual(decision.rule, "b")

    def test_missing_operator_matches_when_field_absent(self):
        engine = RuleEngine([Rule("no-amount", {"amount": {"missing": True}}, "request_more_info")])
        self.assertEqual(engine.decide({}).decision, "request_more_info")

    def test_missing_value_does_not_pass_numeric_comparison(self):
        engine = RuleEngine([Rule("small", {"amount": {"lte": 100}}, "approve")])
        self.assertEqual(engine.decide({}).decision, engine.default)

    def test_default_when_nothing_matches(self):
        engine = RuleEngine([Rule("small", {"amount": {"lte": 100}}, "approve")], default="needs_review")
        decision = engine.decide({"amount": 999})
        self.assertEqual(decision.decision, "needs_review")
        self.assertIsNone(decision.rule)

    def test_any_of_passes_when_one_group_matches(self):
        engine = make_engine(tempfile.mkdtemp(), """
default: needs_review
rules:
  - name: incomplete
    when:
      doc_type: claim
      any_of:
        - claim_number: { missing: true }
        - applicant_email: { missing: true }
    suggest: request_more_info
    priority: 5
""")
        decision = engine.decide({"doc_type": "claim", "claim_number": "C-1"})
        self.assertEqual(decision.decision, "request_more_info")

    def test_any_of_each_group_must_match_internally(self):
        engine = make_engine(tempfile.mkdtemp(), """
default: needs_review
rules:
  - name: grouped
    when:
      doc_type: claim
      any_of:
        - doc_type: claim
          claim_number: { missing: true }
    suggest: request_other
    priority: 5
""")
        self.assertEqual(engine.decide({"doc_type": "claim"}).decision, "request_other")
        self.assertEqual(engine.decide({}).decision, engine.default)

    def test_rule_requires_required_keys(self):
        with self.assertRaises(ValueError):
            Rule.from_dict({"name": "x", "when": {}})

    def test_unknown_operator_raises(self):
        engine = RuleEngine([Rule("bad", {"amount": {"bogus": 1}}, "approve")])
        with self.assertRaises(ValueError):
            engine.decide({"amount": 5})

    def test_regex_operator_case_insensitive(self):
        engine = RuleEngine([Rule("regex", {"status": {"regex": r"urgent"}}, "escalate")])
        self.assertEqual(engine.decide({"status": "Please treat as URGENT"}).decision, "escalate")


class ExtractionTests(unittest.TestCase):
    def test_amount_cast_to_float(self):
        doc = extract_fields(Document(source="t", text="Total: $1,250.00"), FIELDS)
        self.assertEqual(doc.fields["amount"], 1250.0)

    def test_amount_cast_to_float(self):
        doc = extract_fields(Document(source="t", text="Total: $1,250.00"), FIELDS)
        self.assertEqual(doc.fields["amount"], 1250.0)

    def test_amount_with_thousands_separator_casts_to_float(self):
        doc = extract_fields(Document(source="t", text="Total: $12,400.00"), FIELDS)
        self.assertEqual(doc.fields["amount"], 12400.0)

    def test_string_equality_is_case_insensitive(self):
        engine = RuleEngine([Rule("by-type", {"doc_type": "invoice"}, "review")])
        self.assertEqual(engine.decide({"doc_type": "Invoice"}).decision, "review")

    def test_absent_field_not_in_dict(self):
        doc = extract_fields(Document(source="t", text="nothing here"), FIELDS)
        self.assertEqual(doc.fields, {})

    def test_unreadable_number_stays_none(self):
        fields = {"amount": {"regex": r"(?i)total[:\s]+(?P<value>[A-Za-z]+)", "cast": "float"}}
        doc = extract_fields(Document(source="t", text="Total: unknown"), fields)
        self.assertIsNone(doc.fields["amount"])


class DocumentTests(unittest.TestCase):
    def test_json_object_becomes_key_value_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "d.json"
            path.write_text(json.dumps({"total": "$80.00", "invoice_number": "I-9"}), encoding="utf-8")
            doc = Document.from_file(path)
            extract_fields(doc, FIELDS)
            self.assertEqual(doc.fields["invoice_number"], "I-9")
            self.assertEqual(doc.fields["amount"], 80.0)

    def test_unsupported_suffix_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "d.docx"
            path.write_text("x", encoding="utf-8")
            with self.assertRaises(ReadError):
                Document.from_file(path)

    def test_invalid_json_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "d.json"
            path.write_text("{oops", encoding="utf-8")
            with self.assertRaises(ReadError):
                Document.from_file(path)


class PipelineTests(unittest.TestCase):
    def _write(self, tmp: Path, name: str, text: str) -> Path:
        path = tmp / name
        path.write_text(text, encoding="utf-8")
        return path

    def test_end_to_end(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            engine = make_engine(tmp_path, SAMPLE_RULES)
            _, decision = decide_document(
                self._write(tmp_path, "small.txt", "Invoice no. I-1. Total: $45.00"), engine, FIELDS
            )
            self.assertEqual(decision.decision, "approve")
            _, decision = decide_document(
                self._write(tmp_path, "big.txt", "Total: $9,000.00"), engine, FIELDS
            )
            self.assertEqual(decision.decision, "escalate")
            _, decision = decide_document(
                self._write(tmp_path, "none.txt", "no total"), engine, FIELDS
            )
            self.assertEqual(decision.decision, "request_more_info")
            self.assertEqual(decision.rule, "missing-amount")

    def test_missing_file_reports_error(self):
        engine = make_engine(tempfile.mkdtemp(), SAMPLE_RULES)
        with self.assertRaises(ReadError):
            decide_document(Path("/nonexistent/x.txt"), engine, FIELDS)


class MockFixtureTests(unittest.TestCase):
    EXPECTED = {
        "mock_invoice_small.txt": "approve",
        "mock_invoice_large.txt": "escalate",
        "mock_claim_missing_email.json": "request_more_info",
        "mock_application.json": "review",
    }

    def test_mock_files_decide_as_expected(self):
        from docdecision.extract import load_field_specs

        engine = load_engine(PROJECT / "rules.yaml")
        specs = load_field_specs(PROJECT / "fields.yaml")
        for name, expected in self.EXPECTED.items():
            with self.subTest(sample=name):
                _, decision = decide_document(PROJECT / "samples" / name, engine, specs)
                self.assertEqual(decision.decision, expected)


class CliTests(unittest.TestCase):
    def run_cli(self, *args):
        return subprocess.run(
            [sys.executable, "-m", "docdecision", *args],
            cwd=PROJECT, capture_output=True, text=True,
        )

    def test_read_outputs_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "d.txt"
            path.write_text("Invoice # I-7. Total: $30.00", encoding="utf-8")
            result = self.run_cli("read", str(path))
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["fields"]["amount"], 30.0)

    def test_process_outputs_decision(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "d.txt"
            path.write_text("Invoice # I-7. Total: $30.00", encoding="utf-8")
            result = self.run_cli("process", str(path))
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertIn(payload["decision"], {"approve", "escalate", "review", "request_more_info", "needs_review"})

    def test_bundled_sample_invoices(self):
        samples = sorted((PROJECT / "samples").glob("*.txt"))
        for sample in samples:
            with self.subTest(sample=sample.name):
                result = self.run_cli("process", str(sample))
                self.assertEqual(result.returncode, 0, result.stderr)
                payload = json.loads(result.stdout)
                self.assertIn("decision", payload)


if __name__ == "__main__":
    unittest.main()

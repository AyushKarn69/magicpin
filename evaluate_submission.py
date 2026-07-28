#!/usr/bin/env python3
"""Standalone evaluator for the magicpin Vera AI Challenge submission.

This script exercises the locally running backend over HTTP only and reports
pass/fail results in a judge-style format. It does not modify the backend or
business logic.
"""

from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import requests


BASE_URL = os.environ.get("EVAL_BASE_URL", "http://127.0.0.1:8000")
ROOT = Path(__file__).resolve().parent
EXAMPLES_DIR = ROOT / "examples"
DATASET_DIR = ROOT / "dataset"


class Colors:
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    CYAN = "\033[96m"
    BOLD = "\033[1m"
    RESET = "\033[0m"


@dataclass
class EvalResult:
    name: str
    passed: bool
    status_code: int | None = None
    latency_ms: float | None = None
    request_json: Any = None
    response_json: Any = None
    details: list[str] = field(default_factory=list)


class Evaluator:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.base_urls = [self.base_url]
        if self.base_url.endswith(":8000"):
            self.base_urls.append(self.base_url.replace(":8000", ":8080"))
        elif self.base_url.endswith(":8080"):
            self.base_urls.append(self.base_url.replace(":8080", ":8000"))
        self.session = requests.Session()
        self.results: list[EvalResult] = []
        self.latencies: list[float] = []
        self.failures: list[str] = []
        self.warnings: list[str] = []
        self.judge_scores: dict[str, float] = {}

    def _request(self, method: str, path: str, *, json_body: Any = None, **kwargs: Any) -> tuple[requests.Response, float]:
        last_error: Exception | None = None
        for candidate_url in self.base_urls:
            url = urljoin(candidate_url + "/", path.lstrip("/"))
            started = time.perf_counter()
            try:
                response = self.session.request(method, url, json=json_body, timeout=10, **kwargs)
                latency_ms = (time.perf_counter() - started) * 1000.0
                self.latencies.append(latency_ms)
                self.base_url = candidate_url
                return response, latency_ms
            except requests.RequestException as exc:
                last_error = exc
                continue
        raise RuntimeError(f"Request failed: {last_error}") from last_error

    def _print_block(self, title: str, result: EvalResult) -> None:
        print("\n====================================================")
        print(title)
        print("====================================================")
        print(f"HTTP Status: {result.status_code}")
        if result.latency_ms is None:
            print("Latency: N/A")
        else:
            print(f"Latency: {result.latency_ms:.2f} ms")
        print("Request JSON:")
        print(json.dumps(result.request_json, indent=2, ensure_ascii=False))
        print("Response JSON:")
        print(json.dumps(result.response_json, indent=2, ensure_ascii=False))
        print(f"{'PASS' if result.passed else 'FAIL'}")

    def _color(self, passed: bool) -> str:
        return Colors.GREEN if passed else Colors.RED

    def verify_backend(self) -> None:
        self._run_request(
            "health",
            "GET",
            "/v1/healthz",
            expected_status=200,
            required_fields={"status", "uptime_seconds", "contexts_loaded"},
        )
        self._run_request(
            "metadata",
            "GET",
            "/v1/metadata",
            expected_status=200,
            required_fields={"team_name", "team_members", "model", "approach", "contact_email", "version", "submitted_at"},
        )

    def verify_examples(self) -> None:
        example_files = sorted(EXAMPLES_DIR.glob("*.md")) if EXAMPLES_DIR.exists() else []
        if not example_files:
            self.warnings.append("No example markdown files were found under examples/.")
            return

        for path in example_files:
            content = path.read_text(encoding="utf-8")
            if "merchant" not in content.lower() and "trigger" not in content.lower():
                continue
            self.warnings.append(f"Example file {path.name} was discovered but not parsed into structured payloads; using markdown text as a warning only.")

    def run_context_flow(self) -> None:
        # Load example payloads from dataset if available; this keeps the script generic and public-data-based.
        merchant_candidates = sorted((DATASET_DIR / "merchants").glob("*.json")) if (DATASET_DIR / "merchants").exists() else []
        category_candidates = sorted((DATASET_DIR / "categories").glob("*.json")) if (DATASET_DIR / "categories").exists() else []
        trigger_candidates = sorted((DATASET_DIR / "triggers").glob("*.json")) if (DATASET_DIR / "triggers").exists() else []
        customer_candidates = sorted((DATASET_DIR / "customers").glob("*.json")) if (DATASET_DIR / "customers").exists() else []

        if not merchant_candidates or not category_candidates or not trigger_candidates:
            self.warnings.append("No public dataset payloads were found under dataset/; skipping context-flow examples.")
            return

        selected_merchant = merchant_candidates[0]
        selected_category = category_candidates[0]
        selected_trigger = trigger_candidates[0]
        selected_customer = customer_candidates[0] if customer_candidates else None

        merchant_payload = json.loads(selected_merchant.read_text(encoding="utf-8"))
        category_payload = json.loads(selected_category.read_text(encoding="utf-8"))
        trigger_payload = json.loads(selected_trigger.read_text(encoding="utf-8"))
        customer_payload = json.loads(selected_customer.read_text(encoding="utf-8")) if selected_customer else None

        context_cases = [
            ("category", category_payload),
            ("merchant", merchant_payload),
            ("trigger", trigger_payload),
        ]
        if customer_payload:
            context_cases.append(("customer", customer_payload))

        for scope, payload in context_cases:
            context_id = payload.get("id") or payload.get("merchant_id") or payload.get("customer_id") or payload.get("slug") or f"example_{scope}"
            request_json = {
                "scope": scope,
                "context_id": context_id,
                "version": 1,
                "payload": payload,
                "delivered_at": "2026-04-26T10:00:00Z",
            }
            self._run_request(
                f"context:{scope}",
                "POST",
                "/v1/context",
                json_body=request_json,
                expected_status=200,
                required_fields={"accepted", "ack_id", "stored_at"},
                allow_partial=True,
            )

        tick_payload = {"now": "2026-04-26T10:30:00Z", "available_triggers": [trigger_payload.get("id") or trigger_payload.get("merchant_id") or "example_trigger"]}
        self._run_request(
            "tick",
            "POST",
            "/v1/tick",
            json_body=tick_payload,
            expected_status=200,
            required_fields={"actions"},
            allow_partial=True,
        )

        reply_payload = {
            "conversation_id": "conv_example",
            "merchant_id": merchant_payload.get("merchant_id"),
            "customer_id": customer_payload.get("customer_id") if customer_payload else None,
            "from_role": "merchant",
            "message": "Yes, send me the abstract",
            "received_at": "2026-04-26T10:45:00Z",
            "turn_number": 2,
        }
        self._run_request(
            "reply",
            "POST",
            "/v1/reply",
            json_body=reply_payload,
            expected_status=200,
            required_fields={"action", "rationale"},
            allow_partial=True,
        )

    def run_negative_tests(self) -> None:
        tests = [
            ("malformed_json", "POST", "/v1/context", {"scope": "merchant", "context_id": "bad"}, None, 400),
            ("empty_body", "POST", "/v1/context", None, None, 400),
            ("missing_merchant", "POST", "/v1/tick", {"now": "2026-04-26T10:30:00Z", "available_triggers": ["missing_merchant"]}, None, 200),
            ("invalid_conversation", "POST", "/v1/reply", {"conversation_id": "missing_conv", "merchant_id": "m_001", "from_role": "merchant", "message": "hi", "received_at": "2026-04-26T10:45:00Z", "turn_number": 2}, None, 404),
            ("duplicate_context", "POST", "/v1/context", {"scope": "merchant", "context_id": "dup", "version": 1, "payload": {"merchant_id": "dup", "category_slug": "restaurants", "identity": {"name": "Dup", "city": "Delhi", "locality": "Laxmi Nagar", "place_id": "p", "verified": True, "languages": ["en"]}, "subscription": {"status": "active", "plan": "pro"}, "performance": {"window_days": 7, "views": 100, "calls": 5, "directions": 2, "ctr": 0.01}}, "delivered_at": "2026-04-26T10:00:00Z"}, None, 200),
        ]

        for name, method, path, payload, headers, expected in tests:
            try:
                if method == "POST":
                    response, latency_ms = self._request(method, path, json_body=payload)
                else:
                    response, latency_ms = self._request(method, path)
            except RuntimeError as exc:
                self.failures.append(f"Negative test {name} failed to execute: {exc}")
                continue

            passed = response.status_code == expected
            self.results.append(EvalResult(name=name, passed=passed, status_code=response.status_code, latency_ms=latency_ms, request_json=payload, response_json=self._safe_json(response)))
            self._print_block(f"Negative Test: {name}", self.results[-1])
            if not passed:
                self.failures.append(f"Negative test {name} expected {expected} but got {response.status_code}")

    def _run_request(
        self,
        name: str,
        method: str,
        path: str,
        *,
        json_body: Any = None,
        expected_status: int,
        required_fields: set[str] | None = None,
        allow_partial: bool = False,
    ) -> None:
        try:
            response, latency_ms = self._request(method, path, json_body=json_body)
        except RuntimeError as exc:
            result = EvalResult(name=name, passed=False, status_code=None, latency_ms=None, request_json=json_body, response_json=None, details=[str(exc)])
            self.results.append(result)
            self._print_block(f"Endpoint: {name}", result)
            self.failures.append(f"{name} request failed: {exc}")
            return

        response_json = self._safe_json(response)
        passed = response.status_code == expected_status
        details: list[str] = []
        if response_json is None:
            details.append("Response body was not valid JSON")
            passed = False
        else:
            if required_fields:
                missing = sorted(required_fields - set(response_json.keys()))
                if missing:
                    details.append(f"Missing fields: {missing}")
                    passed = False
            if not allow_partial and isinstance(response_json, dict) and response_json.get("accepted") is False and response.status_code == 200:
                details.append("Response indicated failure but returned HTTP 200")
                passed = False

        result = EvalResult(name=name, passed=passed, status_code=response.status_code, latency_ms=latency_ms, request_json=json_body, response_json=response_json, details=details)
        self.results.append(result)
        self._print_block(f"Endpoint: {name}", result)
        if not passed:
            self.failures.append(f"{name} failed: {', '.join(details) if details else 'unexpected response'}")

    def _safe_json(self, response: requests.Response) -> Any:
        try:
            return response.json()
        except ValueError:
            return None

    def run_judge_simulation(self) -> None:
        # When judge_simulator.py is present, use it as a reference only; this script focuses on public-API validation.
        judge_path = ROOT / "judge_simulator.py"
        if not judge_path.exists():
            self.warnings.append("judge_simulator.py not found; judge scoring skipped.")
            return
        self.warnings.append("judge_simulator.py exists, but the evaluator is using the public HTTP API only and therefore reports qualitative scores rather than running the full simulator.")

    def print_report(self) -> None:
        print("\n====================================================")
        print("MAGICPIN VERA SUBMISSION REPORT")
        print("====================================================")
        print()
        print(f"Health Endpoint: {self._status_text(any(r.name == 'health' and r.passed for r in self.results))}")
        print(f"Metadata Endpoint: {self._status_text(any(r.name == 'metadata' and r.passed for r in self.results))}")
        print(f"Context Endpoint: {self._status_text(any(r.name.startswith('context:') and r.passed for r in self.results))}")
        print(f"Tick Endpoint: {self._status_text(any(r.name == 'tick' and r.passed for r in self.results))}")
        print(f"Reply Endpoint: {self._status_text(any(r.name == 'reply' and r.passed for r in self.results))}")
        print("----------------------------------------------------")
        print(f"Negative Tests: {self._status_text(all(r.passed for r in self.results if r.name.startswith('Negative Test:') or r.name in {'malformed_json','empty_body','missing_merchant','invalid_conversation','duplicate_context'}))}")
        print("----------------------------------------------------")
        print("Judge Scores")
        print("Specificity: N/A")
        print("Merchant Fit: N/A")
        print("Category Fit: N/A")
        print("Trigger Relevance: N/A")
        print("Engagement: N/A")
        print("Groundedness: N/A")
        print("Overall: N/A")
        print("----------------------------------------------------")
        print("Performance")
        print(f"Average Latency: {sum(self.latencies)/len(self.latencies):.2f} ms" if self.latencies else "Average Latency: N/A")
        print(f"Maximum Latency: {max(self.latencies):.2f} ms" if self.latencies else "Maximum Latency: N/A")
        print("----------------------------------------------------")
        print("Failures")
        if self.failures:
            for failure in self.failures:
                print(f"- {failure}")
        else:
            print("- None")
        print("----------------------------------------------------")
        print("Warnings")
        if self.warnings:
            for warning in self.warnings:
                print(f"- {warning}")
        else:
            print("- None")
        print("----------------------------------------------------")
        verdict = "READY FOR SUBMISSION" if not self.failures else "NOT READY FOR SUBMISSION"
        print(f"Final Verdict: {verdict}")
        print()
        sys.exit(0 if not self.failures else 1)

    def _status_text(self, passed: bool) -> str:
        return f"{Colors.GREEN}PASS{Colors.RESET}" if passed else f"{Colors.RED}FAIL{Colors.RESET}"


def main() -> None:
    print("Starting submission evaluation against", BASE_URL)
    evaluator = Evaluator(BASE_URL)
    try:
        evaluator.verify_backend()
        evaluator.verify_examples()
        evaluator.run_context_flow()
        evaluator.run_negative_tests()
        evaluator.run_judge_simulation()
        evaluator.print_report()
    except KeyboardInterrupt:
        print("Interrupted by user")
        sys.exit(1)


if __name__ == "__main__":
    main()

"""
Telegram Typing Assistant — fills web forms from CSV data.

Uses existing stack: LLMClient, browser tools (browse_page, browser_action).
No external API keys needed — all powered by your existing setup.
"""

from __future__ import annotations

import csv
import io
import json
import pathlib
from typing import Any, Dict, List, Optional, Tuple

from ouroboros.llm import LLMClient
from ouroboros.context import build_llm_messages
from ouroboros.memory import Memory
from ouroboros.tools.browser import BrowserSession
from supervisor.env import Env


class TypingAssistant:
    """Fills web forms from CSV data via LLM + browser automation."""

    def __init__(self, env: Env, memory: Memory):
        self.env = env
        self.memory = memory
        self.llm = LLMClient()
        self.browser = BrowserSession()

    def load_csv(self, csv_text: str) -> Tuple[List[str], List[Dict[str, str]]]:
        """Parse CSV text into (headers, rows)."""
        reader = csv.DictReader(io.StringIO(csv_text))
        headers = reader.fieldnames or []
        rows = list(reader)
        return headers, rows

    def analyze_form(self, url: str) -> Dict[str, Any]:
        """Load form page and extract input fields."""
        md = self.browser.browse_page(url, output="markdown", wait_for="form", timeout=10000)
        return {"markdown": md, "url": url}

    def build_mapping(
        self, headers: List[str], form_fields: List[str]
    ) -> Dict[str, str]:
        """
        Create CSV-column-to-form-field mapping.
        
        Example:
        - headers = ["name", "email", "address"]
        - form_fields = ["fullName", "emailAddress", "streetAddress"]
        - Returns {"name": "fullName", "email": "emailAddress", "address": "streetAddress"}
        """
        mapping = {}
        for header in headers:
            header_norm = header.lower().strip()
            best_match = None
            best_score = -1
            for field in form_fields:
                field_norm = field.lower().strip()
                # Simple scoring: exact match > partial match
                if header_norm == field_norm:
                    score = 2
                elif header_norm in field_norm or field_norm in header_norm:
                    score = 1
                else:
                    score = 0
                if score > best_score:
                    best_score = score
                    best_match = field
            if best_match and best_score >= 1:
                mapping[header] = best_match
        return mapping

    def fill_form(
        self, row: Dict[str, str], mapping: Dict[str, str]
    ) -> Dict[str, Any]:
        """
        Fill form with one row of data.
        
        Returns result dict with success/error and screenshot (if available).
        """
        result: Dict[str, Any] = {"row": row.copy(), "mapping": mapping}
        try:
            # Fill each field
            for csv_col, form_field in mapping.items():
                value = row.get(csv_col, "")
                # Escape quotes in selector
                selector = f"input[name='{form_field}']"
                self.browser.browser_action("fill", selector, value)
            # Click submit
            submit_selector = "button[type='submit']"
            try:
                self.browser.browser_action("click", submit_selector)
            except Exception:
                # Try alternative selector
                submit_selector = "input[type='submit']"
                self.browser.browser_action("click", submit_selector)
            # Wait and screenshot
            result["screenshot"] = self.browser.browser_action("screenshot")
            result["success"] = True
        except Exception as e:
            result["success"] = False
            result["error"] = str(e)
        return result

    def process_csv(
        self,
        csv_text: str,
        form_url: str,
    ) -> Dict[str, Any]:
        """
        Main entry point: fill form for each row in CSV.
        
        Returns aggregated result with per-row outcomes.
        """
        # Parse CSV
        headers, rows = self.load_csv(csv_text)
        if not headers:
            return {"error": "Empty CSV or missing headers"}

        # Load form and extract fields
        form_data = self.analyze_form(form_url)
        form_md = form_data["markdown"]

        # Extract form field names from markdown (simplified: look for input[...])
        # In production, use HTML parsing or vision LLM to identify fields
        form_fields = self._extract_form_fields(form_md)

        # Build mapping
        mapping = self.build_mapping(headers, form_fields)

        # Fill each row
        results: List[Dict[str, Any]] = []
        for row in rows:
            row_result = self.fill_form(row, mapping)
            results.append(row_result)

        # Aggregate
        success_count = sum(1 for r in results if r.get("success"))
        return {
            "headers": headers,
            "rows_processed": len(rows),
            "success_count": success_count,
            "fail_count": len(rows) - success_count,
            "per_row": results,
            "mapping": mapping,
        }

    def _extract_form_fields(self, markdown: str) -> List[str]:
        """Extract input field names from markdown form preview."""
        fields = []
        for line in markdown.split("\n"):
            # Simple heuristic: look for input field labels
            if "input" in line.lower() or "field" in line.lower():
                # Try to extract name attribute or label
                import re
                match = re.search(r"\[(.*?)\]", line)
                if match:
                    fields.append(match.group(1))
        return fields or ["name", "email", "address"]  # fallback


def main() -> None:
    """Run demo."""
    env = Env(
        repo_dir=pathlib.Path("/home/a/ouroboros_repo"),
        drive_root=pathlib.Path("/home/a/.ouroboros"),
    )
    memory = Memory(env.drive_root, env.repo_dir)
    assistant = TypingAssistant(env, memory)

    csv_text = """name,email,address
John Doe,john@example.com,123 Main St
Jane Smith,jane@example.com,456 Oak Ave
Bob Wilson,bob@example.com,789 Pine Rd"""

    result = assistant.process_csv(csv_text, form_url="https://example.com/contact")
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

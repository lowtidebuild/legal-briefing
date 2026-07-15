import os
import re

from main import run_pipeline


EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
SENSITIVE_ENV_NAMES = {
    "GROQ_API_KEY",
    "GOOGLE_API_KEY",
    "ANTHROPIC_API_KEY",
    "SMTP_PASS",
    "RECIPIENTS",
    "GOOGLE_SHEETS_CREDENTIALS",
    "GOOGLE_SHEETS_ID",
}


def _read_pages_output(output_dir):
    for root, _, files in os.walk(output_dir):
        for name in files:
            path = os.path.join(root, name)
            if name.endswith((".html", ".json", ".css", ".txt", ".xml")):
                with open(path, encoding="utf-8") as handle:
                    yield path, handle.read()


def test_pages_output_does_not_leak_emails_or_secret_markers(tmp_path, monkeypatch):
    secret_values = {
        "GROQ_API_KEY": "test-groq-api-key-should-not-render",
        "GOOGLE_API_KEY": "test-google-api-key-should-not-render",
        "ANTHROPIC_API_KEY": "test-anthropic-key-should-not-render",
        "SMTP_USER": "sender@example.test",
        "SMTP_PASS": "gmail-app-password-should-not-render",
        "RECIPIENTS": "recipient-one@example.test,recipient-two@example.test",
        "GOOGLE_SHEETS_CREDENTIALS": '{"private_key":"sheet-secret-should-not-render"}',
        "GOOGLE_SHEETS_ID": "sheet-id-should-not-render",
    }
    for key, value in secret_values.items():
        monkeypatch.setenv(key, value)

    run_pipeline(
        config_path="config.yaml",
        output_dir=str(tmp_path),
        template_dir="templates",
        static_dir="static",
        dry_run=True,
        use_sample_data=True,
    )

    pages_text = "\n".join(text for _, text in _read_pages_output(tmp_path))

    assert not EMAIL_RE.search(pages_text)
    for key in SENSITIVE_ENV_NAMES:
        assert key not in pages_text
    for value in secret_values.values():
        assert value not in pages_text

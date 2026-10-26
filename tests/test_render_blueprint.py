"""render.yaml is read by Render, not by this code: these tests keep it honest."""

import re
from pathlib import Path

from invoice_api.config import Settings

BLUEPRINT = Path(__file__).parent.parent / "render.yaml"
# Variables Render itself reads, not settings of the app.
_PLATFORM_VARIABLES = {"PORT"}
_SECRETS = {"DATABASE_URL", "ANTHROPIC_API_KEY", "SECRET_KEY"}


def env_vars() -> dict[str, list[str]]:
    """variable name -> the lines of its entry in render.yaml."""
    text = BLUEPRINT.read_text(encoding="utf-8")
    entries = re.split(r"\n\s*- key: ", text)[1:]
    return {entry.splitlines()[0].strip(): entry.splitlines()[1:] for entry in entries}


def test_every_variable_is_a_setting_of_the_app():
    unknown = set(env_vars()) - set(Settings.model_fields) - _PLATFORM_VARIABLES

    assert not unknown


def test_no_secret_is_written_in_the_file():
    for name in _SECRETS & set(env_vars()):
        assert not any(line.strip().startswith("value:") for line in env_vars()[name]), name


def test_the_demo_runs_in_production_with_the_docs_on():
    lines = {name: " ".join(body) for name, body in env_vars().items()}

    assert "production" in lines["ENVIRONMENT"]
    assert "true" in lines["ENABLE_DOCS"]


def test_forwarded_headers_are_not_trusted_blindly():
    # FORWARDED_ALLOW_IPS=* was tested on Render: the platform appends the real IP to
    # whatever the client sends, so the client could choose the IP the limits see.
    assert "FORWARDED_ALLOW_IPS" not in env_vars()

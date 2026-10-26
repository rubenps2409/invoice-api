"""The web page: it is served next to the API without changing it, and its code keeps the
rules that make a page that shows other people's text safe."""

import re
from pathlib import Path

import pytest

from invoice_api.main import _STATIC_DIR

PAGE_FILES = sorted(_STATIC_DIR.glob("*"))
SCRIPTS = sorted(_STATIC_DIR.glob("*.js"))


def index_html() -> str:
    return (_STATIC_DIR / "index.html").read_text(encoding="utf-8")


# --- serving ----------------------------------------------------------------------


async def test_the_page_is_public_html_that_is_always_revalidated(client):
    response = await client.get("/")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "<title>Invoice API</title>" in response.text
    assert response.headers["cache-control"] == "no-cache"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["x-content-type-options"] == "nosniff"


@pytest.mark.parametrize("path", [p.name for p in PAGE_FILES])
async def test_every_file_of_the_page_is_served(client, path):
    response = await client.get(f"/static/{path}")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-cache"
    assert response.headers["x-content-type-options"] == "nosniff"


async def test_scripts_are_served_as_javascript(client):
    response = await client.get("/static/app.js")

    assert "javascript" in response.headers["content-type"]


async def test_the_api_keeps_its_own_json_404(client):
    response = await client.get("/api/does-not-exist")

    assert response.status_code == 404
    assert response.json() == {"detail": "Not Found"}


async def test_a_path_cannot_leave_the_static_folder(client):
    for path in ("/static/../main.py", "/static/%2e%2e/main.py", "/static/..%2fmain.py"):
        assert (await client.get(path)).status_code == 404


async def test_the_interactive_docs_still_work(client):
    assert (await client.get("/docs")).status_code == 200
    assert (await client.get("/openapi.json")).status_code == 200


async def test_the_page_is_not_part_of_the_api_schema(client):
    paths = (await client.get("/openapi.json")).json()["paths"]

    assert "/" not in paths
    assert not any(path.startswith("/static") for path in paths)


# --- what the page may do ---------------------------------------------------------


def test_the_policy_only_allows_the_pages_own_files_and_server():
    html = index_html()
    policy = re.search(r'http-equiv="Content-Security-Policy"\s+content="([^"]+)"', html)

    assert policy, "the page must declare a Content-Security-Policy"
    directives = dict(
        part.strip().split(" ", 1) for part in policy[1].split(";") if part.strip()
    )
    assert directives["default-src"] == "'none'"
    assert directives["script-src"] == "'self'"
    assert directives["connect-src"] == "'self'"
    assert "unsafe" not in policy[1]


def test_the_page_has_no_inline_code_or_styles():
    html = index_html()

    assert not re.search(r"<script(?![^>]*\bsrc=)", html), "inline <script>"
    assert not re.search(r"<style", html), "inline <style>"
    assert not re.search(r"\sstyle=", html), "inline style attribute"
    assert not re.search(r"\son[a-z]+\s*=", html), "inline event handler"


def test_the_page_loads_nothing_from_other_sites():
    html = index_html()
    for url in re.findall(r'(?:src|href)="([^"]+)"', html):
        assert not url.startswith(("http://", "https://", "//")), url
    for script in SCRIPTS:
        assert not re.search(r"https?://", script.read_text(encoding="utf-8")), script.name


@pytest.mark.parametrize("script", SCRIPTS, ids=lambda p: p.name)
def test_scripts_never_build_markup_from_strings(script):
    """What the API returns (a supplier's name, the text of an invoice) is untrusted. The
    scripts only create text nodes, so none of it can become HTML or code."""
    code = script.read_text(encoding="utf-8")
    code = re.sub(r"//.*", "", code)  # comments may mention the forbidden names

    for forbidden in (
        r"\.innerHTML\s*=",
        r"\.outerHTML\s*=",
        r"insertAdjacentHTML",
        r"document\.write",
        r"\beval\s*\(",
        r"new Function",
        r"setAttribute\(\s*[\"']style[\"']",
        r"createContextualFragment",
        r"\.srcdoc",
    ):
        assert not re.search(forbidden, code), f"{script.name}: {forbidden}"


def test_every_module_that_is_imported_exists():
    for script in SCRIPTS:
        for target in re.findall(r'from\s+"\./([\w.-]+)"', script.read_text(encoding="utf-8")):
            assert (Path(_STATIC_DIR) / target).is_file(), f"{script.name} imports {target}"


def test_the_page_is_packaged_with_the_code():
    # The folder sits inside the package, so a wheel installs it with the code.
    assert _STATIC_DIR.parent.name == "invoice_api"
    assert (_STATIC_DIR / "index.html").is_file()


def test_the_login_form_matches_what_the_api_expects():
    """The sign-in call sends form fields named username and password (OAuth2)."""
    auth = (_STATIC_DIR / "auth.js").read_text(encoding="utf-8")

    assert "username: credentials.email" in auth
    assert "/auth/login" in auth

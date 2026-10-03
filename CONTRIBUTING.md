# Contributing

Small, focused fixes and synthetic reproducible examples are welcome.
Report vulnerabilities using [SECURITY.md](SECURITY.md).

1. Use Python 3.11+ with Tkinter, create a virtual environment, and install
   `python -m pip install -r requirements-dev.txt`.
2. Run `python -m pytest -q`, `python -m ruff check src tests tools`,
   `python -m ruff format --check src tests tools`, and `python -m bandit -r src`.
3. Run `python -m pip_audit` and `python -m build` before packaging changes.
4. Run `python tools/make_release.py --audit-git` before committing and
   `python tools/make_release.py` to build the allowlisted source ZIP.

Only `examples/sample.srt` is an approved public subtitle fixture. Tests create
their own temporary, invented inputs. Never commit real media, transcripts,
pairing databases, local diagnostics, credentials, or exported timelines.
Use only synthetic content in screenshots, and review all visible paths.

Preserve the combined audio/video asset-clip and its shared frame-snapped range.
Keep runtime behavior local, and keep installation or other external activity
explicit. Unsupported Resolve import styling should remain clearly labeled.

New public files must be added deliberately to the release allowlist in
`tools/make_release.py`. Use regression tests for security and data-loss fixes.
Mention the Python/Resolve versions actually tested; do not infer an import test
from well-formed XML alone. Contributions use the repository's MIT license.

Windows GUI tests use `isolated_gui_test` so each scenario starts one Tcl/Tk
interpreter in a fresh process. Child tests retain their fixtures and assertions;
an error or timeout fails the parent check.

# Tech stack
- Python ≥3.10 required (PEP 604/585 annotations); CI matrix 3.10–3.14. Dev machine: Fedora Linux, Python 3.14.
- Runtime deps (`requirements.txt`, `>=` lower bounds only, never tested as minimums): `ollama`, `openai` (LM Studio OpenAI-compatible API), `pillow`, `pyexiv2` (Exiv2 binding; not thread-safe), `tqdm`.
- Dev deps (`requirements-dev.txt`): pytest, pytest-cov, `ruff==` exact pin (CI reads Ruff version from it). `requirements-dev.lock` = uv-generated hash lock, used only by CI; regen command + gotchas in `AGENTS.md` CI section.
- Not packaged: `pyproject.toml` holds only `[tool.ruff]` (py310, line-length 120, default rules) and `[tool.coverage.run]`. pytest config in `pytest.ini`.
- CI: GitHub Actions `.github/workflows/ci.yml` — Ruff check + format check, pytest+coverage matrix (Linux only), SonarQube Cloud scan (`sonar-project.properties`, `SONAR_TOKEN` secret). Dismissed Sonar false positives listed in `AGENTS.md`.
- Backends: Ollama `http://localhost:11434`, LM Studio `http://localhost:1234`; default model `qwen3-vl:8b`. Both clients get `--timeout` (default 600s) via `_create_client()`; LM Studio client has `max_retries=0`.
- Also installed locally, NOT configured in repo: `black`, `basedpyright` (Serena LSP). Their output reflects user-global defaults; don't use black (Ruff format is authoritative).

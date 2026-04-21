# Contributing to Darkroom

Darkroom is a public monorepo. The current public contract is intentionally small:

- `runtime/`
- `docs/agents/`
- `docs/platform/`
- `products/tech_blog_monitor/`

Please keep contributions aligned with those public areas unless a maintainer explicitly expands scope.

## Development Setup

Darkroom targets Python 3.10+ and uses `uv` for local development.

```bash
uv sync --group dev
```

If you want a minimal runnable local configuration for `tech_blog_monitor`, start from:

```bash
cp .env.example .env
```

Then adjust only the variables you need. Most features have safe defaults, so a minimal local run can stay on sqlite + fake embeddings.

## Repo Layout

- `runtime/`: reusable runtime abstractions for AI backends
- `docs/agents/`: planner / worker / tester collaboration methodology
- `docs/platform/`: VSM and agentic platform design documents
- `products/tech_blog_monitor/`: the first public product sample

## Recommended Workflow

1. Create a branch from `master`.
2. Keep changes scoped to one problem.
3. Run formatting and tests before opening a PR.
4. Explain user-facing behavior changes and operational tradeoffs in the PR description.

## Local Checks

Run the baseline checks before opening a PR:

```bash
uv run ruff check runtime products/tech_blog_monitor
uv run pytest -q runtime/test products/tech_blog_monitor/test --ignore=products/tech_blog_monitor/test/test_postgres_integration.py
```

If your change only touches one subsystem, run the narrowest relevant tests in addition to the baseline.

Examples:

```bash
uv run pytest -q products/tech_blog_monitor/test/test_retrieval_eval.py
uv run pytest -q products/tech_blog_monitor/test/test_source_adapters.py
uv run pytest -q products/tech_blog_monitor/test/test_observability.py
```

## Product-Specific Notes

### `tech_blog_monitor`

- Prefer additive changes over broad rewrites.
- Keep networked integrations optional and fail-open where possible.
- Do not hardcode private endpoints, credentials, repo roots, or internal URLs.
- When adding a new source adapter, include fixtures and contract tests.
- When changing retrieval or ranking behavior, update or extend the offline evaluation coverage.

### Docs

- Keep docs product-agnostic unless they live under the product subtree.
- Do not introduce internal process links or company-only assumptions.

## Pull Request Guidance

A good PR should state:

- what changed
- why it changed
- how it was validated
- what is intentionally not covered

If you changed runtime behavior, API contracts, or default source coverage, call that out explicitly.

## Security and Secrets

Do not commit:

- real API keys or tokens
- real webhook URLs
- private database URLs
- private repo roots or filesystem paths
- internal runbooks or operational artifacts

Use `.env.example` and example YAML files for shareable configuration.

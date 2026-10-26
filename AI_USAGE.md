# AI Usage

**Tools used:** Claude (claude.ai, Sonnet 4.6), GitHub Copilot (inline suggestions)

---

## Tasks where AI assisted

| Task | How used |
|------|----------|
| SQL query structure | Prompted for window function syntax on p95 calculation; reviewed and tested output |
| Flask boilerplate | Generated initial route skeleton; rewrote error handling and DB pool logic myself |
| Kubernetes YAML | Used to draft StatefulSet; added PDB and corrected probe ports manually |
| Playwright test selectors | Generated regex patterns for `get_by_label`; adjusted for actual DOM structure |
| RCA document structure | Prompted for section headings; all technical findings and commands written manually |

---

## Representative Prompts

1. *"Write a PostgreSQL query for p95 processing time using PERCENTILE_CONT grouped by status"* — output used as-is after verifying against PostgreSQL 15 docs.

2. *"Generate a Flask route for idempotent payment creation that returns 200 for existing ref and 201 for new"* — output restructured; added missing `autocommit=False` and rollback-on-error logic.

3. *"What defects would cause a Kubernetes Service to have empty ENDPOINTS?"* — used to validate my own findings (selector mismatch, probe port mismatch); did not rely solely on AI answer.

4. *"Write pytest fixtures for API tests that share a created customer across the session"* — used `scope="session"` pattern from output; changed assertion in fixture to fail test early instead of silently continuing.

5. *"Generate argparse CLI with --transaction, --stuck, --health, --json flags"* — scaffolded the structure; rewrote the output formatting and exit code logic completely.

---

## Corrections / Improvements to AI Output

- **Flask DB pool:** AI generated `psycopg2.connect()` per request (no pooling). Replaced with `ThreadedConnectionPool` and proper `g.db` teardown — without this, every request opens a new connection, exhausting the DB under load.

- **SQL Q6 (reconciliation):** AI joined `callbacks` directly without `DISTINCT transaction_id`. This double-counted transactions with multiple callback attempts. Fixed the CTE to use `COUNT(DISTINCT c.transaction_id)`.

- **Playwright selectors:** Generated `page.locator("#searchInput")` (fragile ID selector). Changed to `get_by_placeholder` and `get_by_role` — these survive DOM refactors and are the recommended stable-selector approach.

---

## Validation approach

- The seed generator was validated by generating 50,000 transaction INSERT statements and counting the generated callback statements.
- Flask UI and health routes were smoke-tested with Flask's test client.
- Kubernetes manifests were parsed as YAML; a live cluster rollout still requires a configured Kubernetes environment.
- Unit tests run locally: `pytest python/test_support_tool.py -v` — 22 passed.

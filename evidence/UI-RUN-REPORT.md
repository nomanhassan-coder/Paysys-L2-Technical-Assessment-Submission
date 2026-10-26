# MiniPay UI Validation Report

**Run date:** 2026-10-26  
**Environment:** Flask/Gunicorn on `http://localhost:5000`, PostgreSQL 15 in Docker  
**Database:** `minipay`, initialized with `database/schema.sql` and seeded with `database/generate_data.py`

## Browser journeys

| Journey | Result | Evidence |
|---|---|---|
| Open MiniPay search page | Passed | Browser screenshot captured during validation |
| Open login page | Passed | Browser screenshot captured during validation |
| Open new-payment page | Passed | Browser screenshot captured during validation |
| Search seeded transaction `TXN00000001` | Passed | Returned `SUCCESS`, amount `11221.97`, customer `655` |
| Search unknown transaction | Passed | Displayed `Transaction not found.` |
| Submit payment for customer `1`, amount `125.50` | Passed | Returned transaction reference `TXN-8C1F5BA56A0F` |
| API/database health check | Passed | `{"db":"ok","status":"ok"}` |

## Committed screenshots

The browser validation screenshots are stored under
[`evidence/screenshots/`](./screenshots/):

- `ui-search.png`
- `ui-login.png`
- `ui-new-payment.png`
- `ui-search-success.png`
- `ui-search-not-found.png`

## Reproduction commands

```bash
docker run -d --name minipay-postgres \
  -e POSTGRES_DB=minipay \
  -e POSTGRES_USER=minipay \
  -e POSTGRES_PASSWORD=minipay-dev \
  -p 55432:5432 postgres:15-alpine

docker exec -i minipay-postgres psql -U minipay -d minipay \
  < database/schema.sql
python database/generate_data.py > seed.sql
docker exec -i minipay-postgres psql -U minipay -d minipay \
  < seed.sql

cd python
DB_HOST=127.0.0.1 DB_PORT=55432 DB_NAME=minipay \
DB_USER=minipay DB_PASSWORD=minipay-dev API_KEY=changeme \
gunicorn --bind 0.0.0.0:5000 --workers 2 app:app
```

Open `http://localhost:5000/ui` in a browser.

## Automated checks

```bash
pytest tests/ui/test_ui.py -v --base-url http://localhost:5000
pytest python/test_support_tool.py -v
```

The support-tool unit suite passed with 22 tests during this validation. Full
Playwright execution requires Chromium to be installed in the validating
environment.

## CI recommendation

Run the health check and API smoke tests on every pull request. Run the full
Playwright journey and seeded database regression suite on release branches
and before production deployment.

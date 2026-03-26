# OSERVA OFFICE (Merged)

This ZIP merges:

- **oserva_office** (working Flask + SQLite/Postgres backend & all features)
- **office-pulse-grid-main** (the UI/layout theme)

## What changed

1) The app is still Flask + server-rendered templates (so it keeps *all* existing features).
2) The **Pulse Grid** visual theme was applied globally via:
   - `app/static/css/pulse-grid.css`
   - Updated `app/templates/base.html` sidebar/topbar styling
3) The original React layout project is included for reference/future migration in:
   - `frontend_layout_reference/`

## Run locally (Windows / macOS / Linux)

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

pip install -r requirements.txt
python run.py
```

Open: http://127.0.0.1:5000

## Deploy (Railway)

- Set `FLASK_ENV=production`
- Set a strong `SECRET_KEY`
- (Optional) Set `DATABASE_URL` for Postgres

Procfile is already included:

`web: gunicorn -w 4 -b 0.0.0.0:$PORT run:app`

## Notes

- If `FLASK_ENV=production`, the app will **error on boot** unless `SECRET_KEY` is set (to prevent insecure default secrets).

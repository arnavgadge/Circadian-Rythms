# Quickstart

Get CircadianIQ running locally in under 10 minutes.

## 1. Set up the backend

```
python -m venv .venv
```

Activate it:

- Windows (PowerShell): `.venv\Scripts\Activate.ps1`
- macOS/Linux: `source .venv/bin/activate`

Install dependencies:

```
pip install -r requirements.txt
```

(Use `pip install -r requirements-lock.txt` instead if you want the
exact pinned versions used to produce this release.)

## 2. Configure

```
cp .env.example .env
```

The defaults in `.env.example` work out of the box for local SQLite
development — no edits required to get started.

## 3. Initialize the database

```
python scripts/init_db.py
```

This creates the schema and seeds reference data (e.g. the
intervention catalogue).

## 4. (Optional) Generate synthetic data

```
python -m app.scripts.generate_synthetic_data
```

You can skip this and go straight to the demo fast path in step 6
below instead.

## 5. Start the app

Backend API:

```
uvicorn app.api.main:app --reload
```

Frontend, in a second terminal:

```
cd frontend
npm install
npm run dev
```

Open `http://127.0.0.1:5173`.

## 6. See it working immediately (fast path)

Instead of generating and inspecting data by hand, seed the
deterministic demo scenarios and point the API at that database:

```
python -m app.scripts.seed_demo_scenarios --reset
```

Then, before starting the API, set the database URL to the demo
database (adjust the path to your project root):

```
# PowerShell
$env:CIRCADIANIQ_DATABASE_URL = "sqlite:///<path-to-project>/data/demo.db"

# bash
export CIRCADIANIQ_DATABASE_URL="sqlite:///<path-to-project>/data/demo.db"
```

Start the API and frontend as in step 5, then visit:

- `http://127.0.0.1:5173/dashboard/1` — normal case (high confidence, no safety flags)
- `http://127.0.0.1:5173/dashboard/25` — moderate safety flag
- `http://127.0.0.1:5173/dashboard/41` — high safety flag (recommendation suppressed)

The exact participant IDs and how each qualified for its scenario are
recorded in `release/demo/demo_scenarios.json`.

## Where to go next

- Full guided demo walkthrough: `docs/demo_runbook.md`
- Everything else (architecture, subsystem docs, testing, release
  process): `README.md`

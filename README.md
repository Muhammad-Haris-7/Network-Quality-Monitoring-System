# Network Quality Monitoring System

A web dashboard that checks whether websites and servers are reachable and fast,
stores every result, and raises alerts when thresholds are crossed.

**Status:** Week 1 complete (target management API, database schema, validation, tests).

## Features (Week 1)
- Add, view, edit and delete monitored targets (name, address, check type, interval, warning and critical thresholds)
- Input validation with clear error messages
- SQLite database with tables for targets, check results and events
- Automated tests (12 passing)

## Tech stack
Python, FastAPI, SQLAlchemy, SQLite, pytest

## Setup
```
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

## Run
```
uvicorn app.main:app --reload
```
Open http://127.0.0.1:8000/docs to try the API.

## Test
```
python -m pytest -v
```

## API endpoints
| Method | Path | Purpose |
|---|---|---|
| GET | /health | Service check |
| POST | /targets | Add a target |
| GET | /targets | List targets |
| GET | /targets/{id} | View one target |
| PUT | /targets/{id} | Edit a target |
| DELETE | /targets/{id} | Remove a target |

## Project structure
```
app/        backend code (main, models, schemas, database)
tests/      automated tests
```

## Notes
Only monitor systems you own or have permission to test. No network scanning is included.
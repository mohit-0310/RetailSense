---
title: RetailSense
colorFrom: green
colorTo: blue
sdk: docker
app_port: 7860
pinned: false
---

# RetailSense

RetailSense is a local demo of an agentic retail inventory decision support workflow built on the M5 Forecasting dataset.

## Setup

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
```

Optional OpenAI configuration:

```powershell
Copy-Item .env.example .env
```

Set `OPENAI_API_KEY` in `.env` to use the OpenAI Agents SDK path. Without a key, Ask AI uses a deterministic local fallback so the demo remains testable.

## Prepare Data

```powershell
.venv\Scripts\python scripts\prepare_m5_data.py
.venv\Scripts\python scripts\validate_prepared_data.py
```

## Run Locally

```powershell
.venv\Scripts\python -m uvicorn retailsense.api:app --reload --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000`.

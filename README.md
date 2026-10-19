# Kwallo

*football, decoded.* The Kwallo model, automated.

- `pipeline/`: the model (the notebook's sections, in order) and its runner, export and alerts
- `worker/`: the Cloudflare Worker for **@kwalloBot** (alerts sign-up) and lineup-time scheduling
- `.github/workflows/`: the schedules (weekly full run, daily refresh, lineup-time runs)
- `tools/`: one-time helpers
- `tests/`: a check of the bot's logic (`node tests/test_worker.mjs`)

Setup: see **SETUP.md**.

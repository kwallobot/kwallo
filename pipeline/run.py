"""PitchLab pipeline runner: runs the notebook's sections in order, outside Colab.

Modes (set PITCHLAB_MODE):
  full     weekly: everything, including the heavy replays and tests (about 60-80 minutes)
  daily    daily refresh: new results, data and predictions, reusing the weekly tests (about 15-25 minutes)
  lineups  shortly before kickoffs: confirmed lineups, then predictions and verdicts for the next two days (about 10-15 minutes)
Data lives in a local folder (PITCHLAB_DATA, default ./data) synced with Cloudflare R2 before and after the run.
"""
import os, sys, json, time, traceback, io
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import storage, export_site, alerts

MODE = os.environ.get("PITCHLAB_MODE", "daily")
DATA = os.path.abspath(os.environ.get("PITCHLAB_DATA", "./data"))
QUICK = {   # settings switched for the quicker runs (exact text replacements in the sections)
    "RUN_REPLAYS = True": "RUN_REPLAYS = False",
    "RUN_EXPERIMENTS = True": "RUN_EXPERIMENTS = False",
    "RUN_EURO_SELECTION = True": "RUN_EURO_SELECTION = False",
    "TEST_GOAL_LEVEL_AND_REST = True": "TEST_GOAL_LEVEL_AND_REST = False",
    "RUN_LOWER_LEAGUE_TEST = True": "RUN_LOWER_LEAGUE_TEST = False",
    "LINEUP_RUN_MINUTES = 20": "LINEUP_RUN_MINUTES = 4",
    "PITCHAPI_RUN_MINUTES = 10": "PITCHAPI_RUN_MINUTES = 2",
    "PITCHAPI_TACTICS_MINUTES = 10": "PITCHAPI_TACTICS_MINUTES = 2",
    "PITCHAPI_SHOTS_MINUTES = 5": "PITCHAPI_SHOTS_MINUTES = 1",
    "time.time() - t0 > 8 * 60": "time.time() - t0 > 1 * 60",
}
MODES = {
    "full": {},
    "daily": dict(QUICK),
    "lineups": {**QUICK, "PREDICT_DAYS = 7": "PREDICT_DAYS = 2", "RUN_BACKTEST = True": "RUN_BACKTEST = False",
                "LINEUP_RUN_MINUTES = 4": "LINEUP_RUN_MINUTES = 1"},
}
ALWAYS = {'SAVE_DIR = "/content/drive/MyDrive/football"': f'SAVE_DIR = {DATA!r}',
          "SHOW_DASHBOARD = True": "SHOW_DASHBOARD = False", "DOWNLOAD_DASHBOARD = True": "DOWNLOAD_DASHBOARD = False"}

def display(x):
    print(x.to_string() if hasattr(x, "to_string") else x)

def main():
    t_start = time.time()
    os.makedirs(DATA, exist_ok=True)
    print(f"PitchLab pipeline, mode '{MODE}', data in {DATA}")
    synced = storage.sync_down(DATA)
    order = json.load(open(os.path.join(HERE, "cells", "ORDER.json")))
    ns = {"__name__": "__pitchlab__", "display": display}
    failed = None
    for name in order:
        src = open(os.path.join(HERE, "cells", name)).read()
        for a, b in {**ALWAYS, **MODES[MODE]}.items():
            src = src.replace(a, b)
        if MODE == "lineups" and name.split("_", 1)[1] in ("c10_experiments.py", "c8f_lower.py", "c8h_ml.py"):
            continue                                             # not needed shortly before kickoff
        t0 = time.time()
        try:
            exec(compile(src, name, "exec"), ns)
            print(f"[{name}] done in {time.time() - t0:.0f}s")
        except Exception:
            failed = name
            traceback.print_exc()
            print(f"[{name}] FAILED: later sections still run where they can, but the site keeps its previous data for anything missing.")
            if name.split("_", 1)[1] in ("c1_settings.py", "c2_data.py", "c3_models.py", "c5_predict_domestic.py"):
                break                                            # without these nothing downstream makes sense
    if failed not in ("01_c1_settings.py", "02_c2_data.py"):
        export_site.export(ns, DATA, MODE)
        try:
            alerts.send(ns, DATA, MODE)
        except Exception:
            traceback.print_exc()
            print("Alerts: failed this run (predictions were still exported).")
    storage.sync_up(DATA, synced)
    print(f"Finished in {(time.time() - t_start) / 60:.1f} minutes" + (f"; first failure in {failed}" if failed else "."))
    if failed:
        sys.exit(1)

if __name__ == "__main__":
    main()

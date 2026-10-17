# ===================== 10. BUILD THE DASHBOARD =====================
import json
from IPython.display import HTML

def records(df, cols=None):
    if df is None or len(df) == 0:
        return []
    d = df if cols is None else df[[c for c in cols if c in df.columns]]
    return json.loads(d.to_json(orient="records", date_format="iso"))

pred_cols = ["Grid", "Competition", "Group", "Date", "Home", "Away", "pH", "pD", "pA", "bookH", "bookD", "bookA", "pBH", "pBD", "pBA", "BlendW", "pBTTS", "ExpCardsH", "ExpCardsA",
             "ExpHome", "ExpAway", "pOver25", "ExpCorners", "pOverCorners", "ExpCards", "pOverCards", "Note", "Absent"]
all_preds = pd.concat([x for x in [pred_dom, pred_eu] if len(x)], ignore_index=True) if (len(pred_dom) or len(pred_eu)) else pd.DataFrame()
if len(all_preds):
    for col in ["Note", "Absent"]:
        all_preds[col] = all_preds.get(col, pd.Series("", index=all_preds.index)).fillna("")
    all_preds["Grid"] = [np.round(100 * (lambda g_: g_ / g_.sum())(score_grid(r.ExpHome, r.ExpAway, r.pH, r.pD, r.pA))[:6, :6], 1).tolist()
                         for r in all_preds.itertuples()]

sim_recs = records(sim_table.assign(Date=sim_table["Date"].astype(str)) if len(sim_table) else sim_table)

weekly, latest = [], []
_table, _scored = DASH.get("table"), DASH.get("scored")
if _table is not None and _scored is not None and len(_scored):
    weekly = records(_table.reset_index().assign(**{"Week of": lambda d: d["Week of"].astype(str)}))
    lw = _scored[_scored["Week of"] == _scored["Week of"].max()].copy()
    lw["Score"] = lw["FTHG"].astype(int).astype(str) + "-" + lw["FTAG"].astype(int).astype(str)
    lw["pResult"] = lw[["pH", "pD", "pA"]].values[np.arange(len(lw)), outcome(lw)]
    latest = records(lw.sort_values("pResult"), ["Competition", "Home", "Away", "Score", "pH", "pD", "pA", "pResult"])

pred_all_teams = set()
for _pf in [pred_dom, pred_eu]:
    if len(_pf) and {"Home", "Away"}.issubset(_pf.columns):
        pred_all_teams |= set(_pf[["Home", "Away"]].values.ravel())
pred_all_teams |= {o_["opp"] for v_ in globals().get("LAST_TIME", {}).values() for o_ in v_.values()}
payload = {"updated": TODAY.strftime("%Y-%m-%d"), "days": PREDICT_DAYS,
           "order": list(LEAGUES.values()) + list(SOLO) + ["Champions League", "Europa League", "Conference League"],
           "predictions": records(all_preds, pred_cols),
           "sim": {"table": sim_recs, "summary": json.loads(json.dumps(sim_summary, default=float))},
           "scorecard": {"weekly": weekly, "latest": latest},
           "backtest": {"weekly": [], "byComp": []},
           "bt_matches": records(bt_matches.assign(Date=bt_matches["Date"].astype(str))) if len(globals().get("bt_matches", [])) else [],
           "calib": globals().get("calib_bands", []), "cal_result": globals().get("cal_result", {}),
           "bias": records(bias_table.reset_index()) if len(globals().get("bias_table", [])) else [],
           "reports": globals().get("match_reports", []),
           "trends": globals().get("TRENDS", {}), "teams_table": json.loads(json.dumps(globals().get("TEAMS_TABLE", []), default=float).replace("NaN", "null")),
           "players": globals().get("PLAYERS_TABLE", []), "key_players": globals().get("KEY_PLAYERS", {}),
           "scorers": {"|".join(k): v for k, v in globals().get("SCORERS", {}).items()}, "leaderboards": globals().get("LEADERBOARDS", {}),
           "scorer_cal": {k: v for k, v in globals().get("scorer_calibration", {}).items() if k != "table"},
           "expected_xi": {"|".join(k): v for k, v in globals().get("EXPECTED_XI", {}).items()}, "xi_acc": globals().get("xi_acc", {}),
           "bet_check": {"|".join(k): v for k, v in globals().get("BET_CHECK", {}).items()},
           "verdicts": {"|".join(k): v for k, v in globals().get("VERDICTS", {}).items()},
           "markets": {"|".join(k): v for k, v in globals().get("MARKETS", {}).items()},
           "last_time": {"|".join(k): v for k, v in globals().get("LAST_TIME", {}).items()}, "bet_history": globals().get("BET_HISTORY_SUMMARY", {}),
           "team_style": {k: v for k, v in globals().get("TEAM_STYLE", {}).items() if k in set(pred_all_teams)} if "pred_all_teams" in globals() else globals().get("TEAM_STYLE", {}), "my_odds": globals().get("my_odds_summary", {}), "verdict_summary": globals().get("verdict_summary", {}),
           "assist_cal": {k: v for k, v in globals().get("assist_calibration", {}).items() if k != "table"},
           "health": globals().get("HEALTH", []), "clv": globals().get("clv", {}), "edge": {},
           "blend": globals().get("new_blend") or BLEND, "blend_curves": globals().get("blend_curves", {}),
           "disagree": globals().get("disagree", []), "miss_rows": globals().get("miss_rows", []), "miss_totals": globals().get("miss_totals", {}),
           "ledger": globals().get("ledger_summary", {}), "ledger_open": globals().get("ledger_open", []), "ledger_settled": globals().get("ledger_settled", []),
           "edge_rows": globals().get("edge_rows", []), "probable_errors": globals().get("probable_errors", []),
           "extra_tables": ([{"title": "Context factors", "hint": "Each learned before this season and tested on this season's matches; switched on only if better in 95%+ of reshuffles.",
                              "rows": json.loads(pd.DataFrame(ctx2_report).to_json(orient="records"))}] if globals().get("ctx2_report") else []) + json.loads(json.dumps(globals().get("EXTRA_TABLES", []), default=float).replace("NaN", "null")), "adj_check": globals().get("adj_check", []), "adj_decision": globals().get("adj_decision", {}), "brief": globals().get("ANALYST_BRIEF", ""),
           "analyst": globals().get("analyst_score", {})}
_bt_table, _bt_comp = globals().get("bt_table"), globals().get("bt_comp")
if globals().get("btts_edge") is not None:
    payload["edge"]["BTTS"] = float(btts_edge)
if _bt_table is not None and ("ALL WEEKS", "Domestic") in _bt_table.index:
    _r = _bt_table.loc[("ALL WEEKS", "Domestic")]
    for lab, a_, b_ in [("Over 2.5", "Over 2.5 %", "Over 2.5 naive %"), ("Corners", "Corners 9.5 %", "Corners naive %"), ("Cards", "Cards 4.5 %", "Cards naive %")]:
        if pd.notna(_r.get(a_)) and pd.notna(_r.get(b_)):
            payload["edge"][lab] = float(_r[a_] - _r[b_])
if _bt_table is not None:
    payload["backtest"]["weekly"] = records(_bt_table.reset_index().assign(**{"Week of": lambda d: d["Week of"].astype(str)}))
if _bt_comp is not None:
    payload["backtest"]["byComp"] = records(_bt_comp.reset_index())

DASHBOARD_HTML = r'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>PitchLab: match and score predictions</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@500;600;700&family=Source+Sans+3:wght@400;600&display=swap" rel="stylesheet">
<style>
:root {
  /* PitchLab: mint #3ED6A3, deep green #0C352D, black, near-white, sage. Dark is the main look; light for phones set to light mode. */
  --bg: #F4F8F6; --surface: #FFFFFF; --ink: #0C352D; --muted: #4E6B61; --line: #D3E2DB;
  --home: #1E9C74; --draw: #9DB3A8; --away: #0C352D; --warn: #9A6212; --warn-bg: #FBF1DE; --brand: #3ED6A3;
  --display: "Barlow Condensed", "Arial Narrow", "Roboto Condensed", sans-serif;
  --body: "Source Sans 3", "Segoe UI", system-ui, -apple-system, sans-serif;
}
@media (prefers-color-scheme: dark) {
  :root {
    color-scheme: dark;
    --bg: #000000; --surface: #0D1311; --ink: #F8F8F8; --muted: #B8CCB9; --line: #1F2E29;
    --home: #3ED6A3; --draw: #7F948A; --away: #E9EFEC; --warn: #E3AE55; --warn-bg: #2B2414; --brand: #3ED6A3;
  }
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--ink); font-family: var(--body); font-size: 16px; line-height: 1.5; }
.wrap { max-width: 960px; margin: 0 auto; padding: 28px 20px 72px; }
h1 { font-family: var(--display); font-weight: 700; font-size: clamp(2.2rem, 6vw, 3.4rem); line-height: 0.95; margin: 0; letter-spacing: -0.01em; }
.sub { color: var(--muted); margin: 8px 0 0; }
[role="tablist"] { display: flex; gap: 2px; margin: 28px 0 18px; border-bottom: 2px solid var(--line); overflow-x: auto; }
[role="tab"] { font-family: var(--display); font-size: 1.2rem; font-weight: 600; background: none; border: 0; color: var(--muted);
  padding: 8px 14px 6px; border-bottom: 3px solid transparent; margin-bottom: -2px; cursor: pointer; white-space: nowrap; }
[role="tab"][aria-selected="true"] { color: var(--ink); border-bottom-color: var(--home); }
button:focus-visible, select:focus-visible { outline: 2px solid var(--home); outline-offset: 2px; }
.controls { display: flex; flex-wrap: wrap; gap: 10px 16px; align-items: center; margin-bottom: 18px; color: var(--muted); }
select { font: inherit; color: var(--ink); background: var(--surface); border: 1px solid var(--line); border-radius: 6px; padding: 6px 10px; }
label.check { display: inline-flex; gap: 6px; align-items: center; cursor: pointer; }
section.comp { background: var(--surface); border: 1px solid var(--line); border-radius: 12px; margin-bottom: 18px; overflow: hidden; }
section.comp > h2 { font-family: var(--display); font-weight: 600; font-size: 1.35rem; margin: 0; padding: 12px 18px; border-bottom: 1px solid var(--line); }
section.comp > h2 span { color: var(--muted); font-weight: 500; font-size: 1rem; margin-left: 6px; }
.match { padding: 14px 18px 16px; display: grid; grid-template-columns: 84px 1fr; gap: 2px 18px; }
.match + .match { border-top: 1px solid var(--line); }
.when { color: var(--muted); font-size: 0.92rem; padding-top: 3px; }
.teams { display: flex; justify-content: space-between; gap: 12px; font-family: var(--display); font-weight: 600; font-size: 1.3rem; line-height: 1.15; }
.teams .away { text-align: right; }
.bar { display: flex; height: 14px; border-radius: 4px; overflow: hidden; margin-top: 8px; background: var(--line); }
.bar.book { height: 5px; margin-top: 5px; opacity: 0.75; }
.bar i { display: block; height: 100%; }
.bar i + i { border-left: 2px solid var(--surface); }
.h { background: var(--home); } .d { background: var(--draw); } .a { background: var(--away); }
.pcts { display: grid; grid-template-columns: 1fr auto 1fr; font-variant-numeric: tabular-nums; margin-top: 4px; font-size: 0.95rem; }
.pcts b { font-weight: 600; }
.pcts .ph { color: var(--home); } .pcts .pa { color: var(--away); text-align: right; } .pcts .pd { color: var(--muted); text-align: center; }
.booklabel { font-size: 0.82rem; color: var(--muted); margin-top: 2px; font-variant-numeric: tabular-nums; }
.stats { display: flex; flex-wrap: wrap; gap: 4px 22px; margin-top: 10px; font-size: 0.92rem; color: var(--muted); font-variant-numeric: tabular-nums; }
.stats strong { color: var(--ink); font-weight: 600; }
.absent { margin-top: 8px; font-size: 0.9rem; color: var(--muted); }
.vs { color: var(--muted); font-size: 0.85em; }
.flag { margin-top: 10px; font-size: 0.9rem; color: var(--warn); background: var(--warn-bg); border-radius: 6px; padding: 5px 10px; display: inline-block; }
.empty { background: var(--surface); border: 1px dashed var(--line); border-radius: 12px; padding: 28px 22px; color: var(--muted); }
.empty strong { color: var(--ink); display: block; font-family: var(--display); font-size: 1.3rem; font-weight: 600; margin-bottom: 4px; }
.summary { background: var(--surface); border: 1px solid var(--line); border-radius: 12px; padding: 18px 22px; margin-bottom: 18px; max-width: 72ch; }
.summary p { margin: 0 0 8px; } .summary p:last-child { margin: 0; }
.sim-row { display: grid; grid-template-columns: 1fr auto; gap: 4px 18px; padding: 12px 18px; }
.sim-row + .sim-row { border-top: 1px solid var(--line); }
.sim-row .teams { font-size: 1.15rem; justify-content: flex-start; }
.sim-row .likely { color: var(--muted); font-size: 0.92rem; font-variant-numeric: tabular-nums; }
.sim-row .result { font-family: var(--display); font-size: 1.6rem; font-weight: 700; font-variant-numeric: tabular-nums; grid-row: span 2; align-self: center; text-align: right; }
.sim-row .result small { display: block; font-family: var(--body); font-size: 0.75rem; font-weight: 400; color: var(--muted); }
.table-scroll { overflow-x: auto; background: var(--surface); border: 1px solid var(--line); border-radius: 12px; margin-bottom: 18px; }
table { border-collapse: collapse; width: 100%; font-variant-numeric: tabular-nums; font-size: 0.95rem; }
th, td { padding: 9px 14px; text-align: right; white-space: nowrap; border-bottom: 1px solid var(--line); }
th { font-weight: 600; color: var(--muted); font-size: 0.85rem; }
th:first-child, td:first-child, th:nth-child(2), td:nth-child(2) { text-align: left; }
tr.total td { font-weight: 600; background: color-mix(in srgb, var(--home) 8%, var(--surface)); }
.good { color: var(--home); } .bad { color: var(--away); }
h3 { font-family: var(--display); font-weight: 600; font-size: 1.4rem; margin: 26px 0 4px; }
.hint { color: var(--muted); margin: 0 0 12px; max-width: 72ch; }
.score { font-family: var(--display); font-weight: 700; font-size: 1.25rem; }
[hidden] { display: none !important; }
.badge { display: inline-flex; align-items: center; justify-content: center; width: 26px; height: 26px; border-radius: 50%; font-size: 0.6rem; font-weight: 700;
  letter-spacing: 0.02em; vertical-align: middle; margin-right: 6px; border: 2px solid var(--line); flex: none; }
.badge img { width: 100%; height: 100%; object-fit: contain; }
.teams span { display: inline-flex; align-items: center; }
.pitchwrap { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-top: 6px; }
.pitchwrap svg { width: 100%; height: auto; display: block; }
.lasttime { font-size: 0.86rem; margin-top: 6px; }
.lasttime .hit { color: var(--home); font-weight: 600; } .lasttime .miss { color: var(--muted); text-decoration: line-through; }
@media (max-width: 640px) { .pitchwrap { grid-template-columns: 1fr; } }
.verdict { margin-top: 10px; border: 1px solid var(--line); border-radius: 10px; padding: 10px 12px; background: var(--bg); }
.verdict .vt { font-family: var(--display); font-weight: 600; font-size: 1.05rem; margin-bottom: 4px; }
.verdict ol { margin: 4px 0 6px; padding-left: 20px; }
.verdict li { margin: 4px 0; }
.verdict .why { color: var(--muted); font-size: 0.86rem; margin: 2px 0 0 0; padding-left: 14px; }
.verdict .ev { font-size: 0.78rem; color: var(--muted); }
.verdict .line { font-size: 0.9rem; margin: 3px 0; }
.spotted { font-size: 0.82rem; margin-top: 4px; }
.rowlabel { font-size: 0.82rem; color: var(--muted); font-weight: 600; letter-spacing: 0.02em; margin: 6px 0 2px; }
.rowlabel.model { color: var(--ink); }
.trend2 { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-top: 6px; }
.trend2 table { font-size: 0.8rem; }
.trend2 .ls td { color: var(--muted); }
.trend2 .tt { font-weight: 600; margin-bottom: 2px; }
.up { color: var(--home); } .down { color: var(--warn); }
.scorers { font-size: 0.88rem; margin-top: 6px; color: var(--ink); }
.ctrl { display: flex; flex-wrap: wrap; gap: 10px 16px; align-items: center; margin: 4px 0 12px; color: var(--muted); }
th.sortable { cursor: pointer; text-decoration: underline dotted; }
@media (max-width: 640px) { .trend2 { grid-template-columns: 1fr; } }
.blendbox { background: var(--surface); border: 1px solid var(--line); border-radius: 12px; padding: 12px 16px; margin-bottom: 18px; display: grid; grid-template-columns: minmax(220px, 1fr) minmax(240px, 1.2fr); gap: 8px 22px; align-items: center; }
.blendbox input[type=range] { width: 100%; accent-color: var(--home); }
.blendbox .bl-title { font-family: var(--display); font-weight: 600; font-size: 1.15rem; }
.bar.blend { height: 6px; margin-top: 5px; outline: 1px dashed var(--home); outline-offset: 1px; }
.watch { background: var(--surface); border: 1px solid var(--line); border-radius: 12px; padding: 12px 16px; margin-bottom: 10px; }
.watch ul { margin: 6px 0 8px; padding-left: 18px; }
.watch .t { font-family: var(--display); font-weight: 600; font-size: 1.2rem; }
@media (max-width: 640px) { .blendbox { grid-template-columns: 1fr; } }
details.health { margin-top: 12px; background: var(--surface); border: 1px solid var(--line); border-radius: 10px; padding: 8px 14px; font-size: 0.92rem; }
details.health summary { cursor: pointer; }
details.health ul { margin: 8px 0 2px; padding-left: 18px; }
details.health li { margin: 2px 0; }
.ok { color: var(--home); } .warn { color: var(--warn); font-weight: 600; }
.noedge { color: var(--muted); font-size: 0.85em; }
details.sg { margin-top: 8px; font-size: 0.88rem; }
details.sg summary { cursor: pointer; color: var(--muted); }
table.grid { border-collapse: separate; border-spacing: 2px; width: auto; margin-top: 6px; font-size: 0.8rem; }
table.grid th { color: var(--muted); font-weight: 600; padding: 2px 6px; text-align: center; border: 0; }
table.grid td { width: 2.6em; height: 1.9em; text-align: center; padding: 0; border: 0; border-radius: 4px; }
.calib-wrap { display: grid; grid-template-columns: repeat(auto-fit, minmax(230px, 1fr)); gap: 14px; margin: 8px 0 18px; }
.calib { background: var(--surface); border: 1px solid var(--line); border-radius: 12px; padding: 10px 12px; }
.calib h4 { margin: 0 0 4px; font-family: var(--display); font-weight: 600; font-size: 1.1rem; }
.calib svg { width: 100%; height: auto; display: block; }
.mt-controls { display: flex; flex-wrap: wrap; gap: 10px 16px; align-items: center; margin: 6px 0 10px; color: var(--muted); }
.more { font: inherit; padding: 6px 12px; border-radius: 6px; border: 1px solid var(--line); background: var(--surface); color: var(--ink); cursor: pointer; margin-bottom: 18px; }
details.report { background: var(--surface); border: 1px solid var(--line); border-radius: 12px; margin-bottom: 10px; }
details.report > summary { cursor: pointer; padding: 12px 16px; list-style: none; display: flex; flex-wrap: wrap; gap: 4px 14px; align-items: baseline; }
details.report > summary::-webkit-details-marker { display: none; }
details.report > summary .t { font-family: var(--display); font-weight: 600; font-size: 1.2rem; }
details.report > summary .m { color: var(--muted); font-size: 0.9rem; }
.conf { font-size: 0.8rem; font-weight: 600; padding: 1px 8px; border-radius: 999px; border: 1px solid var(--line); }
.conf.High { color: var(--home); } .conf.Low { color: var(--warn); }
details.report pre { margin: 0; padding: 4px 16px 12px; white-space: pre-wrap; font-family: ui-monospace, "SFMono-Regular", Consolas, monospace; font-size: 0.85rem; line-height: 1.5; overflow-x: auto; }
.copy { font: inherit; font-size: 0.9rem; margin: 0 16px 14px; padding: 6px 12px; border-radius: 6px; border: 1px solid var(--line); background: var(--bg); color: var(--ink); cursor: pointer; }
@media (max-width: 600px) {
  .match { grid-template-columns: 1fr; }
  .teams { font-size: 1.15rem; }
}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1><svg viewBox="0 0 64 64" width="38" height="38" aria-hidden="true" style="vertical-align:-6px;margin-right:8px"><path d="M24 6h16M26 6v18L10 52a4 4 0 0 0 3.5 6h37A4 4 0 0 0 54 52L38 24V6" fill="none" stroke="var(--ink)" stroke-width="3" stroke-linejoin="round"/><path d="M17 40h30l6 12a3 3 0 0 1-2.6 4.5H13.6A3 3 0 0 1 11 52z" fill="#3ED6A3"/><line x1="14" y1="48" x2="50" y2="48" stroke="#0C352D" stroke-width="1.6"/><circle cx="32" cy="48" r="4.5" fill="none" stroke="#0C352D" stroke-width="1.6"/><circle cx="30" cy="14" r="1.8" fill="none" stroke="#3ED6A3" stroke-width="1.4"/><circle cx="34" cy="20" r="1.8" fill="none" stroke="#3ED6A3" stroke-width="1.4"/></svg><span style="color:var(--ink)">Pitch</span><span style="color:var(--brand)">Lab</span></h1><div class="hint" style="margin:-6px 0 6px">Match and score predictions</div>
    <p class="sub" id="sub"></p>
    <div id="health"></div>
  </header>
  <div role="tablist" aria-label="Sections">
    <button role="tab" id="tab-pred" aria-selected="true" aria-controls="pane-pred">Predictions</button>
    <button role="tab" id="tab-sim" aria-selected="false" aria-controls="pane-sim">Weekend simulation</button>
    <button role="tab" id="tab-watch" aria-selected="false" aria-controls="pane-watch">Watchlist</button>
    <button role="tab" id="tab-teams" aria-selected="false" aria-controls="pane-teams">Teams</button>
    <button role="tab" id="tab-players" aria-selected="false" aria-controls="pane-players">Players</button>
    <button role="tab" id="tab-reports" aria-selected="false" aria-controls="pane-reports">Match reports</button>
    <button role="tab" id="tab-score" aria-selected="false" aria-controls="pane-score">Scorecard</button>
  </div>
  <div role="tabpanel" id="pane-pred" aria-labelledby="tab-pred">
    <div class="controls">
      <label>Show <select id="comp"></select></label>
      <label class="check"><input type="checkbox" id="differ"> Only where the model and bookmaker differ</label>
    </div>
    <div class="blendbox" id="blendbox"></div>
    <div id="pred-list"></div>
  </div>
  <div role="tabpanel" id="pane-sim" aria-labelledby="tab-sim" hidden></div>
  <div role="tabpanel" id="pane-watch" aria-labelledby="tab-watch" hidden></div>
  <div role="tabpanel" id="pane-teams" aria-labelledby="tab-teams" hidden></div>
  <div role="tabpanel" id="pane-players" aria-labelledby="tab-players" hidden></div>
  <div role="tabpanel" id="pane-reports" aria-labelledby="tab-reports" hidden></div>
  <div role="tabpanel" id="pane-score" aria-labelledby="tab-score" hidden></div>
</div>
<script id="data" type="application/json">__DATA__</script>
<script>
window.onerror = (msg) => { const s = document.getElementById("sub"); if (s) s.textContent = "Dashboard error: " + msg + " (please send this to Claude)"; };
const D = JSON.parse(document.getElementById("data").textContent);
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const pct = v => v == null ? "–" : Math.round(v * 100) + "%";
const num = (v, d = 1) => v == null ? "–" : Number(v).toFixed(d);
const day = s => new Date(s + "T12:00:00").toLocaleDateString(undefined, {weekday: "short", day: "numeric", month: "short"});
const ORDER = D.order;
const preds = D.predictions;
const DIFF = 0.10;

function maxDiff(m) {
  if (m.bookH == null) return 0;
  return Math.max(Math.abs(m.pH - m.bookH), Math.abs(m.pD - m.bookD), Math.abs(m.pA - m.bookA));
}
function bar(h, d, a, cls) {
  return `<div class="bar ${cls}" aria-hidden="true"><i class="h" style="width:${h * 100}%"></i><i class="d" style="width:${d * 100}%"></i><i class="a" style="width:${a * 100}%"></i></div>`;
}
function diffText(m) {
  const parts = [["home win", m.pH - m.bookH], ["draw", m.pD - m.bookD], ["away win", m.pA - m.bookA]];
  parts.sort((x, y) => Math.abs(y[1]) - Math.abs(x[1]));
  const [what, d] = parts[0];
  return `The model rates the ${what} ${Math.round(Math.abs(d) * 100)} points ${d > 0 ? "higher" : "lower"} than the bookmaker`;
}
function keyOf(m) { return [m.Competition, String(m.Date).slice(0, 10), m.Home, m.Away].join("|"); }
function styleOf(team) { return (D.team_style || {})[team] || {}; }
function textOn(hex) {
  const h = String(hex || "#888888").replace("#", ""); if (h.length < 6) return "#fff";
  const [r, g, b] = [0, 2, 4].map(i => parseInt(h.slice(i, i + 2), 16));
  return (0.299 * r + 0.587 * g + 0.114 * b) > 150 ? "#111" : "#fff";
}
function badge(team) {
  const s = styleOf(team), col = s.color || "#777777";
  if (s.logo) return `<span class="badge" style="background:#fff"><img src="${esc(s.logo)}" alt="" loading="lazy"></span>`;
  const ab = (s.abbr || String(team).replace(/[^A-Za-z ]/g, "").split(" ").map(w => w[0]).join("").slice(0, 3)).toUpperCase();
  return `<span class="badge" style="background:${esc(col)};color:${textOn(col)};border-color:${esc(s.alt || col)}" aria-hidden="true">${esc(ab)}</span>`;
}
function pitchSVG(team, e) {
  const players = (e.ours || []), col = styleOf(team).color || "#3b82f6", tc = textOn(col);
  const g = p => { const x = String(p.Pos || "M").toUpperCase()[0]; return "GDMF".includes(x) ? x : "M"; };
  const rows = ["F", "M", "D", "G"].map(k => players.filter(p => g(p) === k)).filter(r => r.length);
  const W = 300, H = 230, short = n => { const w = String(n).split(" "); return w.length > 1 ? w[w.length - 1] : n; };
  let dots = "";
  rows.forEach((row, ri) => {
    const y = 28 + ri * ((H - 56) / Math.max(rows.length - 1, 1));
    row.forEach((p, i) => {
      const x = (W / (row.length + 1)) * (i + 1), op = (0.35 + 0.65 * Math.min(1, p.p || 0)).toFixed(2), doubt = (p.p || 0) < 0.6;
      dots += `<g opacity="${op}"><circle cx="${x}" cy="${y}" r="11" fill="${esc(col)}" stroke="#fff" stroke-width="1.5"/>
        <text x="${x}" y="${y + 3.5}" font-size="9" text-anchor="middle" fill="${tc}" font-weight="700">${Math.round(100 * (p.p || 0))}</text>
        <text x="${x}" y="${y + 23}" font-size="9.5" text-anchor="middle" fill="currentColor">${esc(short(p.Player))}${doubt ? " ⚠" : ""}</text></g>`;
    });
  });
  return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(team)} expected lineup">
    <rect x="2" y="2" width="${W - 4}" height="${H - 4}" rx="8" fill="var(--home-soft, rgba(34,139,34,0.12))" stroke="var(--line)"/>
    <line x1="2" y1="${H / 2}" x2="${W - 2}" y2="${H / 2}" stroke="var(--line)"/><circle cx="${W / 2}" cy="${H / 2}" r="26" fill="none" stroke="var(--line)"/>
    <rect x="${W / 2 - 55}" y="${H - 40}" width="110" height="38" fill="none" stroke="var(--line)"/><rect x="${W / 2 - 55}" y="2" width="110" height="38" fill="none" stroke="var(--line)"/>
    ${dots}</svg>`;
}
function lastTimeHTML(m) {
  const T = (D.last_time || {})[keyOf(m)];
  if (!T) return "";
  const side = (s, team) => {
    const e = T[s]; if (!e) return "";
    return `<div class="lasttime">${badge(team)}<strong>${esc(team)}</strong> ${e.venue === "H" ? "v" : "at"} ${esc(e.opp)} (${day(e.date)}): ` +
      e.picks.map(p => `<span class="${p.won ? "hit" : "miss"}">${p.won ? "✓" : "✗"} ${esc(p.Bet)} (${pct(p.p)})${p.kind === "safer" ? " [safer]" : ""}</span>`).join(" · ") + `</div>`;
  };
  return `<details class="sg"><summary>Last time out: the verdict's picks</summary>${side("home", m.Home)}${side("away", m.Away)}
    <div class="booklabel">How the verdict's picks did in each team's previous match (✓ hit, ✗ missed). A pick hitting last time doesn't make it likelier to hit again: each match is predicted on its own.${(() => { const S = D.bet_history || {}; return S.best ? ` Overall, top picks hit ${S.best.hit.toFixed(0)}% of ${S.best.n} vs ${S.best.expected.toFixed(0)}% the model expected${S.safer ? `; safer picks ${S.safer.hit.toFixed(0)}% vs ${S.safer.expected.toFixed(0)}%` : ""}: a hit rate close to the expected one means the probabilities are honest, not that the picks are profitable.` : ""; })()}</div></details>`;
}
function moreHTML(m) {
  const M = (D.markets || {})[keyOf(m)];
  if (!M || !M.length) return "";
  const fam = {shots: "Shots", sot: "Shots on target", fouls: "Fouls", halftime: "Half-time", halftime_both: "Half-time", timing: "Timing", penalty: "Penalties",
               player_props: "Player props", first_scorer: "First goalscorer", throwins: "Throw-ins"};
  const groups = [...new Set(M.map(x => fam[x.family] || x.family))];
  return `<details class="sg"><summary>More markets (${M.length})</summary>${groups.map(g => `<div class="tt" style="margin-top:6px">${esc(g)}</div>` +
    M.filter(x => (fam[x.family] || x.family) === g).map(x => `<div class="line" style="font-size:0.88rem">${esc(x.Bet)}: <strong>${pct(x.p)}</strong> · fair odds ${x.fair.toFixed(2)} <span class="noedge">${x.trusted ? "calibrated" : "experimental"}</span></div>`).join("")).join("")}
    <div class="booklabel">Fair odds = break-even price. "Calibrated" means the probabilities matched reality in testing (within 3 points in every band); value against bookmakers is untested, as we have no prices for these markets.</div></details>`;
}
function verdictHTML(m) {
  const V = (D.verdicts || {})[keyOf(m)];
  if (!V || !(V.best || []).length) return "";
  const li = b => `<li><strong>${esc(b.Bet)}</strong>: ${pct(b.p)} · fair odds <strong>${b.fair.toFixed(2)}</strong>${b.price ? ` · best price ${b.price.toFixed(2)} (${b.value >= 0 ? "+" : ""}${(100 * b.value).toFixed(0)}% value)` : ""}
      <div class="ev">${esc(b.evidence)}</div>${(b.reasons || []).length ? `<ul class="why">${b.reasons.map(r => `<li>${esc(r)}</li>`).join("")}</ul>` : ""}</li>`;
  const S = D.verdict_summary || {}, best = S.best;
  return `<div class="verdict"><div class="vt">Match verdict</div><ol>${V.best.map(li).join("")}</ol>
    ${V.safer ? `<div class="line"><strong>Safer angle:</strong> ${esc(V.safer.Bet)} (${pct(V.safer.p)}): only worth it at <strong>${(1.05 * V.safer.fair).toFixed(2)}</strong> or better.</div>` : ""}
    ${(V.avoid || []).map(a => `<div class="line"><strong>Avoid:</strong> ${esc(a)}</div>`).join("")}
    <div class="ev">The model's view, not a guaranteed winner; no edge over the bookmakers has been confirmed yet. Fair odds = the price at which a bet breaks even; only prices above it offer value.${best ? ` Track record of its top picks: won ${best.hit.toFixed(0)}% of ${best.settled} vs ${best.expected.toFixed(0)}% expected.` : ""} Not financial advice.</div></div>`;
}
function betHTML(m) {
  const B = (D.bet_check || {})[keyOf(m)];
  if (!B || !B.length) return "";
  const icon = {green: "🟢", yellow: "🟡", white: "⚪", implausible: "⚠️"}, word = {green: "confirmed edge", yellow: "unproven", white: "no value", implausible: "implausible"};
  return `<details class="sg"${B.some(b => b.Verdict === "green") ? " open" : ""}><summary>Bet check ${B.some(b => b.Verdict === "green") ? "🟢" : (B.some(b => b.Verdict === "yellow") ? "🟡" : "⚪")}</summary>
    <div class="table-scroll"><table><thead><tr><th>Bet</th><th>Best price</th><th>Model</th><th>Value</th><th>Verdict</th><th>Stake</th></tr></thead><tbody>${B.map(b => `<tr><td style="text-align:left">${esc(b.Bet)}</td><td>${b.Price.toFixed(2)} <span class="vs">${esc(b.Bookmaker || "")}</span></td><td>${pct(b.Model)}</td><td>${b.EV >= 0 ? "+" : ""}${(100 * b.EV).toFixed(0)}%</td><td>${icon[b.Verdict]} ${word[b.Verdict]}</td><td>${b.Stake ? b.Stake + "u" : "–"}</td></tr>`).join("")}</tbody></table></div>
    <div class="booklabel">Green only where our tests have confirmed an edge for this kind of bet; yellow is the model's view, unproven. Information, not financial advice.</div></details>`;
}
function xiHTML(m) {
  const X = (D.expected_xi || {})[keyOf(m)];
  if (!X) return "";
  const notes = s => { const e = X[s] || {}, pa = e.pitchapi;
    return `${e.rotation ? `<div class="booklabel">⚠ ${esc(e.rotation)}</div>` : ""}${(e.doubts || []).length ? `<div class="booklabel">Doubts: ${e.doubts.map(esc).join(", ")}</div>` : ""}` +
      (pa ? `<div class="booklabel">PitchAPI (${esc(pa.kind)}${pa.formation ? ", " + esc(pa.formation) : ""})${(pa.only_pitchapi || []).length || (pa.only_ours || []).length ? `: differs, has ${(pa.only_pitchapi || []).map(esc).join(", ") || "–"}; we expect ${(pa.only_ours || []).map(esc).join(", ") || "–"}` : ": same eleven"}</div>` : ""); };
  const acc = D.xi_acc || {};
  return `<details class="sg"><summary>Expected lineups</summary><div class="pitchwrap">
      <div><div class="tt">${badge(m.Home)}${esc(m.Home)}</div>${X.home ? pitchSVG(m.Home, X.home) : ""}${notes("home")}</div>
      <div><div class="tt">${badge(m.Away)}${esc(m.Away)}</div>${X.away ? pitchSVG(m.Away, X.away) : ""}${notes("away")}</div></div>
    <div class="booklabel">Numbers are each player's chance of starting (%); paler and ⚠ = less certain. Method: ${esc(acc.best || "")}.${acc.model != null ? ` Tested on the last 100 days: ${acc.model.toFixed(0)}% of starters right (previous method ${acc.model_vs.toFixed(0)}%)${acc.model_cong != null ? `; in busy weeks ${acc.model_cong.toFixed(0)}% vs ${acc.adjusted_cong.toFixed(0)}%` : ""}.` : (acc.matches ? ` Past accuracy: ${Math.max(acc.ours, acc.last_xi, acc.adjusted || 0).toFixed(0)}% of starters.` : "")}</div></details>`;
}
function scorersHTML(m) {
  const S = (D.scorers || {})[[m.Competition, String(m.Date).slice(0, 10), m.Home, m.Away].join("|")];
  if (!S || (!S.home && !S.away)) return "";
  const f = arr => (arr || []).slice(0, 3).map(p => `${esc(p.Player)} ${pct(p.p)}`).join(", ");
  const tag = (D.scorer_cal || {}).trusted ? "" : ` <span class="noedge">(experimental)</span>`;
  const atag = (D.assist_cal || {}).trusted ? "" : ` <span class="noedge">(experimental)</span>`;
  const ah = S.home_assist || [], aa = S.away_assist || [];
  return `<div class="scorers">Likeliest scorers${tag}: ${S.home && S.home.length ? `${esc(m.Home)}: ${f(S.home)}` : ""}${S.home && S.home.length && S.away && S.away.length ? " · " : ""}${S.away && S.away.length ? `${esc(m.Away)}: ${f(S.away)}` : ""}</div>` +
    (ah.length || aa.length ? `<div class="scorers">Likeliest assisters${atag}: ${ah.length ? `${esc(m.Home)}: ${f(ah)}` : ""}${ah.length && aa.length ? " · " : ""}${aa.length ? `${esc(m.Away)}: ${f(aa)}` : ""}</div>` : "");
}
function trendTable(T) {
  if (!T) return `<div class="hint">No recent matches in our data.</div>`;
  const ar = k => T.arrows && T.arrows[k] ? `<span class="${T.arrows[k]}">${T.arrows[k] === "up" ? "▲" : "▼"}</span>` : "";
  const st = T.stats, n = v => v == null ? "–" : v.toFixed(1);
  let rows = "", prevLS = null;
  for (const r of T.rows) {
    if (prevLS === true && !r.LastSeason) rows += `<tr><td colspan="6" class="vs">— new season —</td></tr>`;
    rows += `<tr class="${r.LastSeason ? "ls" : ""}"><td>${day(r.Date)}</td><td>${esc(r.Comp)}</td><td>${r.Venue}</td><td style="text-align:left">${esc(r.Opponent)}</td><td><strong>${esc(r.Score)}</strong> ${r.Result}</td><td>${r.xG ? esc(r.xG) : "–"}</td></tr>`;
    prevLS = r.LastSeason;
  }
  return `<div class="tt">${esc(T.team)}: ${esc(T.form.split("").reverse().join(""))} · ${T.ppg.toFixed(2)} pts/game</div>
    <div class="table-scroll"><table><thead><tr><th>Date</th><th>Comp</th><th></th><th>Opponent</th><th>Score</th><th>xG</th></tr></thead><tbody>${rows}</tbody></table></div>
    ${(T.spotted || []).length ? `<div class="spotted"><strong>Spotted:</strong> ${T.spotted.map(s => `${esc(s.pattern)} in ${s.count}/${s.of} (${esc(s.scope)}${s.league_rate != null ? `; league usually ${Math.round(100 * s.league_rate)}%` : ""})`).join(" · ")}</div>` : ""}
    <div class="booklabel">Last ${T.rows.length} vs season: goals ${n(st.GF[0])}-${n(st.GA[0])} ${ar("GF")}${ar("GA")} (season ${n(st.GF[1])}-${n(st.GA[1])})${st.xGF[0] != null ? ` · xG ${n(st.xGF[0])}-${n(st.xGA[0])} ${ar("xGF")}${ar("xGA")}` : ""}${st.ShotsF[0] != null ? ` · shots ${n(st.ShotsF[0])}-${n(st.ShotsA[0])}` : ""}${T.perf != null ? ` · goals minus xG ${T.perf >= 0 ? "+" : ""}${T.perf.toFixed(2)}/game` : ""} · home ${esc(T.home)}, away ${esc(T.away)}</div>`;
}
function trendHTML(m) {
  const TR = D.trends || {};
  if (!TR[m.Home] && !TR[m.Away]) return "";
  return `<details class="sg"><summary>Last 7 matches (all competitions)</summary><div class="trend2"><div>${trendTable(TR[m.Home])}</div><div>${trendTable(TR[m.Away])}</div></div></details>`;
}
function sortableTable(el, rows, cols, fmt) {
  let key = cols[1], dir = -1;
  const draw = () => {
    const R = [...rows].sort((a, b) => ((a[key] ?? -1e9) > (b[key] ?? -1e9) ? 1 : -1) * dir);
    el.innerHTML = `<div class="table-scroll"><table><thead><tr>${cols.map(c => `<th class="sortable" data-k="${esc(c)}">${esc(c)}${c === key ? (dir < 0 ? " ▼" : " ▲") : ""}</th>`).join("")}</tr></thead><tbody>${R.map(r => `<tr>${cols.map(c => `<td${typeof r[c] === "string" ? ' style="text-align:left"' : ""}>${fmt(c, r[c])}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`;
    el.querySelectorAll("th.sortable").forEach(th => th.onclick = () => { if (key === th.dataset.k) dir = -dir; else { key = th.dataset.k; dir = -1; } draw(); });
  };
  draw();
}
function renderTeams() {
  const el = document.getElementById("pane-teams"), T = D.teams_table || [];
  if (!T.length) { el.innerHTML = `<div class="empty"><strong>No team data yet</strong></div>`; return; }
  const leagues = [...new Set(T.map(r => r.League))];
  el.innerHTML = `<p class="hint">Every team's last 7 competitive matches (league, cups and Europe). Click a column to sort. "Goals minus xG" above zero means scoring more than the chances suggest, which often evens out.</p>
    <div class="ctrl"><label>League <select id="tm-lg"><option value="">All</option>${leagues.map(l => `<option>${esc(l)}</option>`).join("")}</select></label></div><div id="tm-t"></div>`;
  const fmt = (c, v) => v == null ? "–" : (typeof v === "number" ? (c.startsWith("PPG") || c.includes("xG") || c.startsWith("Goals") ? v.toFixed(2) : v.toFixed(1)) : (c === "Form" ? esc(String(v).split("").reverse().join("")) : esc(v)));
  const cols = ["Team", "PPG (last 7)", "Form", "Goals for", "Goals against", "xG for", "xG against", "Goals minus xG", "xG for vs season", "Shots for", "Corners for", "League"];
  const draw = () => { const l = document.getElementById("tm-lg").value; sortableTable(document.getElementById("tm-t"), T.filter(r => !l || r.League === l), cols, fmt); };
  document.getElementById("tm-lg").onchange = draw; draw();
}
function renderPlayers() {
  const el = document.getElementById("pane-players"), P = D.players || [], LB = D.leaderboards || {};
  if (!P.length && !Object.keys(LB).length) { el.innerHTML = `<div class="empty"><strong>No player data yet</strong></div>`; return; }
  const teams = [...new Set(P.map(p => p.FdTeam))].sort();
  el.innerHTML = `<p class="hint">Squads of teams playing in the coming days: this season, all competitions. xG and xA per 90 are from Understat (big five only). Impact is the goal difference per 90 a player adds (our rating). Status shows likely absences, Premier League injury flags and departures.</p>
    <div class="ctrl"><label>Team <select id="pl-team">${teams.map(t => `<option>${esc(t)}</option>`).join("")}</select></label></div><div id="pl-t"></div>
    ${Object.entries(LB).map(([k, rows]) => rows.length ? `<h3>${esc(k)}</h3><div class="lb" data-k="${esc(k)}"></div>` : "").join("")}`;
  const fmt = (c, v) => v == null ? "–" : (typeof v === "number" ? (Number.isInteger(v) ? v : v.toFixed(2)) : esc(v));
  const cols = ["Player", "Pos", "Apps", "Starts", "Minutes", "Goals", "Assists", "Shots", "G+A per 90", "xG per 90", "xA per 90", "Impact", "Status"];
  const draw = () => { const t = document.getElementById("pl-team").value; sortableTable(document.getElementById("pl-t"), P.filter(p => p.FdTeam === t), cols, fmt); };
  if (teams.length) { document.getElementById("pl-team").onchange = draw; draw(); }
  el.querySelectorAll(".lb").forEach(d => { const rows = LB[d.dataset.k]; sortableTable(d, rows, Object.keys(rows[0]), fmt); });
}
function gridHTML(m) {
  const G = m.Grid, n = G.length, mx = Math.max(...G.flat());
  let h = `<details class="sg"><summary>Score grid (chance of each exact score, %)</summary><table class="grid" aria-label="Score probabilities"><tr><th>${esc(m.Home)} \\ ${esc(m.Away)}</th>${G[0].map((_, j) => `<th>${j}</th>`).join("")}</tr>`;
  for (let i = 0; i < n; i++) {
    h += `<tr><th>${i}</th>` + G[i].map(v => {
      const share = Math.round(85 * v / mx);
      return `<td style="background: color-mix(in srgb, var(--home) ${share}%, var(--surface)); color: ${share > 55 ? "#fff" : "var(--ink)"}">${v >= 0.5 ? Math.round(v) : ""}</td>`;
    }).join("") + "</tr>";
  }
  return h + "</table></details>";
}
function matchHTML(m) {
  const stats = [];
  if (m.ExpHome != null) stats.push(`Expected goals <strong>${num(m.ExpHome)}–${num(m.ExpAway)}</strong>`);
  const E = D.edge || {}, ne = k => (E[k] != null && E[k] < 2) ? ` <span class="noedge">(no proven edge)</span>` : "";
  if (m.pOver25 != null) stats.push(`Over 2.5 goals <strong>${pct(m.pOver25)}</strong>${ne("Over 2.5")}`);
  if (m.pBTTS != null) stats.push(`Both teams to score <strong>${pct(m.pBTTS)}</strong>${ne("BTTS")}`);
  if (m.ExpCorners != null) stats.push(`Corners <strong>${num(m.ExpCorners)}</strong>, over 9.5 <strong>${pct(m.pOverCorners)}</strong>${ne("Corners")}`);
  if (m.ExpCards != null) stats.push(`Yellow cards ${m.ExpCardsH != null ? `${esc(m.Home)} <strong>${num(m.ExpCardsH)}</strong> – ${esc(m.Away)} <strong>${num(m.ExpCardsA)}</strong>, total ` : ""}<strong>${num(m.ExpCards)}</strong>, over 4.5 <strong>${pct(m.pOverCards)}</strong>${ne("Cards")}`);
  const book = m.bookH != null
    ? `<div class="rowlabel">Bookmakers</div>` + bar(m.bookH, m.bookD, m.bookA, "book") + `<div class="booklabel">${pct(m.bookH)} / ${pct(m.bookD)} / ${pct(m.bookA)} (margin removed)</div>` : "";
  const bw = BW / 100, bh = bw * m.pH + (1 - bw) * m.bookH, bd = bw * m.pD + (1 - bw) * m.bookD, ba = bw * m.pA + (1 - bw) * m.bookA;
  const blendBar = (m.bookH != null && BW < 100)
    ? `<div class="rowlabel">Blend (${BW}% model, ${100 - BW}% market)</div>` + bar(bh, bd, ba, "blend") + `<div class="booklabel">${pct(bh)} / ${pct(bd)} / ${pct(ba)}</div>` : "";
  const flags = [];
  if (maxDiff(m) >= DIFF) flags.push(diffText(m));
  if (m.Note) flags.push(m.Note);
  return `<div class="match">
    <div class="when">${day(m.Date)}</div>
    <div>
      <div class="teams"><span>${badge(m.Home)}${esc(m.Home)}</span><span class="away">${badge(m.Away)}${esc(m.Away)}</span></div>
      <div class="rowlabel model">Model</div>
      ${bar(m.pH, m.pD, m.pA, "")}
      <div class="pcts"><span class="ph"><b>${pct(m.pH)}</b> home</span><span class="pd">draw <b>${pct(m.pD)}</b></span><span class="pa">away <b>${pct(m.pA)}</b></span></div>
      ${book}
      ${blendBar}
      <div class="stats">${stats.map(s => `<span>${s}</span>`).join("")}</div>
      ${m.Absent ? `<div class="absent">${esc(m.Absent)}</div>` : ""}
      ${verdictHTML(m)}
      ${scorersHTML(m)}
      ${moreHTML(m)}
      ${xiHTML(m)}
      ${lastTimeHTML(m)}
      ${trendHTML(m)}
      ${m.Grid ? gridHTML(m) : ""}
      ${flags.map(f => `<div class="flag">${esc(f)}</div>`).join("<br>")}
    </div>
  </div>`;
}
const compSel = document.getElementById("comp"), differ = document.getElementById("differ");
const comps = ORDER.filter(c => preds.some(m => m.Competition === c));
compSel.innerHTML = `<option value="">All competitions (${preds.length})</option>` +
  comps.map(c => `<option value="${esc(c)}">${esc(c)} (${preds.filter(m => m.Competition === c).length})</option>`).join("");
function renderPred() {
  const sel = compSel.value, onlyDiff = differ.checked;
  const out = comps.filter(c => !sel || c === sel).map(c => {
    const ms = preds.filter(m => m.Competition === c && (!onlyDiff || maxDiff(m) >= DIFF)).sort((x, y) => x.Date.localeCompare(y.Date));
    if (!ms.length) return "";
    return `<section class="comp"><h2>${esc(c)}<span>${ms.length} ${ms.length === 1 ? "match" : "matches"}</span></h2>${ms.map(matchHTML).join("")}</section>`;
  }).join("");
  document.getElementById("pred-list").innerHTML = out || (preds.length
    ? `<div class="empty"><strong>No matches here</strong>No fixtures match these filters. Choose another competition or untick the bookmaker filter.</div>`
    : `<div class="empty"><strong>No fixtures yet</strong>The fixtures file usually updates a few days before the weekend. Run the notebook again then, or add fixtures by hand in MANUAL_FIXTURES.</div>`);
}
let BW = 100;
function renderBlendBox() {
  const el = document.getElementById("blendbox"), C = D.blend_curves || {}, W = D.blend || {};
  const groups = Object.keys(C);
  if (!groups.length) { el.hidden = true; return; }
  const learned = W.Domestic ? Math.round(100 * W.Domestic.w) : Math.round(100 * W[groups[0]].w);
  if (renderBlendBox.first !== false) { BW = 100; renderBlendBox.first = false; }
  const w_ = 300, h_ = 130, pad = 26, all = groups.flatMap(g => C[g].map(p => p.ll)), lo = Math.min(...all), hi = Math.max(...all);
  const sx = v => pad + (w_ - 2 * pad) * v, sy = v => h_ - pad - (h_ - 2 * pad) * (hi === lo ? 0.5 : (v - lo) / (hi - lo));
  const colors = ["var(--home)", "var(--away)", "var(--warn)", "var(--muted)"];
  const lines = groups.map((g, i) => `<polyline fill="none" stroke="${colors[i % 4]}" stroke-width="2" points="${C[g].map(p => `${sx(p.w)},${sy(p.ll)}`).join(" ")}"><title>${esc(g)}</title></polyline>`).join("");
  el.innerHTML = `<div><div class="bl-title">Model + market blend</div>
      <label>Model's share: <strong id="bwv">${BW}%</strong><input type="range" id="bw" min="0" max="100" step="5" value="${BW}" aria-label="Model share in the blend"></label>
      <button class="more" id="bw-learned" style="margin:6px 0 0">Use learned mix (${learned}% model)</button>
      <p class="hint" style="margin:4px 0 0">100% shows the pure model (the independent view). Lower values mix in the bookmakers. Learned best mix: ${groups.map(g => `${esc(g)} ${Math.round(100 * (W[g] || {}).w)}% model`).join(", ")}.${groups.some(g => (W[g] || {}).w === 0) ? " <strong>Where the learned share is 0%, the market currently carries all the weight: the model adds nothing to the bookmakers' prices there yet.</strong>" : ""} The blend is a best estimate, not an independent view.</p></div>
    <div><svg viewBox="0 0 ${w_} ${h_}" role="img" aria-label="Accuracy at each blend weight" style="width:100%;height:auto">
      <line x1="${sx(BW / 100)}" y1="${pad - 8}" x2="${sx(BW / 100)}" y2="${h_ - pad}" stroke="var(--ink)" stroke-dasharray="3 3"/>
      ${lines}
      <text x="${pad}" y="${h_ - 6}" font-size="10" fill="var(--muted)">0% model</text><text x="${w_ - pad}" y="${h_ - 6}" text-anchor="end" font-size="10" fill="var(--muted)">100% model</text>
      <text x="${pad}" y="12" font-size="10" fill="var(--muted)">log loss this season (lower is better)</text></svg>
      <div class="booklabel">${groups.map((g, i) => `<span style="color:${colors[i % 4]}">&#9644;</span> ${esc(g)}`).join(" &nbsp; ")}</div></div>`;
  document.getElementById("bw").oninput = e => { BW = +e.target.value; document.getElementById("bwv").textContent = BW + "%"; renderBlendBox(); renderPred(); };
  document.getElementById("bw-learned").onclick = () => { BW = learned; renderBlendBox(); renderPred(); };
}
compSel.onchange = renderPred; differ.onchange = renderPred; renderBlendBox(); renderPred();

function renderSim() {
  const S = D.sim, s = S.summary, el = document.getElementById("pane-sim");
  if (!S.table.length) { el.innerHTML = `<div class="empty"><strong>Nothing to simulate yet</strong>The simulation covers Saturday and Sunday fixtures. Run the notebook again once the weekend's fixtures are available.</div>`; return; }
  const tops = (s.top || []).map(t => `<p>The ${t.k} strongest favourites all win in <strong>${num(t.chance, 0)}%</strong> of simulated weekends (${t.matches.map(esc).join(", ")}).</p>`).join("");
  el.innerHTML = `<div class="summary">
      <p>Each of the ${s.matches} weekend matches was played 10,000 times using the model's numbers.</p>
      <p>A typical weekend has about <strong>${num(s.home, 0)} home wins, ${num(s.draws, 0)} draws and ${num(s.away, 0)} away wins</strong>, with around <strong>${num(s.goals, 0)} goals</strong> in total (usually between ${num(s.goals_lo, 0)} and ${num(s.goals_hi, 0)}).</p>
      <p>The model's favourite wins about <strong>${num(s.fav_wins, 0)} of the ${s.matches}</strong> matches.</p>${tops}
    </div>` + ORDER.filter(c => S.table.some(r => r.Competition === c)).map(c => {
      const rs = S.table.filter(r => r.Competition === c);
      return `<section class="comp"><h2>${esc(c)}<span>${rs.length} ${rs.length === 1 ? "match" : "matches"}</span></h2>` + rs.map(r => `
        <div class="sim-row">
          <div class="teams"><span>${esc(r.Home)} v ${esc(r.Away)}</span></div>
          <div class="result">${esc(r["One simulated result"])}<small>one simulation</small></div>
          <div class="likely">${day(r.Date)}. Likeliest scores: ${esc(r["Likely scores"])}</div>
        </div>`).join("") + `</section>`;
    }).join("");
}
function weeklyTable(list, firstCol) {
  const cols = [["Matches", 0], ["Model log loss", 3], ["Blend log loss", 3], ["Bookie log loss", 3], ["Gap to bookie", 3], ["Top pick %", 0], ["Over 2.5 %", 0], ["Corners 9.5 %", 0], ["Cards 4.5 %", 0]];
  const labels = {"Top pick %": "Favourite won", "Over 2.5 %": "Over 2.5 right", "Corners 9.5 %": "Corners right", "Cards 4.5 %": "Cards right"};
  const NAIVE = {"Over 2.5 %": "Over 2.5 naive %", "Corners 9.5 %": "Corners naive %", "Cards 4.5 %": "Cards naive %"};
  let row = null;
  const cell = (k, v, d) => {
    if (v == null) return "<td>–</td>";
    let cls = "", extra = "";
    if (k === "Gap to bookie") cls = v <= 0 ? "good" : (v > 0.03 ? "bad" : "");
    if (NAIVE[k] && row && row[NAIVE[k]] != null) {
      const nv = row[NAIVE[k]];
      cls = v >= nv + 2 ? "good" : (v <= nv - 2 ? "bad" : "");
      extra = `<span class="vs"> vs ${Math.round(nv)}%</span>`;
    }
    return `<td class="${cls}">${Number(v).toFixed(d)}${k.endsWith("%") ? "%" : ""}${extra}</td>`;
  };
  const head = firstCol === "week" ? "<th>Week</th><th>Group</th>" : "<th>Competition</th><th></th>";
  if (firstCol === "week") {
    list = [...list].sort((x, y) => {
      const tx = x["Week of"] === "ALL WEEKS", ty = y["Week of"] === "ALL WEEKS";
      if (tx !== ty) return tx ? -1 : 1;
      return String(y["Week of"]).localeCompare(String(x["Week of"])) || String(x.Group).localeCompare(String(y.Group));
    });
  }
  const rows = list.map(r => {
    const total = r["Week of"] === "ALL WEEKS";
    const first = firstCol === "week"
      ? `<td>${total ? "All weeks" : "Week of " + day(r["Week of"])}</td><td>${esc(r.Group)}</td>`
      : `<td>${esc(r.Competition)}</td><td></td>`;
    row = r;
    return `<tr class="${total ? "total" : ""}">${first}${cols.map(([k, d]) => cell(k, r[k], d)).join("")}</tr>`;
  }).join("");
  return `<div class="table-scroll"><table><thead><tr>${head}${cols.map(([k]) => `<th>${labels[k] || k}</th>`).join("")}</tr></thead><tbody>${rows}</tbody></table></div>`;
}
function renderScore() {
  const S = D.scorecard, B = D.backtest, el = document.getElementById("pane-score");
  let out = `<p class="hint">Log loss measures how good the probabilities were: lower is better. The gap is model minus bookmaker on the same matches, so below zero means the model did better. For over/under, "vs" shows how often simply guessing each league's usual side was right: the model only adds value where it beats that number (green).</p>`;
  if (B.weekly.length) {
    out += `<h3>This season, replayed</h3>
      <p class="hint">Every match so far this season, predicted one week at a time using only results from before that week. Season totals first, then the most recent weeks.</p>
      ${weeklyTable(B.weekly, "week")}
      <h3>By competition, weakest first</h3>
      ${weeklyTable(B.byComp, "comp")}` + edgeHTML() + extrasHTML() + calibHTML() + biasHTML() + `<h3>Every match this season</h3><div id="mt"></div>`;
  }
  out += `<h3>Live predictions</h3>`;
  if (!S.weekly.length) {
    out += `<div class="empty"><strong>No results yet</strong>Predictions are scored once the matches have been played. Run the notebook again after the next matchday (and re-export the European files after a European matchday).</div>`;
  } else {
    const latest = S.latest.map(r => `<tr><td>${esc(r.Competition)}</td><td>${esc(r.Home)} <span class="score">${esc(r.Score)}</span> ${esc(r.Away)}</td>
        <td>${pct(r.pH)}</td><td>${pct(r.pD)}</td><td>${pct(r.pA)}</td><td><strong>${pct(r.pResult)}</strong></td></tr>`).join("");
    out += `<p class="hint">Predictions logged before kickoff, scored after the match.</p>${weeklyTable(S.weekly, "week")}
      <h3>Latest week, biggest surprises first</h3>
      <p class="hint">The last column is the chance the model gave to what actually happened.</p>
      <div class="table-scroll"><table><thead><tr><th>Competition</th><th>Match</th><th>Home</th><th>Draw</th><th>Away</th><th>Chance of the result</th></tr></thead><tbody>${latest}</tbody></table></div>`;
  }
  const A = D.analyst || {};
  if (A.matches) out += `<h3>Your analyst picks</h3><p class="hint">On ${A.matches} matches you adjusted: model log loss ${A.model.toFixed(3)}, your picks ${A.analyst.toFixed(3)}${A.book != null ? `, bookmakers ${A.book.toFixed(3)}` : ""}. Lower is better.</p>`;
  el.innerHTML = out;
}
function renderReports() {
  const el = document.getElementById("pane-reports"), R = D.reports || [];
  if (!R.length) { el.innerHTML = `<div class="empty"><strong>No match reports yet</strong>Reports are written for each upcoming fixture once fixtures are available.</div>`; return; }
  const comps = ORDER.filter(c => R.some(r => r.Competition === c));
  el.innerHTML = `<p class="hint">One report per fixture, in the format of your analysis prompt, filled with verified data only. "Copy for Claude" copies the report with a short brief: paste it into a chat with Claude (web search on) to confirm team news and add context. If you then disagree with the model, add your percentages to ANALYST_PICKS in Settings, and the scorecard will track whether your adjustments help.</p>` +
    comps.map(c => `<h3>${esc(c)}</h3>` + R.filter(r => r.Competition === c).map((r, i) => `
      <details class="report"><summary><span class="t">${esc(r.Home)} v ${esc(r.Away)}</span><span class="m">${day(r.Date)}</span><span class="conf ${esc(r.Confidence)}">${esc(r.Confidence)} confidence</span></summary>
      <pre>${esc(r.text)}</pre><button class="copy" data-k="${esc(r.Competition)}|${esc(r.Home)}|${esc(r.Away)}">Copy for Claude</button></details>`).join("")).join("");
  el.querySelectorAll(".copy").forEach(b => b.onclick = () => {
    const [c, h, a] = b.dataset.k.split("|");
    const r = R.find(x => x.Competition === c && x.Home === h && x.Away === a);
    const text = D.brief + "\n\n" + r.text;
    const done = () => { b.textContent = "Copied"; setTimeout(() => b.textContent = "Copy for Claude", 1500); };
    if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(text).then(done, () => fallback());
    else fallback();
    function fallback() { const ta = document.createElement("textarea"); ta.value = text; document.body.appendChild(ta); ta.select();
      try { document.execCommand("copy"); done(); } catch (e) { b.textContent = "Select the text above and copy it"; } ta.remove(); }
  });
}
function edgeHTML() {
  const C = D.clv || {}, E = D.edge || {};
  let h = "";
  if (C.matches) h += `<h3>Closing-line check</h3><p class="hint">Between the early odds and kickoff, bookmakers' prices moved toward the model in <strong>${Math.round(C.toward_pct)}%</strong> of ${C.matches} domestic matches (50% would mean the model knows nothing the market doesn't), by ${C.avg_move >= 0 ? "+" : ""}${C.avg_move.toFixed(1)} points on average. Log loss: model ${C.ll_model.toFixed(3)}, early odds ${C.ll_early.toFixed(3)}, closing odds ${C.ll_close.toFixed(3)}.</p>`;
  const k = Object.keys(E);
  if (k.length) h += `<p class="hint">Over/under markets against "always guess the usual side": ${k.map(x => `${esc(x)} ${E[x] >= 0 ? "+" : ""}${E[x].toFixed(1)} points${E[x] < 2 ? " (no proven edge, shown greyed out with predictions)" : ""}`).join("; ")}.</p>`;
  return h;
}
function calibHTML() {
  const C = D.calib || [];
  if (!C.length) return "";
  const outcomes = [...new Set(C.map(c => c.Outcome))];
  const chart = o => {
    const pts = C.filter(c => c.Outcome === o), W = 220, H = 220, pad = 28, sc = v => pad + (W - 2 * pad) * v / 100, sy = v => H - pad - (H - 2 * pad) * v / 100;
    const maxN = Math.max(...pts.map(p => p.Matches));
    return `<div class="calib"><h4>${esc(o)}</h4><svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(o)}: predicted versus actual">
      <line x1="${sc(0)}" y1="${sy(0)}" x2="${sc(100)}" y2="${sy(100)}" stroke="var(--line)" stroke-width="2"/>
      <line x1="${sc(0)}" y1="${sy(0)}" x2="${sc(100)}" y2="${sy(0)}" stroke="var(--muted)" stroke-width="1"/>
      <line x1="${sc(0)}" y1="${sy(0)}" x2="${sc(0)}" y2="${sy(100)}" stroke="var(--muted)" stroke-width="1"/>
      <text x="${W / 2}" y="${H - 6}" text-anchor="middle" font-size="10" fill="var(--muted)">model's %</text>
      <text x="10" y="${H / 2}" text-anchor="middle" font-size="10" fill="var(--muted)" transform="rotate(-90 10 ${H / 2})">actual %</text>
      ${[0, 50, 100].map(v => `<text x="${sc(v)}" y="${sy(0) + 12}" text-anchor="middle" font-size="9" fill="var(--muted)">${v}</text>`).join("")}
      ${pts.map(p => `<circle cx="${sc(p.Predicted)}" cy="${sy(p.Actual)}" r="${3 + 5 * Math.sqrt(p.Matches / maxN)}" fill="var(--home)" fill-opacity="0.75"><title>${p.Band}: model ${p.Predicted.toFixed(0)}%, actual ${p.Actual.toFixed(0)}% (${p.Matches} matches)</title></circle>`).join("")}
    </svg></div>`;
  };
  return `<h3>Model vs actual: calibration</h3><p class="hint">Each dot groups matches where the model gave a similar chance; bigger dots mean more matches. Dots on the diagonal mean "when the model says 40%, it happens about 40% of the time". Dots below it mean the model was too confident; above, too cautious.</p><div class="calib-wrap">${outcomes.map(chart).join("")}</div>`;
}
function biasHTML() {
  const R = D.bias || [], CR = D.cal_result || {};
  if (!R.length) return "";
  const keys = Object.keys(R[0]).filter(k => k !== "Group");
  let h = `<h3>Bias check</h3><p class="hint">The model's average prediction next to what actually happened, by group.</p><div class="table-scroll"><table><thead><tr><th>Group</th><th></th>${keys.map(k => `<th>${esc(k)}</th>`).join("")}</tr></thead><tbody>` +
    R.map(r => `<tr><td>${esc(r.Group)}</td><td></td>${keys.map(k => `<td>${r[k] == null ? "–" : Number(r[k]).toFixed(k === "Matches" ? 0 : (k.startsWith("Goals") ? 2 : 1))}</td>`).join("")}</tr>`).join("") + `</tbody></table></div>`;
  const notes = Object.entries(CR).map(([g, r]) => r.pct == null ? `${esc(g)}: ${esc(r.status)}` :
    `${esc(g)}: correction ${esc(r.status)} (better in ${Math.round(r.pct)}% of reshuffles on later weeks)`);
  if (notes.length) h += `<p class="hint">Automatic corrections, learned on earlier weeks and tested on later ones: ${notes.join("; ")}.</p>`;
  return h;
}
function renderMatchTable() {
  const el = document.getElementById("mt"), M = D.bt_matches || [];
  if (!el || !M.length) return;
  const comps = ORDER.filter(c => M.some(r => r.Competition === c));
  el.innerHTML = `<p class="hint">Every match this season, as the model predicted it before kickoff (replayed), next to the bookmakers and the result. Saved to Drive as a spreadsheet-friendly file too.</p>
    <div class="mt-controls"><label>Show <select id="mt-comp"><option value="">All competitions</option>${comps.map(c => `<option>${esc(c)}</option>`).join("")}</select></label>
    <label>Sort <select id="mt-sort"><option value="recent">Most recent first</option><option value="surprise">Biggest surprises first</option><option value="best">Best calls first</option></select></label></div>
    <div id="mt-table"></div>`;
  let limit = 50;
  const draw = () => {
    const c = document.getElementById("mt-comp").value, so = document.getElementById("mt-sort").value;
    let rows = M.filter(r => !c || r.Competition === c);
    if (so === "surprise") rows = [...rows].sort((a, b) => a.pResult - b.pResult);
    if (so === "best") rows = [...rows].sort((a, b) => b.pResult - a.pResult);
    const shown = rows.slice(0, limit);
    document.getElementById("mt-table").innerHTML = `<div class="table-scroll"><table><thead><tr><th>Date</th><th>Match</th><th>Model H / D / A</th><th>Bookies H / D / A</th><th>Chance given to result</th><th>Over 2.5 (model)</th><th>Goals</th></tr></thead><tbody>${shown.map(r => `
      <tr><td>${day(String(r.Date).slice(0, 10))}</td><td style="text-align:left">${esc(r.Home)} <span class="score">${esc(r.Score)}</span> ${esc(r.Away)}<br><span class="vs">${esc(r.Competition)}</span></td>
      <td>${pct(r.pH)} / ${pct(r.pD)} / ${pct(r.pA)}</td><td>${r.bookH == null ? "–" : `${pct(r.bookH)} / ${pct(r.bookD)} / ${pct(r.bookA)}`}</td>
      <td class="${r.pResult < 0.2 ? "bad" : (r.pResult > 0.5 ? "good" : "")}"><strong>${pct(r.pResult)}</strong></td><td>${r.pOver25 == null ? "–" : pct(r.pOver25)}</td><td>${r.Goals}</td></tr>`).join("")}</tbody></table></div>` +
      (rows.length > limit ? `<button class="more" id="mt-more">Show more (${rows.length - limit} left)</button>` : "");
    const mb = document.getElementById("mt-more");
    if (mb) mb.onclick = () => { limit += 100; draw(); };
  };
  document.getElementById("mt-comp").onchange = () => { limit = 50; draw(); };
  document.getElementById("mt-sort").onchange = () => { limit = 50; draw(); };
  draw();
}
function renderWatch() {
  const el = document.getElementById("pane-watch"), R = (D.reports || []).filter(r => r.Watch && r.Watch.length).sort((a, b) => (b.Score || 0) - (a.Score || 0)).slice(0, 15);
  if (!R.length) { el.innerHTML = `<div class="empty"><strong>Nothing flagged</strong>No upcoming match has a big model-vs-market disagreement, a large player adjustment, fixture congestion or a data warning.</div>`; return; }
  el.innerHTML = `<p class="hint">The ${R.length} matches most worth checking before kickoff, ranked: big disagreements with the market and large player adjustments. Data caveats (no odds yet, thin data, fixture congestion) are shown underneath each, but don't put a match on the list by themselves.</p>` +
    R.map((r, i) => `<div class="watch"><span class="t">${esc(r.Home)} v ${esc(r.Away)}</span> <span class="vs">${esc(r.Competition)}, ${day(r.Date)}</span>
      <ul>${r.Watch.map(w => `<li>${esc(w)}</li>`).join("")}</ul>${(r.Caveats || []).length ? `<div class="booklabel">Caveats: ${r.Caveats.map(esc).join("; ")}</div>` : ""}<button class="copy" data-i="${i}">Copy for Claude</button></div>`).join("");
  el.querySelectorAll(".copy").forEach(b => b.onclick = () => {
    const r = R[+b.dataset.i], text = D.brief + "\n\n" + r.text;
    const done = () => { b.textContent = "Copied"; setTimeout(() => b.textContent = "Copy for Claude", 1500); };
    const fallback = () => { const ta = document.createElement("textarea"); ta.value = text; document.body.appendChild(ta); ta.select();
      try { document.execCommand("copy"); done(); } catch (e) { b.textContent = "Copy failed: open Match reports"; } ta.remove(); };
    if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(text).then(done, fallback); else fallback();
  });
}
function bettingHTML() {
  let h = "";
  const S = D.ledger || {}, O = D.ledger_open || [], X = D.ledger_settled || [];
  if (S.bets != null) {
    h += `<h3>Paper-betting ledger</h3><p class="hint">Bets the model <em>would</em> make: expected value of 3%+ at the best available price, one flat unit each. No real money; this is the test. Closing-line value (CLV) compares the price taken with Pinnacle's last price before kickoff: consistently positive CLV is the fastest sign of a real edge. Expect hundreds of bets before the numbers mean much.</p>
      <div class="summary"><div class="tile"><div class="k">Bets</div><div class="v">${S.bets}</div><div class="s">${S.settled} settled, ${S.open} open</div></div>
      <div class="tile"><div class="k">Profit</div><div class="v ${S.profit >= 0 ? "good" : "bad"}">${S.profit >= 0 ? "+" : ""}${S.profit.toFixed(2)}u</div><div class="s">${S.roi == null ? "" : `ROI ${S.roi >= 0 ? "+" : ""}${S.roi.toFixed(1)}%`}</div></div>
      <div class="tile"><div class="k">CLV vs Pinnacle</div><div class="v ${S.clv == null ? "" : (S.clv > 0 ? "good" : "bad")}">${S.clv == null ? "–" : `${S.clv >= 0 ? "+" : ""}${S.clv.toFixed(1)}%`}</div><div class="s">${S.beat_close == null ? "not enough closing prices yet" : `beat the close ${S.beat_close.toFixed(0)}% of ${S.clv_n}`}</div></div></div>`;
    const row = r => `<tr><td>${day(r.Date)}</td><td style="text-align:left">${esc(r.Home)} v ${esc(r.Away)}<br><span class="vs">${esc(r.Competition)}</span></td><td>${esc(r.Pick)}</td><td>${Number(r.Price).toFixed(2)} <span class="vs">${esc(r.Bookmaker || "")}</span></td><td>${pct(r.ModelProb)}</td><td>+${(100 * r.EV).toFixed(1)}%</td><td>${r.Profit == null ? "open" : `<span class="${r.Profit > 0 ? "good" : "bad"}">${r.Profit > 0 ? "+" : ""}${Number(r.Profit).toFixed(2)}</span>`}</td><td>${r.CLV == null ? "–" : `${r.CLV >= 0 ? "+" : ""}${(100 * r.CLV).toFixed(1)}%`}</td></tr>`;
    const head = `<thead><tr><th>Date</th><th>Match</th><th>Pick</th><th>Price</th><th>Model</th><th>Value</th><th>Result</th><th>CLV</th></tr></thead>`;
    if (O.length) h += `<p class="hint"><strong>Open bets</strong></p><div class="table-scroll"><table>${head}<tbody>${O.map(row).join("")}</tbody></table></div>`;
    if (X.length) h += `<p class="hint"><strong>Latest settled</strong></p><div class="table-scroll"><table>${head}<tbody>${X.map(row).join("")}</tbody></table></div>`;
  }
  const PE = D.probable_errors || [];
  if (PE.length) h += `<p class="hint"><strong>Not logged: probable data errors.</strong> These "edges" were above +25%, which almost always means a wrong team or a stale price rather than an opportunity. Worth a look: ${PE.map(e => `${esc(e.Match)} (${esc(e.Competition)}): ${esc(e.Pick)} at ${Number(e.Price).toFixed(2)}, model ${pct(e.Model)}`).join("; ")}.</p>`;
  const E = D.edge_rows || [];
  if (E.length) h += `<h3>Edge search</h3><p class="hint">Value bets the model would have made this season (replayed), at the best price, by segment. Each segment is checked on the earlier half of the season and must hold on the later half. CLV here is measured against Pinnacle's closing price where available, otherwise the average closing price. Only "CONFIRMED" means anything; everything else is noise until proven otherwise.</p>
    <div class="table-scroll"><table><thead><tr><th>Segment</th><th></th><th>Bets (earlier)</th><th>ROI</th><th>CLV</th><th>Bets (later)</th><th>ROI</th><th>CLV</th><th>Verdict</th></tr></thead><tbody>${E.map(r => {
      const f = v => v == null ? "–" : `${v >= 0 ? "+" : ""}${Number(v).toFixed(1)}%`;
      return `<tr><td>${esc(r.Segment)}</td><td></td><td>${r["Bets (earlier)"]}</td><td>${f(r["ROI % (earlier)"])}</td><td>${f(r["CLV % (earlier)"])}</td><td>${r["Bets (later)"]}</td><td>${f(r["ROI % (later)"])}</td><td>${f(r["CLV % (later)"])}</td><td class="${r.Verdict === "CONFIRMED" ? "good" : ""}">${esc(r.Verdict)}</td></tr>`; }).join("")}</tbody></table></div>`;
  const A = D.adj_check || [], AD = D.adj_decision || {};
  if (A.length) h += `<h3>Player-adjustment check</h3><p class="hint">How big the player adjustments are, by competition (large = a 20%+ change to a team's expected goals). A competition that stands out may have a data problem rather than real team news.${AD.tested_cap ? ` Cap of ±${Math.round(100 * AD.tested_cap)}% tested on the second half of the season: better in ${Math.round(AD.pct)}% of reshuffles, ${AD.cap ? "switched on" : "not adopted"}.` : ""}</p>
    <div class="table-scroll"><table><thead><tr><th>Competition</th><th></th><th>Matches</th><th>Typical size</th><th>Large (20%+)</th><th></th></tr></thead><tbody>${A.map(r => `<tr><td>${esc(r.Competition)}</td><td></td><td>${r.Matches}</td><td>${r["Typical size %"].toFixed(1)}%</td><td>${r["Large (20%+) %"].toFixed(0)}%</td><td class="${r["Stands out"] ? "bad" : ""}">${r["Stands out"] ? "stands out" : ""}</td></tr>`).join("")}</tbody></table></div>`;
  return h;
}
function myOddsHTML() {
  const S = D.my_odds || {};
  if (!S.settled) return "";
  return `<h3>Your odds ledger (niche markets)</h3><p class="hint">Odds you entered in MY_ODDS, scored after the matches: ${S.settled} settled, won ${S.hit.toFixed(0)}% vs ${S.expected.toFixed(0)}% the model expected; ROI ${S.roi_all >= 0 ? "+" : ""}${S.roi_all.toFixed(1)}%${S.value_bets ? `; on bets priced above fair odds (${S.value_bets}): ROI ${S.roi_value >= 0 ? "+" : ""}${S.roi_value.toFixed(1)}%` : ""}. Hundreds of bets are needed before this means much.</p>`;
}
function tablesHTML() {
  return (D.extra_tables || []).map(T => {
    if (!T.rows || !T.rows.length) return "";
    const keys = Object.keys(T.rows[0]);
    const fmt = v => typeof v === "number" ? (Math.abs(v) < 10 && !Number.isInteger(v) ? v.toFixed(4) : (Number.isInteger(v) ? v : v.toFixed(1))) : esc(v);
    return `<h3>${esc(T.title)}</h3><p class="hint">${esc(T.hint || "")}</p><div class="table-scroll"><table><thead><tr>${keys.map(k => `<th>${esc(k)}</th>`).join("")}</tr></thead><tbody>${T.rows.map(r => `<tr>${keys.map(k => `<td>${fmt(r[k])}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`;
  }).join("");
}
function extrasHTML() {
  let h = bettingHTML() + myOddsHTML() + tablesHTML();
  const Dg = D.disagree || [];
  if (Dg.length) h += `<h3>Disagreement record</h3><p class="hint">Outcomes where the model and the early odds differed. If the model's disagreements carry real information, "Actually happened" sits closer to the model than to the market.</p>
    <div class="table-scroll"><table><thead><tr><th>Disagreement</th><th></th><th>Cases</th><th>Model said</th><th>Market said</th><th>Actually happened</th></tr></thead><tbody>${Dg.map(r => {
      const closer = Math.abs(r["Actually happened %"] - r["Model said %"]) < Math.abs(r["Actually happened %"] - r["Market said %"]);
      return `<tr><td>${esc(r.Disagreement)}</td><td></td><td>${r.Cases}</td><td>${r["Model said %"].toFixed(1)}%</td><td>${r["Market said %"].toFixed(1)}%</td><td class="${closer ? "good" : "bad"}">${r["Actually happened %"].toFixed(1)}% (${closer ? "closer to model" : "closer to market"})</td></tr>`; }).join("")}</tbody></table></div>`;
  const T = D.miss_totals || {}, M = D.miss_rows || [];
  const n = Object.keys(T).length;
  if (n) h += `<h3>Miss review</h3><p class="hint">Matches where the model gave the actual result under 25%. Each possible cause is compared with how often it happens in <em>all</em> matches; only a cause that's clearly more common in the misses can explain them.</p>
    <div class="table-scroll"><table><thead><tr><th>Cause</th><th></th><th>In big misses</th><th>In all matches</th><th>Verdict</th></tr></thead><tbody>${Object.entries(T).map(([k, v]) => `<tr><td>${esc(k)}</td><td></td><td>${v.miss_pct.toFixed(0)}%</td><td>${v.all_pct.toFixed(0)}%</td><td class="${v.stands_out ? "bad" : ""}">${v.stands_out ? "stands out" : (k.startsWith("No ") ? "–" : "no more common than usual")}</td></tr>`).join("")}</tbody></table></div>` +
    (M.length ? `<div class="table-scroll"><table><thead><tr><th>Date</th><th>Match</th><th>Chance given</th><th>Likely cause</th></tr></thead><tbody>${M.map(r => `<tr><td>${day(r.Date)}</td><td style="text-align:left">${esc(r.Match)}<br><span class="vs">${esc(r.Competition)}</span></td><td>${pct(r["Chance given"])}</td><td style="text-align:left;white-space:normal">${esc(r["Likely cause"])}</td></tr>`).join("")}</tbody></table></div>` : "");
  return h;
}
function renderHealth() {
  const H = D.health || [], el = document.getElementById("health");
  if (!H.length) return;
  const bad = H.filter(h => !h.ok);
  el.innerHTML = `<details class="health"${bad.length ? " open" : ""}><summary>Data health: <span class="ok">${H.length - bad.length} OK</span>${bad.length ? `, <span class="warn">${bad.length} need${bad.length === 1 ? "s" : ""} attention</span>` : ""}</summary>
    <ul>${[...bad, ...H.filter(h => h.ok)].map(h => `<li><span class="${h.ok ? "ok" : "warn"}">${h.ok ? "✓" : "!"}</span> <strong>${esc(h.source)}</strong>: ${esc(h.detail)}</li>`).join("")}</ul></details>`;
}
renderHealth(); renderSim(); renderWatch(); renderTeams(); renderPlayers(); renderReports(); renderScore(); renderMatchTable();
document.getElementById("sub").textContent =
  `Updated ${new Date(D.updated + "T12:00:00").toLocaleDateString(undefined, {weekday: "long", day: "numeric", month: "long", year: "numeric"})}. ` +
  `${preds.length} ${preds.length === 1 ? "fixture" : "fixtures"} in the next ${D.days} days.`;
const tabs = [...document.querySelectorAll('[role="tab"]')];
tabs.forEach((t, i) => {
  t.onclick = () => {
    tabs.forEach(o => { const on = o === t; o.setAttribute("aria-selected", on); document.getElementById(o.getAttribute("aria-controls")).hidden = !on; });
  };
  t.onkeydown = e => {
    if (e.key === "ArrowRight" || e.key === "ArrowLeft") { const n = tabs[(i + (e.key === "ArrowRight" ? 1 : tabs.length - 1)) % tabs.length]; n.focus(); n.click(); }
  };
});
</script>
</body>
</html>
'''
def _clean(o):
    """v23: NaN/infinite numbers -> null and numpy types -> plain Python, so the page's data is always valid."""
    if isinstance(o, dict):
        return {str(k): _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (float, np.floating)):
        return None if not np.isfinite(o) else float(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    return o
html = DASHBOARD_HTML.replace("__DATA__", json.dumps(_clean(payload), allow_nan=False, default=str).replace("</", "<\\/"))
dash_path = f"{SAVE_DIR}/dashboard.html"
with open(dash_path, "w", encoding="utf-8") as f:
    f.write(html)
print(f"Dashboard saved to {dash_path}")
if DOWNLOAD_DASHBOARD:
    try:
        from google.colab import files
        files.download(dash_path)
    except ImportError:
        pass
if SHOW_DASHBOARD:
    import html as _html
    display(HTML(f'<iframe srcdoc="{_html.escape(html, quote=True)}" '
                 f'style="width:100%; height:900px; border:0;"></iframe>'))

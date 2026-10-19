"""Writes the public data files the web app and the Telegram bot read (site/ in R2, plus a local copy).
Public data never includes bookmaker names or prices: only the model's probabilities and fair odds."""
import os, json, re, unicodedata
import pandas as pd, numpy as np
import storage

PRIVATE_FIELDS = {"bookH", "bookD", "bookA", "pBH", "pBD", "pBA", "BlendW", "EspnH", "EspnD", "EspnA", "B365H", "B365D", "B365A", "Odds"}

def slug(s):
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")

def clean(o):
    if isinstance(o, dict):
        return {str(k): clean(v) for k, v in o.items() if k not in PRIVATE_FIELDS}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (float, np.floating)):
        return None if not np.isfinite(o) else float(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if isinstance(o, (pd.Timestamp,)):
        return o.isoformat()
    return o

def public_verdict(v):
    """Drop bookmaker prices and value from a verdict; keep probabilities, fair odds, evidence and reasons."""
    if not v:
        return v
    v = json.loads(json.dumps(v, default=str))
    for b in (v.get("best") or []) + ([v["safer"]] if v.get("safer") else []):
        b.pop("price", None); b.pop("value", None)
    v["avoid"] = [a for a in v.get("avoid", []) if " at " not in a]          # avoid-lines that quote a bookmaker price
    return v

def export(ns, data_dir, mode):
    P = ns.get("payload")
    if not P:
        print("Export: no dashboard payload this run, nothing exported.")
        return
    site_dir = os.path.join(data_dir, "site")
    os.makedirs(os.path.join(site_dir, "match"), exist_ok=True)
    kick = {}
    fx = ns.get("espn_fx")
    if fx is not None and len(fx) and "Kickoff" in fx:
        for r in fx.itertuples():
            kick[(r.League, str(r.Date)[:10], r.HomeTeam, r.AwayTeam)] = pd.Timestamp(r.Kickoff).strftime("%Y-%m-%dT%H:%M:%SZ")
    get = lambda name, k: (P.get(name) or {}).get("|".join(k))
    # v31: ESPN identifiers for each fixture, so the Worker can follow it live
    espn_ids = {}
    if fx is not None and len(fx) and "event_id" in fx:
        for r in fx.itertuples():
            espn_ids[(r.League, str(r.Date)[:10], r.HomeTeam, r.AwayTeam)] = (r.code, str(r.event_id))
    eu = ns.get("euro_up")
    inv_codes = {v: k for k, v in (ns.get("EURO_CODES") or {}).items()}
    if eu is not None and len(eu) and "event_id" in eu:
        for r in eu.itertuples():
            c_ = inv_codes.get(getattr(r, "Competition", None))
            if c_:
                espn_ids[(r.Competition, str(r.Date)[:10], r.HomeTeam, r.AwayTeam)] = (c_, str(r.event_id))
    matches, details, teams = [], {}, {}
    for m in P.get("predictions", []):
        k = (m["Competition"], str(m["Date"])[:10], m["Home"], m["Away"])
        ms = f"{k[1]}-{slug(k[2])}-v-{slug(k[3])}"
        v = public_verdict(get("verdicts", k))
        xi = get("expected_xi", k) or {}
        row = clean({**{c: m.get(c) for c in ["Competition", "Group", "Date", "Home", "Away", "pH", "pD", "pA", "pBTTS", "pOver25", "ExpHome", "ExpAway",
                                               "ExpCards", "ExpCardsH", "ExpCardsA", "pOverCards", "ExpCorners", "pOverCorners", "Note", "Absent", "Grid"]},
                     "slug": ms, "kickoff": kick.get(k), "league_slug": slug(k[0]), "home_slug": slug(k[2]), "away_slug": slug(k[3]),
                     "espn": dict(zip(["code", "id"], espn_ids[k])) if k in espn_ids else None,
                     "fair": {o: (1 / m[p] if m.get(p) else None) for o, p in [("H", "pH"), ("D", "pD"), ("A", "pA")]},
                     "top_pick": (v.get("best") or [None])[0] if v else None,
                     "confirmed": {s: bool((xi.get(s) or {}).get("confirmed")) for s in ("home", "away")}})
        matches.append({x: row.get(x) for x in ["slug", "Competition", "league_slug", "Date", "kickoff", "Home", "Away", "home_slug", "away_slug", "espn",
                                            "pH", "pD", "pA", "fair", "pBTTS", "pOver25", "top_pick", "confirmed"]})
        details[ms] = clean({"match": row, "verdict": v, "markets": get("markets", k), "expected_xi": xi, "last_time": get("last_time", k),
                             "scorers": get("scorers", k), "trends": {"home": (P.get("trends") or {}).get(k[2]), "away": (P.get("trends") or {}).get(k[3])},
                             "team_style": {t: (P.get("team_style") or {}).get(t) for t in (k[2], k[3])}})
        for t in (k[2], k[3]):
            teams.setdefault(slug(t), {"slug": slug(t), "name": t, "league": k[0], "league_slug": slug(k[0])})
    idx_path = os.path.join(site_dir, "index.json")
    if mode == "lineups" and os.path.exists(idx_path):              # keep matches this quick run didn't recompute
        old = json.load(open(idx_path))
        mine = {m["slug"] for m in matches}
        today = pd.Timestamp.now("UTC").strftime("%Y-%m-%d")
        matches = matches + [m for m in old.get("matches", []) if m["slug"] not in mine and m["Date"][:10] >= today]
        old_teams = json.load(open(os.path.join(site_dir, "teams.json"))) if os.path.exists(os.path.join(site_dir, "teams.json")) else []
        for t in old_teams:
            teams.setdefault(t["slug"], t)
    matches.sort(key=lambda m: (m.get("kickoff") or m["Date"], m["Competition"]))
    meta = clean({"updated": pd.Timestamp.now("UTC").strftime("%Y-%m-%dT%H:%M:%SZ"), "mode": mode, "verdict_summary": P.get("verdict_summary"),
                  "bet_history": P.get("bet_history"), "xi_accuracy": P.get("xi_acc"), "edge": P.get("edge")})
    files = {"site/index.json": {"meta": meta, "matches": matches}, "site/teams.json": sorted(teams.values(), key=lambda t: t["name"]),
             "site/schedule.json": [{"slug": m["slug"], "kickoff": m["kickoff"], "date": m["Date"][:10], "competition": m["Competition"],
                                     "league_slug": m["league_slug"], "home_slug": m["home_slug"], "away_slug": m["away_slug"], "espn": m.get("espn"),
                                     "pH": m.get("pH"), "pD": m.get("pD"), "pA": m.get("pA"),
                                     "home": m["Home"], "away": m["Away"]} for m in matches]}
    for ms, d in details.items():
        files[f"site/match/{ms}.json"] = d
    n_up = 0
    for key, obj in files.items():
        body = json.dumps(obj, ensure_ascii=False, allow_nan=False, default=str)
        local = os.path.join(data_dir, key)
        os.makedirs(os.path.dirname(local), exist_ok=True)
        open(local, "w").write(body)
        n_up += storage.put_public(key, body.encode("utf-8"))
    print(f"Export: {len(matches)} matches, {len(details)} match files, {len(teams)} teams written" + (f"; {n_up} uploaded to R2." if n_up else " (local only)."))
    # v32: the website's other pages, each file uploaded only when its contents changed
    def write(key, obj):
        body = json.dumps(obj, ensure_ascii=False, allow_nan=False, default=str)
        local = os.path.join(data_dir, key)
        if os.path.exists(local) and open(local, encoding="utf-8").read() == body:
            return 0
        os.makedirs(os.path.dirname(local), exist_ok=True)
        open(local, "w", encoding="utf-8").write(body)
        storage.put_public(key, body.encode("utf-8"))
        return 1
    try:
        import export_pages
        export_pages.build(ns, data_dir, mode, write, slug, clean)
    except Exception:
        import traceback; traceback.print_exc()
        print("Website pages: failed this run (match pages and the bot are unaffected).")

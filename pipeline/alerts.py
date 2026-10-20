"""Sends match alerts to @kwalloAI_bot followers, after each pipeline run.
Two alerts per match: a PREVIEW (about a day before: probabilities, top angle, expected lineups) and LINEUPS (once the
official lineups are out, about 75 minutes before kickoff in the Premier League). Each is sent once per person per match.
Informational only: probabilities and fair odds, no bookmakers."""
import os, json, time, html
import requests, pandas as pd
PREMIUM_ENABLED = os.environ.get("PREMIUM_ENABLED", "0").strip().lower() in ("1", "true", "yes", "on")   # v31: off until premium launches

def _stat(metric, n):
    """v31: daily totals for /stats in the bot (counts only, nothing about individuals)."""
    url, key = os.environ.get("WORKER_URL"), os.environ.get("PIPELINE_KEY")
    if not url or not key or not n:
        return
    try:
        url = url.strip().rstrip("/")
        url = url if url.lower().startswith("http") else "https://" + url
        requests.post(f"{url}/api/stats", headers={"X-Pipeline-Key": key}, json={"metric": metric, "n": int(n)}, timeout=15)
    except Exception:
        pass

def _subs():
    url, key = os.environ.get("WORKER_URL"), os.environ.get("PIPELINE_KEY")
    if not url or not key:
        return None
    url = url.strip().rstrip("/")
    while url.lower().startswith(("https://https", "http://https", "https://http")):   # v29: forgive a doubled "https://"
        url = url.split("://", 1)[1]
    if url.lower().startswith("https//"):
        url = url[len("https//"):]
    if not url.lower().startswith("http"):
        url = "https://" + url
    r = requests.get(f"{url.rstrip('/')}/api/subscribers", headers={"X-Pipeline-Key": key}, timeout=30)
    r.raise_for_status()
    return r.json()

def _send(token, chat_id, text):
    r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage", timeout=30,
                      json={"chat_id": chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True})
    if r.status_code == 429:                                    # Telegram asks us to slow down
        time.sleep(int(r.json().get("parameters", {}).get("retry_after", 3)) + 1)
        return _send(token, chat_id, text)
    return r.status_code == 200

def _pct(p):
    return f"{100 * p:.0f}%" if p is not None else "-"

def _xi_line(xi, side):
    e = (xi or {}).get(side) or {}
    names = [p["Player"].split(" ")[-1] for p in e.get("ours", [])][:11]
    return ", ".join(names) if names else "not available"

def preview_text(d, site):
    m, v = d["match"], d.get("verdict") or {}
    lines = [f"<b>{html.escape(m['Home'])} v {html.escape(m['Away'])}</b> · {html.escape(m['Competition'])}",
             f"Kickoff: {m['kickoff'][11:16] + ' UTC' if m.get('kickoff') else m['Date'][:10]}",
             f"Chances: {html.escape(m['Home'])} {_pct(m.get('pH'))} · draw {_pct(m.get('pD'))} · {html.escape(m['Away'])} {_pct(m.get('pA'))}"]
    if v.get("best") and not PREMIUM_ENABLED:                     # v31: the top angle is premium once premium launches
        b = v["best"][0]
        lines.append(f"Top angle: {html.escape(b['Bet'])} ({_pct(b['p'])}, worth it at {b['fair']:.2f} or better)")
    xi = d.get("expected_xi")
    if xi:
        lines += [f"Expected XI {html.escape(m['Home'])}: {html.escape(_xi_line(xi, 'home'))}", f"Expected XI {html.escape(m['Away'])}: {html.escape(_xi_line(xi, 'away'))}"]
    if site:
        lines.append(f'<a href="{site.rstrip("/")}/match/{m["slug"]}">Full preview</a>')
    lines.append("<i>Kwallo · football, decoded. Model probabilities, not guarantees. 18+.</i>")
    return "\n".join(lines)

def lineups_text(d, site):
    m, v = d["match"], d.get("verdict") or {}
    lines = [f"<b>Lineups are out: {html.escape(m['Home'])} v {html.escape(m['Away'])}</b>"]
    for s, t in [("home", m["Home"]), ("away", m["Away"])]:
        e = (d.get("expected_xi") or {}).get(s) or {}
        lines.append(f"{html.escape(t)}{' (confirmed)' if e.get('confirmed') else ' (expected)'}: {html.escape(_xi_line(d.get('expected_xi'), s))}")
    lines.append(f"Updated chances: {html.escape(m['Home'])} {_pct(m.get('pH'))} · draw {_pct(m.get('pD'))} · {html.escape(m['Away'])} {_pct(m.get('pA'))}")
    if v.get("best") and not PREMIUM_ENABLED:                     # v31: the top angle is premium once premium launches
        b = v["best"][0]
        lines.append(f"Top angle now: {html.escape(b['Bet'])} ({_pct(b['p'])}, worth it at {b['fair']:.2f} or better)")
    if m.get("kickoff"):
        lines.append(f"Kickoff {m['kickoff'][11:16]} UTC")
    if site:
        lines.append(f'<a href="{site.rstrip("/")}/match/{m["slug"]}">Match page</a>')
    return "\n".join(lines)

def send(ns, data_dir, mode):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    subs = _subs() if token else None
    if not token or subs is None:
        print("Alerts: skipped (bot token or worker settings not set).")
        return
    site = os.environ.get("SITE_URL", "")
    idx = json.load(open(os.path.join(data_dir, "site", "index.json")))
    log_path = os.path.join(data_dir, "alerts_sent.json")
    sent = json.load(open(log_path)) if os.path.exists(log_path) else {}
    prefs = {str(k): v for k, v in (subs.get("prefs") or {}).items()}
    by_target = {}
    for s in subs.get("subs", []):
        by_target.setdefault((s["kind"], s["slug"]), set()).add(str(s["chat_id"]))
    now = pd.Timestamp.now("UTC").tz_convert(None)
    n_sent = 0
    for m in idx["matches"]:
        fans = by_target.get(("team", m["home_slug"]), set()) | by_target.get(("team", m["away_slug"]), set()) | by_target.get(("league", m["league_slug"]), set()) | by_target.get(("match", m["slug"]), set())   # v33: single-match follows
        if not fans:
            continue
        ko = pd.Timestamp(m["kickoff"]).tz_localize(None) if m.get("kickoff") else pd.Timestamp(m["Date"]) + pd.Timedelta(hours=15)
        hours = (ko - now).total_seconds() / 3600
        d_path = os.path.join(data_dir, "site", "match", f"{m['slug']}.json")
        if not os.path.exists(d_path) or hours < -0.5:
            continue
        d = json.load(open(d_path))
        todo = []
        if 0 < hours <= 30:
            todo.append(("preview", preview_text))
        if any((m.get("confirmed") or {}).values()) and hours <= 3:
            todo.append(("lineups", lineups_text))
        worker_sent = set((subs.get("lineups_sent") or {}).get(m["slug"], []))      # v35: the Worker sends lineups as soon as they're out
        for kind, make in todo:
            text = make(d, site)
            for chat in fans:
                if not prefs.get(chat, {}).get(kind, 1):
                    continue
                if kind == "lineups" and chat in worker_sent:
                    continue
                key = f"{kind}|{m['slug']}|{chat}"
                if key in sent:
                    continue
                if _send(token, chat, text):
                    sent[key] = now.isoformat(); n_sent += 1
                time.sleep(0.05)
    sent = {k: v for k, v in sent.items() if pd.Timestamp(v) > now - pd.Timedelta(days=21)}   # keep the log small
    json.dump(sent, open(log_path, "w"))
    print(f"Alerts: {n_sent} messages sent to followers.")
    _stat("alerts_pipeline", n_sent)


# ---------- v30: the public Kwallo channel (@kwallo_official) ----------
# Morning digest, big-match previews, yesterday's results and (Mondays) the weekly track record. Each goes out once.
# Informational only: probabilities and fair odds, no bookmakers. The channel can be changed with a GitHub variable TELEGRAM_CHANNEL.
BIG_COMPS = {"Premier League", "La Liga", "Bundesliga", "Serie A", "Ligue 1", "Champions League", "Europa League"}

def _post(token, channel, text, sent, key):
    if key in sent:
        return False
    ok = _send(token, channel, text)
    if ok:
        sent[key] = pd.Timestamp.now("UTC").tz_convert(None).isoformat()
    return ok

def _free_pick(m, data_dir):
    """v31 (premium on): a pick for free users that is never the match's top angle: its second-best angle, else its safer angle."""
    try:
        d = json.load(open(os.path.join(data_dir, "site", "match", f"{m['slug']}.json")))
    except Exception:
        return None
    v = d.get("verdict") or {}
    best, safer = v.get("best") or [], v.get("safer")
    top = best[0]["Bet"] if best else None
    if len(best) > 1:
        return best[1]
    if safer and safer.get("Bet") != top:
        return safer
    return None

def channel_posts(data_dir, mode):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    channel = os.environ.get("TELEGRAM_CHANNEL") or "@kwallo_official"
    if not token or mode == "lineups":
        return
    site = os.environ.get("SITE_URL", "")
    idx_p = os.path.join(data_dir, "site", "index.json")
    if not os.path.exists(idx_p):
        return
    idx = json.load(open(idx_p))
    log_path = os.path.join(data_dir, "channel_sent.json")
    sent = json.load(open(log_path)) if os.path.exists(log_path) else {}
    now = pd.Timestamp.now("UTC").tz_convert(None)
    today, yday = now.strftime("%Y-%m-%d"), (now - pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    n = 0
    # 1. morning digest: today's matches with their top angle (grouped by competition, capped so it fits one message)
    todays = [m for m in idx["matches"] if m["Date"][:10] == today]
    if todays:
        lines = [f"☀️ <b>Kwallo · {now:%A %d %B}</b>", ("<i>football, decoded.</i> Today's chances, with a free pick for each match:" if PREMIUM_ENABLED else "<i>football, decoded.</i> Today's top angles, with fair odds:"), ""]
        by_comp = {}
        for m in sorted(todays, key=lambda m: (m["Competition"] not in BIG_COMPS, m.get("kickoff") or "", m["Competition"])):
            by_comp.setdefault(m["Competition"], []).append(m)
        shown = 0
        for comp, ms in by_comp.items():
            if shown >= 25:
                break
            lines.append(f"<b>{html.escape(comp)}</b>")
            for m in ms[:6]:
                tp = m.get("top_pick") or {}
                ko = f"{m['kickoff'][11:16]} " if m.get("kickoff") else ""
                if PREMIUM_ENABLED:                                    # v31: basic chances plus one non-top pick per match
                    fp = _free_pick(m, data_dir)
                    lines.append(f"{ko}{html.escape(m['Home'])} v {html.escape(m['Away'])}: {_pct(m.get('pH'))} · draw {_pct(m.get('pD'))} · {_pct(m.get('pA'))}"
                                 + (f" · <i>Pick:</i> {html.escape(fp['Bet'])} {_pct(fp['p'])} (fair {fp['fair']:.2f})" if fp else ""))
                else:
                    lines.append(f"{ko}{html.escape(m['Home'])} v {html.escape(m['Away'])}" + (f": {html.escape(tp['Bet'])} {_pct(tp['p'])} (fair {tp['fair']:.2f})" if tp else ""))
                shown += 1
            lines.append("")
        lines.append("<i>Model probabilities, not guarantees. Worth it only above the fair odds. 18+.</i>")
        n += _post(token, channel, "\n".join(lines)[:4000], sent, f"digest|{today}")
    # 2. big-match previews: up to three headline games kicking off in the next 6-30 hours
    soon = []
    for m in idx["matches"]:
        if not m.get("kickoff"):
            continue
        h = (pd.Timestamp(m["kickoff"]).tz_localize(None) - now).total_seconds() / 3600
        if 6 <= h <= 30 and m["Competition"] in BIG_COMPS:
            closeness = 1 - abs((m.get("pH") or 0) - (m.get("pA") or 0))
            soon.append((closeness + (0.3 if "Champions" in m["Competition"] else 0), m))
    for _, m in sorted(soon, key=lambda x: -x[0])[:3]:
        d_path = os.path.join(data_dir, "site", "match", f"{m['slug']}.json")
        if os.path.exists(d_path):
            n += _post(token, channel, "🔥 <b>Big match</b>\n" + preview_text(json.load(open(d_path)), site), sent, f"preview|{m['slug']}")
    # 3. yesterday's results: how the top angles did, against what the model expected
    vl = os.path.join(data_dir, "verdict_log.csv")
    if os.path.exists(vl):
        v = pd.read_csv(vl)
        if "won" in v:
            yall = v[(v["Date"].astype(str) == yday) & (v["kind"] == "best")]
            yv = yall.dropna(subset=["won"])
            pending = len(yall) - len(yv)
            if not len(yv):                                       # v33: never silent, so "nothing to report" is visible
                txt = (f"🏁 <b>Yesterday's top angles</b>: " + (f"none settled yet ({pending} still waiting for final scores; they'll be counted in the track record)."
                                                               if pending else "no settled picks from yesterday."))
                n += _post(token, channel, txt, sent, f"results|{yday}")
            if len(yv) >= 1:
                rows = [f"{'✅' if r.won > 0 else '❌'} {html.escape(str(r.Home))} v {html.escape(str(r.Away))}: {html.escape(str(r.Bet))} ({_pct(r.p)})" for r in yv.head(20).itertuples()]
                txt = (f"🏁 <b>Yesterday's top angles</b>: {int(yv['won'].sum())} of {len(yv)} landed "
                       f"({100 * yv['won'].mean():.0f}% vs {100 * yv['p'].mean():.0f}% the model expected)\n\n" + "\n".join(rows) + (f'\n\n<a href="{os.environ.get("SITE_URL", "").rstrip("/")}/#/track">Full track record</a>' if os.environ.get("SITE_URL") else "")
                       + (f"\n\n{pending} more still waiting for final scores." if pending else "")
                       + "\n\n<i>A hit rate close to the expected one means the probabilities are honest. 18+.</i>")
                n += _post(token, channel, txt[:4000], sent, f"results|{yday}")
            # 4. Mondays (full run): the week's track record
            if mode == "full":
                wk = v[(pd.to_datetime(v["Date"]) >= now - pd.Timedelta(days=7)) & (v["kind"] == "best")].dropna(subset=["won"])
                allv = v[v["kind"] == "best"].dropna(subset=["won"])
                if len(wk) >= 10:
                    txt = (f"📊 <b>Kwallo weekly track record</b>\nLast 7 days: top angles landed {100 * wk['won'].mean():.0f}% "
                           f"(the model expected {100 * wk['p'].mean():.0f}%), {len(wk)} picks.\nSince launch: {100 * allv['won'].mean():.0f}% vs "
                           f"{100 * allv['p'].mean():.0f}% expected, {len(allv)} picks.\n\n<i>We publish every pick, hits and misses. 18+.</i>"
                           + (f'\n<a href="{os.environ.get("SITE_URL", "").rstrip("/")}/#/track">Full track record</a>' if os.environ.get("SITE_URL") else ""))
                    n += _post(token, channel, txt, sent, f"weekly|{now:%G-W%V}")
    sent = {k: s for k, s in sent.items() if pd.Timestamp(s) > now - pd.Timedelta(days=30)}
    json.dump(sent, open(log_path, "w"))
    print(f"Channel {channel}: {n} posts this run.")
    _stat("channel_posts", n)

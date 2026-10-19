"""Sends match alerts to @kwalloBot followers, after each pipeline run.
Two alerts per match: a PREVIEW (about a day before: probabilities, top angle, expected lineups) and LINEUPS (once the
official lineups are out, about 75 minutes before kickoff in the Premier League). Each is sent once per person per match.
Informational only: probabilities and fair odds, no bookmakers."""
import os, json, time, html
import requests, pandas as pd

def _subs():
    url, key = os.environ.get("WORKER_URL"), os.environ.get("PIPELINE_KEY")
    if not url or not key:
        return None
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
    if v.get("best"):
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
    if v.get("best"):
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
        fans = by_target.get(("team", m["home_slug"]), set()) | by_target.get(("team", m["away_slug"]), set()) | by_target.get(("league", m["league_slug"]), set())
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
        for kind, make in todo:
            text = make(d, site)
            for chat in fans:
                if not prefs.get(chat, {}).get(kind, 1):
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

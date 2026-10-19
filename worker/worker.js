// Kwallo Telegram bot (@kwalloAI_bot) + subscriber list for the pipeline + lineup-time run trigger.
// Stores only chat IDs and choices (D1). Informational alerts only: no bookmakers, 18+.
const PRIVACY = "Kwallo stores only your Telegram chat ID and the teams/leagues and alert types you choose, to send you match alerts. " +
  "Nothing else is kept. Send /stop at any time to stop all alerts and delete your data. Alerts are model probabilities, not guarantees; 18+.";
const HELP = "Commands:\n/follow [team or league] - follow\n/list - what you follow\n/settings - choose your alerts\n/unfollow - stop following one\n/stop - stop everything and delete your data\n/privacy - how your data is used";

async function tg(env, method, body) {
  const r = await fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/${method}`, {
    method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) });
  return r.ok;
}
const reply = (env, chat, text, extra = {}) => tg(env, "sendMessage", { chat_id: chat, text, parse_mode: "HTML", disable_web_page_preview: true, ...extra });
const esc = s => String(s).replace(/[&<>]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));

async function directory(env) {
  // teams.json is written by the pipeline: [{slug, name, league, league_slug}]
  const obj = await env.DATA.get("site/teams.json");
  const teams = obj ? await obj.json() : [];
  const leagues = {};
  for (const t of teams) leagues[t.league_slug] = { slug: t.league_slug, name: t.league };
  return { teams, leagues: Object.values(leagues) };
}
function search(dir, q) {
  const norm = s => String(s).toLowerCase().normalize("NFKD").replace(/[^a-z0-9 ]/g, "");
  const n = norm(q);
  if (!n) return [];
  const all = [...dir.teams.map(t => ({ kind: "team", slug: t.slug, name: t.name })), ...dir.leagues.map(l => ({ kind: "league", slug: l.slug, name: l.name }))];
  const exact = all.filter(x => norm(x.name) === n);
  return (exact.length ? exact : all.filter(x => norm(x.name).includes(n))).slice(0, 8);
}
async function follow(env, chat, kind, slug, name) {
  await env.DB.prepare("INSERT OR IGNORE INTO subs (chat_id, kind, slug, name, created) VALUES (?, ?, ?, ?, ?)")
    .bind(chat, kind, slug, name, new Date().toISOString()).run();
  await env.DB.prepare("INSERT OR IGNORE INTO prefs (chat_id) VALUES (?)").bind(chat).run();
  return reply(env, chat, `✅ You're now following <b>${esc(name)}</b>. You'll get a match preview about a day before, and the lineups once they're out.\n\n${HELP}`);
}
async function listSubs(env, chat) {
  const { results } = await env.DB.prepare("SELECT kind, slug, name FROM subs WHERE chat_id = ? ORDER BY name").bind(chat).all();
  return results || [];
}

async function handleUpdate(env, u) {
  await ensureTables(env);                                   // v31: the new tables exist before anything uses them
  if (u.callback_query) {
    const cq = u.callback_query, chat = cq.message.chat.id, [act, kind, slug] = String(cq.data).split(":");
    await tg(env, "answerCallbackQuery", { callback_query_id: cq.id });
    if (act === "f") {
      const dir = await directory(env);
      const hit = [...dir.teams.map(t => ({ kind: "team", ...t })), ...dir.leagues.map(l => ({ kind: "league", ...l }))].find(x => x.kind === kind && x.slug === slug);
      return follow(env, chat, kind, slug, hit ? hit.name : slug);
    }
    if (act === "u") {
      await env.DB.prepare("DELETE FROM subs WHERE chat_id = ? AND kind = ? AND slug = ?").bind(chat, kind, slug).run();
      return reply(env, chat, "Removed. /list shows what you still follow.");
    }
    if (act === "l") {                                         // v31: live alert switches
      const cur = (await livePrefs(env, chat))[kind];
      await env.DB.prepare("INSERT INTO prefs2 (chat_id, k, v) VALUES (?, ?, ?) ON CONFLICT(chat_id, k) DO UPDATE SET v = excluded.v").bind(chat, kind, cur ? 0 : 1).run();
      return settings(env, chat);
    }
    if (act === "s") {
      const col = kind === "preview" ? "preview" : "lineups";
      await env.DB.prepare("INSERT OR IGNORE INTO prefs (chat_id) VALUES (?)").bind(chat).run();
      await env.DB.prepare(`UPDATE prefs SET ${col} = 1 - ${col} WHERE chat_id = ?`).bind(chat).run();
      return settings(env, chat);
    }
    return;
  }
  const msg = u.message;
  if (!msg || !msg.text) return;
  const chat = msg.chat.id, text = msg.text.trim();
  const [cmdRaw, ...rest] = text.split(" "), cmd = cmdRaw.split("@")[0].toLowerCase(), arg = rest.join(" ").trim();
  if (cmd.startsWith("/")) { try { await bump(env, "cmd", cmd); } catch (e) {} }
  if (cmd === "/stats") return adminStats(env, chat);
  if (cmd === "/start") {
    const m = arg.match(/^(team|league)_(.+)$/);
    if (m) {
      const dir = await directory(env);
      const list = m[1] === "team" ? dir.teams : dir.leagues;
      const hit = list.find(x => x.slug === m[2]);
      return follow(env, chat, m[1], m[2], hit ? hit.name : m[2].replace(/-/g, " "));
    }
    return reply(env, chat, `👋 Welcome to <b>Kwallo</b> — football, decoded.\nFree match alerts for the teams and leagues you follow.\n📣 Daily previews, top angles and results: join @kwallo_official\nFollow a team or league with /follow, e.g. <code>/follow Arsenal</code>.\n\n${HELP}\n\n<i>${PRIVACY}</i>`);
  }
  if (cmd === "/follow") {
    if (!arg) return reply(env, chat, "Which team or league? For example: <code>/follow Arsenal</code> or <code>/follow Premier League</code>");
    const hits = search(await directory(env), arg);
    if (!hits.length) return reply(env, chat, "I couldn't find that. Try part of the name, e.g. <code>/follow Man</code>.");
    if (hits.length === 1) return follow(env, chat, hits[0].kind, hits[0].slug, hits[0].name);
    return reply(env, chat, "Which one?", { reply_markup: { inline_keyboard: hits.map(h => [{ text: `${h.name}${h.kind === "league" ? " (league)" : ""}`, callback_data: `f:${h.kind}:${h.slug}` }]) } });
  }
  if (cmd === "/list") {
    const s = await listSubs(env, chat);
    return reply(env, chat, s.length ? "You follow:\n" + s.map(x => `• ${esc(x.name)}${x.kind === "league" ? " (league)" : ""}`).join("\n") : "You don't follow anything yet. Try /follow.");
  }
  if (cmd === "/unfollow") {
    const s = await listSubs(env, chat);
    if (!s.length) return reply(env, chat, "You don't follow anything yet.");
    return reply(env, chat, "Tap to stop following:", { reply_markup: { inline_keyboard: s.map(x => [{ text: `✖ ${x.name}`, callback_data: `u:${x.kind}:${x.slug}` }]) } });
  }
  if (cmd === "/settings") return settings(env, chat);
  if (cmd === "/stop") {
    await env.DB.prepare("DELETE FROM subs WHERE chat_id = ?").bind(chat).run();
    await env.DB.prepare("DELETE FROM prefs WHERE chat_id = ?").bind(chat).run();
    await ensureTables(env);
    await env.DB.batch([env.DB.prepare("DELETE FROM prefs2 WHERE chat_id = ?").bind(chat), env.DB.prepare("DELETE FROM sent_live WHERE chat_id = ?").bind(chat),
                        env.DB.prepare("DELETE FROM outbox WHERE chat_id = ?").bind(chat)]);
    return reply(env, chat, "All alerts stopped and your data deleted. You can come back any time with /follow.");
  }
  if (cmd === "/privacy") return reply(env, chat, PRIVACY);
  return reply(env, chat, HELP);
}
async function settings(env, chat) {
  await ensureTables(env);
  const p = await env.DB.prepare("SELECT preview, lineups FROM prefs WHERE chat_id = ?").bind(chat).first() || { preview: 1, lineups: 1 };
  const lp = await livePrefs(env, chat);
  return reply(env, chat, "Your alerts (tap to switch on/off):", { reply_markup: { inline_keyboard: [
    [{ text: `${p.preview ? "✅" : "⬜"} Match preview (about a day before)`, callback_data: "s:preview:x" }],
    [{ text: `${p.lineups ? "✅" : "⬜"} Lineups out (about 75 min before kickoff)`, callback_data: "s:lineups:x" }],
    ...LIVE_PREFS.map(([k, label]) => [{ text: `${lp[k] ? "✅" : "⬜"} Live: ${label}`, callback_data: `l:${k}:x` }])] } });
}

async function subscribers(env) {
  const subs = (await env.DB.prepare("SELECT chat_id, kind, slug FROM subs").all()).results || [];
  const prefs = {};
  for (const p of (await env.DB.prepare("SELECT chat_id, preview, lineups FROM prefs").all()).results || []) prefs[p.chat_id] = { preview: p.preview, lineups: p.lineups };
  return { subs, prefs };
}


// ================= v31: live alerts, per-user live settings, usage totals =================
let _ready = false;
async function ensureTables(env) {                       // created on first use: no manual database steps
  if (_ready) return;
  await env.DB.batch([
    env.DB.prepare("CREATE TABLE IF NOT EXISTS prefs2 (chat_id INTEGER NOT NULL, k TEXT NOT NULL, v INTEGER NOT NULL, PRIMARY KEY (chat_id, k))"),
    env.DB.prepare("CREATE TABLE IF NOT EXISTS live_state (event_id TEXT PRIMARY KEY, data TEXT, updated TEXT)"),
    env.DB.prepare("CREATE TABLE IF NOT EXISTS outbox (id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id INTEGER, text TEXT, created TEXT)"),
    env.DB.prepare("CREATE TABLE IF NOT EXISTS stats_daily (day TEXT, metric TEXT, k TEXT, n INTEGER, PRIMARY KEY (day, metric, k))"),
    env.DB.prepare("CREATE TABLE IF NOT EXISTS sent_live (chat_id INTEGER, event_id TEXT, n INTEGER, PRIMARY KEY (chat_id, event_id))"),
  ]);
  _ready = true;
}
const LIVE_PREFS = [["goals", "⚽ Goals (with assists)", 1], ["cards", "🟨 Yellow and red cards", 1], ["htft", "⏸ Half-time and full-time", 1],
                    ["pressure", "🔥 Pressure alerts", 1], ["sot", "🎯 Every shot on target", 0], ["subs", "🔄 Substitutions", 0]];
const MAX_PER_MATCH = 15;                                 // per person per match; goals and full-time always get through
async function livePrefs(env, chat) {
  await ensureTables(env);
  const out = Object.fromEntries(LIVE_PREFS.map(([k, , d]) => [k, d]));
  for (const r of (await env.DB.prepare("SELECT k, v FROM prefs2 WHERE chat_id = ?").bind(chat).all()).results || []) out[r.k] = r.v;
  return out;
}
async function bump(env, metric, k = "", n = 1) {
  if (!n) return;
  await ensureTables(env);
  const day = new Date().toISOString().slice(0, 10);
  await env.DB.prepare("INSERT INTO stats_daily (day, metric, k, n) VALUES (?, ?, ?, ?) ON CONFLICT(day, metric, k) DO UPDATE SET n = n + excluded.n")
    .bind(day, metric, String(k), n).run();
}

function snapshot(ev) {                                   // one ESPN scoreboard event -> what we compare minute to minute
  const c = (ev.competitions || [])[0] || {};
  const st = (ev.status || c.status || {}).type || {};
  const comps = c.competitors || [];
  const H = comps.find(x => x.homeAway === "home") || comps[0] || {}, A = comps.find(x => x.homeAway === "away") || comps[1] || {};
  const stat = (t, n) => { const s = (t.statistics || []).find(x => x.name === n); return s ? parseFloat(s.displayValue) : null; };
  const side = id => String(id) === String((H.team || {}).id) ? "h" : (String(id) === String((A.team || {}).id) ? "a" : null);
  const events = (c.details || []).map(d => {
    const t = String((d.type || {}).text || "");
    const names = (d.athletesInvolved || []).map(a => a.displayName || a.shortName).filter(Boolean);
    return { key: `${t}|${(d.clock || {}).displayValue || ""}|${names.join(",")}`, clock: (d.clock || {}).displayValue || "", side: side((d.team || {}).id), names,
             goal: !!d.scoringPlay || /goal/i.test(t), own: !!d.ownGoal || /own goal/i.test(t), pen: !!d.penaltyKick || /penalty/i.test(t),
             red: !!d.redCard || /red card/i.test(t), yellow: (!!d.yellowCard || /yellow/i.test(t)) && !(d.redCard || /red card/i.test(t)), sub: /substitut/i.test(t) };
  });
  const clock = String((ev.status || {}).displayClock || st.shortDetail || "");
  return { state: st.state, name: st.name || "", detail: st.shortDetail || "", minute: parseInt(clock) || 0,
           hs: parseInt(H.score) || 0, as: parseInt(A.score) || 0, H: (H.team || {}).shortDisplayName || "Home", A: (A.team || {}).shortDisplayName || "Away", events,
           stats: { h: { shots: stat(H, "totalShots"), sot: stat(H, "shotsOnTarget"), poss: stat(H, "possessionPct"), corners: stat(H, "wonCorners") },
                    a: { shots: stat(A, "totalShots"), sot: stat(A, "shotsOnTarget"), poss: stat(A, "possessionPct"), corners: stat(A, "wonCorners") } } };
}
function fillStatsFromSummary(snap, s) {                  // when the scoreboard has no statistics, take them from the match summary
  const teams = ((s || {}).boxscore || {}).teams || [];
  const get = (t, n) => { const x = (t.statistics || []).find(y => y.name === n); return x ? parseFloat(x.displayValue) : null; };
  const H = teams.find(t => t.homeAway === "home") || teams[0], A = teams.find(t => t.homeAway === "away") || teams[1];
  for (const [k, t] of [["h", H], ["a", A]]) if (t) snap.stats[k] = { shots: get(t, "totalShots"), sot: get(t, "shotsOnTarget"), poss: get(t, "possessionPct"), corners: get(t, "wonCorners") };
  if (!snap.events.length) {
    snap.events = ((s || {}).keyEvents || []).map(k => {
      const t = String((k.type || {}).text || ""); const names = (k.participants || []).map(p => (p.athlete || {}).displayName).filter(Boolean);
      return { key: `${t}|${(k.clock || {}).displayValue || ""}|${names.join(",")}`, clock: (k.clock || {}).displayValue || "", side: null, names, team: (k.team || {}).displayName,
               goal: /goal/i.test(t), own: /own goal/i.test(t), pen: /penalty/i.test(t), red: /red card/i.test(t), yellow: /yellow/i.test(t) && !/red card/i.test(t), sub: /substitut/i.test(t) };
    });
  }
}

function findAssist(summary, goal) {                       // v31: ESPN often names the assister only in the goal's description
  const texts = [];
  for (const k of (summary.keyEvents || [])) if ((k.clock || {}).displayValue === goal.clock || /goal/i.test(String((k.type || {}).text))) texts.push(String(k.text || ""));
  for (const c of (summary.commentary || [])) if ((c.time || {}).displayValue === goal.clock) texts.push(String(c.text || ""));
  for (const t of texts) {
    if (goal.names[0] && !t.includes(goal.names[0].split(" ").slice(-1)[0])) continue;   // the right goal: mentions the scorer
    const m = t.match(/Assisted by ([^.]+?)(?:\s+(?:with|following|after)\b|\.|$)/i);
    if (m) return m[1].trim();
  }
  return null;
}
const pct = p => (p == null ? "-" : `${Math.round(100 * p)}%`);
function statLine(s) {
  const f = (a, b) => (a == null || b == null ? null : `${a}–${b}`);
  const parts = [f(s.stats.h.shots, s.stats.a.shots) && `Shots ${f(s.stats.h.shots, s.stats.a.shots)}` + (f(s.stats.h.sot, s.stats.a.sot) ? ` (on target ${f(s.stats.h.sot, s.stats.a.sot)})` : ""),
                 f(s.stats.h.poss, s.stats.a.poss) && `possession ${Math.round(s.stats.h.poss)}%–${Math.round(s.stats.a.poss)}%`,
                 f(s.stats.h.corners, s.stats.a.corners) && `corners ${f(s.stats.h.corners, s.stats.a.corners)}`].filter(Boolean);
  return parts.join(" · ");
}
function liveMessages(m, prev, s) {                       // what changed since the last minute -> [{kind, text, always}]
  const out = [], seen = new Set((prev && prev.seen) || []);
  const team = side => (side === "h" ? s.H : side === "a" ? s.A : "");
  for (const e of s.events) {
    if (seen.has(e.key)) continue;
    const who = esc(e.names[0] || ""), tm = esc(team(e.side) || e.team || "");
    if (e.goal) {
      const assist = !e.own && e.names.length > 1 ? `, assist: ${esc(e.names[1])}` : "";
      out.push({ kind: "goals", always: true, text: `⚽ <b>GOAL!</b> ${esc(s.H)} ${s.hs}–${s.as} ${esc(s.A)}\n${who} ${e.clock}${e.pen ? " (penalty)" : ""}${e.own ? " (own goal)" : ""}${assist}` });
    } else if (e.red) out.push({ kind: "cards", text: `🟥 <b>Red card:</b> ${who}${tm ? ` (${tm})` : ""} ${e.clock}\n${esc(s.H)} ${s.hs}–${s.as} ${esc(s.A)}` });
    else if (e.yellow) out.push({ kind: "cards", text: `🟨 Yellow card: ${who}${tm ? ` (${tm})` : ""} ${e.clock}` });
    else if (e.sub) out.push({ kind: "subs", text: `🔄 Substitution${tm ? ` (${tm})` : ""} ${e.clock}: ${esc(e.names.join(" ↔ "))}` });
  }
  if (prev && s.state === "in") {
    for (const k of ["h", "a"]) {                           // shots on target since last minute (not once the match has ended)
      const now_ = s.stats[k].sot, was = prev.stats && prev.stats[k] ? prev.stats[k].sot : null;
      if (now_ != null && was != null && now_ > was) out.push({ kind: "sot", text: `🎯 Shot on target: ${esc(team(k))} (${now_} now) · ${esc(s.H)} ${s.hs}–${s.as} ${esc(s.A)}` });
    }
  }
  if (prev) {
    const ht = /HALFTIME/i.test(s.name) || /^HT$/i.test(s.detail);
    if (ht && !prev.ht_sent) out.push({ kind: "htft", text: `⏸ <b>Half-time:</b> ${esc(s.H)} ${s.hs}–${s.as} ${esc(s.A)}` + (statLine(s) ? `\n${statLine(s)}` : "") });
    if (s.state === "post" && prev.state !== "post") {
      const res = s.hs > s.as ? "H" : s.hs < s.as ? "A" : "D";
      const p = { H: m.pH, D: m.pD, A: m.pA }, fav = ["H", "D", "A"].sort((x, y) => (p[y] || 0) - (p[x] || 0))[0];
      const words = { H: `${esc(s.H)} a`, D: "the draw a", A: `${esc(s.A)} a` }, after = { H: " to win", D: "", A: " to win" };
      out.push({ kind: "htft", always: true, text: `🏁 <b>Full-time:</b> ${esc(s.H)} ${s.hs}–${s.as} ${esc(s.A)}` + (statLine(s) ? `\n${statLine(s)}` : "")
                 + (p[res] != null ? `\nKwallo gave ${words[res]} ${pct(p[res])} chance${after[res]}${fav === res ? " ✅ (our likeliest outcome)" : ""}` : "") });
    }
  }
  return out;
}
function pressureCheck(prev, s) {                         // a side dominating: 4+ shots in 10 minutes, at least twice the other side's
  const hist = (((prev && prev.hist) || []).concat([{ min: s.minute, h: s.stats.h.shots, a: s.stats.a.shots, th: s.stats.h.sot, ta: s.stats.a.sot }])).slice(-40);
  const last = (prev && prev.pressure) || {}, out = [];
  const old = hist.find(x => x.min >= s.minute - 10 && x.h != null);
  if (old && s.stats.h.shots != null && s.state === "in") {
    for (const [k, o, name] of [["h", "a", s.H], ["a", "h", s.A]]) {
      const d = s.stats[k].shots - old[k], dO = s.stats[o].shots - old[o], dt = (s.stats[k].sot || 0) - (old["t" + k] || 0);
      if (d >= 4 && d >= 2 * Math.max(dO, 1) && (!last[k] || s.minute - last[k] >= 15)) {
        out.push({ kind: "pressure", text: `🔥 <b>${esc(name)} are on top:</b> ${d} shots in the last 10 minutes (${Math.max(dt, 0)} on target) · ${esc(s.H)} ${s.hs}–${s.as} ${esc(s.A)}` });
        last[k] = s.minute;
      }
    }
  }
  return { hist, last, out };
}

async function liveTick(env, now = Date.now()) {
  await ensureTables(env);
  const obj = await env.DATA.get("site/schedule.json");
  if (!obj) return "no schedule";
  const sched = await obj.json();
  const live = sched.filter(m => m.espn && m.kickoff && now >= Date.parse(m.kickoff) - 5 * 60000 && now <= Date.parse(m.kickoff) + 150 * 60000);
  let queued = 0;
  if (live.length) {
    const subs = (await env.DB.prepare("SELECT chat_id, kind, slug FROM subs").all()).results || [];
    const by = {};
    for (const s of subs) (by[`${s.kind}:${s.slug}`] = by[`${s.kind}:${s.slug}`] || []).push(s.chat_id);
    const watched = live.map(m => ({ m, fans: [...new Set([...(by[`team:${m.home_slug}`] || []), ...(by[`team:${m.away_slug}`] || []), ...(by[`league:${m.league_slug}`] || [])])] }))
                        .filter(x => x.fans.length);
    const boards = {};
    for (const code of [...new Set(watched.map(x => x.m.espn.code))].slice(0, 12)) {
      try { const r = await fetch(`https://site.api.espn.com/apis/site/v2/sports/soccer/${code}/scoreboard`, { headers: { "user-agent": "Mozilla/5.0" } }); boards[code] = r.ok ? await r.json() : null; }
      catch (e) { boards[code] = null; }
    }
    let summaries = 0;
    const prefCache = {}, rows = [];
    for (const { m, fans } of watched) {
      const ev = (((boards[m.espn.code] || {}).events) || []).find(e => String(e.id) === String(m.espn.id));
      if (!ev) continue;
      const s = snapshot(ev);
      if (s.state === "pre") continue;
      if (s.stats.h.shots == null && summaries < 5) {            // no statistics on the scoreboard: use the match summary
        summaries++;
        try { const r = await fetch(`https://site.api.espn.com/apis/site/v2/sports/soccer/${m.espn.code}/summary?event=${m.espn.id}`, { headers: { "user-agent": "Mozilla/5.0" } });
              if (r.ok) fillStatsFromSummary(s, await r.json()); } catch (e) {}
      }
      const row = await env.DB.prepare("SELECT data FROM live_state WHERE event_id = ?").bind(String(m.espn.id)).first();
      const prev = row ? JSON.parse(row.data) : null;
      const newGoals = prev ? s.events.filter(e => e.goal && !e.own && e.names.length < 2 && !(prev.seen || []).includes(e.key)) : [];
      if (newGoals.length && summaries < 8) {                     // fetch the description once, to name the assister
        summaries++;
        try { const r = await fetch(`https://site.api.espn.com/apis/site/v2/sports/soccer/${m.espn.code}/summary?event=${m.espn.id}`, { headers: { "user-agent": "Mozilla/5.0" } });
              if (r.ok) { const sm = await r.json(); for (const g of newGoals) { const a = findAssist(sm, g); if (a) g.names.push(a); } } } catch (e) {}
      }
      if (prev && prev.state === "post") continue;                // already finished and reported
      let msgs = prev ? liveMessages(m, prev, s) : [];            // the first sighting only sets the starting point
      const pr = pressureCheck(prev, s);
      if (prev) msgs = msgs.concat(pr.out);
      const state = { state: s.state, stats: s.stats, seen: [...new Set([...((prev && prev.seen) || []), ...s.events.map(e => e.key)])],
                      hist: pr.hist, pressure: pr.last, ht_sent: !!((prev && prev.ht_sent) || /HALFTIME/i.test(s.name) || /^HT$/i.test(s.detail)) };
      await env.DB.prepare("INSERT INTO live_state (event_id, data, updated) VALUES (?, ?, ?) ON CONFLICT(event_id) DO UPDATE SET data = excluded.data, updated = excluded.updated")
        .bind(String(m.espn.id), JSON.stringify(state), new Date(now).toISOString()).run();
      for (const msg of msgs) {
        for (const chat of fans) {
          const p = prefCache[chat] || (prefCache[chat] = await livePrefs(env, chat));
          if (!p[msg.kind]) continue;
          const cnt = await env.DB.prepare("SELECT n FROM sent_live WHERE chat_id = ? AND event_id = ?").bind(chat, String(m.espn.id)).first();
          if (!msg.always && cnt && cnt.n >= MAX_PER_MATCH) continue;
          rows.push(env.DB.prepare("INSERT INTO outbox (chat_id, text, created) VALUES (?, ?, ?)").bind(chat, msg.text, new Date(now).toISOString()));
          rows.push(env.DB.prepare("INSERT INTO sent_live (chat_id, event_id, n) VALUES (?, ?, 1) ON CONFLICT(chat_id, event_id) DO UPDATE SET n = n + 1").bind(chat, String(m.espn.id)));
          queued++;
        }
        await bump(env, "alerts_live", msg.kind, fans.length);
      }
    }
    if (rows.length) await env.DB.batch(rows);
  }
  const sent = await flushOutbox(env);
  return `live: ${live.length} in progress, ${queued} queued, ${sent} sent`;
}
async function flushOutbox(env, max = 30) {                 // sends up to 30 a minute (well inside the free plan's limits)
  const q = (await env.DB.prepare("SELECT id, chat_id, text FROM outbox ORDER BY id LIMIT ?").bind(max).all()).results || [];
  const done = [];
  for (const r of q) {
    await tg(env, "sendMessage", { chat_id: r.chat_id, text: r.text, parse_mode: "HTML", disable_web_page_preview: true });
    done.push(env.DB.prepare("DELETE FROM outbox WHERE id = ?").bind(r.id));
  }
  if (done.length) await env.DB.batch(done);
  return q.length;
}
async function adminStats(env, chat) {
  if (!env.ADMIN_CHAT_ID) return reply(env, chat, `Your chat ID is <code>${chat}</code>. To make /stats yours, add it in Cloudflare as a secret named ADMIN_CHAT_ID, then send /stats again.`);
  if (String(chat) !== String(env.ADMIN_CHAT_ID)) return reply(env, chat, HELP);
  await ensureTables(env);
  const one = async (sql, ...b) => (await env.DB.prepare(sql).bind(...b).first()) || {};
  const all = async (sql, ...b) => (await env.DB.prepare(sql).bind(...b).all()).results || [];
  const weekAgo = new Date(Date.now() - 7 * 86400000).toISOString();
  const followers = (await one("SELECT COUNT(DISTINCT chat_id) AS n FROM subs")).n || 0;
  const newWeek = (await one("SELECT COUNT(DISTINCT chat_id) AS n FROM subs WHERE created >= ?", weekAgo)).n || 0;
  const top = await all("SELECT name, kind, COUNT(*) AS n FROM subs GROUP BY kind, slug ORDER BY n DESC LIMIT 8");
  const since = new Date(Date.now() - 7 * 86400000).toISOString().slice(0, 10);
  const totals = await all("SELECT metric, k, SUM(n) AS n FROM stats_daily WHERE day >= ? GROUP BY metric, k ORDER BY metric, n DESC", since);
  const sec = metric => totals.filter(t => t.metric === metric).map(t => `${t.k || "all"} ${t.n}`).join(", ") || "none";
  return reply(env, chat, [`📊 <b>Kwallo stats</b> (last 7 days)`, `Followers: <b>${followers}</b> (${newWeek} new this week)`,
    `Most followed: ${top.map(t => `${esc(t.name)}${t.kind === "league" ? " (league)" : ""} ${t.n}`).join(", ") || "none yet"}`,
    `Live alerts: ${sec("alerts_live")}`, `Preview/lineup alerts: ${sec("alerts_pipeline")}`, `Channel posts: ${sec("channel_posts")}`,
    `Commands: ${sec("cmd")}`].join("\n"));
}

// Every 15 minutes: if a match kicks off in 55-85 minutes and no run was started for that kickoff slot, start a lineup-time run.
async function maybeDispatch(env, now = Date.now()) {
  const obj = await env.DATA.get("site/schedule.json");
  if (!obj) return "no schedule";
  const sched = await obj.json();
  const due = sched.filter(m => m.kickoff && (Date.parse(m.kickoff) - now) / 60000 >= 55 && (Date.parse(m.kickoff) - now) / 60000 <= 85);
  if (!due.length) return "nothing due";
  const slot = due.map(m => m.kickoff.slice(0, 16)).sort()[0];
  const seen = await env.DB.prepare("SELECT slot FROM dispatched WHERE slot = ?").bind(slot).first();
  if (seen) return "already started for " + slot;
  const r = await fetch(`https://api.github.com/repos/${env.GITHUB_REPO}/actions/workflows/lineups.yml/dispatches`, {
    method: "POST", headers: { authorization: `Bearer ${env.GITHUB_TOKEN}`, accept: "application/vnd.github+json", "user-agent": "kwallo-bot" },
    body: JSON.stringify({ ref: "main" }) });
  if (r.ok || r.status === 204) {
    await env.DB.prepare("INSERT OR IGNORE INTO dispatched (slot, at) VALUES (?, ?)").bind(slot, new Date(now).toISOString()).run();
    return "started run for " + slot;
  }
  return "GitHub said " + r.status;
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (request.method === "POST" && url.pathname === "/telegram") {
      if (request.headers.get("X-Telegram-Bot-Api-Secret-Token") !== env.WEBHOOK_SECRET) return new Response("forbidden", { status: 403 });
      try { await handleUpdate(env, await request.json()); } catch (e) { console.log("update failed", e); }
      return new Response("ok");                               // always 200, so Telegram doesn't retry endlessly
    }
    if (url.pathname === "/api/subscribers") {
      if (request.headers.get("X-Pipeline-Key") !== env.PIPELINE_KEY) return new Response("forbidden", { status: 403 });
      return Response.json(await subscribers(env));
    }
    if (url.pathname === "/api/stats" && request.method === "POST") {      // v31: daily totals from the pipeline
      if (request.headers.get("X-Pipeline-Key") !== env.PIPELINE_KEY) return new Response("forbidden", { status: 403 });
      const b = await request.json();
      await bump(env, String(b.metric || "other"), "", parseInt(b.n) || 0);
      return new Response("ok");
    }
    if (url.pathname === "/") return new Response("Kwallo bot is running.");
    return new Response("not found", { status: 404 });
  },
  async scheduled(event, env, ctx) {
    // v31: runs every minute (cron "* * * * *"): live alerts each minute, the lineup-run check every 15 minutes
    const minute = new Date(event.scheduledTime || Date.now()).getUTCMinutes();
    ctx.waitUntil(liveTick(env).then(r => console.log(r)).catch(e => console.log("live failed", e)));
    if (minute % 15 === 0) ctx.waitUntil(maybeDispatch(env).then(r => console.log("lineup check:", r)));
  },
};
export { findAssist, handleUpdate, maybeDispatch, subscribers, search, liveTick, snapshot, liveMessages, pressureCheck, flushOutbox, adminStats };

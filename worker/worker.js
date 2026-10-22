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
// v35: kickoff times in Nigerian time (WAT, UTC+1), labelled: "Wed, 21 Oct 17:45 WAT" or "17:45 WAT"
function watTime(iso, withDay) {
  const s = new Date(Date.parse(iso) + 3600000).toUTCString();     // "Wed, 21 Oct 2026 17:45:00 GMT", shifted to WAT
  return withDay ? `${s.slice(0, 11)} ${s.slice(17, 22)} WAT` : `${s.slice(17, 22)} WAT`;
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
  if (cmd === "/dashboard") {                                    // v31: admin only
    if (!env.ADMIN_CHAT_ID || String(chat) !== String(env.ADMIN_CHAT_ID)) return reply(env, chat, HELP);
    return reply(env, chat, `📈 Your dashboard (latest run): ${env.ORIGIN || ""}/admin/dashboard\nUse any username and your DASHBOARD_PASSWORD.`);
  }
  if (cmd === "/start") {
    const mm = arg.match(/^match_(.+)$/);                         // v33: one match only (alerts until full-time)
    if (mm) {
      const obj = await env.DATA.get("site/schedule.json");
      const hit = obj ? (await obj.json()).find(x => x.slug === mm[1]) : null;
      if (!hit) return reply(env, chat, "That match isn't in the schedule any more. Try /follow with a team name instead.");
      await env.DB.prepare("INSERT OR IGNORE INTO subs (chat_id, kind, slug, name, created) VALUES (?, 'match', ?, ?, ?)")
        .bind(chat, hit.slug, `${hit.home} v ${hit.away}`, new Date().toISOString()).run();
      await env.DB.prepare("INSERT OR IGNORE INTO prefs (chat_id) VALUES (?)").bind(chat).run();
      const ko = hit.kickoff ? watTime(hit.kickoff, true) : hit.date;
      return reply(env, chat, `✅ Following <b>${esc(hit.home)} v ${esc(hit.away)}</b> (${esc(hit.competition)}, ${esc(ko)}). You'll get the lineups, kick-off, goals, cards, half-time and full-time for this match only; it's removed from your list after full-time.\n\n${HELP}`);
    }
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
    [{ text: `${p.lineups ? "✅" : "⬜"} Lineups (the moment they're announced)`, callback_data: "s:lineups:x" }],
    ...LIVE_PREFS.map(([k, label]) => [{ text: `${lp[k] ? "✅" : "⬜"} Live: ${label}`, callback_data: `l:${k}:x` }])] } });
}

async function subscribers(env) {
  const subs = (await env.DB.prepare("SELECT chat_id, kind, slug FROM subs").all()).results || [];
  const prefs = {};
  for (const p of (await env.DB.prepare("SELECT chat_id, preview, lineups FROM prefs").all()).results || []) prefs[p.chat_id] = { preview: p.preview, lineups: p.lineups };
  // v35: lineup alerts the Worker already sent, so the pipeline doesn't send them again
  await ensureTables(env);
  const lineups_sent = {};
  for (const r of (await env.DB.prepare("SELECT slug, chats FROM lineup_sent").all()).results || []) lineups_sent[r.slug] = JSON.parse(r.chats || "[]").map(String);
  return { subs, prefs, lineups_sent };
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
    env.DB.prepare("CREATE TABLE IF NOT EXISTS lineup_sent (slug TEXT PRIMARY KEY, chats TEXT, at TEXT)"),   // v35: lineup alerts sent by the Worker
  ]);
  // v35: an outbox row now holds one message for a list of chats (one database write per alert, not one per follower),
  // and goals / full-time go first. These fail harmlessly once the columns exist.
  for (const sql of ["ALTER TABLE outbox ADD COLUMN prio INTEGER DEFAULT 0", "ALTER TABLE outbox ADD COLUMN chats TEXT"]) {
    try { await env.DB.prepare(sql).run(); } catch (e) {}
  }
  _ready = true;
}
const LIVE_PREFS = [["kickoff", "🟢 Kick-off", 1], ["goals", "⚽ Goals (with assists)", 1], ["cards", "🟨 Yellow and red cards", 1], ["htft", "⏸ Half-time and full-time", 1],
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

// v35: a goal is identified by its minute and side only, so ESPN adding the assister (or renaming the event) later
// no longer looks like a new goal and sends a second GOAL alert
const KEY_V = 2;
function eventKey(e, typeText) {
  if (e.goal) return `goal|${e.clock}|${e.side || e.team || ""}`;
  return `${typeText}|${e.clock}|${(e.names || []).join(",")}`;
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
    const e = { clock: (d.clock || {}).displayValue || "", side: side((d.team || {}).id), names,
             goal: !!d.scoringPlay || /goal/i.test(t), own: !!d.ownGoal || /own goal/i.test(t), pen: !!d.penaltyKick || /penalty/i.test(t),
             red: !!d.redCard || /red card/i.test(t), yellow: (!!d.yellowCard || /yellow/i.test(t)) && !(d.redCard || /red card/i.test(t)), sub: /substitut/i.test(t) };
    e.key = eventKey(e, t);
    return e;
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
      const e = { clock: (k.clock || {}).displayValue || "", side: null, names, team: (k.team || {}).displayName,
               goal: /goal/i.test(t), own: /own goal/i.test(t), pen: /penalty/i.test(t), red: /red card/i.test(t), yellow: /yellow/i.test(t) && !/red card/i.test(t), sub: /substitut/i.test(t) };
      e.key = eventKey(e, t);
      return e;
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
const CORS = { "access-control-allow-origin": "*" };
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
  if (s.state === "in" && ((prev && prev.state === "pre") || (!prev && s.minute <= 5)) && !(prev && prev.ko_sent)) {
    out.push({ kind: "kickoff", always: false, text: `🟢 <b>Kick-off:</b> ${esc(s.H)} v ${esc(s.A)}${m.competition ? ` · ${esc(m.competition)}` : ""}`
               + (m.pH != null ? `\nChances: ${esc(s.H)} ${pct(m.pH)} · draw ${pct(m.pD)} · ${esc(s.A)} ${pct(m.pA)}` : "") });
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

// v35: rows for a list of values in one query (D1 allows 100 bound values per statement, so long lists go in chunks)
async function inList(env, sqlPrefix, values) {
  const out = [];
  for (let i = 0; i < values.length; i += 90) {
    const part = values.slice(i, i + 90);
    if (!part.length) continue;
    const r = await env.DB.prepare(`${sqlPrefix} (${part.map(() => "?").join(",")})`).bind(...part).all();
    out.push(...(r.results || []));
  }
  return out;
}
const bumpStmt = (env, metric, k, n) => env.DB.prepare("INSERT INTO stats_daily (day, metric, k, n) VALUES (?, ?, ?, ?) ON CONFLICT(day, metric, k) DO UPDATE SET n = n + excluded.n")
  .bind(new Date().toISOString().slice(0, 10), metric, String(k), n);
const outboxStmt = (env, chats, text, prio, now) => env.DB.prepare("INSERT INTO outbox (chat_id, chats, text, created, prio) VALUES (NULL, ?, ?, ?, ?)")
  .bind(JSON.stringify(chats), text, new Date(now).toISOString(), prio ? 1 : 0);
function fansOf(m, by) {
  return [...new Set([...(by[`team:${m.home_slug}`] || []), ...(by[`team:${m.away_slug}`] || []), ...(by[`league:${m.league_slug}`] || []), ...(by[`match:${m.slug}`] || [])])];
}
async function followersBy(env) {
  const subs = (await env.DB.prepare("SELECT chat_id, kind, slug FROM subs").all()).results || [];
  const by = {};
  for (const s of subs) (by[`${s.kind}:${s.slug}`] = by[`${s.kind}:${s.slug}`] || []).push(s.chat_id);
  return { subs, by };
}

// v35: B = { left: n } is this minute's budget of outside requests (ESPN, Telegram, GitHub). The free plan allows 50 per run;
// v34 could need more on busy minutes, and the run then stopped part-way, so alerts waited or were lost.
async function liveTick(env, now = Date.now(), B = { left: 45 }) {
  await ensureTables(env);
  const obj = await env.DATA.get("site/schedule.json");
  if (!obj) return "no schedule";
  const sched = await obj.json();
  const live = sched.filter(m => m.espn && m.kickoff && now >= Date.parse(m.kickoff) - 5 * 60000 && now <= Date.parse(m.kickoff) + 150 * 60000);
  let queued = 0;
  if (live.length) {
    const { by } = await followersBy(env);
    const watched = live.map(m => ({ m, fans: fansOf(m, by) })).filter(x => x.fans.length);
    if (watched.length) {
      const boards = {};
      for (const code of [...new Set(watched.map(x => x.m.espn.code))].slice(0, 12)) {
        if (B.left <= 5) break;
        B.left--;
        try { const r = await fetch(`https://site.api.espn.com/apis/site/v2/sports/soccer/${code}/scoreboard`, { headers: { "user-agent": "Mozilla/5.0" } }); boards[code] = r.ok ? await r.json() : null; }
        catch (e) { boards[code] = null; }
      }
      // v35: everything this minute needs from the database in four reads, and one write at the end
      const ids = watched.map(x => String(x.m.espn.id));
      const fansAll = [...new Set(watched.flatMap(x => x.fans))];
      const prevOf = Object.fromEntries((await inList(env, "SELECT event_id, data FROM live_state WHERE event_id IN", ids)).map(r => [r.event_id, JSON.parse(r.data)]));
      const prefs = {};
      for (const c of fansAll) prefs[c] = Object.fromEntries(LIVE_PREFS.map(([k, , d]) => [k, d]));
      for (const r of await inList(env, "SELECT chat_id, k, v FROM prefs2 WHERE chat_id IN", fansAll)) if (prefs[r.chat_id]) prefs[r.chat_id][r.k] = r.v;
      let summaries = 0;
      const rows = [], kinds = {};
      for (const { m, fans } of watched) {
        const ev = (((boards[m.espn.code] || {}).events) || []).find(e => String(e.id) === String(m.espn.id));
        if (!ev) continue;
        const s = snapshot(ev);
        // (v32: "pre" is recorded too, in the 5 minutes before kickoff, so the start of play can be detected)
        if (s.stats.h.shots == null && summaries < 5 && B.left > 5) {   // no statistics on the scoreboard: use the match summary
          summaries++; B.left--;
          try { const r = await fetch(`https://site.api.espn.com/apis/site/v2/sports/soccer/${m.espn.code}/summary?event=${m.espn.id}`, { headers: { "user-agent": "Mozilla/5.0" } });
                if (r.ok) fillStatsFromSummary(s, await r.json()); } catch (e) {}
        }
        const prev0 = prevOf[String(m.espn.id)] || null;
        // v35: state saved by v34 used other event keys: count what is on the board now as already sent (no repeats after the upgrade)
        const prev = prev0 && prev0.kv !== KEY_V ? { ...prev0, seen: s.events.map(e => e.key) } : prev0;
        const newGoals = prev ? s.events.filter(e => e.goal && !e.own && e.names.length < 2 && !(prev.seen || []).includes(e.key)) : [];
        if (newGoals.length && summaries < 8 && B.left > 5) {          // fetch the description once, to name the assister
          summaries++; B.left--;
          try { const r = await fetch(`https://site.api.espn.com/apis/site/v2/sports/soccer/${m.espn.code}/summary?event=${m.espn.id}`, { headers: { "user-agent": "Mozilla/5.0" } });
                if (r.ok) { const sm = await r.json(); for (const g of newGoals) { const a = findAssist(sm, g); if (a) g.names.push(a); } } } catch (e) {}
        }
        if (prev && prev.state === "post") continue;                // already finished and reported
        let msgs = prev ? liveMessages(m, prev, s) : liveMessages(m, null, s).filter(x => x.kind === "kickoff");   // first sighting: kick-off only
        const pr = pressureCheck(prev, s);
        if (prev) msgs = msgs.concat(pr.out);
        const sent = { ...((prev && prev.sent) || {}) };            // v35: alerts per person for this match, kept with the match
        for (const msg of msgs) {
          const to = fans.filter(chat => (prefs[chat] || {})[msg.kind] && (msg.always || (sent[chat] || 0) < MAX_PER_MATCH));
          if (!to.length) continue;
          to.forEach(chat => { sent[chat] = (sent[chat] || 0) + 1; });
          rows.push(outboxStmt(env, to, msg.text, msg.always, now));
          queued += to.length;
          kinds[msg.kind] = (kinds[msg.kind] || 0) + to.length;
        }
        const state = { kv: KEY_V, state: s.state, stats: s.stats, seen: [...new Set([...((prev && prev.seen) || []), ...s.events.map(e => e.key)])], sent,
                        hist: pr.hist, pressure: pr.last, ko_sent: !!((prev && prev.ko_sent) || s.state === "in" || s.state === "post"), ht_sent: !!((prev && prev.ht_sent) || /HALFTIME/i.test(s.name) || /^HT$/i.test(s.detail)) };
        // v35: the match state is saved in the same write as its alerts, so a failed run can't mark events as sent without queueing them
        rows.push(env.DB.prepare("INSERT INTO live_state (event_id, data, updated) VALUES (?, ?, ?) ON CONFLICT(event_id) DO UPDATE SET data = excluded.data, updated = excluded.updated")
          .bind(String(m.espn.id), JSON.stringify(state), new Date(now).toISOString()));
      }
      for (const [k, n] of Object.entries(kinds)) rows.push(bumpStmt(env, "alerts_live", k, n));
      if (rows.length) await env.DB.batch(rows);
    }
  }
  const stale = sched.filter(m => m.kickoff && now - Date.parse(m.kickoff) > 24 * 3600000).map(m => m.slug);
  if (new Date(now).getUTCMinutes() === 7 && stale.length)          // once an hour: tidy finished single-match follows
    await env.DB.batch(stale.slice(0, 40).map(s => env.DB.prepare("DELETE FROM subs WHERE kind = 'match' AND slug = ?").bind(s)));
  const sent = await flushOutbox(env, B);
  return `live: ${live.length} in progress, ${queued} queued, ${sent} sent`;
}

// v35: lineup alerts straight from ESPN, as soon as both teams are announced (about an hour before kickoff), instead of waiting
// for a GitHub run. Checked every 5 minutes for followed matches kicking off in the next 80 minutes; each match is alerted once.
function lineupText(m, s, site) {
  const ko = m.kickoff ? watTime(m.kickoff, false) : "";
  const side = r => { const xi = (r.roster || []).filter(p => p.starter).map(p => (p.athlete || {}).displayName).filter(Boolean);
    return `<b>${esc((r.team || {}).displayName || "")}</b>${r.formation ? ` (${esc(r.formation)})` : ""}: ${esc(xi.join(", "))}`; };
  const R = s.rosters || [], H = R.find(r => r.homeAway === "home") || R[0], A = R.find(r => r.homeAway === "away") || R[1];
  return `📋 <b>Lineups: ${esc(m.home)} v ${esc(m.away)}</b>${m.competition ? ` · ${esc(m.competition)}` : ""}${ko ? `, kick-off ${ko}` : ""}\n\n${side(H)}\n\n${side(A)}`
    + (m.pH != null ? `\n\nChances: ${esc(m.home)} ${pct(m.pH)} · draw ${pct(m.pD)} · ${esc(m.away)} ${pct(m.pA)}` : "")
    + (site ? `\n${site}/#/match/${encodeURIComponent(m.slug)}/lineups` : "");
}
async function lineupTick(env, now = Date.now(), B = { left: 10 }) {
  await ensureTables(env);
  const obj = await env.DATA.get("site/schedule.json");
  if (!obj) return "no schedule";
  const soon = (await obj.json()).filter(m => m.espn && m.kickoff && Date.parse(m.kickoff) > now && Date.parse(m.kickoff) - now <= 80 * 60000);
  if (!soon.length) return "no kickoffs soon";
  const { by } = await followersBy(env);
  const cand = soon.map(m => ({ m, fans: fansOf(m, by) })).filter(x => x.fans.length);
  if (!cand.length) return "nobody follows the next kickoffs";
  const done = Object.fromEntries((await inList(env, "SELECT slug, chats FROM lineup_sent WHERE slug IN", cand.map(x => x.m.slug))).map(r => [r.slug, new Set(JSON.parse(r.chats || "[]").map(String))]));
  const off = new Set((await inList(env, "SELECT chat_id FROM prefs WHERE lineups = 0 AND chat_id IN", [...new Set(cand.flatMap(x => x.fans))])).map(r => String(r.chat_id)));
  const rows = []; let n = 0;
  for (const { m, fans } of cand) {
    const to = fans.filter(c => !off.has(String(c)) && !(done[m.slug] || new Set()).has(String(c)));
    if (!to.length || B.left <= 2) continue;
    B.left--;
    let s = null;
    try { const r = await fetch(`https://site.api.espn.com/apis/site/v2/sports/soccer/${m.espn.code}/summary?event=${m.espn.id}`, { headers: { "user-agent": "Mozilla/5.0" } }); s = r.ok ? await r.json() : null; } catch (e) {}
    const ready = s && (s.rosters || []).length === 2 && s.rosters.every(r => (r.roster || []).filter(p => p.starter).length >= 11);
    if (!ready) continue;
    rows.push(outboxStmt(env, to, lineupText(m, s, env.SITE_URL || ""), true, now));
    rows.push(env.DB.prepare("INSERT INTO lineup_sent (slug, chats, at) VALUES (?, ?, ?) ON CONFLICT(slug) DO UPDATE SET chats = excluded.chats, at = excluded.at")
      .bind(m.slug, JSON.stringify([...new Set([...(done[m.slug] || []), ...to.map(String)])]), new Date(now).toISOString()));
    n += to.length;
  }
  if (n) rows.push(bumpStmt(env, "alerts_live", "lineups", n));
  if (rows.length) await env.DB.batch(rows);
  if (new Date(now).getUTCHours() === 3 && new Date(now).getUTCMinutes() < 5)       // once a day: forget lineup alerts older than 3 days
    await env.DB.prepare("DELETE FROM lineup_sent WHERE at < ?").bind(new Date(now - 3 * 86400000).toISOString()).run();
  return `lineups: ${n} queued`;
}
async function liveScores(env, now = Date.now()) {
  // matches that kicked off in the last 2.5 hours, or finished earlier today: { slug: {state, detail, hs, as} }
  const obj = await env.DATA.get("site/schedule.json");
  if (!obj) return {};
  const sched = await obj.json();
  const today = new Date(now).toISOString().slice(0, 10);
  const due = sched.filter(m => m.espn && m.kickoff && Date.parse(m.kickoff) <= now + 5 * 60000 && (now - Date.parse(m.kickoff) < 150 * 60000 || m.kickoff.slice(0, 10) === today));
  const out = {};
  for (const code of [...new Set(due.map(m => m.espn.code))].slice(0, 25)) {
    let board = null;
    try { const r = await fetch(`https://site.api.espn.com/apis/site/v2/sports/soccer/${code}/scoreboard`, { headers: { "user-agent": "Mozilla/5.0" } }); board = r.ok ? await r.json() : null; } catch (e) {}
    for (const m of due.filter(x => x.espn.code === code)) {
      const ev = ((board || {}).events || []).find(e => String(e.id) === String(m.espn.id));
      if (!ev) continue;
      const s = snapshot(ev);
      if (s.state === "pre") continue;
      out[m.slug] = { state: s.state, detail: s.state === "post" ? "FT" : (/HALFTIME/i.test(s.name) ? "HT" : (s.detail || "")), hs: s.hs, as: s.as };
    }
  }
  // v35: competitions ESPN doesn't cover (the Egyptian Premier League): full-time scores from PitchAPI, which fills them in at full-time
  if (env.PITCHAPI_KEY) {
    const yest = new Date(now - 86400000).toISOString().slice(0, 10);
    const noEspn = sched.filter(m => !m.espn && (m.kickoff ? Date.parse(m.kickoff) + 105 * 60000 <= now && now - Date.parse(m.kickoff) < 36 * 3600000
                                                            : m.date && m.date >= yest && m.date <= today));
    for (const day of [...new Set(noEspn.map(m => String(m.kickoff || m.date).slice(0, 10)))].slice(0, 3)) {
      let list = [];
      try { list = ((await pa(env, `/v1/date/${day}`)) || {}).matches || []; } catch (e) {}
      for (const m of noEspn.filter(x => String(x.kickoff || x.date).slice(0, 10) === day)) {
        let best = null;
        for (const p of list) { const s = (teamSim(m.home, (p.home_team || {}).name) + teamSim(m.away, (p.away_team || {}).name)) / 2; if (s >= 0.6 && (!best || s > best.s)) best = { s, p }; }
        if (best && /finish|ended|^ft$/i.test(String(best.p.status || "")) && best.p.score_home != null && best.p.score_away != null)
          out[m.slug] = { state: "post", detail: "FT", hs: Number(best.p.score_home), as: Number(best.p.score_away) };
      }
    }
  }
  return out;
}
// v35: sends as many queued messages as this minute's request budget allows (goals and full-time first), 10 at a time in parallel.
// Telegram itself allows about 30 messages a second; the limit here is Cloudflare's per-run request allowance.
async function flushOutbox(env, B = { left: 30 }) {
  if (typeof B === "number") B = { left: B };
  if (B.left <= 0) return 0;
  const q = (await env.DB.prepare("SELECT id, chat_id, chats, text FROM outbox ORDER BY prio DESC, id LIMIT 25").all()).results || [];
  if (!q.length) return 0;
  const active = new Set(((await env.DB.prepare("SELECT DISTINCT chat_id FROM subs").all()).results || []).map(r => String(r.chat_id)));   // skip anyone who sent /stop
  const jobs = [], stmts = [];
  for (const r of q) {
    if (B.left <= 0) break;
    const list = (r.chats ? JSON.parse(r.chats) : [r.chat_id]).filter(c => active.has(String(c)));
    const now_ = list.slice(0, B.left), rest = list.slice(B.left);
    B.left -= now_.length;
    now_.forEach(c => jobs.push({ c, text: r.text }));
    stmts.push(rest.length ? env.DB.prepare("UPDATE outbox SET chats = ?, chat_id = NULL WHERE id = ?").bind(JSON.stringify(rest), r.id)
                           : env.DB.prepare("DELETE FROM outbox WHERE id = ?").bind(r.id));
  }
  for (let i = 0; i < jobs.length; i += 10)
    await Promise.all(jobs.slice(i, i + 10).map(j => tg(env, "sendMessage", { chat_id: j.c, text: j.text, parse_mode: "HTML", disable_web_page_preview: true }).catch(() => false)));
  if (stmts.length) await env.DB.batch(stmts);
  return jobs.length;
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
// Lineup-time runs, kept lean to save GitHub minutes (checked every 15 minutes):
//  - only for kickoffs 50-65 minutes away (lineups are out by the time the run fetches them; no waiting inside the run),
//  - only for matches someone follows, or in the headline competitions, and only where ESPN has lineups,
//  - no second run within 20 minutes (one run covers every kickoff in its 15-minute window),
//  - at most LINEUP_DAILY_MAX runs a day (default 6), with followed teams' matches first (they may use 2 more).
const HEADLINE = ["Premier League", "La Liga", "Bundesliga", "Serie A", "Ligue 1", "Champions League", "Europa League", "Conference League"];
async function maybeDispatch(env, now = Date.now()) {
  const obj = await env.DATA.get("site/schedule.json");
  if (!obj) return "no schedule";
  const sched = await obj.json();
  const mins = m => (Date.parse(m.kickoff) - now) / 60000;
  let due = sched.filter(m => m.kickoff && m.espn && mins(m) >= 50 && mins(m) < 65);
  if (!due.length) return "nothing due";
  const comps = (env.LINEUP_COMPS ? String(env.LINEUP_COMPS).split(",").map(s => s.trim()) : HEADLINE);
  const subs = (await env.DB.prepare("SELECT kind, slug FROM subs").all()).results || [];
  const followed = new Set(subs.map(s => `${s.kind}:${s.slug}`));
  const isFollowed = m => followed.has(`team:${m.home_slug}`) || followed.has(`team:${m.away_slug}`) || followed.has(`league:${m.league_slug}`);
  due = due.filter(m => comps.includes(m.competition) || isFollowed(m));
  if (!due.length) return "nothing due that anyone follows";
  const dueFollowed = due.some(isFollowed);
  const recent = await env.DB.prepare("SELECT slot FROM dispatched WHERE at >= ?").bind(new Date(now - 20 * 60000).toISOString()).first();
  if (recent) return "a run started in the last 20 minutes already covers these";
  const today = new Date(now).toISOString().slice(0, 10);
  const nToday = ((await env.DB.prepare("SELECT COUNT(*) AS n FROM dispatched WHERE at >= ?").bind(today).first()) || {}).n || 0;
  const cap = parseInt(env.LINEUP_DAILY_MAX || "6");
  // followed teams first: their slots always run (up to cap + 2); other slots only if a run is still left after
  // reserving one for each later slot today that has a followed match
  const later = new Set(sched.filter(m => m.kickoff && m.espn && m.kickoff.slice(0, 10) === today && mins(m) >= 65 && isFollowed(m))
                             .map(m => m.kickoff.slice(0, 15)));
  if (dueFollowed && nToday >= cap + 2) return `daily ceiling reached (${nToday} runs today)`;
  if (!dueFollowed && nToday + later.size >= cap) return `skipped: keeping ${later.size} run(s) for followed matches later today (${nToday} used, cap ${cap})`;
  const slot = due.map(m => m.kickoff.slice(0, 16)).sort()[0];
  const r = await fetch(`https://api.github.com/repos/${env.GITHUB_REPO}/actions/workflows/lineups.yml/dispatches`, {
    method: "POST", headers: { authorization: `Bearer ${env.GITHUB_TOKEN}`, accept: "application/vnd.github+json", "user-agent": "kwallo-bot" },
    body: JSON.stringify({ ref: "main" }) });
  if (r.ok || r.status === 204) {
    await env.DB.prepare("INSERT OR IGNORE INTO dispatched (slot, at) VALUES (?, ?)").bind(slot, new Date(now).toISOString()).run();
    return `started run for ${slot} (${due.length} matches)`;
  }
  return "GitHub said " + r.status;
}

// ================= v35: a past match's statistics and a player's transfer history, for the website =================
// Both come from ESPN when someone opens the page, and are cached at the edge (finished matches for a day, transfers for a week).
const STAT_LABELS = [["possessionPct", "Possession %"], ["totalShots", "Shots"], ["shotsOnTarget", "Shots on target"], ["wonCorners", "Corners"],
  ["foulsCommitted", "Fouls"], ["yellowCards", "Yellow cards"], ["redCards", "Red cards"], ["offsides", "Offsides"], ["saves", "Saves"],
  ["totalTackles", "Tackles"], ["interceptions", "Interceptions"], ["totalPasses", "Passes"], ["passPct", "Pass accuracy"], ["totalCrosses", "Crosses"]];
// v35: one player, two spellings: ESPN's events say "Isak Määttä" or "Alfon González", its team sheet "Isak Dybvik Määttä" or
// "Alfonso González". Same surname, and one first name starts the other
function sameName(a, b) {
  if (a === b) return true;
  const x = nameToks(a), y = nameToks(b);
  return !!(x.length && y.length && x[x.length - 1] === y[y.length - 1] && (x[0].startsWith(y[0]) || y[0].startsWith(x[0])));
}
async function matchResult(code, id) {
  const r = await fetch(`https://site.api.espn.com/apis/site/v2/sports/soccer/${code}/summary?event=${id}`, { headers: { "user-agent": "Mozilla/5.0" } });
  if (!r.ok) return null;
  const s = await r.json();
  const comp = ((s.header || {}).competitions || [])[0] || {};
  const teams = (comp.competitors || []).map(c => ({ side: c.homeAway, name: (c.team || {}).displayName, score: c.score, winner: !!c.winner }));
  const box = ((s.boxscore || {}).teams || []);
  const asPct = (k, v) => (/Pct$/.test(k) && k !== "possessionPct" && v != null && isFinite(parseFloat(v)) && parseFloat(v) <= 1 ? `${Math.round(100 * parseFloat(v))}%` : v);   // 0.7 -> 70%
  const statOf = side => { const t = box.find(b => b.homeAway === side) || {}; return Object.fromEntries((t.statistics || []).map(x => [x.name, asPct(x.name, x.displayValue)])); };
  const H = statOf("home"), A = statOf("away");
  const stats = STAT_LABELS.filter(([k]) => H[k] != null || A[k] != null).map(([k, label]) => ({ key: k, label, home: H[k] ?? "–", away: A[k] ?? "–" }));
  const events = (s.keyEvents || []).filter(k => /goal|card|penalty|substitut/i.test(String((k.type || {}).text || ""))).map(k => ({
    clock: (k.clock || {}).displayValue || "", type: String((k.type || {}).text || ""), team: (k.team || {}).displayName || "",
    text: k.text || (k.participants || []).map(p => (p.athlete || {}).displayName).filter(Boolean).join(", ") }));
  const st = ((comp.status || {}).type) || {};
  const tid = Object.fromEntries((comp.competitors || []).map(c => [String((c.team || {}).id), c.homeAway]));
  // v35: substitutions (who came on, when, for whom) from the key events: "Substitution, Napoli. A replaces B."
  const subs = {};
  for (const k of s.keyEvents || []) {
    if (!/substitut/i.test(String((k.type || {}).text || ""))) continue;
    const m = String(k.text || "").match(/\.\s*(.+?) replaces (.+?)(?:\s+because of an injury)?\.?$/i);
    const inName = m ? m[1].trim() : ((k.participants || [])[0] || {}).athlete?.displayName, outName = m ? m[2].trim() : ((k.participants || [])[1] || {}).athlete?.displayName;
    const clock = (k.clock || {}).displayValue || "";
    if (inName) subs[inName] = { ...(subs[inName] || {}), on: clock, for: outName || "" };
    if (outName) subs[outName] = { ...(subs[outName] || {}), off: clock };
  }
  const pstat = (p, n) => { const x = (p.stats || []).find(y => y.name === n); return x ? Number(x.value ?? x.displayValue) || 0 : 0; };
  // v35: the whole matchday squad (XI and bench) with shirt numbers, substitutions, goals and cards
  const lineups = (s.rosters || []).map(t => {
    const all = (t.roster || []).map(p => { const nm = (p.athlete || {}).displayName || "", sb = subs[nm] || (Object.entries(subs).find(([k]) => sameName(k, nm)) || [])[1] || {};
      return { name: nm, id: String((p.athlete || {}).id || ""), pos: (p.position || {}).abbreviation || "", jersey: p.jersey || "", starter: !!p.starter,
               on: p.subbedIn ? (sb.on || "") : null, for: p.subbedIn ? (sb.for || ((p.subbedInFor || {}).athlete || {}).displayName || "") : null,
               off: p.subbedOut ? (sb.off || "") : null, goals: pstat(p, "totalGoals"), assists: pstat(p, "goalAssists"),
               yellow: pstat(p, "yellowCards"), red: pstat(p, "redCards") }; });
    // a double substitution can leave the newcomer without a minute: he came on when the player he replaced went off
    // Each substitute is tied to the starter he replaced: same name first; then, for the rest, the closest spelling ("Aleksey" /
    // "Alexey", "Jonny" / "Jonny Otto"); a last pair left over on each side belongs together ("Gabriel Sara" is "Gabriel Gomes").
    // His "for" then carries the team-sheet name, so the website finds the right starter.
    const ins = all.filter(q => q.on != null && q.for), outs = all.filter(p => p.starter && p.off != null), tie = (q, p) => { q.for = p.name; q.tied = p.tied = true; };
    ins.forEach(q => { const p = outs.find(p => !p.tied && sameName(p.name, q.for)); if (p) tie(q, p); });
    const sim = (a, b) => teamSim(String(a).replace(/ß/g, "ss"), String(b).replace(/ß/g, "ss"));
    const pairs = ins.filter(q => !q.tied).flatMap(q => outs.filter(p => !p.tied).map(p => ({ q, p, s: sim(q.for, p.name) }))).sort((a, b) => b.s - a.s);
    for (const { q, p, s } of pairs) if (s >= 0.45 && !q.tied && !p.tied) tie(q, p);
    const lq = ins.filter(q => !q.tied), lp = outs.filter(p => !p.tied);
    if (lq.length === 1 && lp.length === 1) tie(lq[0], lp[0]);
    ins.forEach(q => { const p = all.find(p => p.tied && p.starter && p.name === q.for); if (!p) return;   // a double substitution can leave one minute out
      if (q.on === "" && p.off) q.on = p.off; if (p.off === "" && q.on) p.off = q.on; });
    all.forEach(p => { delete p.tied; });
    return { side: t.homeAway, team: (t.team || {}).displayName, formation: t.formation || null, xi: all.filter(p => p.starter), bench: all.filter(p => !p.starter) };
  });
  let sl = shotList(s, teams);                           // v35: shot-by-shot xG (estimated), for the xG figures and the momentum chart
  const real = ESPN_XG_CODES.has(code) && sl.last ? await espnShots(code, id, tid).catch(() => null) : null;
  if (real) sl = { shots: real, last: sl.last };          // v36: ESPN's own xG for every shot, where it gives it (else Kwallo's estimate)
  const xg = xgEstimate(sl), mom = momentum(sl);
  if (real && xg) { xg.source = "espn"; mom.source = "xg"; }
  return { competition: ((s.header || {}).league || {}).name || "", date: comp.date || null, status: st.detail || "", state: st.state || "",
           completed: !!st.completed, venue: ((s.gameInfo || {}).venue || {}).fullName || "",
           teams: teams.map(t => { const tm = (((comp.competitors || []).find(c => c.homeAway === t.side) || {}).team || {});
             return { ...t, id: String(tm.id || ""), color: tm.color ? `#${tm.color}` : null, alt: tm.alternateColor ? `#${tm.alternateColor}` : null }; }),   // v35: kit colours
           stats, events, lineups, timeline: timeline(s, tid), momentum: mom, xg };
}
// v36: ESPN's play-by-play carries an expected-goals value for every shot in these competitions (checked October 2026: the big five,
//      the three European cups, the Championship, MLS, Liga MX, Brazil, Argentina, the Libertadores and the Sudamericana). Used only
//      if 80% or more of the match's shots so far have one, so a league or a moment where ESPN leaves them out keeps the estimate.
const ESPN_XG_CODES = new Set(["eng.1", "esp.1", "ger.1", "ita.1", "fra.1", "uefa.champions", "uefa.europa", "uefa.europa.conf", "eng.2", "usa.1",
                               "mex.1", "bra.1", "arg.1", "conmebol.libertadores", "conmebol.sudamericana"]);
async function espnShots(code, id, tid) {
  const items = [];
  for (let page = 1; page <= 3; page++) {
    const r = await fetch(`https://sports.core.api.espn.com/v2/sports/soccer/leagues/${code}/events/${id}/competitions/${id}/plays?limit=1000&page=${page}`,
                          { headers: { "user-agent": "Mozilla/5.0" } });
    if (!r.ok) return null;
    const j = await r.json();
    items.push(...(j.items || []));
    if (!j.pageCount || page >= j.pageCount) break;
  }
  const shots = [];
  let tried = 0;
  for (const p of items) {
    const ty = String((p.type || {}).text || "");
    if (p.shootout || p.ownGoal || !SHOT_TYPE.test(ty)) continue;
    tried++;
    const side = tid[String(((p.team || {}).$ref || "").match(/teams\/(\d+)/)?.[1] || "")];
    const m = minuteOfClock((p.clock || {}).displayValue);
    if (p.expectedGoals == null || !side || !m) continue;
    shots.push({ m, side: side === "home" ? "h" : "a", xg: Math.max(0, +p.expectedGoals || 0), goal: !!p.scoringPlay });
  }
  return tried && shots.length >= 0.8 * tried ? shots : null;
}
// v35: the timeline card: goals (with the score and the assister), cards and substitutions, newest first; added time where ESPN says it
function timeline(s, tid) {
  const out = [];
  let hs = 0, as = 0;
  const minuteOf = c => { const p = String(c || "").replace(/'/g, "").split("+").map(x => parseInt(x)); return (p[0] || 0) + (p[1] || 0) / 100; };
  const keys = [...(s.keyEvents || [])].sort((a, b) => minuteOf((a.clock || {}).displayValue) - minuteOf((b.clock || {}).displayValue));
  for (const k of keys) {
    const t = String((k.type || {}).text || ""), clock = (k.clock || {}).displayValue || "", side = tid[String((k.team || {}).id)] || null;
    const names = (k.participants || []).map(p => (p.athlete || {}).displayName).filter(Boolean);
    if (/goal|penalty - scored/i.test(t) && !/missed|saved/i.test(t)) {
      const m = String(k.text || "").match(/(\d+),[^.]*?\s(\d+)\./);           // "Goal! Napoli 1, Bodø/Glimt 0."
      if (m) { hs = +m[1]; as = +m[2]; } else if (side === "home") hs++; else if (side === "away") as++;
      out.push({ clock, side, kind: /own goal/i.test(t) ? "own" : /penalty/i.test(t) ? "pen" : "goal", main: names[0] || "", extra: /own goal/i.test(t) ? "own goal" : (names[1] || ""), score: `${hs}-${as}` });
    } else if (/red card/i.test(t)) out.push({ clock, side, kind: "red", main: names[0] || "" });
    else if (/yellow/i.test(t)) out.push({ clock, side, kind: "yellow", main: names[0] || "" });
    else if (/substitut/i.test(t)) {
      const m = String(k.text || "").match(/\.\s*(.+?) replaces (.+?)(?:\s+because of an injury)?\.?$/i);
      out.push({ clock, side, kind: "sub", main: m ? m[1].trim() : (names[0] || ""), extra: m ? m[2].trim() : (names[1] || "") });
    } else if (/halftime/i.test(t)) out.push({ clock: "HT", kind: "ht", score: `${hs}-${as}` });
  }
  for (const c of s.commentary || []) {                              // "... announced 3 minutes of added time."
    const m = String(c.text || "").match(/(\d+)\s+minutes? of added time/i);
    if (m) out.push({ clock: (c.time || {}).displayValue || "", kind: "added", main: `Additional time ${m[1]} min` });
  }
  return out.sort((a, b) => minuteOf(b.clock === "HT" ? "45+59" : b.clock) - minuteOf(a.clock === "HT" ? "45+59" : a.clock));
}
// v35: Kwallo's own xG for every shot, from ESPN's live commentary: where it was taken, foot or header, and how it was set up.
// ESPN gives no team xG; PitchAPI's real figures replace these after full-time.
// (values checked against PitchAPI's real xG for 12 Champions League matches, October 2026)
const XG_SPOT = [[/penalty/i, 0.76], [/very close range/i, 0.55], [/centre of the six yard box/i, 0.45], [/side of the six yard box/i, 0.26],
  [/difficult angle/i, 0.05], [/centre of the box/i, 0.17], [/side of the box/i, 0.09], [/direct free kick/i, 0.07],
  [/more than \d+ yards/i, 0.015], [/long range/i, 0.03], [/outside the box/i, 0.045]];
// a shot or a goal ("Goal", "Goal - Header", "Shot On Target", "Shot Blocked", "Shot Hit Woodwork", penalties); v36: not "Goal Kick" or "Assists Shot"
const SHOT_TYPE = /^(goal(?! kick)|shot\b|penalty - (scored|missed|saved))/i;
function shotXg(c) {                                     // { xg, goal } for a shot, null for anything else
  const ty = String(((c.play || {}).type || {}).text || ""), tx = String(c.text || "");
  if (!SHOT_TYPE.test(ty) || /own goal/i.test(ty)) return null;
  let xg = (XG_SPOT.find(([re]) => re.test(tx)) || [null, 0.1])[1];   // where from (no place given: an average shot)
  if (xg !== 0.76) {
    if (/header/i.test(tx)) xg *= 0.6;
    if (/through ball/i.test(tx)) xg *= 1.4;
    if (/fast break/i.test(tx)) xg *= 1.3;
  }
  return { xg: Math.min(xg, 0.9), goal: /^goal|scored/i.test(ty) };
}
const minuteOfClock = c => String(c || "").replace(/'/g, "").split("+").map(x => parseInt(x))[0] || 0;
function shotList(s, teams) {                            // every shot: minute, side, xG; and how far the match has got
  const H = (teams.find(t => t.side === "home") || {}).name, A = (teams.find(t => t.side === "away") || {}).name;
  const shots = [];
  let last = 0;
  for (const c of s.commentary || []) {
    const m = minuteOfClock((c.time || {}).displayValue);
    if (!m) continue;
    last = Math.max(last, m);
    const x = shotXg(c), team = ((c.play || {}).team || {}).displayName, side = team === H ? "h" : team === A ? "a" : null;
    if (x && side) shots.push({ m, side, ...x });
  }
  return { shots, last };
}
function xgEstimate({ shots, last }) {                   // each side's total, and each half's
  if (!last) return null;
  const sum = (side, f) => +shots.filter(x => x.side === side && f(x.m)).reduce((t, x) => t + x.xg, 0).toFixed(2);
  const all = () => true, first = m => m <= 45, second = m => m > 45;
  // v36: each side's xG so far at every minute (0-90; stoppage time counts in the 45th and 90th), for the live chances and their graph
  const cum = side => { const v = new Array(91).fill(0); shots.filter(x => x.side === side).forEach(x => { v[x.m <= 45 ? Math.min(x.m, 45) : Math.min(x.m, 90)] += x.xg; });
    for (let i = 1; i <= 90; i++) v[i] += v[i - 1]; return v.map(x => +x.toFixed(3)); };
  return { source: "estimate", home: sum("h", all), away: sum("a", all),
           halves: [[sum("h", first), sum("a", first)], ...(last > 45 ? [[sum("h", second), sum("a", second)]] : [])], cum: { home: cum("h"), away: cum("a") } };
}
// v35: our own momentum: each side's chances minute by minute, from the same shot-by-shot xG
function momentum({ shots, last }) {
  if (!last) return null;
  const h = new Array(91).fill(0), a = new Array(91).fill(0), goals = [];
  for (const x of shots) {
    const slot = x.m <= 45 ? Math.min(x.m, 45) : Math.min(x.m, 90);
    (x.side === "h" ? h : a)[slot] += x.xg;
    if (x.goal) goals.push({ m: slot, side: x.side });
  }
  const smooth = v => v.map((_, i) => i === 0 ? 0 : +(0.5 * v[i] + 0.25 * (v[i - 1] || 0) + 0.25 * (v[i + 1] || 0)).toFixed(3));
  return { source: "xg_est", upto: Math.min(last, 90), home: smooth(h), away: smooth(a), goals };
}
async function transfers(id) {
  const r = await fetch(`https://sports.core.api.espn.com/v2/sports/soccer/athletes/${id}/transactions?lang=en&region=us`, { headers: { "user-agent": "Mozilla/5.0" } });
  if (!r.ok) return [];
  const items = ((await r.json()).items || []).sort((a, b) => String(b.date).localeCompare(String(a.date))).slice(0, 10);
  const refs = [...new Set(items.flatMap(t => [(t.from || {}).$ref, (t.to || {}).$ref]).filter(Boolean))].slice(0, 16);
  const names = {};
  await Promise.all(refs.map(async ref => {
    try { const x = await fetch(ref.replace(/^http:\/\/sports\.core\.api\.espn\.(pvt|com)/, "https://sports.core.api.espn.com"), { headers: { "user-agent": "Mozilla/5.0" } });
          if (x.ok) { const j = await x.json(); names[ref] = j.displayName || j.name || ""; } } catch (e) {}
  }));
  return items.map(t => ({ date: String(t.date || "").slice(0, 10), from: names[(t.from || {}).$ref] || "", to: names[(t.to || {}).$ref] || "",
                           type: t.type || "", fee: t.displayAmount && t.displayAmount !== t.type ? t.displayAmount : "" }));
}
// ================= v35: the match stats card (in play and full-time) =================
// In play: ESPN's statistics (every minute, whole match only). After full-time: PitchAPI's full statistics (xG, big chances,
// ratings, 1st / 2nd half), found by date and team names; until PitchAPI has the match, ESPN's figures stay.
const OVERVIEW = ["possessionPct", "totalShots", "shotsOnTarget", "saves", "wonCorners", "foulsCommitted", "totalPasses", "totalTackles", "yellowCards", "redCards", "offsides"];
function espnCard(R) {
  const by = Object.fromEntries((R.stats || []).map(s => [s.key, s]));
  const items = keys => keys.map(k => by[k]).filter(Boolean).map(s => ({ label: s.label, home: s.home, away: s.away, key: s.key }));
  const rest = (R.stats || []).filter(s => !OVERVIEW.includes(s.key)).map(s => ({ label: s.label, home: s.home, away: s.away, key: s.key }));
  // v35: Kwallo's estimated xG at the top, for the whole match and each half (ESPN's own figures are whole-match only)
  const xg = R.xg, f2 = x => Number(x).toFixed(2),
        xgItem = (h, a) => ({ key: "xg_est", label: xg && xg.source === "espn" ? "Expected goals (xG)" : "Expected goals (xG), estimated", home: f2(h), away: f2(a) });
  const halves = xg ? xg.halves.map((hv, i) => ({ name: i ? "2nd" : "1st", groups: [{ title: "Expected goals (xG)", items: [xgItem(hv[0], hv[1])] }] })) : [];
  return { source: "espn", periods: [{ name: "All", groups: [{ title: "Match overview", items: [...(xg ? [xgItem(xg.home, xg.away)] : []), ...items(OVERVIEW)] },
    ...(rest.length ? [{ title: "More", items: rest }] : [])] }, ...halves] };
}
// v35: PitchAPI's real xG sits right under possession, whichever section PitchAPI put it in
const isXg = it => /^expected_?goals$/i.test(String(it.key || "")) || /^expected goals( \(xg\))?$/i.test(String(it.label || ""));
function xgToTop(periods) {
  for (const p of periods) {
    let item = null;
    for (const g of p.groups) { const i = g.items.findIndex(isXg); if (i >= 0 && !item) item = g.items.splice(i, 1)[0]; }
    if (!item) continue;
    item.label = "Expected goals (xG)";
    let ov = p.groups.find(g => g.title === "Match overview");
    if (!ov) { ov = { title: "Match overview", items: [] }; p.groups.unshift(ov); }
    const at = ov.items.findIndex(it => /posses/i.test(`${it.key || ""} ${it.label || ""}`));
    ov.items.splice(at + 1, 0, item);
    p.groups = p.groups.filter(g => g.items.length);
  }
  return periods;
}
const PA_LABELS = { BallPossesion: "Ball possession", expected_goals: "Expected goals (xG)", big_chance: "Big chances", total_shots: "Total shots", keeper_saves: "Goalkeeper saves",
  corners: "Corner kicks", fouls: "Fouls", passes: "Passes", "matchstats.headers.tackles": "Tackles", free_kicks: "Free kicks", yellow_cards: "Yellow cards", red_cards: "Red cards",
  player_throws: "Throw-ins", Offsides: "Offsides", rating: "Average rating", average_rating: "Average rating", ShotsOnTarget: "Shots on target", shots_on_target: "Shots on target", expected_goals_on_target: "xG on target (xGOT)" };
const prettyKey = k => PA_LABELS[k] || String(k).replace(/^matchstats\.headers\./, "").replace(/[_.]+/g, " ").replace(/([a-z])([A-Z])/g, "$1 $2").replace(/^./, c => c.toUpperCase());
const PA_STOP = new Set(["fc", "fk", "sk", "ac", "nk", "hnk", "afc", "sc", "cf", "club", "sv", "bk", "if", "ks", "mfk", "ofk", "fsv", "the", "cd", "ud", "sd", "rc", "ss", "ssc", "de", "calcio"]);
const PA_ALIAS = { prague: "praha", belgrade: "beograd", munich: "munchen", lisbon: "lisboa" };
const normTeam = s => String(s || "").normalize("NFKD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/[^a-z0-9 ]/g, " ").split(/\s+/)
  .filter(w => w && !PA_STOP.has(w)).map(w => PA_ALIAS[w] || w).join("");
function teamSim(a, b) {                                  // 0..1: letter-pair overlap, or 0.9 when one name contains the other
  const x = normTeam(a), y = normTeam(b);
  if (!x || !y) return 0;
  if (x === y) return 1;
  const pairs = s => { const m = new Map(); for (let i = 0; i < s.length - 1; i++) { const g = s.slice(i, i + 2); m.set(g, (m.get(g) || 0) + 1); } return m; };
  const A = pairs(x), B = pairs(y); let n = 0;
  for (const [g, c] of A) n += Math.min(c, B.get(g) || 0);
  const dice = (2 * n) / Math.max(1, x.length - 1 + y.length - 1);
  return (x.includes(y) || y.includes(x)) && Math.min(x.length, y.length) >= 4 ? Math.max(0.9, dice) : dice;
}
// v35: PitchAPI's stat sections come without names: name each by what it holds
function groupName(items) {
  const k = items.map(i => String(i.key || i.label || "").toLowerCase()).join(" ");
  if (/posses/.test(k)) return "Match overview";
  if (/duel|aerial|dribble/.test(k)) return "Duels";
  if (/tackle|intercept|clearance|block/.test(k)) return "Defending";
  if (/keeper|save|goals_prevented/.test(k)) return "Goalkeeping";
  if (/pass|long_ball|cross/.test(k)) return "Passes";
  if (/expected|xg/.test(k)) return "Expected goals (xG)";
  if (/shot|on_target/.test(k)) return "Shots";
  if (/card|foul/.test(k)) return "Discipline";
  if (/touch|big_chance|corner|offside|box/.test(k)) return "Attack";
  return "More";
}
async function pa(env, path) {
  const r = await fetch(`https://api.pitchapi.dev${path}`, { headers: { "X-API-KEY": env.PITCHAPI_KEY } });
  if (!r.ok) return null;
  return (await r.json()).data || null;
}
async function paDay(env, ctx, day) {                     // one day's PitchAPI matches, cached for 6 hours
  const ck = new Request(`https://kwallo-cache/pa-day/${day}`), hit = await caches.default.match(ck);
  if (hit) return hit.json();
  const list = ((await pa(env, `/v1/date/${day}`)) || {}).matches || [];
  if (list.length) ctx.waitUntil(caches.default.put(ck, new Response(JSON.stringify(list), { headers: { "cache-control": "public, max-age=21600" } })));   // a failed call isn't kept
  return list;
}
async function pitchapiCard(env, ctx, R) {
  if (!env.PITCHAPI_KEY || !R.date) return null;
  const H = (R.teams || []).find(t => t.side === "home") || {}, A = (R.teams || []).find(t => t.side === "away") || {};
  const d0 = new Date(R.date), days = [0, -1, 1].map(k => new Date(d0.getTime() + k * 86400000).toISOString().slice(0, 10));
  let best = null;
  for (const day of days) {
    for (const m of await paDay(env, ctx, day)) {
      const s = (teamSim(H.name, (m.home_team || {}).name) + teamSim(A.name, (m.away_team || {}).name)) / 2;
      if (s >= 0.6 && (!best || s > best.s)) best = { s, id: m.id, home_id: String((m.home_team || {}).id || ""), away_id: String((m.away_team || {}).id || "") };
    }
    if (best) break;
  }
  if (!best) return null;
  const st = await pa(env, `/v1/matches/${best.id}/stats`);
  const periods = ((st || {}).periods || []).map(p => {
    const nm = String(p.period || "");
    const name = /^all$/i.test(nm) ? "All" : /first|1st|^1$|^1h/i.test(nm) ? "1st" : /second|2nd|^2$|^2h/i.test(nm) ? "2nd" : nm;
    const groups = (p.groups || []).map(g => {
      const items = (g.items || []).filter(it => it.home != null && it.away != null).map(it => ({ key: it.key, label: it.title || it.name || it.label || prettyKey(it.key), home: String(it.home), away: String(it.away) }));
      return { title: g.title || g.name || g.header || groupName(items), items };
    }).filter(g => g.items.length);
    groups.sort((a, b) => (b.title === "Match overview") - (a.title === "Match overview"));   // v35: the overview first
    return { name, groups };
  }).filter(p => p.groups.length);
  if (!periods.length) return null;                       // PitchAPI hasn't filled this match in yet
  periods.sort((a, b) => ["All", "1st", "2nd"].indexOf(a.name) - ["All", "1st", "2nd"].indexOf(b.name));
  xgToTop(periods);
  // v35: xG momentum (every shot's xG by minute) and player ratings, both from PitchAPI after full-time
  let mom = null, ratings = null;
  try {
    const sh = await pa(env, `/v1/matches/${best.id}/shots`);
    const h = new Array(91).fill(0), a = new Array(91).fill(0), goals = [];
    let n = 0;
    for (const per of (sh || {}).periods || []) for (const x of per.shots || []) {
      const mn = Math.max(1, Math.min(90, parseInt(x.minute) || 0)), xg = parseFloat(x.expected_goals) || 0, tm = String(x.team_id || "");
      const side = tm && tm === best.home_id ? "h" : tm && tm === best.away_id ? "a" : null;
      if (!side) continue;
      (side === "h" ? h : a)[mn] += xg; n++;
      if (/goal/i.test(String(x.event_type || x.outcome || "")) && !/own/i.test(String(x.event_type || ""))) goals.push({ m: mn, side });
    }
    const smooth = v => v.map((_, i) => i === 0 ? 0 : +(0.5 * v[i] + 0.25 * (v[i - 1] || 0) + 0.25 * (v[i + 1] || 0)).toFixed(3));
    if (n >= 5) mom = { source: "xg", upto: 90, home: smooth(h), away: smooth(a), goals };
  } catch (e) {}
  try {
    const pls = await pa(env, `/v1/matches/${best.id}/players`);
    const flat = (o, acc) => { if (Array.isArray(o)) o.forEach(x => flat(x, acc)); else if (o && typeof o === "object") {
      const k = String(o.key || "").toLowerCase(), v = o.value ?? o.stat;
      if (/rating/.test(k)) { const val = parseFloat(typeof v === "object" && v ? v.value : v); if (isFinite(val)) acc.r = val; }
      Object.values(o).forEach(x => (x && typeof x === "object") && flat(x, acc)); } return acc; };
    const num = p => { const v = [p.shirt_number, p.jersey_number, p.number, (p.player || {}).shirt_number, (p.player || {}).jersey_number, (p.player || {}).number].find(x => x != null && x !== "");
      return v != null ? String(v) : null; };
    const sideOf = p => { const t = String(p.team_id || (p.team || {}).id || ""); return t && t === best.home_id ? "home" : t && t === best.away_id ? "away" : null; };
    ratings = (Array.isArray(pls) ? pls : []).map(p => ({ name: (p.player || {}).name || "", rating: flat(p.stats || [], {}).r, jersey: num(p), side: sideOf(p) }))
      .filter(p => p.name && p.rating != null);
  } catch (e) {}
  return { source: "pitchapi", pa_id: best.id, periods, momentum: mom, ratings };
}
// v35: PitchAPI's ratings onto ESPN's lineups. The two write names differently (ESPN "Yeray", PitchAPI "Yeray Álvarez"), so: surname and
// initial first, then the shirt number on the same side, then a name the two share when only one player fits
const nameToks = s => String(s || "").normalize("NFKD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/[^a-z ]/g, " ").split(/\s+/).filter(w => w.length >= 3);
function withRatings(lineups, ratings) {
  const key = n => normTeam(String(n).split(" ").slice(-1)[0]) + "|" + normTeam(String(n).split(" ")[0]).slice(0, 1);
  const used = new Set(), byKey = {};
  ratings.forEach((r, i) => { (byKey[key(r.name)] = byKey[key(r.name)] || []).push(i); });
  const players = lineups.flatMap(l => [...l.xi, ...l.bench].map(p => ({ p, side: l.side })));
  const take = (p, i) => { p.rating = ratings[i].rating; used.add(i); };
  for (const { p } of players) { const c = (byKey[key(p.name)] || []).filter(i => !used.has(i)); if (c.length === 1) take(p, c[0]); }
  for (const { p, side } of players) {
    if (p.rating != null || !p.jersey) continue;
    const c = ratings.map((r, i) => i).filter(i => !used.has(i) && ratings[i].jersey === String(p.jersey) && ratings[i].side === side);
    if (c.length === 1) take(p, c[0]);
  }
  for (const { p, side } of players) {
    if (p.rating != null) continue;
    const mine = nameToks(p.name);
    const c = ratings.map((r, i) => i).filter(i => !used.has(i) && (ratings[i].side == null || ratings[i].side === side) && nameToks(ratings[i].name).some(w => mine.includes(w)));
    if (c.length === 1) take(p, c[0]);
  }
  return lineups;
}
async function cachedJSON(ctx, key, maxAge, make) {
  const ck = new Request(key), hit = await caches.default.match(ck);
  if (hit) return hit;
  const out = await make();
  if (out == null) return new Response(JSON.stringify({ error: "not available" }), { status: 404, headers: { ...CORS, "content-type": "application/json" } });
  const res = new Response(JSON.stringify(out), { headers: { ...CORS, "content-type": "application/json; charset=utf-8", "cache-control": `public, max-age=${maxAge}` } });
  ctx.waitUntil(caches.default.put(ck, res.clone()));
  return res;
}

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    if (request.method === "POST" && url.pathname === "/telegram") {
      if (request.headers.get("X-Telegram-Bot-Api-Secret-Token") !== env.WEBHOOK_SECRET) return new Response("forbidden", { status: 403 });
      env.ORIGIN = url.origin;
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
    // v32: the website's data (public files written by the pipeline), cached at the edge for 2 minutes
    if (url.pathname === "/api/live") {                               // v33: live and finished scores for the website
      const cacheKey = new Request("https://kwallo-cache/api/live");
      const cached = await caches.default.match(cacheKey);
      if (cached) return cached;
      const out = await liveScores(env);
      const res = new Response(JSON.stringify(out), { headers: { "content-type": "application/json", "access-control-allow-origin": "*", "cache-control": "public, max-age=60" } });
      ctx.waitUntil(caches.default.put(cacheKey, res.clone()));
      return res;
    }
    if (url.pathname.startsWith("/api/site/")) {
      const rel = url.pathname.slice("/api/site/".length);
      // v35: capitals allowed (PitchAPI player pages end in a mixed-case id, e.g. bruno-fernandes-G7uM; they were unreachable before)
      if (!/^[a-zA-Z0-9][a-zA-Z0-9\-\/_.]*\.json$/.test(rel) || rel.includes("..")) return new Response("not found", { status: 404, headers: CORS });
      const cache = caches.default, ck = new Request(url.toString(), { method: "GET" });
      const hit = await cache.match(ck);
      if (hit) return hit;
      const obj = await env.DATA.get(`site/${rel}`);
      if (!obj) return new Response("not found", { status: 404, headers: CORS });
      const res = new Response(obj.body, { headers: { ...CORS, "content-type": "application/json; charset=utf-8", "cache-control": "public, max-age=120" } });
      ctx.waitUntil(cache.put(ck, res.clone()));
      return res;
    }
    if (url.pathname === "/api/result") {                             // v35: a past match's statistics, e.g. ?e=eng.1:740123
      const m = String(url.searchParams.get("e") || "").match(/^([a-z0-9._]{3,30}):(\d{3,12})$/);
      if (!m) return new Response("not found", { status: 404, headers: CORS });
      // v35: with the stats card; cached for a minute in play, 15 minutes after full-time until PitchAPI has it, then a day
      // the tag changes with each Worker version that changes this reply, so a new deploy never serves a day-old cached copy
      const ck = new Request(`https://kwallo-cache/result-v36a/${m[1]}/${m[2]}`), hit = await caches.default.match(ck);
      if (hit) return hit;
      const R = await matchResult(m[1], m[2]).catch(() => null);
      if (!R) return new Response(JSON.stringify({ error: "not available" }), { status: 404, headers: { ...CORS, "content-type": "application/json" } });
      R.card = (R.completed ? await pitchapiCard(env, ctx, R).catch(() => null) : null) || espnCard(R);
      if (R.card.momentum) R.momentum = R.card.momentum;                // v35: xG momentum after full-time, when PitchAPI has the shots
      if (R.card.source === "pitchapi") {                               // v35: PitchAPI's real xG replaces our estimate (under the score too)
        const all = R.card.periods.find(p => p.name === "All") || R.card.periods[0], it = all && all.groups.flatMap(g => g.items).find(isXg);
        if (it && isFinite(parseFloat(it.home)) && isFinite(parseFloat(it.away)))
          R.xg = { ...(R.xg || {}), source: "pitchapi", home: parseFloat(it.home), away: parseFloat(it.away) };   // (v36: keeps the minute-by-minute xG for the graph)
      }
      if ((R.card.ratings || []).length) R.lineups = withRatings(R.lineups || [], R.card.ratings);   // v35: player ratings onto the lineups
      // v36: ESPN publishes a team sheet first and its positions a few minutes later: meanwhile each starter's usual position
      //      (goalkeeper, defender, midfielder, forward) from the club's squad list, so the pitch still shows a team shape
      await Promise.all((R.lineups || []).map(async l => {
        const known = l.xi.filter(p => p.pos && !/^sub$/i.test(p.pos)).length, t = (R.teams || []).find(x => x.side === l.side);
        if (l.xi.length < 11 || known >= 8 || !t || !t.id) return;
        try { const x = await fetch(`https://site.api.espn.com/apis/site/v2/sports/soccer/${m[1]}/teams/${t.id}/roster`, { headers: { "user-agent": "Mozilla/5.0" } });
              if (!x.ok) return;
              const pos = Object.fromEntries(((await x.json()).athletes || []).map(a => [String(a.id || ""), (a.position || {}).abbreviation || ""]));
              l.xi.forEach(p => { if ((!p.pos || /^sub$/i.test(p.pos)) && pos[p.id]) p.pos = pos[p.id]; });
              l.posFrom = "squad"; } catch (e) {}
      }));
      // v35: before the team sheet, each club's full squad (shirt number, name, position) from ESPN
      if (!(R.lineups || []).length || R.lineups.some(l => l.xi.length < 11)) {
        R.squads = {};
        await Promise.all((R.teams || []).map(async t => {
          if (!t.id) return;
          try { const x = await fetch(`https://site.api.espn.com/apis/site/v2/sports/soccer/${m[1]}/teams/${t.id}/roster`, { headers: { "user-agent": "Mozilla/5.0" } });
                if (x.ok) R.squads[t.side] = ((await x.json()).athletes || []).map(a => ({ name: a.displayName, id: String(a.id || ""), jersey: a.jersey || "", pos: (a.position || {}).abbreviation || "" })); } catch (e) {}
        }));
      }
      const maxAge = R.card.source === "pitchapi" ? 86400 : R.completed ? 900 : R.state === "pre" ? 120 : 60;   // before kick-off: every 2 minutes, so the team sheet shows quickly
      const res = new Response(JSON.stringify(R), { headers: { ...CORS, "content-type": "application/json; charset=utf-8", "cache-control": `public, max-age=${maxAge}` } });
      ctx.waitUntil(caches.default.put(ck, res.clone()));
      return res;
    }
    if (url.pathname === "/api/transfers") {                          // v35: a player's transfer history, e.g. ?id=196176
      const id = String(url.searchParams.get("id") || "");
      if (!/^\d{2,12}$/.test(id)) return new Response("not found", { status: 404, headers: CORS });
      return cachedJSON(ctx, `https://kwallo-cache/transfers/${id}`, 7 * 86400, () => transfers(id).catch(() => null));
    }
    if (url.pathname === "/api/hit" && request.method === "POST") {   // v32: anonymous feature counters (no personal data)
      try { const b = await request.json(); const f = String(b.f || "").slice(0, 40).replace(/[^a-z0-9_-]/gi, ""); if (f) ctx.waitUntil(bump(env, "web", f)); } catch (e) {}
      return new Response("ok", { headers: CORS });
    }
    if (request.method === "OPTIONS") return new Response(null, { headers: { ...CORS, "access-control-allow-methods": "GET, POST", "access-control-allow-headers": "content-type" } });
    if (url.pathname === "/admin/dashboard") {                         // v31: your private dashboard, behind a password
      if (!env.DASHBOARD_PASSWORD) return new Response("Set a DASHBOARD_PASSWORD secret on the Worker first.", { status: 503 });
      const auth = request.headers.get("Authorization") || "";
      let ok = false;
      try { ok = auth.startsWith("Basic ") && atob(auth.slice(6)).split(":").slice(1).join(":") === env.DASHBOARD_PASSWORD; } catch (e) {}
      if (!ok) return new Response("Password required", { status: 401, headers: { "WWW-Authenticate": 'Basic realm="Kwallo dashboard"' } });
      const obj = await env.DATA.get("data/dashboard.html");
      if (!obj) return new Response("No dashboard yet: it appears after the next run.", { status: 404 });
      return new Response(obj.body, { headers: { "content-type": "text/html; charset=utf-8", "cache-control": "no-store", "x-robots-tag": "noindex, nofollow" } });
    }
    if (url.pathname === "/") return new Response("Kwallo bot is running.");
    return new Response("not found", { status: 404 });
  },
  async scheduled(event, env, ctx) {
    // v31: runs every minute (cron "* * * * *"): live alerts each minute, the lineup-run check every 15 minutes
    // v35: one shared budget of outside requests per run (the free plan allows 50), used in order: the GitHub lineup-run check,
    //      lineup alerts (every 5 minutes), then live alerts and sending
    const now = event.scheduledTime || Date.now(), minute = new Date(now).getUTCMinutes(), B = { left: 45 };
    ctx.waitUntil((async () => {
      if (minute % 15 === 0) { B.left--; try { console.log("lineup check:", await maybeDispatch(env, now)); } catch (e) { console.log("lineup check failed", e); } }
      if (minute % 5 === 2) { const L = { left: Math.min(10, B.left - 25) }, start = L.left;
        try { console.log(await lineupTick(env, now, L)); } catch (e) { console.log("lineup alerts failed", e); }
        B.left -= start - L.left; }
      try { console.log(await liveTick(env, now, B)); } catch (e) { console.log("live failed", e); }
    })());
  },
};
export { liveScores, findAssist, handleUpdate, maybeDispatch, subscribers, search, liveTick, lineupTick, snapshot, liveMessages, pressureCheck, flushOutbox, adminStats,
         eventKey, matchResult, transfers, espnCard, pitchapiCard, teamSim, timeline, momentum };

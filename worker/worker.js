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
    return reply(env, chat, "All alerts stopped and your data deleted. You can come back any time with /follow.");
  }
  if (cmd === "/privacy") return reply(env, chat, PRIVACY);
  return reply(env, chat, HELP);
}
async function settings(env, chat) {
  const p = await env.DB.prepare("SELECT preview, lineups FROM prefs WHERE chat_id = ?").bind(chat).first() || { preview: 1, lineups: 1 };
  return reply(env, chat, "Your alerts (tap to switch on/off):", { reply_markup: { inline_keyboard: [
    [{ text: `${p.preview ? "✅" : "⬜"} Match preview (about a day before)`, callback_data: "s:preview:x" }],
    [{ text: `${p.lineups ? "✅" : "⬜"} Lineups out (about 75 min before kickoff)`, callback_data: "s:lineups:x" }]] } });
}

async function subscribers(env) {
  const subs = (await env.DB.prepare("SELECT chat_id, kind, slug FROM subs").all()).results || [];
  const prefs = {};
  for (const p of (await env.DB.prepare("SELECT chat_id, preview, lineups FROM prefs").all()).results || []) prefs[p.chat_id] = { preview: p.preview, lineups: p.lineups };
  return { subs, prefs };
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
    if (url.pathname === "/") return new Response("Kwallo bot is running.");
    return new Response("not found", { status: 404 });
  },
  async scheduled(event, env, ctx) {
    ctx.waitUntil(maybeDispatch(env).then(r => console.log("lineup check:", r)));
  },
};
export { handleUpdate, maybeDispatch, subscribers, search };

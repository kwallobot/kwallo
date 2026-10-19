import { DatabaseSync } from "node:sqlite";
import fs from "node:fs";
const W = await import("../worker/worker.js");
const db = new DatabaseSync(":memory:");
db.exec(fs.readFileSync(new URL("../worker/schema.sql", import.meta.url), "utf8"));
const stmt = (sql) => { let a = []; const s = { bind(...x) { a = x; return s; }, async run() { db.prepare(sql).run(...a); return {}; },
  async all() { return { results: db.prepare(sql).all(...a) }; }, async first() { return db.prepare(sql).get(...a) || null; }, _run() { db.prepare(sql).run(...a); } }; return s; };
const D1 = { prepare: stmt, async batch(list) { for (const s of list) s._run(); return []; } };
const t0 = Date.parse("2026-10-24T15:00:00Z");
const sched = [{ slug: "ars-che", kickoff: "2026-10-24T15:00:00Z", competition: "Premier League", league_slug: "premier-league", home_slug: "arsenal", away_slug: "chelsea",
                 espn: { code: "eng.1", id: "777" }, pH: 0.52, pD: 0.25, pA: 0.23 }];
const R2 = { async get(k) { return k === "site/schedule.json" ? { json: async () => sched } : null; } };
let board = null; const sent = [];
const ev = (state, name, clock, hs, as, shots, sot, details) => ({ id: "777", status: { displayClock: clock, type: { state, name, shortDetail: name === "STATUS_HALFTIME" ? "HT" : clock } },
  competitions: [{ details, competitors: [
    { homeAway: "home", score: String(hs), team: { id: "1", shortDisplayName: "Arsenal" }, statistics: [{ name: "totalShots", displayValue: String(shots[0]) }, { name: "shotsOnTarget", displayValue: String(sot[0]) }, { name: "possessionPct", displayValue: "58" }, { name: "wonCorners", displayValue: "4" }] },
    { homeAway: "away", score: String(as), team: { id: "2", shortDisplayName: "Chelsea" }, statistics: [{ name: "totalShots", displayValue: String(shots[1]) }, { name: "shotsOnTarget", displayValue: String(sot[1]) }, { name: "possessionPct", displayValue: "42" }, { name: "wonCorners", displayValue: "2" }] }] }] });
globalThis.fetch = async (url, opts) => {
  if (String(url).includes("espn.com")) return { ok: true, json: async () => ({ events: [board] }) };
  sent.push(JSON.parse(opts.body)); return { ok: true, json: async () => ({}) };
};
const env = { DB: D1, DATA: R2, TELEGRAM_BOT_TOKEN: "t" };
db.prepare("INSERT INTO subs (chat_id, kind, slug, name, created) VALUES (1, 'team', 'arsenal', 'Arsenal', '2026-10-20')").run();
db.prepare("INSERT INTO subs (chat_id, kind, slug, name, created) VALUES (2, 'league', 'premier-league', 'Premier League', '2026-10-20')").run();
const goal = { type: { text: "Goal" }, scoringPlay: true, clock: { displayValue: "23'" }, team: { id: "1" }, athletesInvolved: [{ displayName: "Bukayo Saka" }, { displayName: "Martin Ødegaard" }] };
const yellow = { type: { text: "Yellow Card" }, yellowCard: true, clock: { displayValue: "27'" }, team: { id: "2" }, athletesInvolved: [{ displayName: "Moisés Caicedo" }] };
const steps = [[20, ev("in", "STATUS_FIRST_HALF", "20'", 0, 0, [2, 1], [1, 0], [])],
               [28, ev("in", "STATUS_FIRST_HALF", "28'", 1, 0, [3, 1], [2, 0], [goal, yellow])],
               [36, ev("in", "STATUS_FIRST_HALF", "36'", 1, 0, [8, 2], [4, 0], [goal, yellow])],
               [47, ev("in", "STATUS_HALFTIME", "45'+2'", 1, 0, [9, 3], [4, 1], [goal, yellow])],
               [110, ev("post", "STATUS_FULL_TIME", "90'+4'", 1, 0, [15, 7], [6, 2], [goal, yellow])]];
// chat 2 switches cards off and every-shot-on-target on, through /settings buttons
await W.handleUpdate(env, { callback_query: { id: "a", data: "l:cards:x", message: { chat: { id: 2 } } } });
await W.handleUpdate(env, { callback_query: { id: "b", data: "l:sot:x", message: { chat: { id: 2 } } } });
sent.length = 0;
for (const [min, b] of steps) {
  board = b;
  const r = await W.liveTick(env, t0 + min * 60000);
  console.log(`minute ${min}: ${r}`);
}
for (const chat of [1, 2]) {
  console.log(`\n--- chat ${chat} received ${sent.filter(s => s.chat_id === chat).length} messages ---`);
  for (const s of sent.filter(s => s.chat_id === chat)) console.log("  " + s.text.replace(/\n/g, " | "));
}
sent.length = 0;
await W.handleUpdate(env, { message: { chat: { id: 1 }, text: "/stats" } });
console.log("\n/stats without ADMIN_CHAT_ID ->", sent.at(-1).text);
env.ADMIN_CHAT_ID = "1";
await W.handleUpdate(env, { message: { chat: { id: 1 }, text: "/stats" } });
console.log("/stats as admin ->", sent.at(-1).text.replace(/\n/g, " | "));
await W.handleUpdate(env, { message: { chat: { id: 2 }, text: "/stats" } });
console.log("/stats as someone else -> help text:", sent.at(-1).text.startsWith("Commands"));

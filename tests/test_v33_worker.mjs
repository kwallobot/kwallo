import { DatabaseSync } from "node:sqlite"; import fs from "node:fs";
const W = await import("../worker/worker.js");
const db = new DatabaseSync(":memory:"); db.exec(fs.readFileSync(new URL("../worker/schema.sql", import.meta.url), "utf8"));
const D1 = { prepare(sql) { let a = []; const s = { bind(...x) { a = x; return s; }, async run() { db.prepare(sql).run(...a); return {}; },
  async all() { return { results: db.prepare(sql).all(...a) }; }, async first() { return db.prepare(sql).get(...a) || null; }, _run() { db.prepare(sql).run(...a); } }; return s; },
  async batch(l) { for (const s of l) s._run(); return []; } };
const now = Date.parse("2026-10-24T15:30:00Z");
const sched = [{ slug: "2026-10-24-arsenal-v-chelsea", kickoff: "2026-10-24T15:00:00Z", date: "2026-10-24", competition: "Premier League", home: "Arsenal", away: "Chelsea",
                 home_slug: "arsenal", away_slug: "chelsea", league_slug: "premier-league", espn: { code: "eng.1", id: "9" }, pH: .5, pD: .25, pA: .25 }];
const R2 = { async get(k) { return k === "site/schedule.json" ? { json: async () => sched } : null; } };
const sent = [];
const ev = { id: "9", status: { displayClock: "30'", type: { state: "in", name: "STATUS_FIRST_HALF", shortDetail: "30'" } },
  competitions: [{ details: [], competitors: [{ homeAway: "home", score: "1", team: { id: "1", shortDisplayName: "Arsenal" } }, { homeAway: "away", score: "0", team: { id: "2", shortDisplayName: "Chelsea" } }] }] };
globalThis.fetch = async (url, o) => String(url).includes("espn.com") ? { ok: true, json: async () => ({ events: [ev] }) } : (sent.push(JSON.parse(o.body)), { ok: true, json: async () => ({}) });
const env = { DB: D1, DATA: R2, TELEGRAM_BOT_TOKEN: "t" };
await W.handleUpdate(env, { message: { chat: { id: 7 }, text: "/start match_2026-10-24-arsenal-v-chelsea" } });
console.log("follow reply:", sent.at(-1).text.split("\n")[0]);
await W.handleUpdate(env, { message: { chat: { id: 7 }, text: "/list" } });
console.log("list:", sent.at(-1).text.replace(/\n/g, " | "));
console.log("live scores feed:", JSON.stringify(await W.liveScores(env, now)));
sent.length = 0;
await W.liveTick(env, now);                                  // first sighting
ev.competitions[0].competitors[0].score = "2"; ev.competitions[0].details = [{ type: { text: "Goal" }, scoringPlay: true, clock: { displayValue: "34'" }, team: { id: "1" }, athletesInvolved: [{ displayName: "Saka" }] }];
await W.liveTick(env, now + 4 * 60000);
console.log("match follower got:", sent.filter(s => s.chat_id === 7).map(s => s.text.split("\n")[0]));
await W.liveTick(env, Date.parse("2026-10-25T16:07:00Z"));   // a day later, on the hourly tidy-up
console.log("after a day:", JSON.stringify((await D1.prepare("SELECT kind, slug FROM subs").all()).results));

import { DatabaseSync } from "node:sqlite";
import fs from "node:fs";
const W = await import("../worker/worker.js");
const db = new DatabaseSync(":memory:");
db.exec(fs.readFileSync(new URL("../worker/schema.sql", import.meta.url), "utf8"));
const D1 = { prepare(sql) { let args = []; const st = { bind(...a) { args = a; return st; },
  async run() { db.prepare(sql).run(...args); return {}; }, async all() { return { results: db.prepare(sql).all(...args) }; },
  async first() { return db.prepare(sql).get(...args) || null; }, _run() { db.prepare(sql).run(...args); } }; return st; },
             async batch(list) { for (const s of list) s._run(); return []; } };
const files = { "site/teams.json": [{ slug: "arsenal", name: "Arsenal", league: "Premier League", league_slug: "premier-league" },
                                    { slug: "man-city", name: "Man City", league: "Premier League", league_slug: "premier-league" },
                                    { slug: "man-united", name: "Man United", league: "Premier League", league_slug: "premier-league" }],
                "site/schedule.json": [{ slug: "x", kickoff: new Date(Date.now() + 70 * 60000).toISOString(), home: "Arsenal", away: "Chelsea" }] };
const R2 = { async get(k) { return files[k] ? { json: async () => files[k] } : null; } };
const sent = [];
globalThis.fetch = async (url, opts) => { sent.push({ url: String(url), body: opts && opts.body ? JSON.parse(opts.body) : null });
  return { ok: true, status: 204, json: async () => ({}) }; };
const env = { DB: D1, DATA: R2, TELEGRAM_BOT_TOKEN: "t", WEBHOOK_SECRET: "s3cret", PIPELINE_KEY: "pk", GITHUB_TOKEN: "g", GITHUB_REPO: "me/pitchlab" };
const msg = (text, id = 42) => ({ message: { chat: { id }, text } });
await W.handleUpdate(env, msg("/start team_arsenal"));
await W.handleUpdate(env, msg("/follow man"));
const choose = sent.at(-1).body.reply_markup.inline_keyboard.map(r => r[0].callback_data);
console.log("follow 'man' offers:", choose);
await W.handleUpdate(env, { callback_query: { id: "1", data: choose[0], message: { chat: { id: 42 } } } });
await W.handleUpdate(env, { callback_query: { id: "2", data: "s:preview:x", message: { chat: { id: 42 } } } });
console.log("subscribers:", JSON.stringify(await W.subscribers(env)));
await W.handleUpdate(env, msg("/list"));
console.log("list reply:", sent.at(-1).body.text.replace(/\n/g, " | "));
console.log("dispatch 1:", await W.maybeDispatch(env));
console.log("dispatch 2:", await W.maybeDispatch(env));
console.log("GitHub call:", sent.find(s => s.url.includes("api.github.com")).url);
const res = await W.default.fetch(new Request("https://x/api/subscribers", { headers: { "X-Pipeline-Key": "wrong" } }), env);
console.log("subscriber list with a wrong key ->", res.status);
const res2 = await W.default.fetch(new Request("https://x/telegram", { method: "POST", headers: { "X-Telegram-Bot-Api-Secret-Token": "nope" }, body: "{}" }), env);
console.log("webhook with a wrong secret ->", res2.status);
await W.handleUpdate(env, msg("/stop"));
console.log("after /stop:", JSON.stringify(await W.subscribers(env)));

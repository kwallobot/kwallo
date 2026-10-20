const { JSDOM } = require("jsdom"); const fs = require("fs"), path = require("path");
const SITE = "/tmp/site33", WEB = path.join(__dirname, "..", "web"), slug = fs.readFileSync(SITE + "/first.txt", "utf8");
const html = fs.readFileSync(path.join(WEB, "index.html"), "utf8").replace(/<script src="(config|app)\.js"><\/script>/g, "").replace(/<link[^>]+>/g, "");
const dom = new JSDOM(html, { url: "https://kwallo.pages.dev/#/match/" + slug, runScripts: "dangerously" }); const w = dom.window;
w.fetch = async url => { url = String(url); if (url.endsWith("/api/live")) return { ok: true, json: async () => ({}) };
  const f = path.join(SITE, url.split("/api/site/")[1] || ""); return fs.existsSync(f) ? { ok: true, json: async () => JSON.parse(fs.readFileSync(f, "utf8")) } : { ok: false, status: 404 }; };
w.navigator.sendBeacon = () => true; w.scrollTo = () => {};
w.eval(fs.readFileSync(path.join(WEB, "config.js"), "utf8")); w.eval(fs.readFileSync(path.join(WEB, "app.js"), "utf8"));
const sleep = ms => new Promise(r => setTimeout(r, ms)), $$ = s => [...w.document.querySelectorAll(s)], t = el => el.textContent.replace(/\s+/g, " ").trim();
(async () => { await sleep(300);
  console.log("tabs:", $$(".mtabs a").map(t).join(" | "), "| selected:", t(w.document.querySelector(".mtabs a.on")));
  for (const tab of ["overview", "verdict", "markets", "lineups", "form", "table"]) {
    w.location.hash = `#/match/${slug}/${tab}`; await sleep(300);
    const h = $$("#app h2, #app h3").map(t);
    const extra = tab === "markets" ? " | market types: " + h.filter(x => /^(Shots|Fouls|Half|Goals in|Goal timing|Penalt|Throw|Offsides|Tackles|Player)/.test(x)).join(", ")
                : tab === "table" ? " | highlighted rows: " + $$("tr.hl").map(r => t(r.children[1])).join(", ")
                : tab === "overview" ? " | " + t(w.document.querySelector("[data-tab=overview]") || w.document.body).slice(0, 140) : "";
    console.log(`[${tab}] headings:`, h.filter(x => x).slice(0, 6).join(" | ") + extra);
  }
  process.exit(0);
})();

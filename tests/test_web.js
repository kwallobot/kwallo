// Loads the web app in a simulated browser, serves the simulated run's files, and visits every page.
const { JSDOM, VirtualConsole } = require("jsdom");
const fs = require("fs"), path = require("path");
const SITE = process.argv[2], WEB = path.join(__dirname, "..", "web");
const errors = [];
const vc = new VirtualConsole().on("jsdomError", e => errors.push(e.message)).on("error", e => errors.push(String(e)));
const html = fs.readFileSync(path.join(WEB, "index.html"), "utf8").replace(/<script src="(config|app)\.js"><\/script>/g, "").replace(/<link[^>]+>/g, "");
const dom = new JSDOM(html, { url: "https://kwallo.pages.dev/", runScripts: "dangerously", virtualConsole: vc, pretendToBeVisual: true });
const w = dom.window;
w.fetch = async url => {
  const rel = String(url).split("/api/site/")[1];
  const f = path.join(SITE, rel || "");
  return fs.existsSync(f) ? { ok: true, status: 200, json: async () => JSON.parse(fs.readFileSync(f, "utf8")) } : { ok: false, status: 404, json: async () => ({}) };
};
w.navigator.sendBeacon = () => true;
w.scrollTo = () => {};
w.eval(fs.readFileSync(path.join(WEB, "config.js"), "utf8"));
w.eval(fs.readFileSync(path.join(WEB, "app.js"), "utf8"));
const sleep = ms => new Promise(r => setTimeout(r, ms));
const pick = (dir) => { const fs_ = fs.readdirSync(path.join(SITE, dir)); return fs_[0].replace(/\.json$/, ""); };
(async () => {
  const idx = JSON.parse(fs.readFileSync(path.join(SITE, "index.json"), "utf8"));
  const m0 = idx.matches[0];
  const leadersComp = pick("leaders");
  const routes = ["#/", "#/day/" + (m0.Date || "").slice(0, 10) + "/big", "#/leagues", "#/comp/bundesliga", "#/comp/bundesliga/table", "#/comp/" + leadersComp + "/leaders",
                  "#/leaders", "#/match/" + m0.slug, "#/team/" + m0.home_slug, "#/player/" + pick("player"), "#/angles", "#/track", "#/fav", "#/more", "#/about", "#/privacy", "#/terms", "#/nope"];
  for (const r of routes) {
    w.location.hash = r; await sleep(60);
    const main = w.document.getElementById("app");
    const h1 = (main.querySelector("h1") || {}).textContent;
    const failed = /Couldn't load/.test(main.textContent);
    console.log(`${r.padEnd(48)} -> ${failed ? "FAILED: " + main.textContent.slice(0, 120) : `"${h1}"`}, ${main.querySelectorAll("a,button").length} links/buttons`);
  }
  // interactions: favourite, accumulator (two picks from one match triggers the linked warning)
  w.location.hash = "#/match/" + m0.slug; await sleep(60);
  const btns = [...w.document.querySelectorAll("[data-acca]")];
  if (btns[0]) btns[0].click(); if (btns[1]) btns[1].click();
  w.location.hash = "#/acca"; await sleep(60);
  const t = w.document.getElementById("app").textContent;
  console.log("accumulator:", (t.match(/Combined chance\s*([0-9–]+%?)/) || [])[1], "| linked warning:", /same match/.test(t), "| counter:", w.document.querySelector(".acca-count").textContent);
  w.location.hash = "#/"; await sleep(60);
  const star = w.document.querySelector("[data-fav]"); star.click();
  w.location.hash = "#/fav"; await sleep(60);
  console.log("favourites page shows:", w.document.querySelectorAll("#app .match").length, "match(es)");
  console.log("errors:", errors.length ? errors : "none");
  process.exit(0);
})();

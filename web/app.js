// Kwallo web app (v32; v35: back button and swipes, advised bets against team averages, players / team stats / head-to-head tabs,
// past-match pages, player links and transfer history). Reads the pipeline's public files through the Worker; no accounts, no cookies.
(function () {
  "use strict";
  const C = window.KWALLO || {};
  const API = C.api || "/api/site/";
  const shell = document.getElementById("app");
  let app = shell, routeSeq = 0;                                     // pages render off-screen; only the latest request is shown
  const cache = {};
  const BIG = ["Premier League", "La Liga", "Bundesliga", "Serie A", "Ligue 1", "Champions League", "Europa League", "Conference League"];
  const EUROPE_CUPS = ["Champions League", "Europa League", "Conference League"];
  const REGION = { "Premier League": "England", "Championship": "England", "La Liga": "Spain", "Bundesliga": "Germany", "Serie A": "Italy", "Ligue 1": "France",
    "Eredivisie": "Netherlands", "Primeira Liga": "Portugal", "Belgian Pro League": "Belgium", "Scottish Premiership": "Scotland", "Super Lig": "Turkey",
    "Greek Super League": "Greece", "MLS": "USA", "Saudi Pro League": "Saudi Arabia", "Liga MX": "Mexico", "Argentina Liga Profesional": "Argentina",
    "Brasileirão Série A": "Brazil", "Brasileirão Série B": "Brazil", "Bolivia División Profesional": "Bolivia", "South African Premiership": "South Africa",
    "NPFL (Nigeria)": "Nigeria", "Egyptian Premier League": "Egypt", "Champions League": "Europe", "Europa League": "Europe", "Conference League": "Europe" };
  let LIVE = {}, liveAt = 0;
  async function getLive(force) {                                   // live and finished scores, refreshed at most once a minute
    if (!force && Date.now() - liveAt < 50000) return LIVE;
    try { const r = await fetch((C.liveApi || API.replace(/\/api\/site\/?$/, "/api/live")), { cache: "no-cache" }); if (r.ok) { LIVE = await r.json(); liveAt = Date.now(); } } catch (e) {}
    return LIVE;
  }
  const folded = k => store.get("fold:" + k, null);
  function badge(m, side) {
    const b = ((m.badges || {})[side]) || {}, name = side === "home" ? m.Home : m.Away;
    const abbr = b.a || String(name || "").split(/\s+/).map(w => w[0]).join("").slice(0, 3).toUpperCase();
    return `<span class="badge" style="--c:${esc(b.c || "#6F8F84")}" aria-hidden="true">${esc(abbr)}</span>`;
  }
  function liveCell(m) {                                             // time column: kickoff / live minute / FT, and the score line
    const L = LIVE[m.slug];
    if (L && L.state === "in") return { top: `<b class="live">${esc(L.detail || "Live")}</b>`, live: true, hs: L.hs, as: L.as };
    if (L && L.state === "post") return { top: `<span class="muted">FT</span>`, hs: L.hs, as: L.as };
    return { top: `<span ${m.kickoff ? "" : 'title="Kickoff time not announced yet"'}>${esc(timeOf(m))}</span>`, hs: null, as: null };
  }

  // ---------- small helpers
  const esc = s => String(s == null ? "" : s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const pct = p => (p == null || isNaN(p) ? "–" : `${Math.round(100 * p)}%`);
  const odds = f => (f == null || !isFinite(f) ? "–" : Number(f).toFixed(2));
  const tg = path => `https://t.me/${path}`;
  const store = {
    get(k, d) { try { const v = localStorage.getItem("kwallo:" + k); return v ? JSON.parse(v) : d; } catch (e) { return d; } },
    set(k, v) { try { localStorage.setItem("kwallo:" + k, JSON.stringify(v)); } catch (e) {} },
  };
  async function get(path) {
    if (cache[path]) return cache[path];
    const r = await fetch(API + path, { cache: "no-cache" });
    if (!r.ok) throw new Error(`${path}: ${r.status}`);
    return (cache[path] = await r.json());
  }
  function hit(feature) { try { navigator.sendBeacon(API.replace(/\/api\/site\/?$/, "/api/hit"), JSON.stringify({ f: feature })); } catch (e) {} }
  const localDay = d => { const x = new Date(d); return `${x.getFullYear()}-${String(x.getMonth() + 1).padStart(2, "0")}-${String(x.getDate()).padStart(2, "0")}`; };
  const matchDay = m => (m.kickoff ? localDay(m.kickoff) : String(m.Date || m.date).slice(0, 10));
  const timeOf = m => (m.kickoff ? new Date(m.kickoff).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "TBC");   // v35: time not announced yet
  // v35: seasons written 26/27 ("2627" and "2026/27" both become 26/27); calendar-year seasons ("2026") stay as they are
  const fmtSeason = s => { s = String(s || "");
    if (/^\d{4}$/.test(s) && !/^(19|20)\d{2}$/.test(s)) return `${s.slice(0, 2)}/${s.slice(2)}`;
    const m = s.match(/^(?:19|20)(\d{2})[\/-](?:(?:19|20)?(\d{2}))$/); return m ? `${m[1]}/${m[2]}` : s; };
  function dayLabel(d) {
    const today = localDay(Date.now()), tom = localDay(Date.now() + 864e5), yest = localDay(Date.now() - 864e5);
    if (d === today) return "Today"; if (d === tom) return "Tomorrow"; if (d === yest) return "Yesterday";
    return new Date(d + "T12:00:00").toLocaleDateString([], { weekday: "short", day: "numeric", month: "short" });
  }
  const longDate = d => new Date(String(d).slice(0, 10) + "T12:00:00").toLocaleDateString([], { weekday: "long", day: "numeric", month: "long" });
  const ordinal = n => n + (["th", "st", "nd", "rd"][((n % 100) - 20) % 10] || ["th", "st", "nd", "rd"][n % 100] || "th");

  // ---------- favourites and the accumulator live in this browser only
  const fav = { list: () => store.get("fav", []), has: s => store.get("fav", []).includes(s),
                toggle(s) { const f = new Set(store.get("fav", [])); f.has(s) ? f.delete(s) : f.add(s); store.set("fav", [...f]); hit("favourite"); } };
  const acca = { list: () => store.get("acca", []),
                 has: id => store.get("acca", []).some(x => x.id === id),
                 toggle(sel) { let a = store.get("acca", []); a = a.some(x => x.id === sel.id) ? a.filter(x => x.id !== sel.id) : [...a, sel]; store.set("acca", a); showAccaCount(); hit("accumulator"); },
                 clear() { store.set("acca", []); showAccaCount(); } };
  function showAccaCount() { const n = acca.list().length; document.querySelectorAll(".acca-count").forEach(b => { b.hidden = !n; b.textContent = n || ""; }); }

  // ---------- pieces
  function chanceBar(m, names) {
    const h = m.pH || 0, d = m.pD || 0, a = m.pA || 0;
    return `<div class="bar" role="img" aria-label="${esc(names[0])} ${pct(h)}, draw ${pct(d)}, ${esc(names[1])} ${pct(a)}">`
      + `<i class="h" style="flex-basis:${100 * h}%"></i><i class="d" style="flex-basis:${100 * d}%"></i><i class="a" style="flex-basis:${100 * a}%"></i></div>`;
  }
  // a ★ beside each team's name: tap to add that team to favourites (the row itself opens the match)
  const teamStar = (slug, name) => slug ? `<button class="star small-star ${fav.has("team:" + slug) ? "on" : ""}" data-fav="team:${esc(slug)}" aria-label="Favourite ${esc(name)}" title="Favourite ${esc(name)}">★</button>` : "";
  function matchRow(m) {
    const t = liveCell(m), mk = "match:" + m.slug;
    const line = (side, name, p, sc) => `<span class="mt">${badge(m, side)}<span class="tn">${esc(name)}</span>${sc != null ? `<b class="msc">${sc}</b>` : `<span class="mp num">${pct(p)}</span>`}</span>`;
    return `<a class="mrow ${t.live ? "is-live" : ""}" href="#/match/${esc(m.slug)}">
      <span class="mtime num">${t.top}<span class="muted">${t.hs != null ? "" : "–"}</span></span>
      <span class="mteams">${line("home", m.Home, m.pH, t.hs)}${line("away", m.Away, m.pA, t.as)}
        <span class="md small muted">Draw ${pct(m.pD)}${m.top_pick ? `, top angle: ${esc(m.top_pick.Bet)} ${pct(m.top_pick.p)}` : ""}</span></span>
      <button class="star mstar ${fav.has(mk) ? "on" : ""}" data-fav="${esc(mk)}" aria-label="Favourite this match">★</button>
    </a>`;
  }
  function compCard(key, name, region, count, body, defaultFolded) {
    const f = folded(key); const isF = f == null ? !!defaultFolded : f;
    return `<section class="card ${isF ? "folded" : ""}" data-card="${esc(key)}">
      <button class="card-h" data-fold="${esc(key)}" aria-expanded="${!isF}"><span class="ct"><b>${esc(name)}</b>${region ? `<small>${esc(region)}</small>` : ""}</span>
        ${count != null ? `<span class="cnt num">${count}</span>` : ""}<span class="chev" aria-hidden="true">⌃</span></button>
      <div class="card-b">${body}</div></section>`;
  }
  const selId = (slug, bet) => `${slug}|${bet}`;
  function accaBtn(sel) { return `<button class="btn mini ${acca.has(sel.id) ? "added" : ""}" data-acca="${esc(JSON.stringify(sel))}" aria-label="${acca.has(sel.id) ? "Remove from" : "Add to"} accumulator">${acca.has(sel.id) ? "✓ In acca" : "+ Acca"}</button>`; }
  function alertsLink(slug, label) {
    return C.bot ? `<a class="btn solid cta-tg" href="${tg(C.bot + "?start=team_" + encodeURIComponent(slug))}" target="_blank" rel="noopener">${esc(label)}</a>` : "";
  }
  function formChips(form) { return `<span class="form">${String(form || "").split("").filter(r => "WDL".includes(r)).map(r => `<b class="${r}">${r}</b>`).join("")}</span>`; }
  const empty = msg => `<p class="empty">${msg}</p>`;
  function setNav(name) { document.querySelectorAll("[data-nav]").forEach(a => a.classList.toggle("on", a.dataset.nav === name)); }

  // ---------- v35: the Worker's other endpoints (past matches, transfers), links to players, the back button, team averages
  const workerApi = p => (C.api || "/api/site/").replace(/\/api\/site\/?$/, "/api/" + p);
  async function getJSON(url) {
    if (cache[url]) return cache[url];
    const r = await fetch(url);
    if (!r.ok) throw new Error(`${r.status}`);
    return (cache[url] = await r.json());
  }
  const nameKey = s => String(s || "").normalize("NFKD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/[^a-z]/g, "");
  const slugify = s => String(s || "").normalize("NFKD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
  const playerHref = (teamSlug, name, id) => `#/pf/${encodeURIComponent(teamSlug || "-")}/${encodeURIComponent(id || "-")}/${encodeURIComponent(name || "")}`;
  const resultHref = e => `#/result/${encodeURIComponent(e)}`;
  const backBar = () => `<p class="backbar"><a class="back" href="#/" aria-label="Back to today's matches">‹ Back</a></p>`;
  const f1 = x => (x == null || !isFinite(x) ? "–" : Number(x).toFixed(1));
  const AVG_ROWS = [["GF", "GA", "Goals"], ["xGF", "xGA", "Expected goals (xG)"], ["ShotsF", "ShotsA", "Shots"], ["SOTF", "SOTA", "Shots on target"],
    ["CornersF", "CornersA", "Corners"], ["CardsF", "CardsA", "Cards (a red counts 2)"], ["FoulsF", "FoulsA", "Fouls"], ["TacklesF", "TacklesA", "Tackles"],
    ["OffsidesF", "OffsidesA", "Offsides"], ["ThrowsF", "ThrowsA", "Throw-ins"]];
  function avgTable(tr, H, A) {                                     // each side's averages: last 7 matches, this season in brackets
    const sh = ((tr || {}).home || {}).stats || {}, sa = ((tr || {}).away || {}).stats || {};
    const cell = (s, k) => `<td class="r num">${f1((s[k] || [])[0])}<small class="muted"> (${f1((s[k] || [])[1])})</small></td>`;
    const rows = AVG_ROWS.filter(([kf]) => (sh[kf] || [])[0] != null || (sa[kf] || [])[0] != null);
    if (!rows.length) return "";
    return `<div class="wrap"><table class="avg"><thead><tr><th></th><th class="r" colspan="2">${esc(H)}</th><th class="r" colspan="2">${esc(A)}</th></tr>
      <tr><th>Per match</th><th class="r">for</th><th class="r">against</th><th class="r">for</th><th class="r">against</th></tr></thead><tbody>
      ${rows.map(([kf, ka, label]) => `<tr><td>${esc(label)}</td>${cell(sh, kf)}${cell(sh, ka)}${cell(sa, kf)}${cell(sa, ka)}</tr>`).join("")}</tbody></table></div>
      <p class="small muted">Last 7 matches in every competition; this season's average in brackets.</p>`;
  }
  const STAT_OF = { corners: "Corners", cards: "Cards", shots: "Shots", sot: "SOT", fouls: "Fouls", tackles: "Tackles", offsides: "Offsides", throwins: "Throws", goals: "G" };
  function statFamily(bet, family) {
    if (family && STAT_OF[family]) return family;
    const b = String(bet).toLowerCase();
    if (/corner/.test(b)) return "corners"; if (/card/.test(b)) return "cards"; if (/throw/.test(b)) return "throwins"; if (/tackle/.test(b)) return "tackles";
    if (/offside/.test(b)) return "offsides"; if (/foul/.test(b)) return "fouls"; if (/on target/.test(b)) return "sot"; if (/shot/.test(b)) return "shots";
    if (/goal|score|both teams|over|under|clean sheet|nil/.test(b)) return "goals";
    return null;
  }
  function avgLine(fam, tr, H, A) {                                  // "Arsenal 6.1 for, 3.9 against · Chelsea ..." for the market's own statistic
    const p = STAT_OF[fam];
    if (!p) return "";
    const kf = p === "G" ? "GF" : p + "F", ka = p === "G" ? "GA" : p + "A";
    const sh = ((tr || {}).home || {}).stats || {}, sa = ((tr || {}).away || {}).stats || {};
    if ((sh[kf] || [])[0] == null && (sa[kf] || [])[0] == null) return "";
    const lab = { corners: "corners", cards: "cards", shots: "shots", sot: "shots on target", fouls: "fouls", tackles: "tackles", offsides: "offsides", throwins: "throw-ins", goals: "goals" }[fam];
    return `Last 7, ${lab} per match: ${esc(H)} ${f1((sh[kf] || [])[0])} for, ${f1((sh[ka] || [])[0])} against · ${esc(A)} ${f1((sa[kf] || [])[0])} for, ${f1((sa[ka] || [])[0])} against.`;
  }

  // ---------- pages
  async function pageToday(day, filter) {
    setNav("today");
    const idx = await get("index.json");
    const ms = idx.matches || [];
    const today = localDay(Date.now());
    // v35: the last 7 days as tabs too (results, and what Kwallo predicted), and a date picker back to the 2025/26 season
    const past7 = [...Array(7)].map((_, i) => localDay(Date.now() - (7 - i) * 864e5));
    const days = [...new Set([...past7, today, ...ms.map(matchDay).filter(d => d >= today)])].sort();
    day = day && /^\d{4}-\d{2}-\d{2}$/.test(day) ? day : today;
    filter = filter || "all";
    const dayTabs = (days.includes(day) ? days : [...days, day].sort()).map(d => `<button class="${d === day ? "on" : ""}" data-go="#/day/${d}/${filter}">${esc(dayLabel(d))}</button>`).join("");
    const picker = `<label class="datepick" title="Pick a date">📅 <input type="date" data-datepick min="${PAST_FROM}" max="${days[days.length - 1]}" value="${day}" aria-label="Pick a date"></label>`;
    if (day < today) return pagePastDay(day, filter, dayTabs, picker);
    const favs = new Set(fav.list());
    let list = ms.filter(m => matchDay(m) === day);
    await getLive();
    if (filter === "live") list = list.filter(m => (LIVE[m.slug] || {}).state === "in");
    if (filter === "big") list = list.filter(m => BIG.includes(m.Competition));
    if (filter === "europe") list = list.filter(m => EUROPE_CUPS.includes(m.Competition));
    if (filter === "nigeria") list = list.filter(m => /NPFL/.test(m.Competition));
    if (filter === "fav") list = list.filter(m => favs.has("match:" + m.slug) || favs.has("team:" + m.home_slug) || favs.has("team:" + m.away_slug) || favs.has("comp:" + m.league_slug));
    const groups = {};
    list.sort((a, b) => (a.kickoff || "").localeCompare(b.kickoff || "")).forEach(m => (groups[m.Competition] = groups[m.Competition] || []).push(m));
    const rank = c => (BIG.indexOf(c) + 1) || 99;
    const order = Object.keys(groups).sort((a, b) => rank(a) - rank(b) || a.localeCompare(b));
    const f = (k, l) => `<button class="chip ${filter === k ? "on" : ""}" data-go="#/day/${day}/${k}">${l}</button>`;
    app.innerHTML = `<h1>${esc(dayLabel(day))}</h1><p class="muted">${esc(longDate(day))}. ${list.length} match${list.length === 1 ? "" : "es"}.</p>
      <div class="daybar"><div class="tabs" role="tablist" data-daytabs>${dayTabs}</div>${picker}</div>
      <div class="tabs">${f("all", "All")}${f("live", `● Live${Object.values(LIVE).some(x => x.state === "in") ? ` (${ms.filter(m => (LIVE[m.slug] || {}).state === "in").length})` : ""}`)}${f("big", "Big games")}${f("europe", "Europe")}${f("nigeria", "Nigeria")}${f("fav", "★ Favourites")}</div>
      ${order.length ? order.map(c => compCard("day:" + c, c, REGION[c], groups[c].length, groups[c].map(matchRow).join(""), false)).join("")
        : empty(filter === "fav" ? "None of your favourites play on this day. Tap ★ on a match, or on a team in its match page." : filter === "live" ? "No matches in play right now." : "No matches for this filter on this day.")}
      <p class="small muted">Updated ${idx.meta && idx.meta.updated ? esc(new Date(idx.meta.updated).toLocaleString()) : "recently"}. Chances are the model's; fair odds are the break-even price.</p>`;
    afterRender = () => { const b = shell.querySelector("[data-daytabs] button.on"), bar = shell.querySelector("[data-daytabs]"); if (b && bar) bar.scrollLeft = Math.max(0, b.offsetLeft - (bar.clientWidth - b.offsetWidth) / 2); };   // v35: today in view
  }

  const PAST_FROM = "2025-07-01";
  // v35: a past day: every result in our competitions, with Kwallo's pre-match chances and top angle (✓ / ✗) where we had them
  async function pagePastDay(day, filter, dayTabs, picker) {
    let D = null;
    try { D = await get(`days/${day}.json`); } catch (e) {}
    const favs = new Set(fav.list());
    let list = ((D || {}).matches || []).map(x => ({ ...x, Competition: x.competition }));
    if (filter === "big") list = list.filter(m => BIG.includes(m.Competition));
    if (filter === "europe") list = list.filter(m => EUROPE_CUPS.includes(m.Competition));
    if (filter === "nigeria") list = list.filter(m => /NPFL/.test(m.Competition));
    if (filter === "fav") list = list.filter(m => favs.has("team:" + m.home_slug) || favs.has("team:" + m.away_slug) || favs.has("comp:" + m.league_slug));
    const groups = {};
    list.forEach(m => (groups[m.Competition] = groups[m.Competition] || []).push(m));
    const rank = c => (BIG.indexOf(c) + 1) || 99;
    const order = Object.keys(groups).sort((a, b) => rank(a) - rank(b) || a.localeCompare(b));
    const row = x => {
      const line = (side, name, sc, won) => `<span class="mt">${badge({ Home: x.home, Away: x.away }, side)}<span class="tn">${won ? `<b>${esc(name)}</b>` : esc(name)}</span><b class="msc">${sc}</b></span>`;
      const p = x.pred, t = x.top;
      const note = [p ? `Kwallo: ${pct(p.pH)} · draw ${pct(p.pD)} · ${pct(p.pA)}` : "", t ? `top angle: ${esc(t.bet)} ${t.won === true ? '<span class="won">✓</span>' : t.won === false ? '<span class="lost">✗</span>' : ""}` : ""].filter(Boolean).join(", ");
      const inner = `<span class="mtime num"><span class="muted">FT</span></span><span class="mteams">${line("home", x.home, x.hs, x.hs > x.as)}${line("away", x.away, x.as, x.as > x.hs)}
        ${note ? `<span class="md small muted">${note}</span>` : ""}</span><span></span>`;
      return x.espn ? `<a class="mrow" href="#/result/${encodeURIComponent(x.espn)}/${day}">${inner}</a>` : `<div class="mrow">${inner}</div>`;
    };
    const f = (k, l) => `<button class="chip ${filter === k ? "on" : ""}" data-go="#/day/${day}/${k}">${l}</button>`;
    app.innerHTML = `<h1>${esc(dayLabel(day))}</h1><p class="muted">${esc(longDate(day))}. ${list.length} result${list.length === 1 ? "" : "s"}.</p>
      <div class="daybar"><div class="tabs" role="tablist" data-daytabs>${dayTabs}</div>${picker}</div>
      <div class="tabs">${f("all", "All")}${f("big", "Big games")}${f("europe", "Europe")}${f("nigeria", "Nigeria")}${f("fav", "★ Favourites")}</div>
      ${order.length ? order.map(c => compCard("day:" + c, c, REGION[c], groups[c].length, groups[c].map(row).join(""), false)).join("")
        : empty(D ? "No results for this filter on this day." : day < PAST_FROM ? "Results go back to the start of the 2025/26 season." : "No results on this day.")}
      <p class="small muted">Tap a match for its statistics, timeline and lineups. ✓ / ✗ shows whether Kwallo's top angle for the match came in.</p>`;
    afterRender = () => { const b = shell.querySelector("[data-daytabs] button.on"), bar = shell.querySelector("[data-daytabs]"); if (b && bar) bar.scrollLeft = Math.max(0, b.offsetLeft - (bar.clientWidth - b.offsetWidth) / 2); };
    hit("past_day");
  }

  async function pageLeagues() {
    setNav("leagues");
    const comps = await get("competitions.json");
    const groups = {};
    comps.forEach(c => (groups[c.group_name || "Other"] = groups[c.group_name || "Other"] || []).push(c));
    app.innerHTML = `<h1>Leagues</h1><p><a href="#/leaders">Player leaders by competition</a></p>` + Object.entries(groups).map(([g, cs]) => `<h2 class="grp">${esc(g)}</h2>
      ${cs.map(c => compCard("lg:" + c.slug, c.name, REGION[c.name], c.upcoming || null, `<div class="lg-body" data-lg="${esc(c.slug)}"><p class="muted small">Loading…</p></div>`, true)).join("")}`).join("");
    document.querySelectorAll ? setTimeout(() => shell.querySelectorAll(".card:not(.folded) [data-lg]").forEach(fillLeague), 0) : 0;
  }
  const roundTitle = r => r.name || (r.round == null ? "Next matches" : `Matchday ${r.round}`);   // v35
  async function fillLeague(el) {                                    // next matchday, top of the table, and links, inside the card
    if (el.dataset.done) return; el.dataset.done = "1";
    const slug = el.dataset.lg;
    let c; try { c = await get(`comp/${slug}.json`); } catch (e) { el.innerHTML = empty("Not available yet."); return; }
    const r = (c.rounds || []).find(x => x.round === c.current_round) || (c.rounds || []).slice(-1)[0];
    const fx = r ? r.matches.slice(0, 10).map(m => `<li class="num small">${esc(m.date)}: <a href="#/team/${esc(m.home_slug)}">${esc(m.home)}</a> ${m.played ? `<b>${esc(m.score)}</b>` : "v"}
        <a href="#/team/${esc(m.away_slug)}">${esc(m.away)}</a>${m.slug ? ` <a href="#/match/${esc(m.slug)}">Prediction</a>` : ""}</li>`).join("") : "";
    const tb = (c.table || []).slice(0, 5).map(x => `<tr><td class="num">${x.pos}</td><td><a href="#/team/${esc(x.team_slug)}">${esc(x.team)}</a></td><td class="r num">${x.P}</td><td class="r num"><b>${x.Pts}</b></td></tr>`).join("");
    el.innerHTML = `${r ? `<h3>${esc(roundTitle(r))}</h3><ul class="list">${fx}</ul>` : ""}
      ${tb ? `<h3>Table</h3><div class="wrap"><table><thead><tr><th>#</th><th>Team</th><th class="r">P</th><th class="r">Pts</th></tr></thead><tbody>${tb}</tbody></table></div>` : ""}
      <p class="links"><a href="#/comp/${esc(slug)}/table">Full table</a> <a href="#/comp/${esc(slug)}/matches">All matchdays</a> <a href="#/comp/${esc(slug)}/leaders">Leaders</a>
        <button class="star ${fav.has("comp:" + slug) ? "on" : ""}" data-fav="comp:${esc(slug)}" aria-label="Favourite ${esc(c.name)}">★</button></p>`;
  }

  async function pageComp(slug, tab, round) {
    setNav("leagues");
    let c;
    try { c = await get(`comp/${slug}.json`); }
    catch (e) { if (tab !== "leaders") throw e; c = { name: slug.replace(/-/g, " "), rounds: [], table: [] }; }   // leaders-only competitions
    tab = tab || "matches";
    const rounds = c.rounds || [];
    const cur = round != null && round !== "" ? String(round) : String(c.current_round ?? (rounds.length ? rounds[rounds.length - 1].round : ""));
    const t = (k, l) => `<button class="${tab === k ? "on" : ""}" data-go="#/comp/${slug}/${k}">${l}</button>`;
    let body = "";
    if (tab === "matches") {
      // v35: cups' rounds have names ("Next matches", "Round of 16"); never "null". The stars sit either side of the fixture.
      const r = rounds.find(x => String(x.round) === cur) || rounds[rounds.length - 1];
      body = r ? `<div class="tabs">${rounds.map(x => `<button class="${x.round === r.round ? "on" : ""}" data-go="#/comp/${slug}/matches/${encodeURIComponent(x.round)}" aria-label="${esc(roundTitle(x))}">${esc(x.name || x.round)}</button>`).join("")}</div>
        <h2>${esc(roundTitle(r))}</h2><ul class="list">${r.matches.map(m => `<li class="num">${esc(m.date)}:
          ${teamStar(m.home_slug, m.home)}<a href="#/team/${esc(m.home_slug)}">${esc(m.home)}</a> ${m.played ? `<b>${esc(m.score)}</b>` : "v"} <a href="#/team/${esc(m.away_slug)}">${esc(m.away)}</a>${teamStar(m.away_slug, m.away)}
          ${m.slug ? ` <a class="small" href="#/match/${esc(m.slug)}">Prediction</a>` : ""}</li>`).join("")}</ul>` : empty("No matchdays yet.");
    } else if (tab === "table") {
      body = (c.table || []).length ? `<div class="wrap"><table><thead><tr><th>#</th><th>Team</th><th class="r">P</th><th class="r">W</th><th class="r">D</th><th class="r">L</th><th class="r">GD</th><th class="r">Pts</th><th>Form</th></tr></thead><tbody>
        ${c.table.map(x => `<tr><td class="num">${x.pos}</td><td><a href="#/team/${esc(x.team_slug)}">${esc(x.team)}</a></td><td class="r num">${x.P}</td><td class="r num">${x.W}</td><td class="r num">${x.D}</td>
          <td class="r num">${x.L}</td><td class="r num">${x.GD > 0 ? "+" : ""}${x.GD}</td><td class="r num"><b>${x.Pts}</b></td><td>${formChips(x.form)}</td></tr>`).join("")}</tbody></table></div>`
        : empty("This competition has no league table (cup or knockout stage).");
    } else {
      body = await leadersTable(slug);
    }
    app.innerHTML = `<h1 class="title-row"><span>${esc(c.name)}</span><button class="star ${fav.has("comp:" + slug) ? "on" : ""}" data-fav="comp:${esc(slug)}" aria-label="Favourite ${esc(c.name)}" title="Favourite">★</button></h1>
      ${c.season ? `<p class="muted">Season ${esc(fmtSeason(c.season))}</p>` : ""}
      <div class="tabs">${t("matches", "Matchdays")}${t("table", "Table")}${t("leaders", "Leaders")}</div>${body}`;
    hit("competition");
  }

  async function leadersTable(slug) {
    let L;
    try { L = await get(`leaders/${slug}.json`); } catch (e) { return empty("Player statistics for this competition aren't available yet."); }
    const labels = L.labels || {};
    const keys = Object.keys(labels).filter(k => !/^minutes/.test(k)).sort((a, b) => (labels[a].order || 0) - (labels[b].order || 0));
    if (!keys.length) return empty("Player statistics for this competition aren't available yet.");
    const val = (p, k, mode) => {                                // new files hold {p90, total}; older ones a single per-90 number
      if (k === "minutes") return p.minutes || 0;
      const x = p.stats && p.stats[k];
      if (x == null) return null;
      if (typeof x === "object") return mode === "total" ? x.total : (x.p90 != null ? x.p90 : (p.minutes ? 90 * (x.total || 0) / p.minutes : null));
      return mode === "total" ? (p.minutes ? x * p.minutes / 90 : null) : x;
    };
    const isAvg = k => { const l = labels[k] || {}; if (/^(expected_|xg)/.test(k)) return false;                 // v35: xG and xA are totals (per 90 and total)
      return ["double", "percent", "rating"].includes(l.type) || /rating|percent|accuracy|pct/.test(k); };   // averages: no per-90 or total
    const hasData = k => (L.players || []).some(p => val(p, k, "total") != null);
    const def = ["goals", "expected_goals"].find(k => keys.includes(k) && hasData(k)) || keys.find(hasData) || keys[0];
    let [sortKey, sortMode, dir] = store.get("leaders_sort2:" + slug, [def, "p90", -1]);
    if (sortKey !== "minutes" && !keys.includes(sortKey)) [sortKey, sortMode, dir] = [def, "p90", -1];
    const minMin = store.get("leaders_min", 270);
    const rows = (L.players || []).filter(p => (p.minutes || 0) >= minMin)
      .sort((a, b) => dir * ((val(a, sortKey, sortMode) ?? -1e9) - (val(b, sortKey, sortMode) ?? -1e9))).slice(0, 60);
    const shown = (sortKey === "minutes" ? [] : [sortKey]).concat(keys.filter(k => k !== sortKey && hasData(k))).slice(0, 4);
    const fmt = x => (x == null || !isFinite(x) ? "–" : (Math.abs(x) >= 10 ? Math.round(x) : Math.round(x * 100) / 100));
    const th = (k, mode, label, sub) => { const on = k === sortKey && mode === sortMode;
      return `<th class="r ${on ? "sorted" : ""}" data-sort="${esc(slug)}|${esc(k)}|${mode}" aria-sort="${on ? (dir < 0 ? "descending" : "ascending") : "none"}">${esc(label)}${on ? (dir < 0 ? " ↓" : " ↑") : ""}${sub ? `<small>${sub}</small>` : ""}</th>`; };
    return `<p class="small muted"><label>Players with at least <select data-leaders-min>${[0, 270, 450, 900].map(x => `<option value="${x}" ${x === minMin ? "selected" : ""}>${x}</option>`).join("")}</select> minutes</label>.
        Tap a column heading to sort by it.</p>
      <p><label>Sort by <select data-leaders-sort="${esc(slug)}">${keys.filter(hasData).map(k => `<option value="${esc(k)}" ${k === sortKey ? "selected" : ""}>${esc(labels[k].label || k)}${isAvg(k) ? " (average)" : " per 90"}</option>`).join("")}
        <option value="minutes" ${sortKey === "minutes" ? "selected" : ""}>Minutes played (total)</option></select></label></p>
      <div class="wrap"><table class="leaders"><thead><tr><th>Player</th><th>Team</th>${th("minutes", "total", "Minutes", "total")}
        ${shown.map(k => isAvg(k) ? th(k, "total", labels[k].label || k, "average") : th(k, "p90", labels[k].label || k, "per 90") + th(k, "total", labels[k].label || k, "total")).join("")}</tr></thead>
      <tbody>${rows.map(p => `<tr><td><a href="#/player/${esc(p.slug)}">${esc(p.name)}</a></td><td class="small">${esc(p.team)}</td><td class="r num">${p.minutes || 0}</td>
        ${shown.map(k => isAvg(k) ? `<td class="r num">${fmt(val(p, k, "total"))}</td>` : `<td class="r num">${fmt(val(p, k, "p90"))}</td><td class="r num tot">${fmt(val(p, k, "total"))}</td>`).join("")}</tr>`).join("")}</tbody></table></div>
      ${rows.length ? "" : empty("No players reach that many minutes yet.")}`;
  }

  async function pageLeadersPicker() {
    setNav("leagues");
    const comps = await get("competitions.json");
    app.innerHTML = `<h1>Leaders</h1><p class="muted">Pick a competition to see its players, sortable by any statistic.</p>
      <ul class="list">${comps.map(c => `<li><a href="#/comp/${esc(c.slug)}/leaders">${esc(c.name)}</a></li>`).join("")}</ul>`;
  }

  const FAMILY = [["shots", "Shots"], ["sot", "Shots on target"], ["fouls", "Fouls"], ["halftime", "Half-time"], ["halftime_both", "Goals in both halves"],
    ["timing", "Goal timing"], ["penalty", "Penalties"], ["throwins", "Throw-ins"], ["offsides", "Offsides"], ["tackles", "Tackles"], ["player_props", "Player props"]];
  const famName = f => (FAMILY.find(([k]) => k === f) || [f, String(f || "Other").replace(/_/g, " ").replace(/^./, c => c.toUpperCase())])[1];
  const famRank = f => { const i = FAMILY.findIndex(([k]) => k === f); return i < 0 ? 99 : i; };
  const TABS = [["overview", "Overview"], ["verdict", "Verdict"], ["markets", "Markets"], ["goals", "Goals & more"], ["lineups", "Lineups"], ["players", "Players"],
    ["teamstats", "Team stats"], ["h2h", "H2H"], ["form", "Form"], ["table", "Table"]];          // v35: goals & more, players, team stats, head-to-head
  function advisedBets(d, slug, sel, H, A) {                        // v35: the model's advised bets, each beside both teams' averages for its statistic
    const v = d.verdict || {}, tr = d.trends || {}, seen = new Set(), out = [];
    const add = (b, label) => { if (!b || !b.Bet || seen.has(b.Bet)) return; seen.add(b.Bet); out.push({ ...b, label }); };
    (v.best || []).forEach(b => add(b, "Top angle"));
    add(v.safer, "Safer angle");
    (d.markets || []).filter(x => x.trusted && x.p >= 0.6).sort((a, b) => b.p - a.p).slice(0, 6)
      .forEach(x => add({ Bet: String(x.Bet).replace(/\s*\(expected [\d.]+\)/, ""), p: x.p, fair: x.fair, family: x.family, ex: (String(x.Bet).match(/\(expected ([\d.]+)\)/) || [])[1] }, "Tested market"));
    if (!out.length) return "";
    return `<section class="section" data-tab="markets"><h2>Advised bets</h2><p class="small muted">The model's picks for this match, each against both teams' recent averages. Only worth taking above the fair odds.</p>
      <ul class="list">${out.map(b => { const line = /player_props|first_scorer/.test(b.family || "") ? "" : avgLine(statFamily(b.Bet, b.family), tr, H, A);   // a player's bet: no team average
        return `<li class="angle"><span><span class="tag">${esc(b.label)}</span> <b>${esc(b.Bet)}</b><br><span class="small muted">Fair odds ${odds(b.fair)}${b.ex ? `, expected ${esc(b.ex)}` : ""}</span></span>
          <span class="side"><span class="p num">${pct(b.p)}</span>${accaBtn(sel(b.Bet, b.p, b.fair))}</span>
          <span class="why">${esc((b.reasons || []).join(" ") || b.evidence || "")}${line ? `<span class="avgline">${line}</span>` : ""}</span></li>`; }).join("")}</ul></section>`;
  }
  function scorersBlock(S, H, A, hs, as) {                          // v35: likeliest scorers and assisters (as on the dashboard)
    if (!S) return "";
    const list = (arr, team, ts) => (arr || []).slice(0, 5).map(p => `<li><a href="${playerHref(ts, p.Player)}">${esc(p.Player)}</a> <span class="num">${pct(p.p)}</span></li>`).join("");
    const block = (title, h, a) => (h || []).length || (a || []).length ? `<h3>${title}</h3><div class="stat-grid two"><div><b>${esc(H)}</b><ul class="list small">${list(h, H, hs)}</ul></div>
      <div><b>${esc(A)}</b><ul class="list small">${list(a, A, as)}</ul></div></div>` : "";
    const body = block("Likeliest scorers", S.home, S.away) + block("Likeliest assisters", S.home_assist, S.away_assist);
    return body ? `<section class="section" data-tab="markets"><h2>Players to watch</h2>${body}<p class="small muted">Each player's chance to score or assist at least once.</p></section>` : "";
  }
  function h2hBlock(rows, H, A) {
    if (!(rows || []).length) return "";
    let w = 0, d = 0, l = 0, g = 0, n = 0;
    rows.forEach(r => { const [x, y] = String(r.score || "").split("-").map(Number); if (!isFinite(x) || !isFinite(y)) return; n++; g += x + y;
      const hg = r.home === H ? x : y, ag = r.home === H ? y : x; if (hg > ag) w++; else if (hg === ag) d++; else l++; });
    return `<section class="section" data-tab="h2h"><h2>Head to head</h2>${n ? `<p><b>${esc(H)}</b> ${w} wins, ${d} draws, <b>${esc(A)}</b> ${l} wins in the last ${n} meetings; ${(g / n).toFixed(1)} goals a game.</p>` : ""}
      <div class="wrap"><table><thead><tr><th>Date</th><th>Match</th><th class="r">Score</th><th class="r">Corners</th><th class="r">Cards</th></tr></thead><tbody>
      ${rows.map(r => `<tr ${r.espn ? `class="click" data-go="${resultHref(r.espn)}"` : ""}><td class="num small">${esc(r.date)}</td><td>${esc(r.home)} v ${esc(r.away)} <span class="small muted">${esc(r.comp || "")}</span></td>
        <td class="r num"><b>${esc(r.score || "–")}</b></td><td class="r num">${esc(r.corners || "–")}</td><td class="r num">${esc(r.cards || "–")}</td></tr>`).join("")}</tbody></table></div>
      <p class="small muted">Tap a match for its full statistics.</p></section>`;
  }
  // ---------- v35: the match page. Every tab is rendered once; tapping or swiping switches in place (no reload, no history entry),
  // the tab bar keeps the chosen tab in view, and a tab opens at its top. Live parts (overview, stats, lineups, players, table) load on first view.
  const EMPTY_TAB = { verdict: "No verdict for this match yet.", markets: "No markets for this match yet.", goals: "No markets for this match yet.",
    lineups: "Expected lineups appear a few days before the match, and the official ones about an hour before kickoff.", form: "No recent matches on record.",
    teamstats: "No match statistics on record for these teams yet.", h2h: "These teams haven't met in the matches we hold.", stats: "Statistics appear once the match starts.",
    players: "No player statistics for these teams yet.", table: "This competition has no league table (cup or knockout stage)." };
  const posLine = pos => { const b = String(pos || "").toUpperCase().trim().split("-")[0];
    if (["G", "GK"].includes(b)) return "G";
    if (["D", "DF", "CB", "CD", "LCB", "RCB", "LB", "RB", "LWB", "RWB", "WB", "SW"].includes(b)) return "D";
    if (["M", "MF", "DM", "CDM", "CM", "LCM", "RCM", "LM", "RM", "AM", "CAM", "LAM", "RAM"].includes(b)) return "M";
    if (["F", "FW", "S", "ST", "CF", "LF", "RF", "LW", "RW", "SS", "W"].includes(b)) return "F";
    return "GDMF".includes(b[0]) && b[0] ? b[0] : "M"; };
  function goalsMarketsBlock(m, H, A, sel) {
    if (!m.Grid) return "";
    const gm = gridMarkets(m.Grid, H, A), g = {};
    gm.forEach(([f, b, p]) => (g[f] = g[f] || []).push([b, p]));
    return `<section class="section" data-tab="goals"><h2>Goal markets</h2><p class="small muted">Expected goals: ${esc(H)} ${Number(m.ExpHome).toFixed(2)}, ${esc(A)} ${Number(m.ExpAway).toFixed(2)}, total ${(Number(m.ExpHome) + Number(m.ExpAway)).toFixed(2)}.</p>`
      + Object.entries(g).map(([f, xs]) => `<h3>${esc(f)}</h3><div class="wrap"><table><tbody>${xs.map(([b, p]) => `<tr><td>${esc(b)}</td><td class="r num">${pct(p)}</td><td class="r num">${odds(p > 0 ? 1 / p : null)}</td>
          <td class="r">${accaBtn(sel(`${f}: ${b}`, p, p > 0 ? 1 / p : null))}</td></tr>`).join("")}</tbody></table></div>`).join("") + `</section>`;
  }
  function timingBlock(t, H, A) {                                   // v35: goals by 15-minute period
    if (!t || !(t.p_goal || []).length) return "";
    const cell = (v, mx) => v == null ? `<td class="r num">–</td>` : `<td class="r num heat" style="--a:${Math.min(1, v / Math.max(mx, 1e-9)).toFixed(2)}">${Math.round(100 * v)}%</td>`;
    const mxP = Math.max(...t.p_goal), side = s => (t[s] || {}), share = (s, k) => (side(s)[k] || []);
    const mxS = Math.max(0.01, ...["home", "away"].flatMap(s => [...share(s, "for"), ...share(s, "against")]));
    const hasTeams = !!(t.home || t.away);
    return `<section class="section" data-tab="markets"><h2>When the goals come</h2><div class="wrap"><table class="timing"><thead><tr><th>Minutes</th><th class="r">Goal in this match</th>
      ${hasTeams ? `<th class="r">${esc(H)} scored</th><th class="r">${esc(H)} conceded</th><th class="r">${esc(A)} scored</th><th class="r">${esc(A)} conceded</th>` : ""}</tr></thead><tbody>
      ${t.bands.map((b, i) => `<tr><td class="num">${esc(b)}</td>${cell(t.p_goal[i], mxP)}${hasTeams ? cell(share("home", "for")[i], mxS) + cell(share("home", "against")[i], mxS) + cell(share("away", "for")[i], mxS) + cell(share("away", "against")[i], mxS) : ""}</tr>`).join("")}
      </tbody></table></div><p class="small muted">"Goal in this match": the model's chance of at least one goal in each period. The team columns show each side's share of its goals scored and conceded in each period this season${hasTeams ? ` (${esc(H)}: ${side("home").n_for || 0} scored, ${side("home").n_against || 0} conceded; ${esc(A)}: ${side("away").n_for || 0} scored, ${side("away").n_against || 0} conceded)` : ""}.</p></section>`;
  }
  function momentumCard(R, H, A) {                                  // v35: match momentum, home up and away down, goals marked
    const mo = (R || {}).momentum;
    if (!mo || !(mo.home || []).length) return "";
    const W = 340, Hh = 150, mid = Hh / 2, n = 90, bw = W / n, upto = mo.upto || 90;
    const vals = [...mo.home.slice(1, upto + 1), ...mo.away.slice(1, upto + 1)].filter(x => x > 0).sort((a, b) => a - b);
    const mx = Math.max(mo.source === "xg" ? 0.15 : 0.5, vals.length ? vals[Math.floor(0.95 * (vals.length - 1))] : 0.5);   // one big spike doesn't flatten the rest
    const bars = (arr, up) => arr.slice(1, upto + 1).map((v, i) => { const h = Math.sqrt(Math.min(1, v / mx)) * (mid - 16); if (h < 0.5) return "";
      return `<rect x="${(i * bw + 0.4).toFixed(1)}" y="${up ? (mid - h).toFixed(1) : mid}" width="${(bw - 0.8).toFixed(1)}" height="${h.toFixed(1)}" class="${up ? "mh" : "ma"}"/>`; }).join("");
    const goals = (mo.goals || []).map(g => `<text x="${((g.m - 0.5) * bw).toFixed(1)}" y="${g.side === "h" ? 11 : Hh - 3}" text-anchor="middle" class="mg">⚽</text>`).join("");
    return `<section class="scard momentum"><h3>Match momentum</h3><svg viewBox="0 0 ${W} ${Hh}" role="img" aria-label="Match momentum: ${esc(H)} above, ${esc(A)} below">
      <rect x="0" y="14" width="${W}" height="${mid - 14}" class="mzh"/><rect x="0" y="${mid}" width="${W}" height="${mid - 14}" class="mza"/>
      ${bars(mo.home, true)}${bars(mo.away, false)}<line x1="${45 * bw}" y1="14" x2="${45 * bw}" y2="${Hh - 14}" class="mht"/>${goals}</svg>
      <p class="skeys small"><span class="dot h"></span>${esc(H)}<span class="dot a"></span>${esc(A)}</p>
      <p class="small muted mnote">${mo.source === "xg" ? "From the quality (xG) of every shot." : "From shots, chances and corners, minute by minute."}</p></section>`;
  }
  function timelineCard(R, H, A) {                                  // v35: goals, cards and substitutions, newest first
    const T = (R || {}).timeline || [];
    if (!T.length) return "";
    const tm = R.teams || [], hs = (tm.find(t => t.side === "home") || {}).score, as = (tm.find(t => t.side === "away") || {}).score;
    const head = R.completed ? `FT ${esc(hs)} - ${esc(as)}` : R.state === "in" ? `<span class="live">${esc(R.status || "Live")}</span> ${esc(hs)} - ${esc(as)}` : esc(R.status || "");
    const icon = k => ({ goal: "⚽", own: "⚽", pen: "⚽", yellow: '<i class="cardi y"></i>', red: '<i class="cardi r"></i>', sub: '<i class="subi">⇄</i>' }[k] || "•");
    const row = e => {
      if (e.kind === "ht") return `<div class="tl mid"><span>HT ${esc(e.score || "")}</span></div>`;
      if (e.kind === "added") return `<div class="tl mid"><span class="chip">${esc(e.main)}</span></div>`;
      const pill = e.score ? `<span class="spill">${esc(e.score.replace("-", " - "))}</span>` : "";
      const tag = e.kind === "pen" ? " (pen)" : e.kind === "own" ? " (OG)" : "";
      return `<div class="tl ${e.side === "away" ? "a" : "h"}"><span class="min num">${esc(e.clock)}</span><span class="ic">${icon(e.kind)}</span>${pill}
        <span class="nm">${esc(e.main)}${tag}${e.extra && e.kind !== "own" ? ` <span class="muted">${esc(e.extra)}</span>` : ""}</span></div>`;
    };
    return `<section class="scard timeline"><div class="tlhead"><span>${head}</span></div>${T.map(row).join("")}</section>`;
  }
  const ratingChip = r => r == null ? "" : `<span class="rchip ${r >= 7.5 ? "r1" : r >= 7 ? "r2" : r >= 6.5 ? "r3" : "r4"}">${Number(r).toFixed(1)}</span>`;
  function lineupsLive(R, H, A, hsl, asl, coach) {                 // v35: the official team sheet, bench and substitutions (ESPN)
    const L = (R || {}).lineups || [];
    const ok = L.length === 2 && L.every(l => (l.xi || []).length >= 11);
    if (!ok) {
      const S = (R || {}).squads || {};
      if (!S.home && !S.away) return "";
      const list = (arr, ts) => POS.map(([k, lab]) => { const g = (arr || []).filter(p => posLine(p.pos) === k); return g.length ? `<div class="pos"><span class="small muted">${lab}</span>
        ${g.map(p => `<a class="pl" href="${playerHref(ts, p.name, p.id)}"><span class="jn num">${esc(p.jersey || "")}</span> ${esc(p.name)}</a>`).join("")}</div>` : ""; }).join("");
      return `<h2>Squads</h2><p class="small muted">The full squads. The official team sheets appear here as soon as they're announced, about an hour before kickoff.</p>
        <div class="stat-grid two"><div><h3>${esc(H)}</h3>${list(S.home, hsl)}</div><div><h3>${esc(A)}</h3>${list(S.away, asl)}</div></div>`;
    }
    const side = s => L.find(l => l.side === s) || {};
    const asXI = l => ({ ours: (l.xi || []).map(p => ({ Player: p.name, Pos: p.pos, Line: posLine(p.pos), p: 1, id: p.id })), confirmed: true, formation: l.formation });
    const ev = p => `${"⚽".repeat(Math.min(p.goals || 0, 4))}${p.yellow ? '<i class="cardi y"></i>' : ""}${p.red ? '<i class="cardi r"></i>' : ""}`;
    const block = (s, ts) => { const l = side(s), co = (coach || {})[s];
      const used = (l.bench || []).filter(p => p.on != null), unused = (l.bench || []).filter(p => p.on == null);
      const pl = p => `<a href="${playerHref(ts, p.name, p.id)}">${esc(p.name)}</a>`;
      return `<div class="lblock" data-lblock="${s}" ${s === "away" ? "hidden" : ""}>
        ${co ? `<p class="coach"><span class="jn">C</span> ${esc(co)} <span class="muted small">Coach</span></p>` : ""}
        <h3>Starting XI${l.formation ? ` <span class="muted small">${esc(l.formation)}</span>` : ""}</h3><ul class="list sq">
        ${(l.xi || []).map(p => `<li><span class="jn num">${esc(p.jersey)}</span><span class="who">${pl(p)} ${ev(p)}<br><span class="small muted">${esc(p.pos)}${p.off != null ? ` · <span class="offi">↘</span> ${esc(p.off)}` : ""}</span></span>${ratingChip(p.rating)}</li>`).join("")}</ul>
        ${used.length ? `<h3>Substitutions</h3><ul class="list sq">${used.map(p => `<li><span class="jn num">${esc(p.jersey)}</span><span class="who">${pl(p)} ${ev(p)}<br><span class="small"><span class="oni">➜</span> <span class="num">${esc(p.on)}</span> <span class="muted">Out: ${esc(p.for || "")}</span></span></span>${ratingChip(p.rating)}</li>`).join("")}</ul>` : ""}
        ${unused.length ? `<h3>${used.length ? "Unused substitutes" : "Substitutes"}</h3><ul class="list sq">${unused.map(p => `<li><span class="jn num">${esc(p.jersey)}</span><span class="who">${pl(p)}<br><span class="small muted">${esc(p.pos)}</span></span></li>`).join("")}</ul>` : ""}
      </div>`; };
    return `<h2>Lineups</h2><p class="small muted">Official team sheets${R.completed ? "; ratings after full-time" : ""}.</p>
      ${pitchSVG(asXI(side("home")), asXI(side("away")), H, A, null, null, hsl, asl)}
      <div class="pswitch lswitch" role="tablist"><button data-lside="home" class="on">${esc(H)}</button><button data-lside="away">${esc(A)}</button></div>
      ${block("home", hsl)}${block("away", asl)}`;
  }
  const PT = {};                                                    // v35: players tab data per team, for sorting
  const PCOLS = [["matches", "Apps"], ["minutes", "Mins"], ["goals", "G"], ["assists", "A"], ["xg", "xG"], ["xa", "xA"], ["shots", "Sh"], ["sot", "SoT"], ["ga90", "G+A /90"]];
  function renderPlayers(el) {
    const st = PT[el.dataset.teamPlayers] || { rows: [], key: "minutes", dir: -1 };
    const val = (p, k) => k === "ga90" ? (p.minutes >= 90 && (p.goals != null || p.assists != null) ? 90 * ((p.goals || 0) + (p.assists || 0)) / p.minutes : null) : p[k];
    const rows = st.rows.slice().sort((a, b) => st.dir * ((val(a, st.key) ?? -1e9) - (val(b, st.key) ?? -1e9)));
    const show = k => rows.some(p => val(p, k) != null);
    const cols = PCOLS.filter(([k]) => show(k));
    const fmt = (k, v) => v == null ? "–" : (k === "xg" || k === "xa" || k === "ga90") ? Number(v).toFixed(2) : Math.round(v);
    el.innerHTML = `<h3>${esc(el.dataset.name)}</h3>` + (rows.length ? `<div class="wrap"><table class="leaders"><thead><tr><th>Player</th>${cols.map(([k, l]) =>
        `<th class="r ${k === st.key ? "sorted" : ""}" data-psort="${k}">${l}${k === st.key ? (st.dir < 0 ? " ↓" : " ↑") : ""}</th>`).join("")}</tr></thead><tbody>
      ${rows.map(p => `<tr><td><a href="#/player/${esc(p.slug)}${p.espn_id ? "/" + esc(p.espn_id) : ""}">${esc(p.name)}</a></td>${cols.map(([k]) => `<td class="r num">${fmt(k, val(p, k))}</td>`).join("")}</tr>`).join("")}
      </tbody></table></div>` : empty("No player statistics for this team yet."));
  }
  function fill(target, fn) {
    const el = typeof target === "string" ? shell.querySelector(target) : target;
    if (!el || el.dataset.loaded) return;
    el.dataset.loaded = "1";
    fn(el).catch(() => { el.innerHTML = empty("Not available right now. Try again in a minute."); });
  }
  function loadPane(key) {
    const root = shell.querySelector("#mroot");
    if (!root) return;
    const H = root.dataset.h, A = root.dataset.a, ev = root.dataset.ev, live = root.dataset.live === "1", started = root.dataset.started === "1";
    const result = () => getJSON(workerApi(`result?e=${encodeURIComponent(ev)}&m=${live || !started ? Math.floor(Date.now() / 60000) : "ft"}`));
    const coach = { home: root.dataset.coachH || null, away: root.dataset.coachA || null };
    if (key === "overview" && ev) fill("[data-ovlive]", async el => { const R = await result(); el.innerHTML = momentumCard(R, H, A) + timelineCard(R, H, A); });
    if (key === "stats" && ev) fill("[data-stats]", async el => { const R = await result(); el.innerHTML = R && R.card ? statsCard(R.card, H, A, live) : empty("Statistics for this match aren't available yet."); });
    if (key === "lineups" && ev) fill("[data-lineups-live]", async el => {
      const R = await result(), html = lineupsLive(R, H, A, root.dataset.hs, root.dataset.as, coach);
      const official = /Starting XI/.test(html);
      el.innerHTML = html;
      const xi = shell.querySelector("[data-xi]");
      if (xi && official) xi.hidden = true;                          // the team sheet replaces the expected lineup
    });
    if (key === "players") shell.querySelectorAll("[data-team-players]").forEach(el => fill(el, async el => {
      let t = null;
      try { t = await get(`team/${el.dataset.teamPlayers}.json`); } catch (e) {}
      PT[el.dataset.teamPlayers] = PT[el.dataset.teamPlayers] || { rows: ((t || {}).players || []), key: "minutes", dir: -1 };
      renderPlayers(el);
    }));
    if (key === "table") fill("[data-match-table]", async tbl => {
      let c = null;
      try { c = await get(`comp/${tbl.dataset.matchTable}.json`); } catch (e) {}
      tbl.innerHTML = c && (c.table || []).length ? `<h2>${esc(c.name)} table</h2><div class="wrap"><table><thead><tr><th>#</th><th>Team</th><th class="r">P</th><th class="r">GD</th><th class="r">Pts</th><th>Form</th></tr></thead><tbody>
        ${c.table.map(x => `<tr class="${[tbl.dataset.h, tbl.dataset.a].includes(x.team_slug) ? "hl" : ""}"><td class="num">${x.pos}</td><td><a href="#/team/${esc(x.team_slug)}">${esc(x.team)}</a></td><td class="r num">${x.P}</td>
          <td class="r num">${x.GD > 0 ? "+" : ""}${x.GD}</td><td class="r num"><b>${x.Pts}</b></td><td>${formChips(x.form)}</td></tr>`).join("")}</tbody></table></div>` : empty(EMPTY_TAB.table);
    });
  }
  function showTab(key, byUser) {
    const root = shell.querySelector("#mroot"), bar = shell.querySelector(".mtabs");
    if (!root || !bar) return;
    const links = [...bar.querySelectorAll("a[data-k]")];
    if (!links.some(a => a.dataset.k === key)) return;
    root.querySelectorAll("[data-tab]").forEach(s => { s.hidden = s.dataset.tab !== key; });
    links.forEach(a => { const on = a.dataset.k === key; a.classList.toggle("on", on); a.setAttribute("aria-selected", String(on)); });
    const on = links.find(a => a.dataset.k === key), hdr0 = document.querySelector("header.top");
    if (hdr0) bar.style.top = hdr0.offsetHeight + "px";                // sticks right under the header, whatever its height on this screen
    bar.scrollLeft = Math.max(0, on.offsetLeft - (bar.clientWidth - on.offsetWidth) / 2);   // the chosen tab stays in view
    if (byUser) {
      try { history.replaceState(null, "", `#/match/${root.dataset.slug}/${key}`); } catch (e) {}
      const anchor = shell.querySelector("#tabanchor"), hdr = document.querySelector("header.top");
      const target = anchor.getBoundingClientRect().top + window.scrollY - (hdr ? hdr.offsetHeight : 0);
      if (window.scrollY > target) window.scrollTo(0, target);       // the new tab starts at its top, under the tab bar
      hit("tab_" + key);
    }
    loadPane(key);
  }
  async function pageMatch(slug, tab) {
    setNav("today");
    const d = await get(`match/${slug}.json`);
    await getLive();
    const L0 = LIVE[slug], m = d.match || {}, ev0 = m.espn, v = d.verdict || {};
    const hasEv = !!(ev0 && ev0.code && ev0.id), started = !!(L0 && L0.state && L0.state !== "pre");
    const hasStats = hasEv && started;
    const ko = m.kickoff ? Date.parse(m.kickoff) : null;
    const sheetSoon = hasEv && (started || (ko != null && ko - Date.now() < 3 * 3600000));      // the team sheet can be out: read it live
    const TABS_ = hasStats ? [TABS[0], ["stats", L0.state === "in" ? "● Stats" : "Stats"], ...TABS.slice(1)] : TABS;
    tab = TABS_.some(([k]) => k === tab) ? tab : "overview";
    const ts_ = d.team_style || {};
    const mb_ = { badges: { home: { c: (ts_[m.Home] || {}).color, a: (ts_[m.Home] || {}).abbr }, away: { c: (ts_[m.Away] || {}).color, a: (ts_[m.Away] || {}).abbr } } };
    const H = m.Home, A = m.Away, hs = m.home_slug || "", as = m.away_slug || "";
    const sel = (bet, p, fair) => ({ id: selId(slug, bet), match: `${H} v ${A}`, slug, bet, p, fair });
    const fairOf = p => (p ? 1 / p : null);
    const markets = (d.markets || []).slice().sort((a, b) => b.p - a.p);
    const fam = {};
    markets.forEach(x => (fam[x.family || "other"] = fam[x.family || "other"] || []).push(x));
    const xi = ((((d.expected_xi || {}).home) || {}).ours || []).length;
    const confirmed = !!(((d.expected_xi || {}).home) || {}).confirmed;
    const coach = d.coach || {};
    app.innerHTML = `${backBar()}<section class="hero big">
        <p class="meta">${esc(m.Competition)}</p>
        <p class="follow-row"><button class="btn follow ${fav.has("match:" + slug) ? "added" : ""}" data-fav="match:${esc(slug)}" data-follow-match="${esc(slug)}">☆ Follow this match</button></p>
        <div class="mhead">
          <button class="star ${fav.has("team:" + hs) ? "on" : ""}" data-fav="team:${esc(hs)}" aria-label="Favourite ${esc(H)}">★</button>
          <div class="mside">${badge(Object.assign({}, m, mb_), "home")}<b>${esc(H)}</b></div>
          <div class="mcentre num" id="mcentre">${L0 && L0.state !== "pre" ? `<b class="score">${L0.hs}–${L0.as}</b><span class="${L0.state === "in" ? "live" : "muted"}">${esc(L0.detail || "")}</span>`
              : `<b class="score">${esc(timeOf(m))}</b><span class="muted">${esc(dayLabel(String(m.Date).slice(0, 10)))}</span>`}</div>
          <div class="mside">${badge(Object.assign({}, m, mb_), "away")}<b>${esc(A)}</b></div>
          <button class="star ${fav.has("team:" + as) ? "on" : ""}" data-fav="team:${esc(as)}" aria-label="Favourite ${esc(A)}">★</button>
        </div>
        ${chanceBar(m, [H, A])}
        <div class="bar-legend num"><span><b>${pct(m.pH)}</b>${esc(H)}, fair ${odds(fairOf(m.pH))}</span><span><b>${pct(m.pD)}</b>Draw, fair ${odds(fairOf(m.pD))}</span>
          <span style="text-align:right"><b>${pct(m.pA)}</b>${esc(A)}, fair ${odds(fairOf(m.pA))}</span></div>
        ${m.ExpHome != null ? `<p class="muted">Expected goals: ${esc(H)} ${Number(m.ExpHome).toFixed(2)}, ${esc(A)} ${Number(m.ExpAway).toFixed(2)}.</p>` : ""}
      </section>
      <div id="tabanchor"></div>
      <nav class="mtabs" role="tablist">${TABS_.map(([k, l]) => `<a role="tab" data-k="${k}" href="#/match/${esc(slug)}/${k}" class="${k === tab ? "on" : ""}" aria-selected="${k === tab}">${l}</a>`).join("")}</nav>
      <div id="mroot" data-slug="${esc(slug)}" data-h="${esc(H)}" data-a="${esc(A)}" data-hs="${esc(hs)}" data-as="${esc(as)}" data-ev="${hasEv ? esc(ev0.code + ":" + ev0.id) : ""}"
           data-live="${L0 && L0.state === "in" ? 1 : 0}" data-started="${started ? 1 : 0}" data-coach-h="${esc(coach.home || "")}" data-coach-a="${esc(coach.away || "")}">
      <section class="section" data-tab="overview">
        ${started && hasEv ? `<div data-ovlive><p class="muted small">Loading the match timeline…</p></div>` : ""}
        ${m.Grid ? (() => { const tot = m.Grid.flat().reduce((s, x) => s + x, 0) || 1, cs = []; m.Grid.forEach((r, i) => r.forEach((x, j) => cs.push([i, j, x / tot])));
            return `<h3>Likeliest scores</h3><p class="num">${cs.sort((a_, b_) => b_[2] - a_[2]).slice(0, 5).map(([i, j, p]) => `<b>${i}–${j}</b> ${pct(p)}`).join(" · ")}</p>`; })() : ""}
        ${v.best && v.best.length ? `<h3>Top angle</h3><p><b>${esc(v.best[0].Bet)}</b>, ${pct(v.best[0].p)}, fair ${odds(v.best[0].fair)}.</p>` : ""}
        ${m.pBTTS != null || m.pOver25 != null ? `<p>${m.pBTTS != null ? `Both teams to score ${pct(m.pBTTS)}. ` : ""}${m.pOver25 != null ? `Over 2.5 goals ${pct(m.pOver25)}.` : ""}</p>` : ""}
        ${m.Absent ? `<h3>Likely missing</h3><p class="small">${esc(m.Absent)}</p>` : ""}
        ${m.Note ? `<p class="small muted">${esc(m.Note)}</p>` : ""}
      </section>
      ${hasStats ? `<section class="section" data-tab="stats"><div data-stats><p class="muted small">Loading the match statistics…</p></div></section>` : ""}
      ${v.best && v.best.length ? `<section class="section" data-tab="verdict"><h2>Verdict</h2><ul class="list">${v.best.map(b => `<li class="angle"><span><b>${esc(b.Bet)}</b><br><span class="small muted">Fair odds ${odds(b.fair)}</span></span>
          <span class="side"><span class="p num">${pct(b.p)}</span>${accaBtn(sel(b.Bet, b.p, b.fair))}</span><span class="why">${esc((b.reasons || []).join(" ") || b.evidence || "")}</span></li>`).join("")}
        ${v.safer ? `<li class="angle"><span>Safer angle: <b>${esc(v.safer.Bet)}</b><br><span class="small muted">Fair odds ${odds(v.safer.fair)}</span></span>
          <span class="side"><span class="p num">${pct(v.safer.p)}</span>${accaBtn(sel(v.safer.Bet, v.safer.p, v.safer.fair))}</span></li>` : ""}</ul>
        ${(v.avoid || []).length ? `<p class="small"><b>Avoid:</b> ${v.avoid.map(esc).join(" ")}</p>` : ""}</section>` : ""}
      ${advisedBets(d, slug, sel, H, A)}
      ${scorersBlock(d.scorers, H, A, hs, as)}
      ${m.Grid ? `<section class="section" data-tab="markets"><h2>Score grid</h2>${gridTable(m.Grid, H, A)}</section>` : ""}
      ${timingBlock(d.timing, H, A)}
      ${goalsMarketsBlock(m, H, A, sel)}
      ${m.ExpCorners != null || m.ExpCards != null ? `<section class="section" data-tab="goals"><h2>Corners and cards</h2><div class="wrap"><table><tbody>
          ${m.ExpCorners != null ? `<tr><td>Expected corners</td><td class="r num">${Number(m.ExpCorners).toFixed(1)}</td><td></td></tr>` : ""}
          ${m.pOverCorners != null ? `<tr><td>Over 9.5 corners</td><td class="r num">${pct(m.pOverCorners)}</td><td class="r num">${odds(1 / m.pOverCorners)}</td></tr><tr><td>Under 9.5 corners</td><td class="r num">${pct(1 - m.pOverCorners)}</td><td class="r num">${odds(1 / (1 - m.pOverCorners))}</td></tr>` : ""}
          ${m.ExpCards != null ? `<tr><td>Expected cards${m.ExpCardsH != null ? ` (${esc(H)} ${Number(m.ExpCardsH).toFixed(1)}, ${esc(A)} ${Number(m.ExpCardsA).toFixed(1)})` : ""}</td><td class="r num">${Number(m.ExpCards).toFixed(1)}</td><td></td></tr>` : ""}
          ${m.pOverCards != null ? `<tr><td>Over 4.5 cards</td><td class="r num">${pct(m.pOverCards)}</td><td class="r num">${odds(1 / m.pOverCards)}</td></tr><tr><td>Under 4.5 cards</td><td class="r num">${pct(1 - m.pOverCards)}</td><td class="r num">${odds(1 / (1 - m.pOverCards))}</td></tr>` : ""}
        </tbody></table></div></section>` : ""}
      ${markets.length ? `<section class="section" data-tab="goals"><h2>More markets</h2>${Object.entries(fam).sort((x, y) => famRank(x[0]) - famRank(y[0])).map(([f, xs]) => `<h3>${esc(famName(f))}</h3><div class="wrap"><table><tbody>
          ${xs.map(x => { const ex = (String(x.Bet).match(/\(expected ([\d.]+)\)/) || [])[1], base = String(x.Bet).replace(/\s*\(expected [\d.]+\)/, "");
              const under = /\bover\b/i.test(base) ? base.replace(/\bover\b/i, m_ => m_[0] === "O" ? "Under" : "under") : null;
              return `<tr><td>${esc(base)} <span class="tag ${x.trusted ? "trusted" : ""}">${x.trusted ? "trusted" : "experimental"}</span>${ex ? `<br><span class="small muted">Expected: ${esc(ex)}</span>` : ""}</td>
                <td class="r num">${pct(x.p)}</td><td class="r num">${odds(x.fair)}</td><td class="r">${accaBtn(sel(base, x.p, x.fair))}</td></tr>`
                + (under ? `<tr><td>${esc(under)}</td><td class="r num">${pct(1 - x.p)}</td><td class="r num">${odds(x.p < 1 ? 1 / (1 - x.p) : null)}</td><td class="r">${accaBtn(sel(under, 1 - x.p, x.p < 1 ? 1 / (1 - x.p) : null))}</td></tr>` : ""); }).join("")}</tbody></table></div>`).join("")}
          <p class="small muted">Trusted markets have passed their calibration test; experimental ones are still being tested. "Under" lines are the other side of each market.</p></section>` : ""}
      <section class="section" data-tab="lineups">
        ${sheetSoon ? `<div data-lineups-live></div>` : ""}
        ${xi ? `<div data-xi><h2>${confirmed ? "Lineups" : "Expected lineups"}</h2>
          ${coach.home || coach.away ? `<p class="small">${coach.home ? `<b>${esc(H)}</b> coach: ${esc(coach.home)}` : ""}${coach.home && coach.away ? " · " : ""}${coach.away ? `<b>${esc(A)}</b> coach: ${esc(coach.away)}` : ""}</p>` : ""}
          <p class="small muted">${confirmed ? "Official lineups." : "Expected lineups: fainter players are less certain to start; the number is each player's start chance."}</p>
          ${pitchSVG((d.expected_xi || {}).home, (d.expected_xi || {}).away, H, A, (mb_.badges.home || {}).c, (mb_.badges.away || {}).c, hs, as)}<div class="stat-grid" style="grid-template-columns:1fr 1fr">
          <div style="display:block"><h3>${esc(H)}</h3>${xiByPosition((d.expected_xi || {}).home, hs)}</div><div style="display:block"><h3>${esc(A)}</h3>${xiByPosition((d.expected_xi || {}).away, as)}</div></div>
          ${["home", "away"].map(s => { const e = (d.expected_xi || {})[s] || {}; return !e.confirmed && (e.doubts || []).length ? `<p class="small"><b>${esc(s === "home" ? H : A)}, doubts and absences:</b> ${e.doubts.map(esc).join(", ")}</p>` : ""; }).join("")}</div>` : (sheetSoon ? "" : empty(EMPTY_TAB.lineups))}
      </section>
      <section class="section" data-tab="players"><h2>Players</h2><p class="small muted">This season, every competition. Tap a column heading to sort.</p>
        <div data-team-players="${esc(hs)}" data-name="${esc(H)}"><p class="muted small">Loading…</p></div><div data-team-players="${esc(as)}" data-name="${esc(A)}"><p class="muted small">Loading…</p></div></section>
      ${avgTable(d.trends, H, A) ? `<section class="section" data-tab="teamstats"><h2>Team stats</h2>${avgTable(d.trends, H, A)}
        ${["home", "away"].map(s => { const t = (d.trends || {})[s]; return t ? `<p class="small"><b>${esc(s === "home" ? H : A)}</b>: ${t.ppg != null ? `${Number(t.ppg).toFixed(2)} points a game in the last 7` : ""}${t.home ? `, at home ${esc(t.home)}` : ""}${t.away ? `, away ${esc(t.away)}` : ""}${t.perf != null ? `; goals minus xG ${t.perf >= 0 ? "+" : ""}${Number(t.perf).toFixed(2)} a game` : ""}.</p>` : ""; }).join("")}</section>` : ""}
      ${h2hBlock(d.h2h, H, A)}
      ${(d.trends || {}).home || (d.trends || {}).away ? `<section class="section" data-tab="form"><h2>Last 7 matches</h2>${lastSeven((d.trends || {}).home, H)}${lastSeven((d.trends || {}).away, A)}</section>` : ""}
      ${d.last_time && (d.last_time.home || d.last_time.away) ? `<section class="section" data-tab="form"><h2>Last time out</h2>${["home", "away"].map(s => { const lt = d.last_time[s]; if (!lt || !(lt.picks || []).length) return "";
          return `<h3>${esc(s === "home" ? H : A)}${lt.match ? `: ${esc(lt.match)} ${esc(lt.score || "")}` : ""}</h3><ul class="list">${lt.picks.map(p => `<li>${p.won ? '<span class="won">✓</span>' : '<span class="lost">✗</span>'} ${esc(p.Bet)} (${pct(p.p)})</li>`).join("")}</ul>`; }).join("")}</section>` : ""}
      <section class="section" data-tab="table"><div data-match-table="${esc(m.league_slug || "")}" data-h="${esc(hs)}" data-a="${esc(as)}"><p class="muted small">Loading the table…</p></div></section>
      </div>
      <p class="small muted">Probabilities are the model's, not guarantees. A pick is only worth taking above its fair odds. 18+.</p>`;
    const root = app.querySelector("#mroot");
    TABS_.forEach(([k]) => { if (!root.querySelector(`[data-tab="${k}"]`)) root.insertAdjacentHTML("beforeend", `<section class="section" data-tab="${k}">${empty(EMPTY_TAB[k] || "Nothing here yet.")}</section>`); });
    root.querySelectorAll("[data-tab]").forEach(s => { s.hidden = s.dataset.tab !== tab; });
    afterRender = () => showTab(tab, false);
    hit("match");
  }

  async function pageTeam(slug) {
    setNav("leagues");
    const t = await get(`team/${slug}.json`);
    const r = t.record;
    const spotted = ((t.trends || {}).spotted || []).slice(0, 5);
    app.innerHTML = `<h1>${esc(t.name)}</h1>
      <p class="muted">${t.league_slug ? `<a href="#/comp/${esc(t.league_slug)}">${esc(t.league)}</a>` : esc(t.league || "")}${r ? `, ${ordinal(r.pos)} with ${r.Pts} points from ${r.P} matches` : ""}</p>
      <p><button class="star ${fav.has("team:" + slug) ? "on" : ""}" data-fav="team:${esc(slug)}" aria-label="Favourite">★</button> Favourite ${alertsLink(slug, "Get alerts on Telegram")}</p>
      ${r ? `<p>Form ${formChips(r.form)}</p>` : ""}
      ${(t.upcoming || []).length ? `<h2>Next matches</h2>${t.upcoming.map(u => matchRow({ slug: u.slug, kickoff: u.kickoff, Date: u.date, Home: u.venue === "H" ? t.name : u.opp, Away: u.venue === "H" ? u.opp : t.name,
          home_slug: u.venue === "H" ? slug : "", pH: u.pH, pD: u.pD, pA: u.pA, Competition: u.competition })).join("")}` : ""}
      ${(t.form || []).length ? `<h2>Recent results</h2><ul class="list">${t.form.slice().reverse().map(f => `<li class="num">${esc(f.date)}: ${f.venue === "H" ? "v" : "at"} ${esc(f.opp)} <b>${esc(f.score)}</b> ${formChips(f.result)}</li>`).join("")}</ul>` : ""}
      ${spotted.length ? `<h2>Trends</h2><ul class="list">${spotted.map(s => `<li>${esc(s.pattern)}: ${s.count} of the last ${s.of}${s.base != null ? ` <span class="small muted">(league usually ${pct(s.base)})</span>` : ""}</li>`).join("")}</ul>` : ""}
      ${(() => { const st = (t.trends || {}).stats || {}, rows = AVG_ROWS.filter(([kf]) => (st[kf] || [])[0] != null);          // v35: team stats
          return rows.length ? `<h2>Team stats</h2><div class="wrap"><table class="avg"><thead><tr><th>Per match</th><th class="r">for</th><th class="r">against</th></tr></thead><tbody>
            ${rows.map(([kf, ka, label]) => `<tr><td>${esc(label)}</td><td class="r num">${f1((st[kf] || [])[0])}<small class="muted"> (${f1((st[kf] || [])[1])})</small></td>
              <td class="r num">${f1((st[ka] || [])[0])}<small class="muted"> (${f1((st[ka] || [])[1])})</small></td></tr>`).join("")}</tbody></table></div>
            <p class="small muted">Last 7 matches in every competition; this season's average in brackets.</p>` : ""; })()}
      ${(t.players || []).length ? `<h2>Squad</h2><div class="wrap"><table><thead><tr><th>Player</th><th class="r">Matches</th><th class="r">Minutes</th><th class="r">Rating</th></tr></thead><tbody>
          ${t.players.map(p => `<tr><td><a href="#/player/${esc(p.slug)}">${esc(p.name)}</a></td><td class="r num">${p.matches || 0}</td><td class="r num">${p.minutes || 0}</td><td class="r num">${p.rating ? Number(p.rating).toFixed(1) : "–"}</td></tr>`).join("")}</tbody></table></div>` : ""}`;
    hit("team");
  }

  // v35: the match stats card (in play and full-time): All / 1st / 2nd, possession as one split bar with % pills, every other
  // statistic as two half-bars growing from the middle (each side's share of the total; the side ahead brighter)
  const leadNum = v => { const m = String(v == null ? "" : v).match(/-?\d+(\.\d+)?/); return m ? parseFloat(m[0]) : NaN; };
  function statsCard(card, H, A, live) {
    const periods = (card && card.periods) || [];
    if (!periods.length) return "";
    const row = it => {
      const h = leadNum(it.home), a = leadNum(it.away), tot = h + a;
      if (/posses/i.test(`${it.key || ""} ${it.label || ""}`)) {          // (PitchAPI spells it "BallPossesion")
        const hp = isFinite(h) ? h : 50;
        return `<div class="srow poss"><div class="slab"><span class="pill h">${esc(String(it.home).replace(/%?$/, "%"))}</span><span>${esc(it.label)}</span><span class="pill a">${esc(String(it.away).replace(/%?$/, "%"))}</span></div>
          <div class="pbar"><i class="h" style="flex-basis:${hp}%"></i><i class="a" style="flex-basis:${100 - hp}%"></i></div></div>`;
      }
      const sh = isFinite(tot) && tot > 0 ? 100 * h / tot : 0, sa = isFinite(tot) && tot > 0 ? 100 * a / tot : 0;
      return `<div class="srow"><div class="slab"><b class="num">${esc(it.home)}</b><span>${esc(it.label)}</span><b class="num">${esc(it.away)}</b></div>
        <div class="halves"><span class="half h ${h >= a ? "lead" : ""}"><i style="width:${sh.toFixed(1)}%"></i></span><span class="half a ${a >= h ? "lead" : ""}"><i style="width:${sa.toFixed(1)}%"></i></span></div></div>`;
    };
    const blocks = periods.map((p, i) => `<div class="pblock" data-pblock="${i}" ${i ? "hidden" : ""}>${p.groups.map(g => `<section class="scard"><h3>${esc(g.title)}</h3>${g.items.map(row).join("")}</section>`).join("")}</div>`).join("");
    const sw = periods.length > 1 ? `<div class="pswitch" role="tablist">${periods.map((p, i) => `<button role="tab" data-period="${i}" class="${i ? "" : "on"}" aria-selected="${!i}">${esc(p.name.toUpperCase())}</button>`).join("")}</div>` : "";
    const note = card.source === "pitchapi" ? "Full statistics after full-time." : live ? "Live statistics, updated every minute. The full set (xG, big chances, halves) appears after full-time." : "Full statistics (xG, big chances, halves) appear shortly after full-time.";
    return `<div class="statscard"><p class="skeys"><span class="dot h"></span>${esc(H)}<span class="dot a"></span>${esc(A)}</p>${sw}${blocks}<p class="small muted">${note}</p></div>`;
  }
  // v35: headings for the player's statistics, recent matches and transfer history (from ESPN, through the Worker)
  async function transfersBlock(id) {
    if (!id || id === "-") return "";
    let T = [];
    try { T = await getJSON(workerApi(`transfers?id=${encodeURIComponent(id)}`)); } catch (e) { return ""; }
    return `<h2 id="transfers">Transfer history</h2>${(T || []).length ? `<ul class="list">${T.map(t => `<li><span class="num">${esc(t.date)}</span>: ${esc(t.from || "?")} → <b>${esc(t.to || "?")}</b>
        <span class="small muted">${esc([t.type, t.fee].filter(Boolean).join(", "))}</span></li>`).join("")}</ul>` : empty("No transfers on record.")}`;
  }
  async function pagePlayer(slug, espnId) {
    setNav("leagues");
    const p = await get(`player/${slug}.json`);
    const labels = p.labels || {};
    const sections = {};
    Object.entries(p.stats || {}).forEach(([k, v]) => { const l = labels[k] || { label: k, section: "Other" }; (sections[l.section || "Other"] = sections[l.section || "Other"] || []).push({ k, l, v }); });
    const val = v => (v && typeof v === "object" ? v : { total: v });
    const n1 = x => (x != null && isFinite(x) ? Math.round(x * 10) / 10 : "–"), n2 = x => (x != null && isFinite(x) ? Number(x).toFixed(2) : "–");
    const tb = await transfersBlock(p.espn_id || espnId);
    app.innerHTML = `${backBar()}<h1>${esc(p.name)}</h1>
      <p class="muted"><a href="#/team/${esc(p.team_slug)}">${esc(p.team)}</a>${p.position ? `, ${esc(p.position)}` : ""}. ${p.matches || 0} matches, ${p.minutes || 0} minutes this season.</p>
      <p class="links small"><a href="#/player/${esc(slug)}${espnId ? "/" + esc(espnId) : ""}" data-jump="stats">Player stats</a> <a href="#/player/${esc(slug)}" data-jump="recent">Recent matches</a>${tb ? ` <a href="#/player/${esc(slug)}" data-jump="transfers">Transfer history</a>` : ""}</p>
      <h2 id="stats">Player stats</h2><p class="small muted">Totals for ${esc(p.period || "this season")}, every competition.</p>
      ${(p.by_competition || []).length > 0 ? `<h3>By competition</h3><div class="wrap"><table><thead><tr><th>Competition</th><th class="r">Apps</th><th class="r">Mins</th><th class="r">Goals</th><th class="r">Assists</th><th class="r">xG</th><th class="r">xA</th></tr></thead><tbody>
        ${p.by_competition.map(c => `<tr><td>${esc(c.competition)}</td><td class="r num">${c.matches}</td><td class="r num">${c.minutes}</td><td class="r num">${c.goals != null ? Math.round(c.goals) : "–"}</td>
          <td class="r num">${c.assists != null ? Math.round(c.assists) : "–"}</td><td class="r num">${c.xg != null ? Number(c.xg).toFixed(2) : "–"}</td><td class="r num">${c.xa != null ? Number(c.xa).toFixed(2) : "–"}</td></tr>`).join("")}</tbody></table></div>` : ""}
      ${Object.keys(sections).length ? Object.entries(sections).map(([s, xs]) => `<h3>${esc(s)}</h3><div class="wrap"><table><thead><tr><th>Statistic</th><th class="r">Total</th><th class="r">Per 90</th><th class="r">Per match</th></tr></thead><tbody>
        ${xs.sort((a, b) => (a.l.order || 0) - (b.l.order || 0)).map(({ l, v }) => { const x = val(v); return `<tr><td>${esc(l.label || "")}</td><td class="r num">${n1(x.total)}</td>
          <td class="r num">${n2(x.per90)}</td><td class="r num">${n2(x.per_match)}</td></tr>`; }).join("")}</tbody></table></div>`).join("") : empty("No statistics this season yet.")}
      <h2 id="recent">Recent matches</h2>${(p.log || []).length ? `<ul class="list">${p.log.slice().reverse().map(g => `<li class="num">${esc(g.date)}: ${esc(g.competition || "")} ${g.started === false ? "(sub)" : ""}
          <span class="small muted">${Object.entries(g.stats || {}).slice(0, 6).map(([k, x]) => `${esc((labels[k] || {}).label || k)} ${esc(x)}`).join(", ")}</span></li>`).join("")}</ul>` : empty("No recent matches on record.")}
      ${tb}
      <p class="small muted">Source: ${esc(p.source === "pitchapi" ? "full match statistics" : "match reports")}${tb ? "; transfers from ESPN" : ""}.</p>`;
    hit("player");
  }
  // v35: a player tapped in a lineup or list: find his page from his club's squad (by ESPN id, then by name)
  async function pageFindPlayer(teamSlug, id, name) {
    setNav("leagues");
    let t = null;
    if (teamSlug && teamSlug !== "-") { try { t = await get(`team/${teamSlug}.json`); } catch (e) {} }
    const ps = (t || {}).players || [], nk = nameKey(name), sur = nameKey(String(name || "").split(" ").slice(-1)[0]);
    const hitP = ps.find(p => id && id !== "-" && String(p.espn_id) === String(id)) || ps.find(p => nameKey(p.name) === nk)
      || (ps.filter(p => nameKey(String(p.name).split(" ").slice(-1)[0]) === sur).length === 1 ? ps.find(p => nameKey(String(p.name).split(" ").slice(-1)[0]) === sur) : null);
    if (hitP) { app.innerHTML = `<p class="loading">Opening ${esc(hitP.name)}…</p>`; location.replace(`#/player/${hitP.slug}${id && id !== "-" ? "/" + id : ""}`); return; }
    const tb = await transfersBlock(id);
    app.innerHTML = `${backBar()}<h1>${esc(name || "Player")}</h1>${t ? `<p class="muted"><a href="#/team/${esc(teamSlug)}">${esc(t.name)}</a></p>` : ""}
      ${empty("Detailed statistics aren't available for this player yet.")}${tb}`;
  }
  // v35: a past match: score, statistics, goals and cards, lineups (ESPN, through the Worker)
  async function pageResult(e, date) {
    let P = null;                                                     // v35: what Kwallo said before kickoff (from that day's results file)
    if (date && /^\d{4}-\d{2}-\d{2}$/.test(date)) { try { P = ((await get(`days/${date}.json`)).matches || []).find(x => x.espn === e) || null; } catch (err) {} }
    setNav("today");
    const R = await getJSON(workerApi(`result?e=${encodeURIComponent(e)}`));
    const T = R.teams || [], H = T.find(t => t.side === "home") || T[0] || {}, A = T.find(t => t.side === "away") || T[1] || {};
    const bar = s => { const h = parseFloat(s.home), a = parseFloat(s.away), tot = h + a;
      return isFinite(h) && isFinite(a) && tot > 0 ? `<div class="bar mini" aria-hidden="true"><i class="h" style="flex-basis:${100 * h / tot}%"></i><i class="a" style="flex-basis:${100 * a / tot}%"></i></div>` : ""; };
    app.innerHTML = `${backBar()}<section class="hero"><p class="meta">${esc(R.competition)}${R.date ? `, ${esc(longDate(R.date))}` : ""}${R.venue ? ` · ${esc(R.venue)}` : ""}</p>
        <div class="mhead"><span></span><div class="mside"><b>${esc(H.name)}</b></div><div class="mcentre num"><b class="score">${esc(H.score ?? "–")}–${esc(A.score ?? "–")}</b>
          <span class="muted">${esc(R.status || "")}</span></div><div class="mside"><b>${esc(A.name)}</b></div><span></span></div></section>
      ${P && (P.pred || P.top) ? `<section class="scard kpred"><h3>Kwallo's prediction before kick-off</h3>
        ${P.pred ? `${chanceBar(P.pred, [H.name, A.name])}<div class="bar-legend num"><span><b>${pct(P.pred.pH)}</b>${esc(H.name)}</span><span><b>${pct(P.pred.pD)}</b>Draw</span><span style="text-align:right"><b>${pct(P.pred.pA)}</b>${esc(A.name)}</span></div>` : ""}
        ${P.top ? `<p>Top angle: <b>${esc(P.top.bet)}</b>${P.top.p != null ? ` (${pct(P.top.p)})` : ""} ${P.top.won === true ? '<span class="won">✓ came in</span>' : P.top.won === false ? '<span class="lost">✗ missed</span>' : ""}</p>` : ""}</section>` : ""}
      ${momentumCard(R, H.name, A.name)}${timelineCard(R, H.name, A.name)}
      ${R.card ? `<h2>Match stats</h2>${statsCard(R.card, H.name, A.name, !R.completed)}`
        : (R.stats || []).length ? `<h2>Match stats</h2><div class="wrap"><table class="mstats"><tbody>${R.stats.map(s => `<tr><td class="r num"><b>${esc(s.home)}</b></td><td class="c">${esc(s.label)}${bar(s)}</td><td class="num"><b>${esc(s.away)}</b></td></tr>`).join("")}</tbody></table></div>` : ""}
      ${lineupsLive(R, H.name, A.name, slugify(H.name), slugify(A.name), {})}
      <p class="small muted">Match data from ESPN.</p>`;
    hit("result");
  }

  async function pageAngles() {
    setNav("angles");
    const b = await get("best.json");
    const list = b.angles || [];
    app.innerHTML = `<h1>Best angles</h1><p class="muted">The strongest picks across all competitions, ranked. Each one is only worth taking above its fair odds.</p>
      ${list.length ? `<ul class="list">${list.map(a => `<li class="angle"><span><b>${esc(a.Bet)}</b><br><a class="small" href="#/match/${esc(a.slug)}">${esc(a.home)} v ${esc(a.away)}</a>
          <span class="small muted">, ${esc(a.competition)}, ${esc(a.kickoff ? new Date(a.kickoff).toLocaleString([], { weekday: "short", hour: "2-digit", minute: "2-digit" }) : a.date)}</span></span>
          <span class="side"><span class="p num">${pct(a.p)}</span><span class="small muted">fair ${odds(a.fair)}</span>${accaBtn({ id: selId(a.slug, a.Bet), match: `${a.home} v ${a.away}`, slug: a.slug, bet: a.Bet, p: a.p, fair: a.fair })}</span>
          <span class="why">${esc((a.reasons || []).join(" ") || a.evidence || "")}</span></li>`).join("")}</ul>`
        : empty("No angles yet for the coming days. They appear after the morning update.")}`;
    hit("best_angles");
  }

  function pageAcca() {
    setNav("acca");
    const a = acca.list();
    const perMatch = {};
    a.forEach(x => (perMatch[x.slug] = (perMatch[x.slug] || 0) + 1));
    const linked = Object.values(perMatch).some(n => n > 1);
    const p = a.reduce((s, x) => s * (x.p || 0), 1);
    app.innerHTML = `<h1>Accumulator</h1>
      ${a.length ? `<ul class="list">${a.map(x => `<li class="angle"><span><b>${esc(x.bet)}</b><br><a class="small" href="#/match/${esc(x.slug)}">${esc(x.match)}</a></span>
          <span class="p num">${pct(x.p)}</span><span class="why"><button class="btn" data-acca="${esc(JSON.stringify(x))}">Remove</button></span></li>`).join("")}</ul>
        <section class="hero"><p class="muted">Combined chance</p><h1 class="num">${pct(p)}</h1><p>Fair odds for the accumulator: <b class="num">${odds(p > 0 ? 1 / p : null)}</b></p>
          ${linked ? `<p class="warn">Two or more picks come from the same match. Those outcomes are linked, so the combined chance above isn't reliable: keep one pick per match.</p>` : ""}
          <p class="small muted">The combined chance multiplies each pick's chance, so every extra pick lowers it. Accumulators are much harder to win than they look.</p>
          <button class="btn" data-acca-clear>Clear all</button></section>`
        : empty("Your accumulator is empty. Add picks from Best angles or any match page.")}`;
  }

  async function pageTrack() {
    setNav("track");
    const t = await get("track.json");
    const row = (l, x) => (x && x.n ? `<tr><td>${esc(l)}</td><td class="r num">${x.n}</td><td class="r num"><b>${x.hit != null ? x.hit.toFixed(0) + "%" : "–"}</b></td><td class="r num">${x.expected != null ? x.expected.toFixed(0) + "%" : "–"}</td></tr>` : "");
    const head = `<thead><tr><th></th><th class="r">Picks</th><th class="r">Hit</th><th class="r">Expected</th></tr></thead>`;
    const live = (t.overall || {}).live || {}, rep = (t.overall || {}).replay || {};
    const per = t.by_period || {};
    app.innerHTML = `<h1>Track record</h1><p class="muted prose">Every pick is checked against the result. A good model hits about as often as it expects to: if picks rated 70% come in about 70% of the time, the probabilities are honest.</p>
      <h2>Overall</h2><div class="wrap"><table>${head}<tbody>${row("Best picks, live", live.best)}${row("Safer picks, live", live.safer)}${row("Best picks, season replay", rep.best)}${row("Safer picks, season replay", rep.safer)}</tbody></table></div>
      <h2>Over time</h2><div class="wrap"><table>${head}<tbody>${row("Last 7 days", per.last_7_days)}${row("Last 30 days", per.last_30_days)}${row("Last 12 months", per.last_365_days)}</tbody></table></div>
      ${(t.calibration || []).length ? `<h2>When we said…</h2>${t.calibration.map(c => `<div class="cal"><span class="num">${esc(c.band)}</span><span class="track"><i style="width:${Math.min(100, c.hit || 0)}%"></i><s style="left:${Math.min(100, c.expected || 0)}%"></s></span>
          <span class="num">${c.hit != null ? c.hit.toFixed(0) + "%" : "–"}</span></div>`).join("")}<p class="small muted">Bars show how often picks in each band came in; the line marks what the model expected.</p>` : ""}
      ${(t.by_competition || []).length ? `<h2>By competition</h2><div class="wrap"><table>${head}<tbody>${t.by_competition.map(c => row(c.competition, c)).join("")}</tbody></table></div>` : ""}
      ${(t.by_family || []).length ? `<h2>By market</h2><div class="wrap"><table>${head}<tbody>${t.by_family.map(c => row(c.family, c)).join("")}</tbody></table></div>` : ""}
      ${(t.recent || []).length ? `<h2>Recent picks</h2><ul class="list">${t.recent.slice(0, 40).map(x => `<li>${x.won ? '<span class="won">✓</span>' : '<span class="lost">✗</span>'} ${esc(x.pick)} <span class="num">(${pct(x.p)})</span>
          <span class="small muted">${esc(x.match)}, ${esc(x.competition)}, ${esc(x.date)}</span></li>`).join("")}</ul>` : ""}`;
    hit("track_record");
  }

  async function pageFav() {
    setNav("more");
    const favs = fav.list();
    if (!favs.length) { app.innerHTML = `<h1>Favourites</h1>` + empty("Tap ★ next to a team or league to keep it here. Favourites are saved in this browser only."); return; }
    const idx = await get("index.json");
    const set = new Set(favs);
    await getLive();
    const list = (idx.matches || []).filter(m => set.has("match:" + m.slug) || set.has("team:" + m.home_slug) || set.has("team:" + m.away_slug) || set.has("comp:" + m.league_slug));
    app.innerHTML = `<h1>Favourites</h1><p class="small muted">${favs.filter(f => !f.startsWith("match:")).map(f => `<a href="#/${f.startsWith("team:") ? "team" : "comp"}/${esc(f.split(":")[1])}">${esc(f.split(":")[1].replace(/-/g, " "))}</a>`).join(", ")}</p>
      ${list.length ? list.map(matchRow).join("") : empty("No upcoming matches for your favourites in the next few days.")}`;
  }

  function pageMore() {
    setNav("more");
    app.innerHTML = `<h1>More</h1><ul class="list">
      <li><a href="#/fav">Favourites</a></li><li><a href="#/leaders">Leaders</a></li><li><a href="#/acca">Accumulator</a></li>
      ${C.channel ? `<li><a href="${tg(C.channel)}" target="_blank" rel="noopener">Kwallo on Telegram</a>: daily picks, previews and results</li>` : ""}
      ${C.bot ? `<li><a href="${tg(C.bot)}" target="_blank" rel="noopener">Match alerts bot</a>: previews, lineups and live updates for the teams you follow</li>` : ""}
      <li><a href="#/about">About Kwallo</a></li><li><a href="#/privacy">Privacy</a></li><li><a href="#/terms">Terms</a></li></ul>`;
  }

  // ---------- v33: markets derived from the score grid (rows = home goals, columns = away goals, rescaled to 100%)
  function gridMarkets(G, H, A) {
    const tot = G.flat().reduce((s, x) => s + x, 0) || 1, P = G.map(r => r.map(x => x / tot));
    const sum = f => { let s = 0; P.forEach((r, i) => r.forEach((x, j) => { if (f(i, j)) s += x; })); return s; };
    const out = [];
    [0.5, 1.5, 2.5, 3.5, 4.5].forEach(l => { const o = sum((i, j) => i + j > l); out.push(["Total goals", `Over ${l}`, o], ["Total goals", `Under ${l}`, 1 - o]); });
    const btts = sum((i, j) => i > 0 && j > 0); out.push(["Both teams to score", "Yes", btts], ["Both teams to score", "No", 1 - btts]);
    [[H, (i, j) => i], [A, (i, j) => j]].forEach(([t, g]) => [0.5, 1.5, 2.5].forEach(l => { const o = sum((i, j) => g(i, j) > l); out.push([`${t} goals`, `Over ${l}`, o], [`${t} goals`, `Under ${l}`, 1 - o]); }));
    out.push(["Clean sheet", `${H} keep a clean sheet`, sum((i, j) => j === 0)], ["Clean sheet", `${A} keep a clean sheet`, sum((i, j) => i === 0)]);
    out.push(["Win to nil", `${H} win to nil`, sum((i, j) => i > j && j === 0)], ["Win to nil", `${A} win to nil`, sum((i, j) => j > i && i === 0)]);
    const hw = sum((i, j) => i > j), aw = sum((i, j) => j > i);
    out.push(["Draw no bet", H, hw / (hw + aw)], ["Draw no bet", A, aw / (hw + aw)]);
    out.push(["Handicap", `${H} win by 2+`, sum((i, j) => i - j >= 2)], ["Handicap", `${A} win by 2+`, sum((i, j) => j - i >= 2)]);
    out.push(["Result and both teams to score", `${H} win and both score`, sum((i, j) => i > j && j > 0)], ["Result and both teams to score", `${A} win and both score`, sum((i, j) => j > i && i > 0)]);
    const odd = sum((i, j) => (i + j) % 2 === 1); out.push(["Odd or even goals", "Odd", odd], ["Odd or even goals", "Even", 1 - odd]);
    [0, 1, 2, 3].forEach(n => out.push(["Exact total goals", `${n} goals`, sum((i, j) => i + j === n)])); out.push(["Exact total goals", "4 or more", sum((i, j) => i + j >= 4)]);
    return out;
  }
  function gridTable(G, H, A) {
    const tot = G.flat().reduce((s, x) => s + x, 0) || 1, n = Math.min(G.length, 6), mx = Math.max(...G.flat());
    const cells = [];
    G.forEach((r, i) => r.forEach((x, j) => cells.push([i, j, x / tot])));
    const top = cells.sort((a, b) => b[2] - a[2]).slice(0, 5).map(([i, j, p]) => `${i}–${j} (${pct(p)})`).join(", ");
    return `<p class="small muted">Likeliest scores: ${top}. Rows are ${esc(H)}'s goals, columns ${esc(A)}'s.</p>
      <div class="wrap"><table class="grid"><thead><tr><th>${esc(H)} \\ ${esc(A)}</th>${[...Array(n).keys()].map(j => `<th class="r">${j}</th>`).join("")}</tr></thead><tbody>
      ${G.slice(0, n).map((r, i) => `<tr><th>${i}</th>${r.slice(0, n).map(x => `<td class="r num" style="--a:${(x / mx).toFixed(2)}">${(100 * x / tot).toFixed(1)}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`;
  }
  function lastSeven(t, name) {                                     // a team's last 7 matches, form and spotted trends
    if (!t || !(t.rows || []).length) return "";
    const rows = t.rows.slice(-7).reverse();
    return `<h3>${esc(name)} ${formChips((t.form || "").slice(-7))}${t.ppg != null ? ` <span class="small muted">${Number(t.ppg).toFixed(2)} points per game</span>` : ""}</h3>
      <div class="wrap"><table><thead><tr><th>Date</th><th></th><th>Opponent</th><th class="r">Score</th><th class="r">xG</th></tr></thead><tbody>
      ${rows.map(r => `<tr ${r.espn ? `class="click" data-go="${resultHref(r.espn)}"` : ""}><td class="num small">${esc(String(r.Date).slice(5))}</td><td class="small muted">${r.Venue === "H" ? "home" : "away"}</td><td>${r.espn ? `<a href="${resultHref(r.espn)}">${esc(r.Opponent)}</a>` : esc(r.Opponent)} <span class="small muted">${esc(r.Comp || "")}</span></td>
        <td class="r num">${formChips(r.Result)} ${esc(r.Score)}</td><td class="r num small">${esc(r.xG || "–")}</td></tr>`).join("")}</tbody></table></div>
      ${rows.some(r => !r.xG) ? `<p class="small muted">xG shows "–" where no source covers that match (some cup and European ties, and leagues without xG data).</p>` : ""}
      ${rows.some(r => r.espn) ? `<p class="small muted">Tap a match for its full statistics.</p>` : ""}
      ${(t.spotted || []).length ? `<ul class="list small">${t.spotted.slice(0, 5).map(s => `<li>${esc(typeof s === "string" ? s : (s.pattern ? `${s.pattern}: ${s.count} of the last ${s.of}${s.base != null ? `, league usually ${pct(s.base)}` : ""}` : JSON.stringify(s)))}</li>`).join("")}</ul>` : ""}`;
  }
  const POS = [["G", "Goalkeeper"], ["D", "Defenders"], ["M", "Midfielders"], ["F", "Forwards"]];
  const posDepth = pos => { const c = String(pos || "").toUpperCase().trim(), b = c.split("-")[0];   // v35: how far forward a position plays
    if (["G", "GK"].includes(b)) return 0;
    if (["CB", "CD", "SW", "LCB", "RCB", "D", "DF"].includes(b)) return 1;
    if (["LB", "RB"].includes(b)) return 1.1;
    if (["LWB", "RWB", "WB"].includes(b)) return 1.6;
    if (["DM", "CDM"].includes(b)) return 2;
    if (["CM", "LCM", "RCM", "M", "MF"].includes(b)) return 2.5;
    if (["LM", "RM"].includes(b)) return 2.6;
    if (["AM", "CAM", "LAM", "RAM"].includes(b)) return 3.2;
    if (["LW", "RW", "W"].includes(b)) return 3.4;
    if (b === "CF" && /-[LR]$/.test(c)) return 3.6;
    if (["F", "FW", "ST", "CF", "S", "SS", "LF", "RF"].includes(b)) return 4;
    return 2.5; };
  // v34: the lineup on a pitch. Home in the bottom half, away in the top half; each line ordered left to right by position code
  const sideRank = pos => { const c = String(pos || "").toUpperCase().trim();      // wide left 0, left of centre 1, centre 2, right of centre 3, wide right 4
    if (/-L$/.test(c)) return 1; if (/-R$/.test(c)) return 3; if (/^L/.test(c)) return 0; if (/^R/.test(c)) return 4; return 2; };
  // v35: the away side plays downwards from the top, so its left flank is on the right of the screen (mirrored);
  //      every player links to his page
  function pitchSVG(home, away, H, A, cHome, cAway, hs, as) {
    const W = 340, Hh = 520;
    // v35: drawn in the team's formation (e.g. 3-4-2-1 = back three, four, two attacking midfielders, one striker): outfield players are
    //      ordered from deepest to most advanced by their usual position and dealt into the formation's rows. Without a formation, by line,
    //      with ESPN's CF-L / CF-R beside a central striker counted as attacking midfielders.
    const lines = (e, mirror) => {
      const ps = (e && e.ours) || [], rk = p => (mirror ? 4 - sideRank(p.Pos) : sideRank(p.Pos));
      const gk = ps.filter(p => (p.Line || posLine(p.Pos)) === "G"), out = ps.filter(p => !gk.includes(p));
      const f = String((e && e.formation) || "").split("-").map(Number);
      let rows;
      if (f.length >= 2 && f.every(n => n > 0) && f.reduce((a, b) => a + b, 0) === out.length) {
        const sorted = out.map((p, i) => ({ p, i })).sort((a, b) => posDepth(a.p.Pos) - posDepth(b.p.Pos) || a.i - b.i).map(x => x.p);
        let k = 0; rows = f.map(n => sorted.slice(k, (k += n)));
      } else {
        const hasNine = out.some(p => /^(F|CF|ST|FW)$/i.test(String(p.Pos || "").trim()));
        const ln = p => (hasNine && /^CF-[LR]$/i.test(String(p.Pos || "").trim())) ? "M" : (p.Line || posLine(p.Pos));
        rows = ["D", "M", "F"].map(k => out.filter(p => ln(p) === k)).filter(r => r.length);
      }
      rows = [gk, ...rows].map(r => r.slice().sort((x, y) => rk(x) - rk(y)));
      return { rows, label: f.length >= 2 && f.every(n => n > 0) && f.reduce((a, b) => a + b, 0) === out.length ? f.join("-") : rows.slice(1).map(r => r.length).join("-") };
    };
    const formation = g => g.label;
    const dots = (g, top, color, ts) => {
      const n = g.rows.length - 1, ys = [34, ...[...Array(n)].map((_, i) => n === 1 ? 160 : 90 + (i * (230 - 90)) / (n - 1))];
      return g.rows.map((row, r) => row.map((p, i, arr) => { const x = (W / (arr.length + 1)) * (i + 1), y = Math.round(top ? ys[r] : Hh - ys[r]), op = p.p != null ? Math.max(0.35, Math.min(1, p.p)) : 1;
        const sur = String(p.Player || "").split(" ").slice(-1)[0];
        return `<a href="${playerHref(ts, p.Player, p.id)}" aria-label="${esc(p.Player)}"><g opacity="${op.toFixed(2)}"><circle cx="${x.toFixed(1)}" cy="${y}" r="13" fill="${color}" stroke="#fff" stroke-width="1.5"/>
          <text x="${x.toFixed(1)}" y="${y + 27}" text-anchor="middle" class="pn">${esc(sur.slice(0, 12))}</text>
          ${p.p != null && p.p < 0.995 ? `<text x="${x.toFixed(1)}" y="${y + 4}" text-anchor="middle" class="pp">${Math.round(100 * p.p)}</text>` : ""}</g></a>`; }).join("")).join("");
    };
    const gh = lines(home, false), ga = lines(away, true);
    return `<figure class="pitchfig"><figcaption class="small"><span><b>${esc(A)}</b> ${formation(ga) ? `(${formation(ga)})` : ""}</span></figcaption>
      <svg viewBox="0 0 ${W} ${Hh}" role="img" aria-label="Lineups on the pitch: ${esc(H)} ${formation(gh)}, ${esc(A)} ${formation(ga)}">
        <rect x="1" y="1" width="${W - 2}" height="${Hh - 2}" rx="10" class="turf"/>
        <g class="lines" fill="none"><line x1="1" y1="${Hh / 2}" x2="${W - 1}" y2="${Hh / 2}"/><circle cx="${W / 2}" cy="${Hh / 2}" r="42"/>
          <rect x="${W / 2 - 80}" y="1" width="160" height="62"/><rect x="${W / 2 - 80}" y="${Hh - 63}" width="160" height="62"/>
          <rect x="${W / 2 - 34}" y="1" width="68" height="22"/><rect x="${W / 2 - 34}" y="${Hh - 23}" width="68" height="22"/></g>
        ${dots(ga, true, cAway || "#6F8F84", as)}${dots(gh, false, cHome || "#2E8F6A", hs)}
      </svg><figcaption class="small"><span><b>${esc(H)}</b> ${formation(gh) ? `(${formation(gh)})` : ""}</span></figcaption></figure>`;
  }
  function xiByPosition(e, ts) {
    const list = (e && e.ours) || [], groups = {};
    const lineOf = pos => { const b = String(pos || "").toUpperCase().trim().split("-")[0];
      if (["G", "GK"].includes(b)) return "G";
      if (["D", "DF", "CB", "CD", "LCB", "RCB", "LB", "RB", "LWB", "RWB", "WB", "SW"].includes(b)) return "D";
      if (["M", "MF", "DM", "CDM", "CM", "LCM", "RCM", "LM", "RM", "AM", "CAM", "LAM", "RAM"].includes(b)) return "M";
      if (["F", "FW", "S", "ST", "CF", "LF", "RF", "LW", "RW", "SS", "W"].includes(b)) return "F";
      return "GDMF".includes(b[0]) && b[0] ? b[0] : "M"; };
    list.forEach(p => { const k = p.Line || lineOf(p.Pos); (groups[k] = groups[k] || []).push(p); });
    return POS.filter(([k]) => groups[k]).map(([k, lab]) => `<div class="pos"><span class="small muted">${lab}</span>${groups[k].map(p => `<a class="pl" href="${playerHref(ts, p.Player, p.id)}">${esc(p.Player)}${p.p != null && !e.confirmed ? ` <span class="num small muted">${pct(p.p)}</span>` : ""}</a>`).join("")}</div>`).join("")
      + (Object.keys(groups).some(k => !POS.some(([x]) => x === k)) ? `<div class="pos"><span class="small muted">Other</span>${Object.entries(groups).filter(([k]) => !POS.some(([x]) => x === k)).flatMap(([, v]) => v).map(p => `<a class="pl" href="${playerHref(ts, p.Player, p.id)}">${esc(p.Player)}</a>`).join("")}</div>` : "");
  }

  const TEXT = {
    about: `<h1>About Kwallo</h1><div class="prose"><p>Kwallo means "ball" in Hausa. We build football predictions that say exactly how likely each outcome is, and then check ourselves in public.</p>
      <p>Every match gets probabilities from a statistical model of team strength, expected goals, lineups and form, tested week by week against real results. Fair odds are the break-even price: a pick is only worth taking when you're offered more.</p>
      <p>Every market is tested before we call it trusted, and our <a href="#/track">track record</a> shows how often our picks come in compared with what we expected.</p>
      <p>Kwallo is for information and entertainment. We don't take bets and we don't promote bookmakers. If you bet, be 18 or over, set a limit, and never chase losses.</p>
      <p>Contact: ${C.contact ? `<a href="mailto:${esc(C.contact)}">${esc(C.contact)}</a>` : "by Telegram"}.</p></div>`,
    privacy: `<h1>Privacy</h1><div class="prose"><p><i>Draft, to be reviewed before launch.</i></p>
      <p>This website has no accounts and sets no cookies. Your favourites and accumulator are stored only in your own browser, and you can clear them at any time.</p>
      <p>We count visits and feature use in total (for example, how many times match pages were opened) using privacy-friendly analytics that don't identify you.</p>
      <p>If you use our Telegram bot, we store only your Telegram chat ID and the teams, leagues and alert types you choose. Send /stop to the bot to delete them.</p>
      <p>Questions or requests: ${C.contact ? esc(C.contact) : "contact us on Telegram"}.</p></div>`,
    terms: `<h1>Terms</h1><div class="prose"><p><i>Draft, to be reviewed before launch.</i></p>
      <p>Kwallo provides statistical predictions for information and entertainment. Probabilities are estimates, not guarantees, and past results don't predict future ones.</p>
      <p>Nothing on Kwallo is betting advice or an offer of a bet. You are responsible for your own decisions. Betting is for adults (18+) only, where it's legal.</p>
      <p>Match data comes from third-party sources and may occasionally be wrong or delayed.</p></div>`,
  };

  // ---------- router
  let afterRender = null;                                           // v35: a page's follow-up once it's on screen (the match page's tabs)
  async function route(keepScroll) {
    const my = ++routeSeq;
    afterRender = null;
    app = document.createElement("div");
    const parts = (location.hash.replace(/^#\/?/, "") || "").split("/").map(decodeURIComponent);
    if (!keepScroll) try { window.scrollTo(0, 0); } catch (e) {}
    try {
      switch (parts[0]) {
        case "": await pageToday(); break;
        case "day": await pageToday(parts[1], parts[2]); break;
        case "leagues": await pageLeagues(); break;
        case "comp": await pageComp(parts[1], parts[2], parts[3]); break;
        case "leaders": await pageLeadersPicker(); break;
        case "match": await pageMatch(parts[1], parts[2]); break;
        case "team": await pageTeam(parts[1]); break;
        case "player": await pagePlayer(parts[1], parts[2]); break;
        case "pf": await pageFindPlayer(parts[1], parts[2], parts[3]); break;          // v35
        case "result": await pageResult(parts[1], parts[2]); break;                    // v35 (date: to show Kwallo's prediction)
        case "angles": await pageAngles(); break;
        case "acca": pageAcca(); break;
        case "track": await pageTrack(); break;
        case "fav": await pageFav(); break;
        case "more": pageMore(); break;
        case "about": case "privacy": case "terms": setNav("more"); app.innerHTML = TEXT[parts[0]]; break;
        default: app.innerHTML = `<h1>Page not found</h1>${empty('That page doesn\'t exist. <a href="#/">Go to today\'s matches</a>.')}`;
      }
    } catch (e) {
      app.innerHTML = `<h1>Couldn't load this page</h1>${empty(`The data didn't arrive (${esc(e.message)}). Check your connection and <a href="${esc(location.hash || "#/")}">try again</a>.`)}`;
    }
    if (my === routeSeq) { shell.innerHTML = app.innerHTML; try { shell.focus({ preventScroll: true }); } catch (e) {}   // a newer page won: drop this one
      app = shell;
      if (afterRender) { const f = afterRender; afterRender = null; try { f(); } catch (e) {} } }
    app = shell;
  }

  // ---------- one listener for every button
  document.addEventListener("click", ev => {
    const tabA = ev.target.closest(".mtabs a[data-k]");               // v35: match tabs switch in place
    if (tabA && !ev.metaKey && !ev.ctrlKey) { ev.preventDefault(); showTab(tabA.dataset.k, true); return; }
    const ps = ev.target.closest("th[data-psort]");                  // v35: sort a team's players
    if (ps) { const el = ps.closest("[data-team-players]"), st = PT[el.dataset.teamPlayers]; if (st) { st.dir = st.key === ps.dataset.psort ? -st.dir : -1; st.key = ps.dataset.psort; renderPlayers(el); } return; }
    const ls = ev.target.closest("[data-lside]");                    // v35: home / away lineup switch
    if (ls) { const box = ls.closest("[data-lineups-live]") || shell; box.querySelectorAll("[data-lside]").forEach(b => b.classList.toggle("on", b === ls));
      box.querySelectorAll("[data-lblock]").forEach(b => { b.hidden = b.dataset.lblock !== ls.dataset.lside; }); return; }
    const per = ev.target.closest("[data-period]");                  // v35: All / 1st / 2nd on the stats card
    if (per) { const card = per.closest(".statscard"); card.querySelectorAll("[data-period]").forEach(b => { const on = b === per; b.classList.toggle("on", on); b.setAttribute("aria-selected", String(on)); });
      card.querySelectorAll("[data-pblock]").forEach(x => { x.hidden = x.dataset.pblock !== per.dataset.period; }); return; }
    const jump = ev.target.closest("[data-jump]");                   // v35: in-page headings (player page)
    if (jump) { ev.preventDefault(); const t = document.getElementById(jump.dataset.jump); if (t) t.scrollIntoView({ behavior: "smooth", block: "start" }); return; }
    const th = ev.target.closest("th[data-sort]");
    if (th) {
      const [slug, k, mode] = th.dataset.sort.split("|");
      const cur = store.get("leaders_sort2:" + slug, null);
      store.set("leaders_sort2:" + slug, [k, mode, cur && cur[0] === k && cur[1] === mode ? -cur[2] : -1]);
      hit("leaders_sort"); route(); return;
    }
    const el = ev.target.closest("[data-go],[data-fav],[data-acca],[data-acca-clear],[data-fold]");
    if (!el) return;
    if (el.dataset.go) { location.hash = el.dataset.go; return; }
    ev.preventDefault(); ev.stopPropagation();
    if (el.dataset.followMatch) {
      const was = fav.has("match:" + el.dataset.followMatch);
      if (!was) fav.toggle("match:" + el.dataset.followMatch);
      el.classList.add("added"); el.textContent = "★ Following this match";
      if (C.bot) window.open(tg(C.bot + "?start=match_" + encodeURIComponent(el.dataset.followMatch)), "_blank", "noopener");
      return;
    }
    if (el.dataset.fold) {                                           // fold or unfold a competition card (remembered)
      const card = el.closest(".card"), isF = !card.classList.contains("folded");
      card.classList.toggle("folded", isF); el.setAttribute("aria-expanded", String(!isF)); store.set("fold:" + el.dataset.fold, isF);
      if (!isF) card.querySelectorAll("[data-lg]").forEach(fillLeague);
      return;
    }
    if (el.dataset.fav) { fav.toggle(el.dataset.fav); const on = fav.has(el.dataset.fav);
      document.querySelectorAll(`[data-fav="${CSS.escape(el.dataset.fav)}"]`).forEach(s => s.classList.toggle("on", on)); return; }
    if (el.hasAttribute("data-acca-clear")) { acca.clear(); route(); return; }
    if (el.dataset.acca) {
      acca.toggle(JSON.parse(el.dataset.acca));
      if (location.hash.startsWith("#/acca")) route();
      else { el.classList.toggle("added"); el.textContent = el.classList.contains("added") ? "✓ In acca" : "+ Acca"; }
    }
  });
  document.addEventListener("change", ev => {
    const el = ev.target;
    if (el.matches("[data-leaders-sort]")) {
      const avg = /rating|percent|accuracy|pct/.test(el.value);
      store.set("leaders_sort2:" + el.dataset.leadersSort, [el.value, el.value === "minutes" || avg ? "total" : "p90", -1]); route(); hit("leaders_sort");
    }
    if (el.matches("[data-leaders-min]")) { store.set("leaders_min", Number(el.value)); route(); }
    if (el.matches("[data-datepick]") && /^\d{4}-\d{2}-\d{2}$/.test(el.value)) { hit("date_picker"); location.hash = `#/day/${el.value}/all`; }   // v35
  });
  document.querySelectorAll(".tg-channel").forEach(x => { if (C.channel) x.href = tg(C.channel); else x.remove(); });
  document.querySelectorAll(".tg-bot").forEach(x => { if (C.bot) x.href = tg(C.bot); else x.remove(); });
  if (C.cfAnalyticsToken) {                                       // Cloudflare Web Analytics: cookie-free visitor counts
    const s = document.createElement("script");
    s.defer = true; s.src = "https://static.cloudflareinsights.com/beacon.min.js"; s.setAttribute("data-cf-beacon", JSON.stringify({ token: C.cfAnalyticsToken }));
    document.head.appendChild(s);
  }
  // ---------- v35: swipes. From the middle of the screen: the next / previous match tab. From the screen's edge: back to today's matches.
  // Tables that scroll sideways keep their own swipe. (On phones the browser's own edge-swipe "back" may come first.)
  (function swipes() {
    let sx = 0, sy = 0, st = 0, edge = false, ok = false;
    const scrollsX = el => { for (; el && el !== document.body; el = el.parentElement) {
      if (el.scrollWidth > el.clientWidth + 4 && /auto|scroll/.test(getComputedStyle(el).overflowX)) return true; } return false; };
    document.addEventListener("touchstart", e => {
      if (e.touches.length !== 1) { ok = false; return; }
      const t = e.touches[0]; sx = t.clientX; sy = t.clientY; st = Date.now();
      edge = sx < 28 || sx > window.innerWidth - 28; ok = edge || !scrollsX(e.target);
    }, { passive: true });
    document.addEventListener("touchend", e => {
      if (!ok) return; ok = false;
      const t = e.changedTouches[0], dx = t.clientX - sx, dy = t.clientY - sy;
      if (Date.now() - st > 700 || Math.abs(dx) < 70 || Math.abs(dx) < 1.6 * Math.abs(dy)) return;
      const h = location.hash || "#/";
      if (edge) { if (h !== "#/") { hit("swipe_home"); location.hash = "#/"; } return; }
      if (!/^#\/match\//.test(h)) return;
      const tabs = [...shell.querySelectorAll(".mtabs a[data-k]")];          // v35: counted from the tab on screen
      const cur = tabs.findIndex(a => a.classList.contains("on")), nx = cur + (dx < 0 ? 1 : -1);
      if (cur >= 0 && nx >= 0 && nx < tabs.length) { hit("swipe_tab"); showTab(tabs[nx].dataset.k, true); }
    }, { passive: true });
  })();
  window.addEventListener("hashchange", route);
  setInterval(async () => {
    const h = location.hash || "#/";
    if (!(h === "#/" || h.startsWith("#/day/") || h.startsWith("#/fav") || h.startsWith("#/match/")) || document.hidden) return;
    const before = JSON.stringify(LIVE); await getLive(true);
    if (JSON.stringify(LIVE) !== before) { const y = window.scrollY; await route(true); try { window.scrollTo(0, y); } catch (e) {} }
  }, 60000);
  showAccaCount();
  route();
})();

// Kwallo web app (v32). Reads the pipeline's public files through the Worker; no accounts, no cookies.
(function () {
  "use strict";
  const C = window.KWALLO || {};
  const API = C.api || "/api/site/";
  const shell = document.getElementById("app");
  let app = shell, routeSeq = 0;                                     // pages render off-screen; only the latest request is shown
  const cache = {};
  const BIG = ["Premier League", "La Liga", "Bundesliga", "Serie A", "Ligue 1", "Champions League", "Europa League", "Conference League"];
  const EUROPE_CUPS = ["Champions League", "Europa League", "Conference League"];

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
  const timeOf = m => (m.kickoff ? new Date(m.kickoff).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "–");
  const fmtSeason = s => { s = String(s || ""); return /^\d{4}$/.test(s) && !/^(19|20)\d{2}$/.test(s) ? `20${s.slice(0, 2)}/${s.slice(2)}` : s; };
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
    return `<a class="match" href="#/match/${esc(m.slug)}">
      <div class="row"><span class="num muted" ${m.kickoff ? "" : 'title="Kickoff time not announced yet"'}>${esc(timeOf(m))}</span>
        <span class="teams"><span class="team">${esc(m.Home)}${teamStar(m.home_slug, m.Home)}</span> <span class="muted">v</span> <span class="team">${esc(m.Away)}${teamStar(m.away_slug, m.Away)}</span></span><span></span></div>
      ${chanceBar(m, [m.Home, m.Away])}
      <div class="bar-legend num"><span>${pct(m.pH)}</span><span>draw ${pct(m.pD)}</span><span>${pct(m.pA)}</span></div>
      ${m.top_pick ? `<div class="pick">Top angle: <b>${esc(m.top_pick.Bet)}</b>, ${pct(m.top_pick.p)}, fair ${odds(m.top_pick.fair)}</div>` : ""}
    </a>`;
  }
  const selId = (slug, bet) => `${slug}|${bet}`;
  function accaBtn(sel) { return `<button class="btn mini ${acca.has(sel.id) ? "added" : ""}" data-acca="${esc(JSON.stringify(sel))}" aria-label="${acca.has(sel.id) ? "Remove from" : "Add to"} accumulator">${acca.has(sel.id) ? "✓ In acca" : "+ Acca"}</button>`; }
  function alertsLink(slug, label) {
    return C.bot ? `<a class="btn solid cta-tg" href="${tg(C.bot + "?start=team_" + encodeURIComponent(slug))}" target="_blank" rel="noopener">${esc(label)}</a>` : "";
  }
  function formChips(form) { return `<span class="form">${String(form || "").split("").filter(r => "WDL".includes(r)).map(r => `<b class="${r}">${r}</b>`).join("")}</span>`; }
  const empty = msg => `<p class="empty">${msg}</p>`;
  function setNav(name) { document.querySelectorAll("[data-nav]").forEach(a => a.classList.toggle("on", a.dataset.nav === name)); }

  // ---------- pages
  async function pageToday(day, filter) {
    setNav("today");
    const idx = await get("index.json");
    const ms = idx.matches || [];
    const days = [...new Set(ms.map(matchDay))].sort();
    if (!days.length) { app.innerHTML = `<h1>Today</h1>` + empty("No fixtures in the next few days. New fixtures appear after the morning update."); return; }
    const today = localDay(Date.now());
    day = day && days.includes(day) ? day : (days.includes(today) ? today : days[0]);
    filter = filter || "all";
    const favs = new Set(fav.list());
    let list = ms.filter(m => matchDay(m) === day);
    if (filter === "big") list = list.filter(m => BIG.includes(m.Competition));
    if (filter === "europe") list = list.filter(m => EUROPE_CUPS.includes(m.Competition));
    if (filter === "nigeria") list = list.filter(m => /NPFL/.test(m.Competition));
    if (filter === "fav") list = list.filter(m => favs.has("team:" + m.home_slug) || favs.has("team:" + m.away_slug) || favs.has("comp:" + m.league_slug));
    const groups = {};
    list.sort((a, b) => (a.kickoff || "").localeCompare(b.kickoff || "")).forEach(m => (groups[m.Competition] = groups[m.Competition] || []).push(m));
    const rank = c => (BIG.indexOf(c) + 1) || 99;
    const order = Object.keys(groups).sort((a, b) => rank(a) - rank(b) || a.localeCompare(b));
    const f = (k, l) => `<button class="chip ${filter === k ? "on" : ""}" data-go="#/day/${day}/${k}">${l}</button>`;
    app.innerHTML = `<h1>${esc(dayLabel(day))}</h1><p class="muted">${esc(longDate(day))}. ${list.length} match${list.length === 1 ? "" : "es"}.</p>
      <div class="tabs" role="tablist">${days.map(d => `<button class="${d === day ? "on" : ""}" data-go="#/day/${d}/${filter}">${esc(dayLabel(d))}</button>`).join("")}</div>
      <div class="tabs">${f("all", "All")}${f("big", "Big games")}${f("europe", "Europe")}${f("nigeria", "Nigeria")}${f("fav", "★ Favourites")}</div>
      ${order.length ? order.map(c => `<section class="group"><h3><span>${esc(c)}</span><span>${groups[c].length}</span></h3>${groups[c].map(matchRow).join("")}</section>`).join("")
        : empty(filter === "fav" ? "None of your favourites play on this day. Tap ★ next to a match to follow a team." : "No matches for this filter on this day.")}
      <p class="small muted">Updated ${idx.meta && idx.meta.updated ? esc(new Date(idx.meta.updated).toLocaleString()) : "recently"}. Chances are the model's; fair odds are the break-even price.</p>`;
  }

  async function pageLeagues() {
    setNav("leagues");
    const comps = await get("competitions.json");
    const groups = {};
    comps.forEach(c => (groups[c.group_name || "Other"] = groups[c.group_name || "Other"] || []).push(c));
    app.innerHTML = `<h1>Leagues</h1><p><a href="#/leaders">Player leaders by competition</a></p>` + Object.entries(groups).map(([g, cs]) => `<section class="group"><h3><span>${esc(g)}</span></h3>
      <ul class="list">${cs.map(c => `<li><a href="#/comp/${esc(c.slug)}">${esc(c.name)}</a> <button class="star ${fav.has("comp:" + c.slug) ? "on" : ""}" data-fav="comp:${esc(c.slug)}" aria-label="Favourite ${esc(c.name)}">★</button>
        <span class="small muted">${c.upcoming ? `${c.upcoming} upcoming` : ""}</span></li>`).join("")}</ul></section>`).join("");
  }

  async function pageComp(slug, tab, round) {
    setNav("leagues");
    let c;
    try { c = await get(`comp/${slug}.json`); }
    catch (e) { if (tab !== "leaders") throw e; c = { name: slug.replace(/-/g, " "), rounds: [], table: [] }; }   // leaders-only competitions
    tab = tab || "matches";
    const rounds = c.rounds || [];
    const cur = round ? Number(round) : c.current_round || (rounds.length ? rounds[rounds.length - 1].round : null);
    const t = (k, l) => `<button class="${tab === k ? "on" : ""}" data-go="#/comp/${slug}/${k}">${l}</button>`;
    let body = "";
    if (tab === "matches") {
      const r = rounds.find(x => x.round === cur) || rounds[rounds.length - 1];
      body = r ? `<div class="tabs">${rounds.map(x => `<button class="${x.round === r.round ? "on" : ""}" data-go="#/comp/${slug}/matches/${x.round}" aria-label="Matchday ${x.round}">${x.round}</button>`).join("")}</div>
        <h2>Matchday ${r.round}</h2><ul class="list">${r.matches.map(m => `<li class="num">${esc(m.date)}:
          <a href="#/team/${esc(m.home_slug)}">${esc(m.home)}</a>${teamStar(m.home_slug, m.home)} ${m.played ? `<b>${esc(m.score)}</b>` : "v"} <a href="#/team/${esc(m.away_slug)}">${esc(m.away)}</a>${teamStar(m.away_slug, m.away)}
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
    const isAvg = k => { const l = labels[k] || {}; return ["double", "percent", "rating"].includes(l.type) || /rating|percent|accuracy|pct/.test(k); };   // averages: no per-90 or total
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

  async function pageMatch(slug) {
    setNav("today");
    const d = await get(`match/${slug}.json`);
    const m = d.match || {}, v = d.verdict || {};
    const H = m.Home, A = m.Away;
    const hs = m.home_slug || "", as = m.away_slug || "";
    const sel = (bet, p, fair) => ({ id: selId(slug, bet), match: `${H} v ${A}`, slug, bet, p, fair });
    const fairOf = p => (p ? 1 / p : null);
    const extra = [["Both teams to score", m.pBTTS], ["Over 2.5 goals", m.pOver25], ["Over the corners line", m.pOverCorners], ["Over the cards line", m.pOverCards]].filter(x => x[1] != null);
    const markets = (d.markets || []).slice().sort((a, b) => b.p - a.p);
    const fam = {};
    markets.forEach(x => (fam[x.family || "other"] = fam[x.family || "other"] || []).push(x));
    const xiSide = s => { const e = (d.expected_xi || {})[s] || {}; return (e.ours || []).map(p => `<li>${esc(p.Player)} <span class="small muted">${esc(p.Pos || "")}</span>
        <span class="num small muted">${p.p != null && !e.confirmed ? pct(p.p) : ""}</span></li>`).join(""); };
    const xi = ((((d.expected_xi || {}).home) || {}).ours || []).length;
    const confirmed = !!(((d.expected_xi || {}).home) || {}).confirmed;
    app.innerHTML = `<section class="hero big">
        <p class="meta">${esc(m.Competition)}, ${esc(longDate(m.Date))}${m.kickoff ? `, ${esc(timeOf(m))}` : ""}</p>
        <h1>${esc(H)} v ${esc(A)}</h1>
        ${chanceBar(m, [H, A])}
        <div class="bar-legend num"><span><b>${pct(m.pH)}</b>${esc(H)}, fair ${odds(fairOf(m.pH))}</span><span><b>${pct(m.pD)}</b>Draw, fair ${odds(fairOf(m.pD))}</span>
          <span style="text-align:right"><b>${pct(m.pA)}</b>${esc(A)}, fair ${odds(fairOf(m.pA))}</span></div>
        ${m.ExpHome != null ? `<p class="muted">Expected goals: ${esc(H)} ${Number(m.ExpHome).toFixed(2)}, ${esc(A)} ${Number(m.ExpAway).toFixed(2)}.</p>` : ""}
        <p>${hs ? alertsLink(hs, `Get alerts for ${H}`) : ""} ${as ? alertsLink(as, `Get alerts for ${A}`) : ""}</p>
      </section>
      ${v.best && v.best.length ? `<section class="section"><h2>Verdict</h2><ul class="list">${v.best.map(b => `<li class="angle"><span><b>${esc(b.Bet)}</b><br><span class="small muted">Fair odds ${odds(b.fair)}</span></span>
          <span class="side"><span class="p num">${pct(b.p)}</span>${accaBtn(sel(b.Bet, b.p, b.fair))}</span><span class="why">${esc((b.reasons || []).join(" ") || b.evidence || "")}</span></li>`).join("")}
        ${v.safer ? `<li class="angle"><span>Safer angle: <b>${esc(v.safer.Bet)}</b><br><span class="small muted">Fair odds ${odds(v.safer.fair)}</span></span>
          <span class="side"><span class="p num">${pct(v.safer.p)}</span>${accaBtn(sel(v.safer.Bet, v.safer.p, v.safer.fair))}</span></li>` : ""}</ul>
        ${(v.avoid || []).length ? `<p class="small"><b>Avoid:</b> ${v.avoid.map(esc).join(" ")}</p>` : ""}</section>` : ""}
      ${extra.length ? `<section class="section"><h2>Goals, corners and cards</h2><ul class="list">${extra.map(([n, p]) => `<li class="angle"><span>${esc(n)}<br><span class="small muted">Fair odds ${odds(1 / p)}</span></span><span class="p num">${pct(p)}</span></li>`).join("")}</ul></section>` : ""}
      ${markets.length ? `<section class="section"><h2>More markets</h2>${Object.entries(fam).map(([f, xs]) => `<h3>${esc(f.replace(/_/g, " ").replace(/^./, c => c.toUpperCase()))}</h3><div class="wrap"><table><tbody>
          ${xs.map(x => `<tr><td>${esc(x.Bet)} <span class="tag ${x.trusted ? "trusted" : ""}">${x.trusted ? "trusted" : "experimental"}</span></td><td class="r num">${pct(x.p)}</td><td class="r num">${odds(x.fair)}</td>
            <td class="r">${accaBtn(sel(x.Bet, x.p, x.fair))}</td></tr>`).join("")}</tbody></table></div>`).join("")}
          <p class="small muted">Trusted markets have passed their calibration test; experimental ones are still being tested.</p></section>` : ""}
      ${xi ? `<section class="section"><h2>${confirmed ? "Lineups" : "Expected lineups"}</h2><div class="stat-grid" style="grid-template-columns:1fr 1fr">
          <div style="display:block"><h3>${esc(H)}</h3><ul class="list">${xiSide("home")}</ul></div><div style="display:block"><h3>${esc(A)}</h3><ul class="list">${xiSide("away")}</ul></div></div>
          <p class="small muted">${confirmed ? "Official lineups." : "Percentages are each player's chance of starting."}</p></section>` : ""}
      ${d.last_time && (d.last_time.home || d.last_time.away) ? `<section class="section"><h2>Last time out</h2>${["home", "away"].map(s => { const lt = d.last_time[s]; if (!lt || !(lt.picks || []).length) return "";
          return `<h3>${esc(s === "home" ? H : A)}${lt.match ? `: ${esc(lt.match)} ${esc(lt.score || "")}` : ""}</h3><ul class="list">${lt.picks.map(p => `<li>${p.won ? '<span class="won">✓</span>' : '<span class="lost">✗</span>'} ${esc(p.Bet)} (${pct(p.p)})</li>`).join("")}</ul>`; }).join("")}</section>` : ""}
      <p class="small muted">Probabilities are the model's, not guarantees. A pick is only worth taking above its fair odds. 18+.</p>`;
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
      ${(t.players || []).length ? `<h2>Squad</h2><div class="wrap"><table><thead><tr><th>Player</th><th class="r">Matches</th><th class="r">Minutes</th><th class="r">Rating</th></tr></thead><tbody>
          ${t.players.map(p => `<tr><td><a href="#/player/${esc(p.slug)}">${esc(p.name)}</a></td><td class="r num">${p.matches || 0}</td><td class="r num">${p.minutes || 0}</td><td class="r num">${p.rating ? Number(p.rating).toFixed(1) : "–"}</td></tr>`).join("")}</tbody></table></div>` : ""}`;
    hit("team");
  }

  async function pagePlayer(slug) {
    setNav("leagues");
    const p = await get(`player/${slug}.json`);
    const labels = p.labels || {};
    const sections = {};
    Object.entries(p.stats || {}).forEach(([k, v]) => { const l = labels[k] || { label: k, section: "Other" }; (sections[l.section || "Other"] = sections[l.section || "Other"] || []).push({ k, l, v }); });
    const val = v => (v && typeof v === "object" ? v : { total: v });
    const n1 = x => (x != null && isFinite(x) ? Math.round(x * 10) / 10 : "–"), n2 = x => (x != null && isFinite(x) ? Number(x).toFixed(2) : "–");
    app.innerHTML = `<h1>${esc(p.name)}</h1>
      <p class="muted"><a href="#/team/${esc(p.team_slug)}">${esc(p.team)}</a>${p.position ? `, ${esc(p.position)}` : ""}. ${p.matches || 0} matches, ${p.minutes || 0} minutes this season.</p>
      ${Object.entries(sections).map(([s, xs]) => `<h2>${esc(s)}</h2><div class="wrap"><table><thead><tr><th>Statistic</th><th class="r">Total</th><th class="r">Per 90</th><th class="r">Per match</th></tr></thead><tbody>
        ${xs.sort((a, b) => (a.l.order || 0) - (b.l.order || 0)).map(({ l, v }) => { const x = val(v); return `<tr><td>${esc(l.label || "")}</td><td class="r num">${n1(x.total)}</td>
          <td class="r num">${n2(x.per90)}</td><td class="r num">${n2(x.per_match)}</td></tr>`; }).join("")}</tbody></table></div>`).join("")}
      ${(p.log || []).length ? `<h2>Recent matches</h2><ul class="list">${p.log.slice().reverse().map(g => `<li class="num">${esc(g.date)}: ${esc(g.competition || "")} ${g.started ? "" : "(sub)"}
          <span class="small muted">${Object.entries(g.stats || {}).slice(0, 6).map(([k, x]) => `${esc((labels[k] || {}).label || k)} ${esc(x)}`).join(", ")}</span></li>`).join("")}</ul>` : ""}
      <p class="small muted">Source: ${esc(p.source === "pitchapi" ? "full match statistics" : "match reports")}.</p>`;
    hit("player");
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
    const list = (idx.matches || []).filter(m => set.has("team:" + m.home_slug) || set.has("team:" + m.away_slug) || set.has("comp:" + m.league_slug));
    app.innerHTML = `<h1>Favourites</h1><p class="small muted">${favs.map(f => `<a href="#/${f.startsWith("team:") ? "team" : "comp"}/${esc(f.split(":")[1])}">${esc(f.split(":")[1].replace(/-/g, " "))}</a>`).join(", ")}</p>
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
  async function route() {
    const my = ++routeSeq;
    app = document.createElement("div");
    const parts = (location.hash.replace(/^#\/?/, "") || "").split("/").map(decodeURIComponent);
    try { window.scrollTo(0, 0); } catch (e) {}
    try {
      switch (parts[0]) {
        case "": await pageToday(); break;
        case "day": await pageToday(parts[1], parts[2]); break;
        case "leagues": await pageLeagues(); break;
        case "comp": await pageComp(parts[1], parts[2], parts[3]); break;
        case "leaders": await pageLeadersPicker(); break;
        case "match": await pageMatch(parts[1]); break;
        case "team": await pageTeam(parts[1]); break;
        case "player": await pagePlayer(parts[1]); break;
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
    if (my === routeSeq) { shell.innerHTML = app.innerHTML; try { shell.focus({ preventScroll: true }); } catch (e) {} }   // a newer page won: drop this one
    app = shell;
  }

  // ---------- one listener for every button
  document.addEventListener("click", ev => {
    const th = ev.target.closest("th[data-sort]");
    if (th) {
      const [slug, k, mode] = th.dataset.sort.split("|");
      const cur = store.get("leaders_sort2:" + slug, null);
      store.set("leaders_sort2:" + slug, [k, mode, cur && cur[0] === k && cur[1] === mode ? -cur[2] : -1]);
      hit("leaders_sort"); route(); return;
    }
    const el = ev.target.closest("[data-go],[data-fav],[data-acca],[data-acca-clear]");
    if (!el) return;
    if (el.dataset.go) { location.hash = el.dataset.go; return; }
    ev.preventDefault(); ev.stopPropagation();
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
  });
  document.querySelectorAll(".tg-channel").forEach(x => { if (C.channel) x.href = tg(C.channel); else x.remove(); });
  document.querySelectorAll(".tg-bot").forEach(x => { if (C.bot) x.href = tg(C.bot); else x.remove(); });
  if (C.cfAnalyticsToken) {                                       // Cloudflare Web Analytics: cookie-free visitor counts
    const s = document.createElement("script");
    s.defer = true; s.src = "https://static.cloudflareinsights.com/beacon.min.js"; s.setAttribute("data-cf-beacon", JSON.stringify({ token: C.cfAnalyticsToken }));
    document.head.appendChild(s);
  }
  window.addEventListener("hashchange", route);
  showAccaCount();
  route();
})();

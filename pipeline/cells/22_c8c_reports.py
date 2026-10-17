# ===================== 8b. MATCH REPORTS =====================
# One report per upcoming fixture, in the format of your analysis prompt, pre-filled with verified data.
# Probabilities come from the tested model. Anything we can't verify is marked as unavailable, never guessed.
ANALYST_BRIEF = """HOW TO USE THESE REPORTS WITH CLAUDE
Paste one report into a chat with Claude (web search on) together with this brief:

You are a football data analyst. The report below was produced by a tested statistical model.
Keep the model's probabilities as the baseline. Using web search:
1. Confirm or correct the KEY ABSENCES with at least two reliable sources (official club sites, major outlets),
   giving the date of each report. Treat the model's absences as inference until confirmed.
2. Add context the model can't see: confirmed lineups if announced, rotation risk, motivation, tactics, weather.
3. If this changes the picture, suggest adjusted Home/Draw/Away percentages, kept SEPARATE from the model's,
   with the reason. Otherwise say no adjustment is needed.
Rules: timestamp every fact, separate facts from inference, mark anything unverified as "unconfirmed",
never invent stats or quotes, present conflicting sources rather than picking one.
This is analysis, not betting advice."""

match_reports = []
if MATCH_REPORTS and (len(pred_dom) or len(pred_eu)):
    SHORT = {"Champions League": "UCL", "Europa League": "UEL", "Conference League": "UECL"}
    res_parts = [all_matches.rename(columns={"League": "Comp"})[["Comp", "Season", "Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG"]]] + \
                [info["data"].rename(columns={"League": "Comp"})[["Comp", "Season", "Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG"]] for info in SOLO.values()] + [
                 extra_matches.rename(columns={"League": "Comp"})[["Comp", "Season", "Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG"]]]
    if len(euro):
        res_parts.append(euro.rename(columns={"Competition": "Comp"})[["Comp", "Season", "Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG"]])
    if len(other_dom):
        res_parts.append(other_dom.rename(columns={"League": "Comp"})[["Comp", "Season", "Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG"]])
    SHORT.update(other_names)
    allres = pd.concat(res_parts, ignore_index=True)
    allres["Date"] = pd.to_datetime(allres["Date"])
    allres = allres[allres["Date"] < TODAY].sort_values("Date")
    latest_result = allres["Date"].max()

    def team_games(team, before):
        g = allres[((allres["HomeTeam"] == team) | (allres["AwayTeam"] == team)) & (allres["Date"] < before)]
        return g.sort_values("Date", ascending=False)

    def form_text(team, before, n=6):
        g = team_games(team, before).head(n)
        if g.empty:
            return "unavailable (no matches in our data)", []
        letters, lines = [], []
        for r in g.itertuples():
            home = r.HomeTeam == team
            gf, ga = (r.FTHG, r.FTAG) if home else (r.FTAG, r.FTHG)
            res_ = "W" if gf > ga else ("D" if gf == ga else "L")
            letters.append(res_)
            opp = r.AwayTeam if home else r.HomeTeam
            lines.append(f"{res_} {int(gf)}-{int(ga)} v {opp} ({'H' if home else 'A'}), {SHORT.get(r.Comp, r.Comp)}, {r.Date:%d %b}")
        summary = f"{''.join(letters)} (W{letters.count('W')} D{letters.count('D')} L{letters.count('L')}, most recent first)"
        return summary, lines

    def table_position(team, league):
        src, season = league_frame(league), league_season(league)
        s_ = src[(src["League"] == league) & (src["Season"] == season)]
        if s_.empty or team not in set(s_["HomeTeam"]) | set(s_["AwayTeam"]):
            return None
        rows = []
        for t in set(s_["HomeTeam"]) | set(s_["AwayTeam"]):
            h_, a_ = s_[s_["HomeTeam"] == t], s_[s_["AwayTeam"] == t]
            gf = h_["FTHG"].sum() + a_["FTAG"].sum(); ga = h_["FTAG"].sum() + a_["FTHG"].sum()
            pts = 3 * ((h_["FTHG"] > h_["FTAG"]).sum() + (a_["FTAG"] > a_["FTHG"]).sum()) + (h_["FTHG"] == h_["FTAG"]).sum() + (a_["FTAG"] == a_["FTHG"]).sum()
            rows.append((t, pts, gf - ga, gf, len(h_) + len(a_)))
        tab = pd.DataFrame(rows, columns=["t", "pts", "gd", "gf", "p"]).sort_values(["pts", "gd", "gf"], ascending=False).reset_index(drop=True)
        r = tab[tab["t"] == team].iloc[0]
        note = " (single table; MLS also has conferences)" if league == "MLS" else ""
        return f"{tab.index[tab['t'] == team][0] + 1} of {len(tab)}, {int(r.pts)} pts from {int(r.p)} games, GD {int(r.gd):+d}{note}"

    def venue_record(team, league, at_home):
        src, season = league_frame(league), league_season(league)
        s_ = src[(src["League"] == league) & (src["Season"] == season)]
        g = s_[s_["HomeTeam"] == team] if at_home else s_[s_["AwayTeam"] == team]
        if g.empty:
            return "no league games yet this season"
        gf, ga = (g["FTHG"], g["FTAG"]) if at_home else (g["FTAG"], g["FTHG"])
        return f"W{(gf > ga).sum()} D{(gf == ga).sum()} L{(gf < ga).sum()}, goals {int(gf.sum())}-{int(ga.sum())} in {len(g)} {'home' if at_home else 'away'} league games"

    def xg_text(team, league):
        if not len(xg) or not (xg["League"] == league).any():
            return None, "unavailable (no expected-goals data for this league yet)"
        s_ = xg[(xg["League"] == league) & (xg["Season"] == league_season(league))].drop_duplicates(["HomeTeam", "AwayTeam", "Season"])
        s_ = s_.merge(league_frame(league)[["League", "Season", "HomeTeam", "AwayTeam", "FTHG", "FTAG"]], on=["League", "Season", "HomeTeam", "AwayTeam"], how="left")
        h_, a_ = s_[s_["HomeTeam"] == team], s_[s_["AwayTeam"] == team]
        n = len(h_) + len(a_)
        if n == 0:
            return None, "unavailable (team not linked to Understat)"
        xgf = (h_["xGH"].sum() + a_["xGA"].sum()) / n
        xga = (h_["xGA"].sum() + a_["xGH"].sum()) / n
        gf = (h_["FTHG"].sum() + a_["FTAG"].sum()) / n
        ga = (h_["FTAG"].sum() + a_["FTHG"].sum()) / n
        last = pd.concat([h_.assign(f=h_["xGH"], a=h_["xGA"]), a_.assign(f=a_["xGA"], a=a_["xGH"])]).sort_values("Date", ascending=False).head(6)
        lastxt = ", ".join(f"{r.f:.1f}-{r.a:.1f}" for r in last.itertuples())
        flag = (gf - xgf)
        return flag, (f"{xgf:.2f} xG for / {xga:.2f} xG against per game ({n} games); scoring {gf:.2f} and conceding {ga:.2f} per game; "
                      f"last 6 xG (for-against): {lastxt}")

    def h2h_text(a, b):
        g = allres[((allres["HomeTeam"] == a) & (allres["AwayTeam"] == b)) | ((allres["HomeTeam"] == b) & (allres["AwayTeam"] == a))]
        g = g.sort_values("Date", ascending=False).head(5)
        if g.empty:
            return f"no meetings in our data (it starts in {SEASONS[0][:2]}/{SEASONS[0][2:]})"
        return "; ".join(f"{r.HomeTeam} {int(r.FTHG)}-{int(r.FTAG)} {r.AwayTeam} ({SHORT.get(r.Comp, r.Comp)}, {r.Date:%b %Y})" for r in g.itertuples())

    fpl_news = {}
    if len(fpl_out) and len(lu):
        pname = lu.drop_duplicates("player_id").set_index("player_id")["player"].to_dict()
        gone = ("joined", "loan", "left the club", "transferred", "released", "contract terminated")
        for r in fpl_out.itertuples():
            if r.status == "u" or any(g_ in str(r.news).lower() for g_ in gone):
                continue                                   # left the club: not an absence
            fpl_news.setdefault(r.team_id, []).append(f"{pname.get(r.player_id, r.name.title())} ({r.news or 'flagged'})")

    upcoming_all = pd.concat([x[["Competition", "Date", "Home", "Away"]] for x in [pred_dom, pred_eu, espn_schedule] if len(x)], ignore_index=True)
    upcoming_all["Date"] = pd.to_datetime(upcoming_all["Date"])
    upcoming_all = upcoming_all.drop_duplicates(subset=["Home", "Away", "Date"])
    ids = pd.DataFrame(columns=["Competition", "Home", "Away", "event_id", "home_id", "away_id"])
    if "fixtures" in globals() and len(fixtures) and "home_id" in fixtures:
        ids = fixtures.rename(columns={"League": "Competition", "HomeTeam": "Home", "AwayTeam": "Away"})[["Competition", "Home", "Away", "event_id", "home_id", "away_id"]]
    if len(euro_up) and "home_id" in euro_up:
        ids = pd.concat([ids, euro_up.rename(columns={"HomeTeam": "Home", "AwayTeam": "Away"})[["Competition", "Home", "Away", "event_id", "home_id", "away_id"]]])
    ids = ids.dropna(subset=["home_id"]).drop_duplicates(["Competition", "Home", "Away"])

    preds_all = pd.concat([x for x in [pred_dom, pred_eu] if len(x)], ignore_index=True).merge(ids, on=["Competition", "Home", "Away"], how="left")
    for m in preds_all.itertuples(index=False):
        md = m._asdict()
        for k_ in ["Absent", "Note"]:
            md[k_] = md.get(k_) if isinstance(md.get(k_), str) else ""
        when = pd.Timestamp(md["Date"])
        home, away, comp = md["Home"], md["Away"], md["Competition"]
        europe = comp in ("Champions League", "Europa League", "Conference League")
        hl = None if europe else comp
        f_h, f_h_lines = form_text(home, when)
        f_a, f_a_lines = form_text(away, when)
        flags, risks = [], []
        # absences
        absences = []
        if md["Absent"]:
            absences.append(md["Absent"].replace("Likely missing, ", "Model's inference (regulars absent from the last squad, long absences or red-card suspensions): "))
        for side, tid in [("home", md.get("home_id")), ("away", md.get("away_id"))]:
            if comp == "Premier League" and tid in fpl_news:
                absences.append(f"Fantasy Premier League flags, {side} ({TODAY:%d %b %Y}): " + "; ".join(fpl_news[tid][:6]))
        if not absences:
            absences.append("none flagged by the model" + ("" if europe else "; not confirmed against team news"))
        # context: rest days and next match
        ctx, congested = [], []
        for t in [home, away]:
            played = team_games(t, when).head(1)
            sched = upcoming_all[((upcoming_all["Home"] == t) | (upcoming_all["Away"] == t)) & (upcoming_all["Date"] < when)].sort_values("Date").tail(1)
            prev_ = []
            if len(played):
                prev_.append((played["Date"].iloc[0], played["Comp"].iloc[0], "played"))
            if len(sched):
                s_row = sched.iloc[0]
                venue = "home" if s_row["Home"] == t else f"away at {s_row['Home']}"
                prev_.append((s_row["Date"], s_row["Competition"], f"scheduled, {venue}"))
            if prev_:
                d_, c_, how = max(prev_, key=lambda x: x[0])
                gap_ = (when - d_).days
                ctx.append(f"{t}: {gap_} day{'s' if gap_ != 1 else ''} since their previous match ({SHORT.get(c_, c_)}, {d_:%a %d %b}, {how})")
                if gap_ <= 3:
                    congested.append(t)
            nxt = upcoming_all[((upcoming_all["Home"] == t) | (upcoming_all["Away"] == t)) & (upcoming_all["Date"] > when)].sort_values("Date").head(1)
            if len(nxt):
                n_ = (nxt['Date'].iloc[0] - when).days
                ctx.append(f"{t} play again in {n_} day{'s' if n_ != 1 else ''} ({SHORT.get(nxt['Competition'].iloc[0], nxt['Competition'].iloc[0])})")
                if n_ <= 3 and t not in congested:
                    congested.append(t)
        if len(up_feats) and isinstance(md.get("event_id"), str):
            uf = up_feats[up_feats["event_id"] == md["event_id"]]
            for side_, t_ in [("h", home), ("a", away)]:
                dn = uf[f"{side_}_departed_names"].iloc[0] if len(uf) and f"{side_}_departed_names" in uf else ""
                if isinstance(dn, str) and dn:
                    ctx.append(f"{t_}: recent departures (no longer in the squad, not counted as absences): {dn}")
        if md["Note"]:
            ctx.append(md["Note"])
        # numbers
        pH, pD, pA = md["pH"], md["pD"], md["pA"]
        g = score_grid(md["ExpHome"], md["ExpAway"], pH, pD, pA)
        flat = g.ravel() / g.sum()
        top = np.argsort(flat)[::-1][:3]
        scores = ", ".join(f"{i // g.shape[1]}-{i % g.shape[1]} ({100 * flat[i]:.0f}%)" for i in top) + f"; together {100 * flat[top].sum():.0f}% of outcomes"
        hh, aa = np.indices(g.shape)
        gn = g / g.sum()
        fav_home = pH >= pA
        margin2 = gn[(hh - aa >= 2) if fav_home else (aa - hh >= 2)].sum()
        margin_line = f"- {home if fav_home else away} to win by 2+ goals: {100 * margin2:.0f}%"
        has_book = pd.notna(md.get("bookH", np.nan))
        gap = max(abs(pH - md["bookH"]), abs(pD - md["bookD"]), abs(pA - md["bookA"])) if has_book else None
        xgf_h, xg_h = xg_text(home, hl) if not europe else (None, "see domestic league data")
        xgf_a, xg_a = xg_text(away, hl) if not europe else (None, "see domestic league data")
        # confidence (transparent rule)
        if len(f_h_lines) < 6 or len(f_a_lines) < 6: flags.append("short recent history for one side")
        if "promoted" in md["Note"]: flags.append("a team new to the league")
        if "Other-country" in md["Note"] or "not rated" in md["Note"]: flags.append("a club rated from European results only")
        elif "results only" in md["Note"]: flags.append("a club from a league we rate from results only (no lineups or odds)")
        if not has_book: flags.append("no bookmaker odds to check against")
        if gap is not None and gap >= 0.12: flags.append(f"the model and bookmakers differ by {100 * gap:.0f} points")
        big_adj = [f"{t_} {100 * (v_ - 1):+.0f}%" for t_, v_ in [(home, md.get("AdjHome")), (away, md.get("AdjAway"))]
                   if v_ is not None and pd.notna(v_) and abs(v_ - 1) >= 0.20]
        confidence = "Low" if flags else ("High" if gap is not None and gap <= 0.05 and not congested and not big_adj else "Medium")
        # reasoning, built only from the numbers above
        fav = max([(pH, f"{home} to win"), (pD, "a draw"), (pA, f"{away} to win")])
        reason = [f"The model's most likely outcome is {fav[1]} ({100 * fav[0]:.0f}%), with expected goals of {md['ExpHome']:.2f} for {home} and {md['ExpAway']:.2f} for {away}, "
                  f"based on both teams' time-weighted results (recent matches count most) and home advantage."]
        adj_h, adj_a = md.get("AdjHome"), md.get("AdjAway")
        if adj_h is not None and pd.notna(adj_h) and pd.notna(adj_a) and (abs(adj_h - 1) >= 0.03 or abs(adj_a - 1) >= 0.03):
            reason.append(f"Likely absences on both sides change the expected goals by {100 * (adj_h - 1):+.0f}% for {home} and {100 * (adj_a - 1):+.0f}% for {away}.")
        for t, f_ in [(home, xgf_h), (away, xgf_a)]:
            if f_ is not None and abs(f_) >= 0.3:
                uses = (f"the model's ratings here already use a {int(100 * XG_WEIGHT)}/{100 - int(100 * XG_WEIGHT)} mix of expected and actual goals, so part of this is built in"
                        if XG_WEIGHT > 0 and (comp in UNDERSTAT_LEAGUES or comp in XG_EXTRA_LEAGUES) else "the model uses actual goals here")
                reason.append(f"{t} are {'outscoring' if f_ > 0 else 'underperforming'} their expected goals by {abs(f_):.2f} per game, which often evens out over time ({uses}).")
        if has_book:
            reason.append(f"Bookmakers make it {100 * md['bookH']:.0f}% / {100 * md['bookD']:.0f}% / {100 * md['bookA']:.0f}%"
                          + (", close to the model." if gap < 0.05 else f", up to {100 * gap:.0f} points away from the model."))
        risks = ["Absences are the model's inference unless marked as Fantasy Premier League flags; confirm team news closer to kickoff.",
                 "Starting lineups are not announced yet.",
                 "In the numbers only if they passed their tests (see the health panel): derbies, weather, team home advantage, motivation, referees; "
                 "tactics are not modelled yet (v22). Fixture congestion, including cup ties BSD covers, is flagged here but not in the numbers."] + [f"Note: {f_}." for f_ in flags] + \
                [f"Fixture congestion: {' and '.join(congested)} {'play' if len(congested) > 1 else 'plays'} within 3 days of this match, so rotation is likely and isn't in the model." if congested else ""]
        if big_adj:
            risks.append(f"Large player adjustment ({', '.join(big_adj)} expected goals): it rests on who missed the last squad, so check team news before relying on it.")
        risks = [r_ for r_ in risks if r_]
        if xgf_h is None and not europe:
            risks.append("No expected-goals data for this league, so finishing luck can't be checked.")
        sources = ["football-data.co.uk (results, odds)"] + (["ESPN (lineups, fixtures, odds)"] if PLAYER_MODEL else []) \
                  + (["Understat (expected goals)"] if xgf_h is not None or xgf_a is not None else []) \
                  + (["Fantasy Premier League (injury flags)"] if comp == "Premier League" and fpl_news else []) + ["our model (probabilities)"]
        lines = [f"MATCH: {home} vs {away} ({comp}, {when:%a %d %b %Y})",
                 f"Data as of: {TODAY:%d %b %Y}; latest result in data {latest_result:%d %b %Y}",
                 "", "KEY DATA SUMMARY",
                 f"- {home} form (last 6, all competitions in our data): {f_h}"] + [f"    {x}" for x in f_h_lines] + [
                 f"- {away} form (last 6): {f_a}"] + [f"    {x}" for x in f_a_lines]
        if not europe:
            pos_h, pos_a = table_position(home, comp), table_position(away, comp)
            lines += [f"- League position: {home} {pos_h or 'unavailable'}; {away} {pos_a or 'unavailable'}",
                      f"- {home} at home this season: {venue_record(home, comp, True)}",
                      f"- {away} away this season: {venue_record(away, comp, False)}",
                      f"- xG/xGA (season; Understat or PitchAPI): {home}: {xg_h} | {away}: {xg_a}"]
        for t_ in (home, away):
            tr_ = TRENDS.get(t_) if "TRENDS" in globals() else None
            if tr_:
                st_ = tr_["stats"]
                xg_part = f", xG {st_['xGF'][0]:.1f}-{st_['xGA'][0]:.1f} per game" if st_["xGF"][0] is not None else ""
                arr = ", ".join(f"{k_} {'up' if v_ == 'up' else 'down'} vs season" for k_, v_ in tr_["arrows"].items())
                perf = f", goals minus xG {tr_['perf']:+.2f}/game" if tr_["perf"] is not None else ""
                lines.append(f"- {t_} last {TREND_N} (all competitions): {tr_['form'][::-1]} ({tr_['ppg']:.2f} pts/game), goals {st_['GF'][0]:.1f}-{st_['GA'][0]:.1f} per game{xg_part}{perf}"
                             + (f"; {arr}" if arr else ""))
            kp_ = KEY_PLAYERS.get(t_) if "KEY_PLAYERS" in globals() else None
            if kp_:
                lines.append(f"- {t_} key players: " + "; ".join(f"{p_['role']} {p_['Player']} ({p_.get('Goals', p_.get('Assists'))} in {p_['Apps']} apps)"
                                                                + (f", {p_['Status']}" if p_["Status"] else "") for p_ in kp_))
        xi_ = EXPECTED_XI.get((comp, when.strftime("%Y-%m-%d"), home, away)) if "EXPECTED_XI" in globals() else None
        if xi_:
            for side_, t_ in [("home", home), ("away", away)]:
                e_ = xi_.get(side_, {})
                if e_.get("ours"):
                    lines.append(f"- {t_} expected XI (ours): " + ", ".join(f"{p_['Player']} ({100 * p_['p']:.0f}%)" for p_ in e_["ours"])
                                 + (f"; doubts: {', '.join(e_['doubts'])}" if e_.get("doubts") else ""))
                pa_ = e_.get("pitchapi")
                if pa_ and (pa_.get("only_pitchapi") or pa_.get("only_ours")):
                    lines.append(f"    PitchAPI ({pa_['kind']}, {pa_.get('formation') or 'formation n/a'}) differs: has {', '.join(pa_['only_pitchapi']) or '-'}; "
                                 f"we expect {', '.join(pa_['only_ours']) or '-'} instead")
        lines += [f"- H2H (last 5 in our data): {h2h_text(home, away)}",
                  "- Key absences:"] + [f"    {x}" for x in absences] + [
                  "- Context notes:"] + [f"    {x}" for x in (ctx or ["none"])] + [
                  f"- Market: " + (f"bookmakers {100 * md['bookH']:.0f}% / {100 * md['bookD']:.0f}% / {100 * md['bookA']:.0f}% (margin removed)" if has_book else "no odds available"),
                  "", "PREDICTION",
                  f"- Outcome probabilities: Home Win {100 * pH:.0f}% / Draw {100 * pD:.0f}% / Away Win {100 * pA:.0f}%",
                  f"- Most likely scorelines: {scores}", margin_line]
        if pd.notna(md.get("pOver25", np.nan)):
            lines.append(f"- Over 2.5 goals: {100 * md['pOver25']:.0f}%")
        if pd.notna(md.get("pBTTS", np.nan)):
            lines.append(f"- Both teams to score: Yes {100 * md['pBTTS']:.0f}% / No {100 - 100 * md['pBTTS']:.0f}%")
        sc_ = SCORERS.get((comp, when.strftime("%Y-%m-%d"), home, away), {}) if "SCORERS" in globals() else {}
        if sc_.get("home") or sc_.get("away"):
            exp_tag = "" if scorer_calibration.get("trusted") else " (experimental: still being calibration-tested)"
            lines.append("- Likeliest scorers" + exp_tag + ": " + " | ".join(
                f"{t_}: " + ", ".join(f"{p_['Player']} {100 * p_['p']:.0f}%" for p_ in sc_.get(s_, [])[:3]) for t_, s_ in [(home, "home"), (away, "away")] if sc_.get(s_)))
        if pd.notna(md.get("pBH", np.nan)):
            lines.append(f"- Model + market blend ({100 * md['BlendW']:.0f}% model): Home {100 * md['pBH']:.0f}% / Draw {100 * md['pBD']:.0f}% / Away {100 * md['pBA']:.0f}% "
                         "(a best estimate, not an independent view)")
        lines += [f"- Confidence level: {confidence} (High = full data, within 5 points of the bookmakers, no fixture congestion and no large player adjustment; Low = any data warning below)",
                  "", "REASONING", " ".join(reason),
                  "", "RISK FACTORS"] + [f"- {r}" for r in risks] + [
                  "", "SOURCES USED", "- " + "; ".join(sources),
                  "", "This is a statistical analysis with irreducible uncertainty, not betting advice."]
        watch, caveats = [], []
        if gap is not None and gap >= 0.10:
            watch.append(f"model and bookmakers differ by {100 * gap:.0f} points: check what the market may know")
        if big_adj:
            watch.append(f"large player adjustment ({', '.join(big_adj)}): confirm team news")
        if congested:
            caveats.append(f"fixture congestion ({', '.join(congested)})")
        caveats += [f_ for f_ in flags if "differ" not in f_]
        score_ = (100 * gap if gap is not None else 0) + 15 * len(big_adj)
        match_reports.append({"Competition": comp, "Date": when.strftime("%Y-%m-%d"), "Home": home, "Away": away,
                              "Confidence": confidence, "text": "\n".join(lines), "Watch": watch, "Caveats": caveats, "Score": float(score_), "Gap": float(gap) if gap is not None else 0.0})

    path = f"{SAVE_DIR}/match_reports_{TODAY:%Y-%m-%d}.md"
    with open(path, "w", encoding="utf-8") as f_:
        f_.write(ANALYST_BRIEF + "\n\n" + "\n\n---\n\n".join(r["text"] for r in sorted(match_reports, key=lambda r: (r["Date"], r["Competition"]))))
    print(f"{len(match_reports)} match reports written to {path} and added to the dashboard.")
    wl = sorted([m_ for m_ in match_reports if m_["Watch"]], key=lambda m_: -m_["Score"])[:15]
    flagged = sum(1 for m_ in match_reports if m_["Watch"])
    print(f"\nMatchday watchlist: the {len(wl)} matches most worth checking ({flagged} have news to check; data caveats are listed separately)")
    for m_ in wl:
        print(f"  {m_['Home']} v {m_['Away']} ({m_['Competition']}, {m_['Date']}): " + "; ".join(m_["Watch"])
              + (f"  [caveats: {'; '.join(m_['Caveats'])}]" if m_["Caveats"] else ""))
    if match_reports:
        print("\nExample:\n")
        print(match_reports[0]["text"])
else:
    print("No upcoming fixtures to report on (or MATCH_REPORTS is off).")

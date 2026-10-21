# ===================== 6b. TEAM NEWS (v35): injuries, suspensions and doubts from ESPN's match news, read by Claude =====================
# For each match in the next 3 days, ESPN's match page and both clubs' news pages list the news (previews, press-conference quotes,
# training reports, injury updates). Claude Haiku
# reads the headlines and summaries and names the players the news rules out or calls doubtful, chosen only from that club's own
# recent squad (so it can't invent names). Results are cached per match and only re-read when the news changes.
# Needs an Anthropic API key as ANTHROPIC_API_KEY (GitHub secret); without it this section is skipped and nothing else changes.
# Feeds the expected lineups (section 7a): "out" players are dropped, "doubt" players are listed as doubts.
NEWS_RUN_MINUTES = 6
NEWS_DAYS = 3
NEWS_MODEL = "claude-haiku-5-5"
NEWS_PATH = f"{SAVE_DIR}/news_flags.json"
NEWS_FLAGS = {}                                     # (our team name, normalised player name) -> ("out" | "doubt", short reason)
_news_norm = lambda s: unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower().strip()

def news_flag(team, player):
    """("out" | "doubt", reason) if team news names this player, else None."""
    if not player:
        return None
    return NEWS_FLAGS.get((team, _news_norm(player)))

NEWS_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["players"],
               "properties": {"players": {"type": "array", "items": {
                   "type": "object", "additionalProperties": False, "required": ["side", "name", "status", "reason"],
                   "properties": {"side": {"type": "string", "enum": ["home", "away"]}, "name": {"type": "string"},
                                  "status": {"type": "string", "enum": ["out", "doubt"]},
                                  "reason": {"type": "string", "description": "a few words, e.g. 'hamstring', 'suspended', 'illness'"}}}}}}

def _news_ask(client_, home_, away_, squads_, text_):
    prompt_ = (f"Match: {home_} (home) v {away_} (away).\n\n"
               f"{home_} squad: {', '.join(squads_['home'])}\n{away_} squad: {', '.join(squads_['away'])}\n\n"
               f"News about this match:\n{text_}\n\n"
               "List the players from these two squads that the news says will miss this match (status 'out': injured, suspended, ill, "
               "not in the squad) or whose availability is uncertain (status 'doubt': a late fitness test, 'doubtful', 'a question mark'). "
               "Use each player's name exactly as written in the squad lists. Leave out players the news says are fit or back, managers and "
               "coaches, players not in the squad lists, and anything the news doesn't actually say. An empty list is a normal answer.")
    r_ = client_.messages.create(model=NEWS_MODEL, max_tokens=2000, output_config={"effort": "low", "format": {"type": "json_schema", "schema": NEWS_SCHEMA}},
                                 messages=[{"role": "user", "content": prompt_}])
    if r_.stop_reason != "end_turn":                     # refusal or cut short: no answer for this match this run
        return None
    txt_ = next((b.text for b in r_.content if b.type == "text"), "")
    return json.loads(txt_).get("players", []) if txt_ else None

news_cache = json.load(open(NEWS_PATH)) if os.path.exists(NEWS_PATH) else {}
_key_ = os.environ.get("ANTHROPIC_API_KEY")
if not _key_:
    print("Team news: skipped (add an ANTHROPIC_API_KEY secret to read injury and press-conference news).")
else:
    try:
        import anthropic, hashlib
        _client = anthropic.Anthropic(api_key=_key_)
        ev_rows_ = []
        if len(espn_fx) and "event_id" in espn_fx:
            ev_rows_ += [(r_.code, str(r_.event_id), r_.League, r_.Date, r_.HomeTeam, r_.AwayTeam, str(r_.home_id), str(r_.away_id)) for r_ in espn_fx.itertuples()]
        _inv_eu_ = {v_: k_ for k_, v_ in EURO_CODES.items()}
        if len(euro_up) and "event_id" in euro_up:
            ev_rows_ += [(_inv_eu_.get(r_.Competition), str(r_.event_id), r_.Competition, r_.Date, r_.HomeTeam, r_.AwayTeam,
                          str(getattr(r_, "home_id", "")), str(getattr(r_, "away_id", ""))) for r_ in euro_up.itertuples() if _inv_eu_.get(r_.Competition)]
        ev_rows_ = [x_ for x_ in ev_rows_ if TODAY <= pd.Timestamp(x_[3]) < TODAY + pd.Timedelta(days=NEWS_DAYS)]
        lu_ = globals().get("lu", pd.DataFrame())
        recent_ = lu_[pd.to_datetime(lu_["date"]) >= TODAY - pd.Timedelta(days=90)] if len(lu_) else lu_
        names_by_team_ = recent_.groupby(recent_["team_id"].astype(str))["player"].apply(lambda s_: sorted(set(map(str, s_.dropna())))).to_dict() if len(recent_) else {}
        t0_, n_read, n_flag, n_new = time.time(), 0, 0, 0
        club_news_ = {}
        for code_, eid_, comp_, date_, home_, away_, hid_, aid_ in ev_rows_:
            if time.time() - t0_ > NEWS_RUN_MINUTES * 60:
                print("  Team news: time limit reached; the rest continue next run.")
                break
            sq_ = {"home": names_by_team_.get(hid_, []), "away": names_by_team_.get(aid_, [])}
            if not sq_["home"] and not sq_["away"]:
                continue
            s_ = espn_get(f"{ESPN_BASE}/{code_}/summary?event={eid_}", pause=0.3) or {}
            arts_ = ((s_.get("news") or {}).get("articles") or [])[:12]
            # v35: each club's own news page too (training reports, press conferences), last 7 days, cached per club for this run
            for t_id_ in (hid_, aid_):
                if t_id_ and t_id_ not in club_news_:
                    club_news_[t_id_] = (espn_get(f"{ESPN_BASE}/{code_}/news?team={t_id_}&limit=12", pause=0.3) or {}).get("articles") or []
                arts_ = arts_ + [a_ for a_ in club_news_.get(t_id_, []) if str(a_.get("published", ""))[:10] >= (TODAY - pd.Timedelta(days=7)).strftime("%Y-%m-%d")]
            seen_h_, uniq_ = set(), []
            for a_ in arts_:
                if a_.get("headline") and a_["headline"] not in seen_h_:
                    seen_h_.add(a_["headline"]); uniq_.append(a_)
            text_ = "\n".join(f"- {a_.get('headline', '')}: {a_.get('description', '')}" for a_ in uniq_[:30])
            if not text_:
                continue
            h_ = hashlib.md5((text_ + "|".join(sq_["home"] + sq_["away"])).encode()).hexdigest()
            c_ = news_cache.get(eid_)
            if not c_ or c_.get("hash") != h_:
                found_ = _news_ask(_client, home_, away_, sq_, text_)
                if found_ is None:
                    continue
                c_ = {"hash": h_, "date": str(pd.Timestamp(date_))[:10], "home": home_, "away": away_, "players": found_}
                news_cache[eid_] = c_
                n_new += 1
            n_read += 1
            for p_ in c_.get("players", []):
                side_ = p_.get("side")
                team_ = home_ if side_ == "home" else away_
                if p_.get("name") in sq_.get(side_, []):          # only names from that club's own squad
                    NEWS_FLAGS[(team_, _news_norm(p_["name"]))] = (p_.get("status", "doubt"), str(p_.get("reason", ""))[:60])
                    n_flag += 1
        news_cache = {k_: v_ for k_, v_ in news_cache.items() if pd.Timestamp(v_.get("date", "2000-01-01")) >= TODAY - pd.Timedelta(days=10)}
        json.dump(news_cache, open(NEWS_PATH, "w"))
        print(f"Team news: {n_read} matches read ({n_new} with new news sent to Claude), {n_flag} players flagged out or doubtful.")
        health("Team news (Claude)", True, f"{n_read} matches, {n_flag} players flagged")
    except Exception as e_:
        print("Team news: failed this run:", str(e_)[:120])
        health("Team news (Claude)", False, "failed this run")

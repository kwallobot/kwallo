# ===================== 6. SAVE PREDICTIONS TO THE LOG =====================
new = pd.concat([x for x in [pred_dom, pred_eu] if len(x)], ignore_index=True) if (len(pred_dom) or len(pred_eu)) else pd.DataFrame()
if new.empty:
    print("Nothing new to save.")
else:
    new["PredictedOn"] = TODAY.strftime("%Y-%m-%d")
    if os.path.exists(LOG_PATH):
        old = pd.read_csv(LOG_PATH)
        new = pd.concat([old, new], ignore_index=True)
    before = len(new)
    new = new.drop_duplicates(subset=["Competition", "Date", "Home", "Away"], keep="last")
    new.to_csv(LOG_PATH, index=False)
    print(f"Saved. The log now holds {len(new)} predictions ({before - len(new)} older duplicates replaced by today's).")

if ANALYST_PICKS:
    AP = f"{SAVE_DIR}/analyst_log.csv"
    a = pd.DataFrame(ANALYST_PICKS, columns=["Competition", "Date", "Home", "Away", "aH", "aD", "aA"])
    tot = a[["aH", "aD", "aA"]].sum(axis=1)
    for c in ["aH", "aD", "aA"]:
        a[c] = a[c] / tot
    a["LoggedOn"] = TODAY.strftime("%Y-%m-%d")
    if os.path.exists(AP):
        a = pd.concat([pd.read_csv(AP), a], ignore_index=True)
    a.drop_duplicates(subset=["Competition", "Date", "Home", "Away"], keep="first").to_csv(AP, index=False)
    print(f"Analyst picks logged ({len(ANALYST_PICKS)} in Settings). Picks are only kept the first time, so they can't be changed after kickoff.")

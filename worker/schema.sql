-- PitchLab bot: only chat IDs and choices are stored. /stop deletes everything for that chat.
CREATE TABLE IF NOT EXISTS subs (chat_id INTEGER NOT NULL, kind TEXT NOT NULL, slug TEXT NOT NULL, name TEXT, created TEXT,
                                 PRIMARY KEY (chat_id, kind, slug));
CREATE TABLE IF NOT EXISTS prefs (chat_id INTEGER PRIMARY KEY, preview INTEGER NOT NULL DEFAULT 1, lineups INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS dispatched (slot TEXT PRIMARY KEY, at TEXT);

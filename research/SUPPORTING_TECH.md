# EduPulse — Supporting Tech Research

Researched 2026-09-26. All items verified real via GitHub. Purpose: feed
the lead-engine build (cutoff predictor, Telegram monitoring, intent
scoring, counselor alerts). Nothing here costs money.

---

## Need 1 — Historical MBA cutoff datasets (college predictor)

### 1A. `pathak0806/mba-eligify` ⭐ primary borrow
- URL: https://github.com/pathak0806/mba-eligify
- Status: public, created 2026-03-17, 5 commits, Flask + pandas.
- Data file: `CatScore_MBA_Dataset.xlsx` — **70 top Indian MBA colleges ×
  30 attributes**: `college_name, city, state`, category-wise CAT cutoffs
  (`CAT_General, CAT_EWS, CAT_OBC, CAT_SC, CAT_ST`), `Fees (Lakhs)`,
  `Avg Package (LPA)`, `Highest Package (LPA)`, `Placement %`,
  `nirf_2025_management_rank`, `tier`, specializations, scholarships,
  official website. Covers IIMs, XLRI, MDI, IMT, SIBM, NMIMS, SPJIMR,
  NITs, Tier 1/2/3.
- Predictor logic in `app.py` (copy the pattern):
  `CATEGORY_MAP` (General→CAT_General …) → filter
  `cat_score >= cutoff AND 12th% >= minimum` → sort by
  `roi_score = Avg Package / Fees` desc → JSON → cards.
- **Gap:** CAT only — no XAT / NMAT / SNAP columns. Extend the sheet with
  the reference values in 1B before building the multi-exam predictor.
- What to borrow: the xlsx as the seed dataset + the
  category-map → filter → ROI-sort algorithm verbatim.

### 1B. Reference cutoff values (for XAT / NMAT / SNAP columns)
No ready-made GitHub CSV found for these exams; use these verified
published values when extending the dataset:
- XAT (jagranjosh.com/colleges/mba): XLRI 93–96, XIMB 90+, SPJIMR 93+,
  GIM 85+, IMT Ghaziabad 90–95, TAPMI 85+.
- SNAP: SIBM Pune 98.5 percentile, SCMHRD 98+, SIIB 85+, SIBM Bangalore
  88+ (careers360 Q&A).
- NMAT scores are marks, not percentiles (unilist.in): NMIMS Mumbai 230+,
  KJ Somaiya 220+, XIM University 200–220, TAPMI 200+, Great Lakes 200+,
  IFMR/SOIL/BML 160–200, ICFAI 150–180.
- CAT sanity anchors (shiksha PDF, Dec 2025): IIM-A/B 99–100, IIM-C 99,
  L/K/I/Kozhikode 97–98, new IIMs 90–96, FMS 99.69, MDI 95+, SPJIMR 85.

### 1C. Predictor architecture patterns
- `chetx27/kcet-predictor` — https://github.com/chetx27/kcet-predictor —
  Python pipeline that extracts cutoffs from official PDF notifications
  (`extract_cutoffs.py --file … --year 2024`) into a DB; year-versioned,
  never mixes years. Borrow the **year-tagged cutoff import pattern** so
  2025 vs 2026 cutoffs stay separate.
- `rusikes-dev/collegehelper` — https://github.com/rusikes-dev/collegehelper —
  predictor with admin panel; paywall enforced server-side (counts only,
  never serializes paid rows). Borrow later if the predictor is monetized.

---

## Need 2 — Telegram monitoring via Telethon

Replaces the dead `t.me/s/` preview scraper (returns 0 items). All need a
free API ID + hash from https://my.telegram.org (2-minute signup).

### 2A. `kronael/tools` → `tg-fetch/` ⭐ best code pattern
- URL: https://github.com/kronael/tools (tg-fetch subdirectory)
- Status: real, 1,021 commits, Unlicense, tg-fetch updated ~10 days ago.
- Two single-file PEP 723 scripts (`uv run` auto-installs telethon):
  `main.py` = resumable message archiver → JSONL
  (`{id, date, sender_id, text, reply_to_msg_id, media}`),
  `users.py` = group participants snapshot → JSONL.
  TOML config, one shared `.session` file, user-auth (bot auth can't read
  history — correct call).
- What to borrow: the TOML-config + shared-session + JSONL-output shape;
  run `main.py` per CAT group on the 5-min scheduler instead of preview
  pages.

### 2B. `om22-12-86/telegram-keyword-tracker` ⭐ best listener pattern
- URL: https://github.com/om22-12-86/telegram-keyword-tracker
- Status: real, created 2026-09-14, 11 commits, MIT.
- Real-time `events.NewMessage` listener on configured channels; keyword
  hit → terminal alert + `alerts.json`
  (`{timestamp, message, alert}`). Config via `config.json`
  (`api_id, api_hash, target_words, channel_ids`).
- ⚠️ README warning (honest, keep it): Telethon user clients can get
  flagged as spam — **use a secondary Telegram account, never the main
  one**.
- What to borrow: the NewMessage-listener + keyword-filter loop for the
  real-time high-intent alert path.

### 2C. `mrutyunjayamuduli1998/telegram-cti-monitor`
- URL: https://github.com/mrutyunjayamuduli1998/telegram-cti-monitor
- Status: real, updated ~106 days ago.
- Pattern: on startup backfill last 100 messages per channel into SQLite,
  then start the real-time listener; keyword categories + regex; summary DM
  to own Saved Messages.
- What to borrow: the **backfill-then-listen** startup pattern and the
  SQLite `messages` / `alerts` table shape.

### 2D. Already-known, verified
- `alexa-3/tg-scraper` (member extraction → CSV: username, role) and
  `dineshkumarbarupal/telegrammemberadder` (scrape + add) — fine for the
  member-list/DM-funnel side; 2A/2B cover the message side better.

---

## Need 3 — Free intent/lead scoring (stdlib + regex, no GPU, no paid API)

No turnkey "MBA intent classifier" repo exists; the right move is a
hand-built weighted taxonomy (~80 lines, zero dependencies). Design:

```
score = Σ keyword_weights  (+ boosters)  (− dampeners)
≥ 60 → 🔥 HIGH   ·  25–59 → ⚡ ACTIVE   ·  < 25 → 💡 EXPLORING
```

- HIGH (+25 each): "which college", "should i apply", "is it worth",
  "admission", "cutoff for", "chances with", "call from", "convert",
  "waitlist", "fee structure", "worth joining"
- ACTIVE (+10 each): "vs", "review", "placements", "package",
  "better than", "syllabus", "preparation", "mock", "percentile"
- Boosters (+15): message is a question (`?`), contains a number +
  "percentile", "urgent"/"asap"/"please help", exam year ("2026"/"2027")
- Dampeners (−20): "news", "ranking released", "announced", "webinar"
  promo, job postings ("hiring", "vacancy")
- Keep a `intent_signals` table: `uid, score, tier, matched_terms` so the
  taxonomy is auditable and tunable from the admin UI.

Supporting references:
- `kambanthemaker/textclassifier` (via https://dev.to/kambanthemaker/a-light-weight-text-classifier-in-python-4o36) —
  zero-dependency word-count classifier, fastText-format training files.
  What to borrow: only if the taxonomy later needs to self-tune from
  counselor-labeled examples; not needed for v1.
- Tier-threshold pattern from `ogikicollins/extruct-gtm-skills`
  `skills/lead-scoring/SKILL.md` (100-pt model, Hot 70–100 / Warm 40–69 /
  Cold 0–39) — adapt thresholds to the 0–100 intent scale above.

---

## Need 4 — Free counselor alerting (real-time)

### 4A. Telegram Bot API direct send ⭐ recommended primary
- Cost: free, unlimited. One stdlib GET, no SDK:
  `https://api.telegram.org/bot<TOKEN>/sendMessage?chat_id=<ID>&text=…`
- The project already owns a bot + the counselor's chat ID is known
  (5312511086); ~20 lines in a new `alerts.py`. Instant delivery,
  supports groups if a counselor group is added later.
- What to borrow: nothing — just write the send function.

### 4B. CallMeBot free WhatsApp API — fallback for WhatsApp
- Cost: free for personal use (fair use), one-way broadcast only.
- Setup: WhatsApp `I allow callmebot to send me messages` to
  +34 644 59 71 67 → API key arrives by reply (~2 min).
- Send: `GET https://api.callmebot.com/whatsapp.php?phone=<countrycode+number>&text=<urlencoded>&apikey=<KEY>`
- Used in production by `manveeranand/streakforge` and
  `mouarg/lotto-alert-template` (both $0 stacks). Limit: no replies,
  no groups, rate-limited.
- What to borrow: drop-in replacement for the Twilio stub when no
  Twilio credentials exist.

### 4C. Existing `whatsapp.py` stubs
Keep the Twilio / Meta Cloud API chain as-is for later; recommended
runtime order: **Telegram Bot API → CallMeBot → Twilio/Meta**.

---

## Suggested build order
1. Vendor `CatScore_MBA_Dataset.xlsx` + extend with 1B columns → predictor.
2. Replace `scrape_telegram_public()` with Telethon `tg-fetch` pattern (2A)
   + keyword listener (2B) feeding the `intelligence` table.
3. Add `intent_signals` scoring (Need 3) into the scheduler cycle.
4. Add `alerts.py` (4A primary, 4B fallback); ping counselor on 🔥 items.

# CAT College Predictor (Phase 3 — Lead Magnet)

A free "Check your MBA college chances" tool. The aspirant enters name,
phone, expected CAT percentile and category → gets an instant
**reach / target / safe** shortlist of B-schools → taps
**"Get my full list on WhatsApp"** to drop their phone number into
`predictor_leads`, the warm-lead pool for counselor follow-up.

## How it works

1. **Dataset** — `data/colleges.json` (70 colleges), baked at build time from
   [pathak0806/mba-eligify](https://github.com/pathak0806/mba-eligify)'s
   `CatScore_MBA_Dataset.xlsx` (thank you, open source). Each college has:
   name, city, per-category CAT cutoffs (General/EWS/OBC/SC/ST),
   tier, avg package (LPA), fees (lakhs), placement %.
   The app runs **without the xlsx at runtime** — only the JSON is read.
2. **Logic** — `predictor.py::predict(cat_percentile, category, workex_months, gender)`:
   - eligible = category cutoff ≤ percentile (uses the dataset's **real
     per-category cutoffs** — no fabricated relaxation),
   - `reach` = colleges up to 2 points *above* the percentile (aspirational),
   - `target` = cutoff 0–3 points below the percentile,
   - `safe` = cutoff ≥ 3 points below the percentile.
   - sorted by tier (Tier 1 → Tier 3), then cutoff descending.
   - `workex_months` / `gender` are accepted for the counselor handoff;
     they don't currently shift cutoffs (no diversity-weight modeling yet).
3. **Routes** — `predictor_routes.py`, Flask Blueprint `predictor_bp`
   (registered in `app.py` by the parent agent — not here):
   - `GET /predictor` → the predictor page,
   - `POST /api/predict` → `{percentile, category, predictions, counts}`,
   - `POST /api/predict/lead` → validates a 10-digit Indian mobile
     (accepts `+91` prefix) and saves `{name, phone, cat_percentile, category}`
     to `predictor_leads`. Returns 400 with a friendly error on bad input.
   - `GET /api/predict/leads-count` → total leads captured (admin use).
4. **Storage** — `predictor.ensure_schema()` creates `predictor_leads`
   (`id, name, phone, cat_percentile, category, created_at`) in
   `data/edupulse.db` with its own sqlite3 connection. **No edits to
   `database.py`** were needed.
5. **Frontend** — `templates/predictor.html` + `static/predictor.css` +
   `static/predictor.js`. Same dark-navy/indigo design language as the
   landing page, system fonts, zero CDN dependencies, mobile-friendly.
   Lead flow: predict first (free, no friction), WhatsApp CTA captures the
   phone number *after* the value is shown — higher conversion.

## Data source credit

College cutoffs, tiers, fees and packages: `CatScore_MBA_Dataset.xlsx` from
**pathak0806/mba-eligify** (GitHub). Cutoffs are indicative of recent
admission cycles — the page says so in the footer. Avg packages for some
Tier-3 rows in the source were placeholder-flat (₹10 LPA); treat those as
directional.

## Updating colleges.json

Re-download the source file and regenerate:

```bash
cd ~/workspace/projects/edupulse-mba-leads
curl -sL -o /tmp/catscore.xlsx \
  https://raw.githubusercontent.com/pathak0806/mba-eligify/main/CatScore_MBA_Dataset.xlsx
python3 - <<'EOF'
import pandas as pd, json
df = pd.read_excel('/tmp/catscore.xlsx')
def num(v, d=0):
    try:
        n = float(v); return n if n == n else d
    except Exception: return d
out = [{
    "name": str(r['college_name']).strip(),
    "city": str(r['city']).strip(),
    "cutoff_percentile": num(r['CAT_General']),
    "cutoffs": {"General": num(r['CAT_General']), "EWS": num(r['CAT_EWS']),
                "OBC": num(r['CAT_OBC']), "SC": num(r['CAT_SC']), "ST": num(r['CAT_ST'])},
    "tier": str(r['tier']).strip(),
    "avg_package_lpa": num(r['Avg Package (LPA)']),
    "fees_lakhs": num(r['Fees (Lakhs)']),
    "placement_pct": num(r['Placement %']),
} for _, r in df.iterrows()]
json.dump(out, open('data/colleges.json', 'w'), indent=2)
print(len(out), "colleges written")
EOF
```

Or hand-edit `data/colleges.json` directly — `predict()` tolerates a
missing `cutoffs` dict (falls back to `cutoff_percentile`).

## Quick test

```bash
python3 -c "
import sys; sys.path.insert(0,'.')
from predictor import predict
for c in predict(92, 'General')[:6]:
    print(c['tag'].upper(), c['name'], c['cutoff'], c['tier'])
"
```

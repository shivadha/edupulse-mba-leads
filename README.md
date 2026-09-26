# 🎓 EduPulse India — Real-Time MBA Aspirant Lead Generation & Admissions Intelligence

EduPulse India is an **internal lead intelligence & counseling CRM** engineered for college admissions teams, MBA consultants, and higher-education counselors in India.

It continuously discovers and scrapes real-time student inquiries, percentile questions, college comparison doubts, and admission intent from **12 Indian education hubs**, refreshing automatically in the background every 5 minutes.

---

## 🚀 Key Capabilities

- **Real-Time Multi-Source Scraper**:
  1. **Reddit**: Subreddits (`r/CATpreparation`, `r/Indian_Academia`, `r/MBA`, `r/IIM`, `r/GRE`)
  2. **Shiksha.com**: Top Indian education portal feeds and queries
  3. **Careers360**: Real-time admission alert feeds & exam updates
  4. **MBAUniverse**: Specialized management education articles & queries
  5. **Pagalguy**: India's legacy MBA aspirant discussion threads
  6. **College Portals**: IIMs, XLRI, SPJIMR, FMS, MDI, IIFT admissions updates
  7. **Quora India**: MBA & CAT queries via DuckDuckGo proxy
  8. **Google News India**: Filtered education & entrance exam news
  9. **Google Trends**: Real-time trending keywords for CAT, XAT, NMAT, SNAP, GMAT
  10. **YouTube Coaching Channels**: Video titles & discussions from premier coaching channels
  11. **Telegram Groups**: Public MBA aspirant community updates
  12. **National Education RSS Feeds**: TOI, NDTV, Indian Express education desks

- **Non-Blocking Background Scheduler**:
  - Automatically runs an initial sweep on server boot.
  - Recursively fetches and deduplicates new records every 5 minutes (`APScheduler` / threading).
  - Stores all leads with MD5 UID deduplication in SQLite.

- **Internal Admissions CRM & Telecaller Pitch Generator**:
  - Live stream of aspirant inquiries tagged with **Target Exam** (CAT, XAT, GMAT, CMAT, NMAT, SNAP) and **Intent Level** (🔥 High Intent, ⚡ Active Inquirer, 💡 Exploring).
  - 1-Click **"📞 Pitch Script"**: Auto-generates a personalized phone pitch for admissions counselors based on candidate queries, percentiles, and college interests.
  - 1-Click **"➕ Add to CRM"**: Converts raw scraped inquiries into structured leads in the admissions call queue.
  - **Instant CSV Export**: Download all scraped aspirant records into Excel / CSV for bulk telecalling and WhatsApp outreach.

- **Modern Light Theme UI**:
  - Clean white surfaces, Inter & Plus Jakarta Sans typography, soft shadows, vibrant badges, and responsive design.

---

## 🛠️ Tech Stack

- **Backend**: Python 3.10+, Flask, SQLite3, Threading
- **Scraper Engine**: Custom 3-tier fetch chain with rotating User-Agents, RSS XML parsers, and BeautifulSoup
- **Frontend**: Vanilla HTML5, CSS3 (Modern Light Design System), Vanilla JS (Zero external heavy dependencies)
- **Messaging**: Integrated WhatsApp Click-to-Chat & counseling notification triggers

---

## 📦 Installation & Quickstart

```bash
# Clone the repository
git clone https://github.com/shivadha/edupulse-mba-leads.git
cd edupulse-mba-leads

# Install dependencies
pip install -r requirements.txt

# Run the platform
python app.py
```

The portal will be immediately accessible at:
- **Internal Admissions CRM & Dashboard**: [http://localhost:5050/](http://localhost:5050/)
- **Live Scraper Engine Status**: [http://localhost:5050/admin](http://localhost:5050/admin)
- **Paid Lead Sources Guide**: [http://localhost:5050/paid-leads](http://localhost:5050/paid-leads)
- **Public Landing Page**: [http://localhost:5050/landing](http://localhost:5050/landing)

---

## 📡 API Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/api/intelligence` | `GET` | Retrieve live scraped student inquiries (`?source=`, `?exam=`, `?limit=`) |
| `/api/stats` | `GET` | Aggregated lead metrics, exam volume distribution, and scheduler health |
| `/api/leads` | `GET` | Direct CRM leads in the counseling call queue |
| `/api/convert-lead` | `POST` | Convert a scraped aspirant inquiry into a CRM lead |
| `/api/export-leads` | `GET` | Download full intelligence database as a CSV file |
| `/api/scrape-now` | `POST` | Trigger an immediate manual background scrape sweep |

---

## 📄 License
MIT License. Created for internal admissions intelligence and lead qualification.

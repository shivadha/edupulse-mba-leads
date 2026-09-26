"""
EduPulse India — Intent scoring engine (Phase 1)
=================================================
Rule-based scorer (stdlib + regex only) that classifies every scraped
item into an intent level:

    high    (70-100)  — student is deciding / applying NOW. Call-worthy.
    medium  (40-69)   — researching / preparing. Nurture-worthy.
    low     (0-39)    — news / generic info. Background noise.

High-intent signals : "which college can I get", "should I apply",
                      percentile + college in same text, "admission chances",
                      "convert" / "waitlist" / "shortlist", "call from <college>",
                      fee / placement / salary / ROI questions framed as decisions,
                      "profile evaluation".
Medium              : exam prep questions, mock/strategy/syllabus,
                      college comparisons ("X vs Y", "which is better"), cutoffs.
Low                 : news, rankings, deadline announcements, generic info.

Usage:
    from scraper.intent import score_intent
    level, score = score_intent(title, snippet)
"""

import re

# ---------------------------------------------------------------------------
# Pattern groups: (compiled regex, weight)
# ---------------------------------------------------------------------------

# --- HIGH intent (decision / application stage) -----------------------------
_HIGH_PATTERNS = [
    # direct "can I get in" questions
    (r"which colleg\w*\s+(can|will|should)\s+i\s+get", 30),
    (r"can i get (a call|admission|into|any iim)", 30),
    (r"what (colleges|schools|bschools|b-schools) can i (get|expect|target)", 30),
    (r"chances of (getting|converting|admission|a call)", 28),
    (r"admission chances", 28),
    (r"should i apply", 26),
    (r"is it worth (applying|joining)", 24),
    (r"profile evaluation", 24),
    (r"evaluate my profile", 24),
    # convert / waitlist / shortlist journey
    (r"\bconvert\w*\b.{0,20}(iim|xlri|fms|mdi|spjimr|iift|call)", 26),
    (r"\bwaitlist\w*\b", 24),
    (r"\bwaitlisted\b", 24),
    (r"\bshortlist\w*\b", 22),
    (r"call from (iim|xlri|fms|mdi|sp jain|spjimr|iift|nmims|sibm)", 26),
    (r"gd.?pi|personal interview|group discussion", 18),
    (r"final (admission|convert|selection|merit)", 22),
    # decision-framed money questions
    (r"(fees|fee).{0,40}(worth|worth it|justif|roi|return)", 22),
    (r"(placement|salary|package|ctc|average package).{0,40}(worth|good|worth it|iim|xlri)", 20),
    (r"\broi\b.{0,30}(mba|college|iim)", 20),
    (r"loan.{0,30}(mba|iim|worth)", 18),
    # application mechanics = about to apply
    (r"application (form|deadline|last date|portal)", 16),
    (r"how to apply", 16),
    (r"documents required|document verification", 16),
    (r"counselling|cap round|spot round", 16),
]

# --- MEDIUM intent (research / prep stage) ----------------------------------
_MEDIUM_PATTERNS = [
    (r"how to (prepare|crack|study)", 14),
    (r"preparation (strategy|plan|tips)", 14),
    (r"\bstrategy\b.{0,20}(cat|xat|gmat|exam|section)", 12),
    (r"\bmock(s| test)?\b.{0,20}(score|attempt|analysis|how many)", 12),
    (r"syllabus|exam pattern", 10),
    (r"which is better", 14),
    (r"\bvs\b.{0,30}(iim|xlri|college|mba)", 14),
    (r"(iim|xlri|fms|mdi|spjimr)\s+vs\s+(iim|xlri|fms|mdi|spjimr|iift)", 16),
    (r"compar(e|ison).{0,30}(college|mba|iim|bschool)", 12),
    (r"\bcutoff\w*\b", 12),
    (r"cut.?off.{0,20}(20\d\d|percentile|expected)", 12),
    (r"best (college|mba|bschool|coaching)", 10),
    (r"top.{0,20}(mba|b.school|bschool|college).{0,20}(india|in india)", 8),
    (r"eligibility|criteria", 10),
    (r"work (ex|experience).{0,30}(mba|iim|admission|help)", 10),
    (r"gap year|drop.{0,10}year", 10),
    (r"scholarship", 10),
    (r"hostel|campus life", 8),
]

# --- LOW intent markers (news / generic info — pull score down) --------------
_LOW_PATTERNS = [
    (r"\branked?\b.{0,20}(#\d+|no\.?\s*\d+|among|in (asia|world|india))", -18),
    (r"(ranks|ranking).{0,30}(businessweek|nirf|qs|ft|financial times)", -18),
    (r"announces|launches|introduces|partners with", -12),
    (r"inaugurat|convocation|alumni meet|summit 20", -14),
    (r"exam (date|schedule|calendar).{0,30}(announced|released|declared)", -10),
    (r"registration (opens|begins|starts)|registrations open", -8),
    (r"admit card (released|released|download|out)", -8),
    (r"result (declared|announced|out)|results declared", -8),
    (r"answer key (released|out)", -8),
    (r"webinar|masterclass|live session.{0,20}(register|join)", -6),
    (r"daily quiz|question of the day|vocab of the day", -10),
    (r"motivational|success story|toppers? (talk|speak)", -8),
]

# Percentile mention: "92 percentile", "99.5 %ile", "95+ percentile"
_PERCENTILE_RE = re.compile(r"(\d{2}(?:\.\d{1,2})?)\s*(?:\+)?\s*(percentile|%ile|percentile\b)", re.I)

# Known college tokens — percentile + college in same text = strong signal
_COLLEGE_RE = re.compile(
    r"\biim\b|xlri|\bfms\b|\bmdi\b|spjimr|sp jain|iift|nmims|sibm|scmhrd|"
    r"iim[-\s]?(ahmedabad|bangalore|calcutta|lucknow|kozhikode|indore)|"
    r"baby iim|new iim|tiss|mdi|imt|fore|ximb|great lakes|dms iit",
    re.I,
)

# Exam tokens — percentile + exam name is also a hot combo
_EXAM_RE = re.compile(r"\bcat\b|\bxat\b|\bgmat\b|\bcmat\b|\bsnap\b|\bnmat\b|\bmat\b|\biift\b", re.I)

# Question framing boost
_QUESTION_RE = re.compile(r"\?\s*$|\b(please|kindly|need|help|suggest|advice|doubt|query)\b", re.I)


def _compile(patterns):
    return [(re.compile(p, re.I), w) for p, w in patterns]


_HIGH = _compile(_HIGH_PATTERNS)
_MEDIUM = _compile(_MEDIUM_PATTERNS)
_LOW = _compile(_LOW_PATTERNS)


def score_intent(title: str = "", snippet: str = "") -> tuple:
    """Return (level, score). level in {'high','medium','low'}, score 0-100."""
    text = f"{title or ''} {snippet or ''}".strip()
    if not text:
        return ("low", 5)

    score = 20  # base: generic MBA-related content

    for rx, w in _HIGH:
        if rx.search(text):
            score += w
    for rx, w in _MEDIUM:
        if rx.search(text):
            score += w
    for rx, w in _LOW:
        if rx.search(text):
            score += w

    # percentile + college/exam combo = hottest signal
    if _PERCENTILE_RE.search(text) and (_COLLEGE_RE.search(text) or _EXAM_RE.search(text)):
        score += 25
    elif _PERCENTILE_RE.search(text):
        score += 12

    # personal question framing
    if _QUESTION_RE.search(text):
        score += 6

    score = max(0, min(100, score))

    if score >= 70:
        level = "high"
    elif score >= 40:
        level = "medium"
    else:
        level = "low"
    return (level, score)


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    cases = [
        ("92 percentile in CAT, which colleges can I get?", "", "high"),
        ("Should I apply to IIM Lucknow with 95%ile?", "", "high"),
        ("Waitlisted at XLRI BM, chances of convert?", "", "high"),
        ("Got a call from MDI Gurgaon, how to prepare for GDPI?", "", "high"),
        ("CAT vs XAT which is better for finance roles?", "", "medium"),
        ("How to prepare for CAT quant in 3 months?", "", "medium"),
        ("IIM Ahmedabad cutoff 2025 expected percentile", "", "medium"),
        ("Bloomberg ranks SP Jain Global #6 in Asia-Pacific", "", "low"),
        ("CAT 2026 registration opens August 1", "", "low"),
        ("Daily quiz: solve this RC question", "", "low"),
    ]
    for title, snippet, expected in cases:
        level, score = score_intent(title, snippet)
        mark = "OK " if level == expected else "MISS"
        print(f"[{mark}] {score:3d} {level:6s} (want {expected:6s}) :: {title[:60]}")

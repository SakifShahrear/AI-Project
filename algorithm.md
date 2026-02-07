# Algorithm Overview

This project uses three simple, rule-based algorithms in the verification pipeline,
combined into a single score:

## 1) Text Similarity

**Location:** [utils.py](utils.py)

**Function:** `text_similarity_score(...)`

**Purpose:** Compares OCR text to scraped web content using token overlap.

## 2) Field Confidence

**Location:** [utils.py](utils.py)

**Function:** `field_confidence_score(...)`

**Purpose:** Scores presence of key fields (competition, organizer, date) and
their appearance in URLs or scraped content.

## 3) Anomaly Score

**Location:** [utils.py](utils.py)

**Function:** `anomaly_score(...)`

**Purpose:** Penalizes suspicious OCR text patterns (too short, too many digits,
or suspicious keywords).

## Combined Score

**Location:** [utils.py](utils.py)

**Function:** `calculate_combined_score(...)`

**Weights:**

- Text similarity 40%
- Field confidence 40%
- Anomaly score 20%

**Where used:** [app.py](app.py) in Step 4 (Calculating accuracy score).

## 4) URL Relevance Ranking

**Location:** [utils.py](utils.py)

**Function:** `rank_search_urls(...)`

**Purpose:** Orders search results so the most relevant URLs are scraped first.

**Signals used:**

- Official domains (.gov, .edu, .org)
- Social media domains
- Organizer/competition tokens in the URL
- Event year in the URL

**Where used:** [app.py](app.py) before scraping in Step 3 (Searching online for verification).

# 🛡️ AI Certificate Authenticator

Complete AI-powered certificate verification system using OCR, Google Gemini AI, and web search to detect fake certificates.

## Features

- 📸 **OCR Text Extraction** - Extract text from certificate images using EasyOCR
- 🤖 **AI Data Extraction** - Use Google Gemini to structure OCR data (competition name, organizer, date)
- 🔍 **Web Search Verification** - Search for official sources (.gov, .edu, .org) and social media events
- 📊 **Accuracy Scoring** - Calculate authenticity score based on multiple factors
- 🧠 **AI Probability Analysis** - Gemini AI determines existence probability (0-1 scale)
- 💾 **Supabase Integration** - Store certificates and verification results
- 📈 **Dashboard** - View verification history and statistics

## Setup

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

If you want to use `pytesseract` fallback OCR, install Tesseract OCR engine in your OS and ensure it is available in PATH.

For spaCy NER extraction, install an English model:

```bash
python -m spacy download en_core_web_sm
```

### 2. Environment Variables

Create a `.env` file in the project root:

```env
# Supabase Configuration
SUPABASE_URL=https://your-project-ref.supabase.co
SUPABASE_KEY=your-anon-key-here

# Google Gemini AI
GEMINI_API_KEY=your-gemini-api-key-here

# Optional: SERP API
SERP_API_KEY=your-serp-api-key-here

# Optional: Organizer alias dataset (CSV)
# Default path is ./datasets/organizer_aliases.csv
ORGANIZER_ALIAS_DATASET=./datasets/organizer_aliases.csv
```

### 3. Supabase Setup

Create two tables in your Supabase project:

**Table: `certificates`**

```sql
CREATE TABLE certificates (
    id BIGSERIAL PRIMARY KEY,
    competition_name TEXT,
    organizer TEXT,
    accuracy_score FLOAT,
    image_url TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);
```

**Table: `verification_results`**

```sql
CREATE TABLE verification_results (
    id BIGSERIAL PRIMARY KEY,
    file_url TEXT,
    competition_name TEXT,
    organizer TEXT,
    accuracy_score FLOAT,
    status TEXT,
    event_date TEXT,
    ai_probability FLOAT,
    search_results_count INT,
    verified_at TIMESTAMP DEFAULT NOW()
);
```

**Storage Bucket:**

- Create a bucket named `cert-uploads`
- Set it to public or configure appropriate policies

### 4. Run the Application

```bash
streamlit run app.py
```

## Project Structure

```
AI project/
├── app.py                 # Streamlit frontend
├── database.py           # Supabase integration
├── ocr_handler.py        # OCR and AI extraction
├── search_agent.py       # Web search functionality
├── utils.py              # Accuracy calculation
├── requirements.txt      # Python dependencies
├── .env                  # Environment variables (create this)
└── (no .env.example)
```

## Usage

1. **Upload Certificate** - Upload a JPG/PNG image
2. **AI Extraction** - System extracts text and structures data
3. **Web Verification** - Searches for official sources
4. **Score Calculation** - Calculates authenticity score
5. **AI Analysis** - Gemini evaluates probability
6. **Save Results** - Store in Supabase database
7. **View History** - Check past verifications

## Organizer Alias Dataset (Recommended)

To improve organizer extraction from noisy OCR text, maintain a CSV file:

`datasets/organizer_aliases.csv`

Required columns:

- `alias`
- `canonical_name`

Example rows:

- `BUET,Bangladesh University of Engineering and Technology`
- `MIST,Military Institute of Science and Technology`

You can add your own short forms and spelling variations. The app uses this mapping during organizer reconciliation.

## Scoring System

- **+50 points**: Official domain (.gov/.edu/.org) found
- **+30 points**: Social media event page found
- **+20 points**: Year in certificate matches search results

**Status:**

- ✅ **Verified** (70-100): High confidence authentic
- ⚠️ **Suspicious** (40-69): Needs further verification
- ❌ **Fake** (<40): Likely fabricated

## API Keys

- **Supabase**: Get from [supabase.com](https://supabase.com)
- **Google Gemini**: Get from [ai.google.dev](https://ai.google.dev)

## Technologies

- **Frontend**: Streamlit
- **AI**: Google Gemini 1.5 Flash
- **OCR**: EasyOCR
- **Database**: Supabase (PostgreSQL)
- **Search**: googlesearch-python
- **Image Processing**: OpenCV, Pillow

## License

MIT License

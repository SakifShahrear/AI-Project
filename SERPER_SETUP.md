# Serper API Setup Instructions

## What is Serper API?

Serper API provides access to Google Search results without being blocked.

- **Fast**: 1-2 second response time
- **Reliable**: 99.9% uptime
- **Free tier**: 2,500 searches/month
- **No blocking**: Official Google Search API

## Setup Steps:

1. **Get your API key:**
   - Go to: https://serper.dev
   - Click "Sign Up" (use Google/GitHub)
   - You get **2,500 free searches** immediately
   - Copy your API key from the dashboard

2. **Add to .env file:**
   Open `d:\AI project\.env` and add:

   ```
   SERPER_API_KEY="your_api_key_here"
   ```

3. **Test it:**
   ```bash
   cd "d:\AI project"
   python -c "from search_agent import search_competition; results = search_competition('', 'ICT Division', max_results=3); print(f'Found {len(results)} results'); [print(f'{i+1}. {url}') for i, url in enumerate(results)]"
   ```

## Search Priority Order:

1. **Serper API** (primary - fast & reliable)
2. **Gemini Grounded** (fallback if Serper fails)
3. **Google search** (last resort - often blocked)

## Benefits:

- ✅ No rate limiting
- ✅ No blocking
- ✅ Real Google results
- ✅ Bangladesh domain filtering
- ✅ 2,500 free searches/month

## Pricing (after free tier):

- $50/month for 5,000 searches
- Pay-as-you-go: $5 per 1,000 searches

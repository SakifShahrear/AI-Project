"""
Certificate Investigator Module
Implements expert-level verification for Bangladeshi academic and professional certificates.
Uses AI to cross-reference OCR data with web scraped content.
"""

import json
import os
import re
from typing import Dict, List, Optional
import google.generativeai as genai
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Initialize Gemini API
_gemini_api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
if _gemini_api_key:
    genai.configure(api_key=_gemini_api_key)
model = genai.GenerativeModel("gemini-2.0-flash")


def _is_leaked_or_blocked_api_key_error(message: str) -> bool:
    lowered = (message or "").lower()
    return (
        "api key was reported as leaked" in lowered
        or ("403" in lowered and "api key" in lowered)
        or "invalid api key" in lowered
        or "permission denied" in lowered
    )


def format_web_data(web_info: List[Dict]) -> str:
    """
    Format scraped web data into a readable format for the AI investigator.
    
    Args:
        web_info: List of dicts with 'url' and 'content' keys
    
    Returns:
        Formatted string of web data
    """
    if not web_info:
        return "No web data available"
    
    formatted = []
    for i, item in enumerate(web_info[:10], 1):  # Limit to first 10 sources
        url = item.get('url', 'Unknown URL')
        content = item.get('content', 'No content')
        # Truncate content to 500 chars per source
        content_preview = content[:500] + "..." if len(content) > 500 else content
        formatted.append(f"\n--- Source {i} ---\nURL: {url}\nContent: {content_preview}\n")
    
    return "".join(formatted) if formatted else "No web data available"


def investigate_certificate(
    candidate_name: str,
    competition_name: str,
    organizer: str,
    extracted_text: str,
    web_info: List[Dict],
    event_date: Optional[str] = None,
    location: Optional[str] = "Bangladesh"
) -> Dict:
    """
    Run expert investigator verification on a certificate.
    
    Args:
        candidate_name: Name of the certificate holder
        competition_name: Name of the event/competition
        organizer: Name of the organizing entity
        extracted_text: Raw OCR extracted text from certificate
        web_info: List of dicts with scraped web data
        event_date: Optional date of the event
        location: Location of the event (default: Bangladesh)
    
    Returns:
        Dict with: status, accuracy_score, reasoning, evidence_found
    """
    
    # Format web data
    formatted_web_info = format_web_data(web_info)
    
    # Create the investigator prompt
    verification_prompt = f"""
You are an expert Investigator specializing in verifying Bangladeshi academic and professional certificates. 

--- CONTEXT ---
In Bangladesh, many legitimate events are organized by private organizations, tech communities, and universities, not just government bodies. Your goal is to find any digital footprint of the event.

--- INPUT DATA ---
- Candidate Name: {candidate_name}
- Event Name: {competition_name}
- Organizer: {organizer}
- Event Date: {event_date or "Not provided"}
- Location: {location}
- OCR Extracted Text: {extracted_text[:1000]}... (truncated)
- Scraped Web Data: {formatted_web_info}

--- INVESTIGATION STEPS ---
1. **Event Legitimacy**: Check if the scraped web data mentions '{competition_name}'. Look for news articles, social media summaries, or event registration pages on local domains (.bd, .com, .org).
2. **Organizer Verification**: Is the '{organizer}' a known entity in Bangladesh? Even if not famous, does the scraped data show they have a physical address or official presence?
3. **Cross-Referencing**:
   - Match dates ({event_date or "dates in certificate"}) and location ({location}).
   - Look for specific keywords like "Winner", "Participant", "Certificate", "Registration", "Symposium".
4. **Local Nuance**: If the search results show a Facebook Event or a LinkedIn post mentioning this event, consider it strong evidence of legitimacy.
5. **Text Analysis**: Compare the OCR extracted text quality with typical certificate language. Professional certificates have specific formatting and language patterns.

--- SCORING LOGIC ---
- 90-100: Found the event AND the candidate's name on a website/news/list.
- 70-89: Found the event, date, and organizer match perfectly, but candidate name isn't on the public web.
- 40-69: Found the organizer, but the specific event is hard to verify (Suspicious).
- 0-39: No trace of the event or organizer exists online (Likely Fake).

--- OUTPUT FORMAT (JSON ONLY) ---
{{
    "status": "Verified" | "Suspicious" | "Fake",
    "accuracy_score": <0-100>,
    "reasoning": "Explain in detail. Example: 'Found event mentions on 2 local tech blogs and matched the organizer's Dhaka address.'",
    "evidence_found": "Specific website or link that confirmed the event",
    "candidate_verified": true | false,
    "organizer_verified": true | false,
    "event_found_online": true | false,
    "keywords_found": ["list", "of", "matching", "keywords"]
}}
"""
    
    try:
        # Call Gemini with retry logic
        response = model.generate_content(verification_prompt)
        response_text = response.text
        
        # Parse the JSON response
        result = parse_investigator_response(response_text)
        
        return result
        
    except Exception as e:
        # Return error response in correct format
        error_text = str(e)
        print(f"Error during investigation: {error_text}")

        if _is_leaked_or_blocked_api_key_error(error_text):
            reasoning = "Gemini API key is blocked/leaked. Expert investigator is unavailable; using rule-based and search evidence instead."
        else:
            reasoning = "Investigator AI is temporarily unavailable; using available rule-based and search evidence."

        return {
            "status": "Suspicious",
            "accuracy_score": 0,
            "reasoning": reasoning,
            "evidence_found": "None",
            "candidate_verified": False,
            "organizer_verified": False,
            "event_found_online": False,
            "keywords_found": []
        }


def parse_investigator_response(response_text: str) -> Dict:
    """
    Parse JSON from the investigator AI response.
    Handles various formatting and cleaning issues.
    
    Args:
        response_text: Raw response from Gemini
    
    Returns:
        Dict with parsed investigation results
    """
    try:
        # Clean markdown code blocks
        cleaned = response_text.strip()
        cleaned = re.sub(r"```json\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"```\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = cleaned.strip()
        
        # Try direct parsing
        result = json.loads(cleaned)
        
        # Validate required fields
        required_fields = ["status", "accuracy_score", "reasoning", "evidence_found"]
        for field in required_fields:
            if field not in result:
                result[field] = None
        
        # Ensure accuracy_score is an integer
        if isinstance(result.get("accuracy_score"), str):
            result["accuracy_score"] = int(re.search(r'\d+', result["accuracy_score"]).group() or 0)
        
        return result
        
    except json.JSONDecodeError:
        # Try to extract JSON from the response
        json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', response_text, flags=re.DOTALL)
        if json_match:
            try:
                result = json.loads(json_match.group(0))
                required_fields = ["status", "accuracy_score", "reasoning", "evidence_found"]
                for field in required_fields:
                    if field not in result:
                        result[field] = None
                return result
            except json.JSONDecodeError:
                pass
        
        # Return default structure if parsing fails
        return {
            "status": "Suspicious",
            "accuracy_score": 0,
            "reasoning": "Could not parse AI response",
            "evidence_found": "None",
            "candidate_verified": False,
            "organizer_verified": False,
            "event_found_online": False,
            "keywords_found": []
        }
    
    except Exception as e:
        return {
            "status": "Suspicious",
            "accuracy_score": 0,
            "reasoning": f"Error parsing response: {str(e)}",
            "evidence_found": "None",
            "candidate_verified": False,
            "organizer_verified": False,
            "event_found_online": False,
            "keywords_found": []
        }


def run_investigation_summary(investigation_result: Dict) -> str:
    """
    Create a human-readable summary of the investigation.
    
    Args:
        investigation_result: Dict from investigate_certificate()
    
    Returns:
        Formatted summary string
    """
    status = investigation_result.get("status", "Unknown")
    score = investigation_result.get("accuracy_score", 0)
    reasoning = investigation_result.get("reasoning", "No reasoning provided")
    evidence = investigation_result.get("evidence_found", "None")
    
    status_emoji = {
        "Verified": "✅",
        "Suspicious": "⚠️",
        "Fake": "❌"
    }
    
    emoji = status_emoji.get(status, "❓")
    
    summary = f"""
{emoji} **Investigation Status: {status}**

📊 **Accuracy Score:** {score}/100

📝 **Reasoning:**
{reasoning}

🔗 **Evidence Found:**
{evidence}

🎯 **Verification Flags:**
- Candidate Verified: {'✅ Yes' if investigation_result.get('candidate_verified') else '❌ No'}
- Organizer Verified: {'✅ Yes' if investigation_result.get('organizer_verified') else '❌ No'}
- Event Found Online: {'✅ Yes' if investigation_result.get('event_found_online') else '❌ No'}

🔑 **Keywords Matched:** {', '.join(investigation_result.get('keywords_found', [])) or 'None'}
"""
    
    return summary

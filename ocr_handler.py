import json
import os
import re
import time
from typing import Dict, List
from urllib.parse import urlparse

import cv2
import easyocr
import numpy as np
import google.generativeai as genai

# OCR Reader Initialize (English language)
# Disable GPU to avoid pinned memory warnings on CPU-only systems
reader = easyocr.Reader(['en'], gpu=False)


def parse_ai_response(response_text: str) -> dict:
	"""
	Parse JSON from Gemini AI response, handling various formats.
	Cleans markdown code blocks and extracts JSON.
	
	Args:
		response_text (str): Raw response from Gemini
	
	Returns:
		dict: Parsed JSON or default structure on failure
	"""
	try:
		# Remove backticks and markdown formatting
		clean_json = response_text.strip()
		clean_json = re.sub(r'```json\s*', '', clean_json, flags=re.IGNORECASE)
		clean_json = re.sub(r'```\s*', '', clean_json, flags=re.IGNORECASE)
		clean_json = clean_json.strip()
		
		# Try direct parsing
		return json.loads(clean_json)
	except json.JSONDecodeError:
		# Try extracting JSON from text
		match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', response_text, flags=re.DOTALL)
		if match:
			try:
				return json.loads(match.group(0))
			except:
				pass
		
		# Return default error structure
		return {
			"status": "Suspicious",
			"accuracy_score": 0,
			"reasoning": "Error parsing AI response",
			"match_found": False
		}
	except Exception:
		return {
			"status": "Suspicious",
			"accuracy_score": 0,
			"reasoning": "Error parsing AI response",
			"match_found": False
		}


def _extract_retry_delay_seconds(message: str, default_seconds: float) -> float:
    try:
        match = re.search(r"retry in ([0-9.]+)s", message, flags=re.IGNORECASE)
        if match:
            return float(match.group(1))
        match = re.search(r"retry_delay\s*\{\s*seconds:\s*([0-9.]+)", message, flags=re.IGNORECASE)
        if match:
            return float(match.group(1))
    except Exception:
        pass
    return default_seconds


def _generate_with_retry(model: "genai.GenerativeModel", prompt: str, max_retries: int = 3):
    """
    Call Gemini with retry/backoff on rate-limit errors (HTTP 429).
    """
    base_delay = 5.0
    for attempt in range(max_retries):
        try:
            return model.generate_content(prompt)
        except Exception as e:
            message = str(e)
            rate_limited = "429" in message or "quota" in message.lower() or "rate limit" in message.lower()
            if rate_limited and attempt < max_retries - 1:
                wait_seconds = _extract_retry_delay_seconds(message, base_delay * (2 ** attempt))
                time.sleep(wait_seconds)
                continue
            raise

def _clean_ocr_text(text: str) -> str:
    """
    Clean common OCR artifacts and noise from extracted text.
    """
    if not text:
        return text
    
    # Remove standalone numbers that are likely OCR artifacts
    # e.g., "BEAR SUMMIT 2 AND NATIONAL 0" -> "BEAR SUMMIT AND NATIONAL"
    text = re.sub(r'\b[0-9]\b(?!\d)', ' ', text)
    
    # Fix common OCR mistakes in Bangladesh-related text
    text = re.sub(r'\bBoNGuADESH\b', 'BANGLADESH', text, flags=re.IGNORECASE)
    text = re.sub(r'\bBANGLADESIi\b', 'BANGLADESH', text, flags=re.IGNORECASE)
    text = re.sub(r'\bDHAI<A\b', 'DHAKA', text, flags=re.IGNORECASE)
    
    # Remove obvious garbage strings (random caps/symbols)
    text = re.sub(r'\b[A-Z]{2,}[a-z]{1,2}[A-Z]{2,}\b', ' ', text)  # e.g., "BoNGuADESH"
    text = re.sub(r'[=\-]{3,}', ' ', text)  # Remove long dashes/equals
    text = re.sub(r'\b[A-Z]{1,2}[a-z]{1,2}[A-Z]{1,2}\s+[A-Z]{2}\b', ' ', text)  # e.g., "LWAE UE"
    
    # Clean up multiple spaces
    text = re.sub(r'\s+', ' ', text)
    
    return text.strip()


def extract_certificate_data(image_path):
    # ইমেজ লোড করা
    img = cv2.imread(image_path)
    
    # প্রি-প্রসেসিং: গ্রেস্কেল এবং নয়েজ রিমুভ (OCR একুরেসি বাড়াতে)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    processed_img = cv2.fastNlMeansDenoising(gray, None, 10, 7, 21)
    
    # টেক্সট এক্সট্রাক্ট করা
    results = reader.readtext(processed_img, detail=0)
    
    # সব টেক্সটকে একটি স্ট্রিংয়ে রূপান্তর
    full_text = " ".join(results)
    
    # Clean OCR artifacts and noise
    cleaned_text = _clean_ocr_text(full_text)
    
    return cleaned_text


def _parse_gemini_json(text: str) -> dict:
    """
    Parse JSON from Gemini response, handling various formats including markdown code blocks.
    """
    # Remove all markdown code block markers
    cleaned = text.strip()
    cleaned = re.sub(r"```json\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"```\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = cleaned.strip()
    
    # Try parsing directly first
    try:
        data = json.loads(cleaned)
        # Ensure all required keys exist
        return {
            "competition_name": data.get("competition_name"),
            "organizer_name": data.get("organizer_name"),
            "event_date": data.get("event_date"),
        }
    except json.JSONDecodeError:
        pass
    
    # Try extracting JSON object from text
    match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', cleaned, flags=re.DOTALL)
    if match:
        try:
            data = json.loads(match.group(0))
            return {
                "competition_name": data.get("competition_name"),
                "organizer_name": data.get("organizer_name"),
                "event_date": data.get("event_date"),
            }
        except json.JSONDecodeError:
            pass
    
    # If all parsing fails, return default structure
    return {
        "competition_name": None,
        "organizer_name": None,
        "event_date": None,
    }


def _heuristic_extract_event_date(text: str) -> str | None:
    if not text:
        return None

    # Common date patterns (including ranges and various formats)
    patterns = [
        r"\b\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4}\b",
        r"\b\d{4}[-/.]\d{1,2}[-/.]\d{1,2}\b",
        r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+\d{4}\b",
        r"\b\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\s+\d{4}\b",
        r"\b\d{1,2}[-]\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\s+\d{4}\b",
        r"\b(?:Date|Dated|Held on|Event Date)[:\s]+([\d\-/.\s]+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)?[\w\s,\-]+\d{4})\b",
        r"\b202[0-9]\b",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return match.group(1) if match.lastindex else match.group(0)

    return None


def _heuristic_extract_organizer_name(text: str) -> str | None:
    if not text:
        return None
    
    # Clean the text first
    text = _clean_ocr_text(text)

    patterns = [
        r"(?:organized by|organised by|organizer|organiser)[:\s]+([A-Z][A-Za-z0-9&.,\-/() ]{3,100}?)(?:\n|\.|,|$)",
        r"(?:presented by|hosted by|conducted by)[:\s]+([A-Z][A-Za-z0-9&.,\-/() ]{3,100}?)(?:\n|\.|,|$)",
        r"(?:in collaboration with|in association with)[:\s]+([A-Z][A-Za-z0-9&.,\-/() ]{3,100}?)(?:\n|\.|,|$)",
        r"(?:ICT|Ministry|Department|Division|University|Institute|Foundation|Society|Association|Board|Council|Committee)\s+(?:of\s+)?[A-Z][A-Za-z0-9&.,\-/() ]{3,80}",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            result = match.group(1) if match.lastindex else match.group(0)
            # Clean up trailing punctuation and whitespace
            result = re.sub(r'[.,;:]+$', '', result.strip())
            if len(result) > 3:
                return result

    return None


def _heuristic_extract_competition_name(text: str) -> str | None:
    if not text:
        return None
    
    # Clean the text first
    text = _clean_ocr_text(text)

    keywords = (
        "competition", "contest", "challenge", "summit", "conference",
        "workshop", "hackathon", "symposium", "olympiad", "expo",
        "festival", "tournament", "camp", "award", "program", "programme",
        "championship", "event", "seminar", "bootcamp"
    )

    # Try to find the largest text block containing keywords
    lines = text.split('\n')
    best_match = None
    max_length = 0

    for keyword in keywords:
        # Pattern 1: Find lines containing the keyword
        for i, line in enumerate(lines):
            if re.search(rf'\b{keyword}\b', line, flags=re.IGNORECASE):
                # Try to capture surrounding context (up to 3 lines)
                context_lines = []
                for j in range(max(0, i-1), min(len(lines), i+2)):
                    if lines[j].strip():
                        context_lines.append(lines[j].strip())
                
                if context_lines:
                    combined = ' '.join(context_lines)
                    # Clean and extract meaningful part
                    cleaned = re.sub(r'\s+', ' ', combined)
                    if len(cleaned) > max_length and len(cleaned) < 150:
                        best_match = cleaned
                        max_length = len(cleaned)
        
        # Pattern 2: Direct regex pattern
        pattern = rf"([A-Z][A-Za-z0-9&.,\-/() ]{{3,100}}\b{keyword}\b[A-Za-z0-9&.,\-/() ]{{0,50}})"
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            candidate = match.group(1).strip()
            if len(candidate) > max_length:
                best_match = candidate
                max_length = len(candidate)

    return best_match


def _extract_fields_heuristic(raw_text: str) -> dict:
    return {
        "competition_name": _heuristic_extract_competition_name(raw_text),
        "organizer_name": _heuristic_extract_organizer_name(raw_text),
        "event_date": _heuristic_extract_event_date(raw_text),
    }


def extract_certificate_fields_heuristic(raw_text: str) -> dict:
    """
    Heuristic-only extraction (no AI). Always returns a dict with
    competition_name, organizer_name, and event_date keys.
    """
    return _extract_fields_heuristic(raw_text)


def extract_certificate_fields_gemini(raw_text: str, model_name: str = "models/gemini-flash-latest") -> dict:
    """
    Use Google Gemini to extract structured certificate fields from raw text.

    Returns JSON with keys: competition_name, organizer_name, event_date.
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY environment variable is required")

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(model_name)

    prompt = f"""
You are an expert at extracting information from certificates. Analyze the following OCR text and extract key details.

IMPORTANT: Return ONLY a valid JSON object with these exact keys:
- "competition_name": The name of the competition/event/program (e.g., "BEAR SUMMIT 2025", "AI Hackathon")
- "organizer_name": The organizing institution/company (e.g., "ICT Division", "National Science Complex", "Tech University")
- "event_date": The event date in any readable format (e.g., "16-17 July 2025", "2025-07-16")

Rules:
1. Look for words like "Competition", "Event", "Summit", "Hackathon", "Conference", "Workshop"
2. Look for organizing body near words like "Organized by", "Presented by", "Hosted by"
3. Look for dates near words like "Date:", "Held on", or month names
4. If you cannot find a field with high confidence, set it to null
5. DO NOT include markdown formatting or code blocks - return pure JSON only

OCR TEXT:
{raw_text}

JSON OUTPUT:"""

    try:
        response = _generate_with_retry(model, prompt)
        return _parse_gemini_json(response.text)
    except Exception as e:
        # Fallback to heuristic extraction on quota/rate limit or any failure
        return _extract_fields_heuristic(raw_text)


# Alias for backward compatibility and clearer naming in Streamlit app
def ai_extract_structured_info(raw_text: str) -> dict:
    """
    Extract structured information from raw OCR text using AI.
    Alias for extract_certificate_fields_gemini.
    
    Returns dict with competition_name, organizer_name, event_date.
    """
    return extract_certificate_fields_gemini(raw_text)


def _calculate_text_similarity(text1: str, text2: str) -> float:
    """Calculate simple word overlap similarity between two texts."""
    if not text1 or not text2:
        return 0.0
    
    # Normalize and tokenize
    words1 = set(re.findall(r'\w+', text1.lower()))
    words2 = set(re.findall(r'\w+', text2.lower()))
    
    if not words1 or not words2:
        return 0.0
    
    # Calculate Jaccard similarity
    intersection = len(words1 & words2)
    union = len(words1 | words2)
    
    return intersection / union if union > 0 else 0.0


def _is_official_domain(url: str) -> bool:
    """Check if URL is from official domain (.gov, .edu, .org)."""
    try:
        netloc = urlparse(url).netloc.lower()
        return netloc.endswith('.gov') or netloc.endswith('.edu') or netloc.endswith('.org')
    except Exception:
        return False


def verify_competition_existence(
    ocr_data: Dict[str, str],
    search_results: List[str],
    model_name: str = "models/gemini-flash-latest"
) -> Dict[str, any]:
    """
    Compare extracted certificate text with search results to determine competition existence.
    
    Args:
        ocr_data: Dictionary with keys 'competition_name', 'organizer_name', 'event_date'
        search_results: List of URLs from search engine
        model_name: Gemini model to use for analysis
    
    Returns:
        Dictionary with:
        - probability: Float between 0 and 1
        - reasons: List of supporting evidence
        - conclusion: Text summary
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY environment variable is required")
    
    reasons = []
    probability_factors = []
    
    # Factor 1: Number of search results
    num_results = len(search_results)
    if num_results == 0:
        probability_factors.append(0.0)
        reasons.append(f"No search results found (strong indication of fake)")
    elif num_results >= 5:
        probability_factors.append(0.9)
        reasons.append(f"Found {num_results} search results (strong online presence)")
    elif num_results >= 3:
        probability_factors.append(0.7)
        reasons.append(f"Found {num_results} search results (moderate online presence)")
    else:
        probability_factors.append(0.4)
        reasons.append(f"Found only {num_results} search result(s) (weak online presence)")
    
    # Factor 2: Official domain presence
    official_domains = [url for url in search_results if _is_official_domain(url)]
    if official_domains:
        probability_factors.append(0.95)
        reasons.append(f"Found {len(official_domains)} official domain(s) (.gov/.edu/.org) - highly credible")
    elif search_results:
        probability_factors.append(0.5)
        reasons.append("No official domains found - credibility uncertain")
    
    # Factor 3: Use Gemini to analyze search results
    if search_results and ocr_data.get('competition_name'):
        try:
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel(model_name)
            
            prompt = (
                f"Analyze if this competition exists based on the following:\n\n"
                f"Competition Name: {ocr_data.get('competition_name', 'Unknown')}\n"
                f"Organizer: {ocr_data.get('organizer_name', 'Unknown')}\n"
                f"Event Date: {ocr_data.get('event_date', 'Unknown')}\n\n"
                f"Search Results URLs:\n" + "\n".join(f"- {url}" for url in search_results[:10]) + "\n\n"
                f"Based on the URLs and information provided, assess:\n"
                f"1. Do these URLs appear to be about the same competition?\n"
                f"2. Are they from credible sources?\n"
                f"3. Does the competition appear to be real or fabricated?\n\n"
                f"Return a JSON with: {{'analysis': 'brief explanation', 'confidence': 0.0 to 1.0}}"
            )
            
            response = _generate_with_retry(model, prompt)
            analysis_result = _parse_gemini_json(response.text)
            
            if 'confidence' in analysis_result:
                ai_confidence = float(analysis_result.get('confidence', 0.5))
                probability_factors.append(ai_confidence)
                reasons.append(f"AI Analysis: {analysis_result.get('analysis', 'No details')}")
            
        except Exception as e:
            reasons.append(f"AI analysis failed: {str(e)}")
    
    # Calculate final probability (weighted average)
    if probability_factors:
        final_probability = sum(probability_factors) / len(probability_factors)
    else:
        final_probability = 0.1
    
    # Cap between 0 and 1
    final_probability = max(0.0, min(1.0, final_probability))
    
    # Generate conclusion
    if final_probability >= 0.75:
        conclusion = f"HIGH PROBABILITY ({final_probability:.2f}) - Competition likely exists"
    elif final_probability >= 0.50:
        conclusion = f"MODERATE PROBABILITY ({final_probability:.2f}) - Competition may exist, needs verification"
    elif final_probability >= 0.25:
        conclusion = f"LOW PROBABILITY ({final_probability:.2f}) - Competition authenticity doubtful"
    else:
        conclusion = f"VERY LOW PROBABILITY ({final_probability:.2f}) - Competition likely fabricated"
    
    return {
        "probability": round(final_probability, 3),
        "reasons": reasons,
        "conclusion": conclusion,
        "search_results_count": num_results,
        "official_domains_count": len(official_domains) if search_results else 0
    }


def ai_verify_validity(extracted_text: str, search_results: List[str], scraped_content: List[dict] = None, model_name: str = "models/gemini-flash-latest") -> str:
	"""
	Professional Forensic Document Verifier using Gemini AI.
	Compares OCR data with web search results and scraped content.
	
	Args:
		extracted_text (str): Raw text extracted from certificate via OCR
		search_results (List[str]): List of URLs from web search
		scraped_content (List[dict]): List of scraped web content (optional)
		model_name (str): Gemini model to use
	
	Returns:
		str: JSON string with status, accuracy_score, reasoning, match_found
	"""
	api_key = os.getenv("GEMINI_API_KEY")
	if not api_key:
		raise ValueError("GEMINI_API_KEY environment variable is required")
	
	# Prepare collected web information
	collected_info = ""
	
	if search_results:
		collected_info += f"Found {len(search_results)} search results:\n"
		for i, url in enumerate(search_results[:10], 1):
			collected_info += f"{i}. {url}\n"
	else:
		collected_info += "No search results found.\n"
	
	if scraped_content:
		collected_info += f"\n--- SCRAPED WEB CONTENT (from {len(scraped_content)} websites) ---\n"
		for i, data in enumerate(scraped_content[:3], 1):  # Limit to 3 to avoid token overflow
			collected_info += f"\nSource {i}: {data['url']}\n"
			collected_info += f"{data['content'][:1000]}...\n"  # First 1000 chars
	else:
		collected_info += "\nNo web content was scraped.\n"
	
	# Create the powerful forensic verification prompt
	verification_prompt = f"""
You are a Professional Forensic Document Verifier. Your task is to compare the data extracted from a certificate (OCR) against real-world data found on the internet (Web Search).

--- 1. DATA FROM CERTIFICATE (OCR) ---
{extracted_text[:2000]}

--- 2. DATA FROM WEB SEARCH (SERPER + SCRAPING) ---
{collected_info}

--- INSTRUCTIONS ---
1. Cross-reference the "Candidate Name", "Event Name", "Organizer", and "Date" from the OCR with the Web Data.
2. If the Event exists online and the dates/organizers match, increase the authenticity score.
3. If you find a list of winners or participants on the web and the candidate's name is there, it's a 100% match.
4. If no direct match is found, check if the event is a future event (e.g., July 2025). If it is, verify if the event is announced or scheduled.
5. Look for matching keywords, organization names, dates, and locations between OCR and web content.
6. Check if the organizer name in the certificate matches the organizer mentioned in web content.
7. Verify if event dates align between certificate and web announcements.
8. Provide a reasoning for your verdict.

--- SCORING GUIDELINES ---
- 90-100: Perfect match found (event exists, dates match, organizer confirmed, participant name found)
- 70-89: Strong match (event exists, dates/organizer match, but no participant list found)
- 50-69: Moderate match (event exists but some details don't align perfectly)
- 30-49: Weak match (event found but significant discrepancies)
- 0-29: No match or fake (no evidence of event online, or major contradictions)

--- OUTPUT FORMAT (JSON ONLY) ---
Return ONLY a valid JSON object with these keys:
- "status": "Verified", "Suspicious", or "Fake"
- "accuracy_score": (A number between 0-100)
- "reasoning": "A brief explanation of your decision (2-3 sentences)"
- "match_found": true/false

DO NOT include markdown formatting, code blocks, or any text outside the JSON object.
"""
	
	try:
		genai.configure(api_key=api_key)
		model = genai.GenerativeModel(model_name)
		
		# Generate response with retry
		response = _generate_with_retry(model, verification_prompt)
		
		# Parse the response
		result = parse_ai_response(response.text)
		
		# Ensure all required keys exist
		if "status" not in result:
			result["status"] = "Suspicious"
		if "accuracy_score" not in result:
			result["accuracy_score"] = 0
		if "reasoning" not in result:
			result["reasoning"] = "Unable to verify certificate authenticity"
		if "match_found" not in result:
			result["match_found"] = False
		
		# Legacy compatibility: also include probability and is_authentic
		result["probability"] = result["accuracy_score"] / 100.0
		result["is_authentic"] = result["status"] == "Verified"
		result["reasons"] = [result["reasoning"]]
		
		return json.dumps(result, indent=2)
		
	except Exception as e:
		# Fallback response on error
		fallback_result = {
			"status": "Suspicious",
			"accuracy_score": 0,
			"reasoning": f"AI verification failed: {str(e)}",
			"match_found": False,
			"probability": 0.0,
			"is_authentic": False,
			"reasons": [f"Error: {str(e)}"]
		}
		return json.dumps(fallback_result, indent=2)


if __name__ == "__main__":
    # Example usage
    """
    sample_ocr = {
        "competition_name": "AI Hackathon 2026",
        "organizer_name": "Tech University",
        "event_date": "2026-03-15"
    }
    
    sample_urls = [
        "https://techuniversity.edu/events/ai-hackathon",
        "https://facebook.com/events/ai-hackathon-2026",
        "https://linkedin.com/events/tech-ai-competition"
    ]
    
    result = verify_competition_existence(sample_ocr, sample_urls)
    print(f"Probability: {result['probability']}")
    print(f"Conclusion: {result['conclusion']}")
    print("Reasons:")
    for reason in result['reasons']:
        print(f"  - {reason}")
    """

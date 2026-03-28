import json
import os
import re
import time
import csv
from difflib import SequenceMatcher
from typing import Dict, List
from urllib.parse import urlparse

import cv2
import easyocr
import numpy as np
import google.generativeai as genai
from PIL import Image

try:
    import pytesseract
except Exception:
    pytesseract = None

try:
    import spacy
except Exception:
    spacy = None

# OCR Reader Initialize (English language)
# Disable GPU to avoid pinned memory warnings on CPU-only systems
reader = easyocr.Reader(['en'], gpu=False)
_SPACY_NLP = None
_SPACY_LOAD_ATTEMPTED = False


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


def _is_leaked_or_blocked_api_key_error(message: str) -> bool:
    if not message:
        return False
    lowered = message.lower()
    return (
        "api key was reported as leaked" in lowered
        or ("403" in lowered and "api key" in lowered)
        or "permission denied" in lowered
        or "invalid api key" in lowered
    )


def _generate_with_retry(model: "genai.GenerativeModel", content, max_retries: int = 3):
    """
    Call Gemini with retry/backoff on rate-limit errors (HTTP 429).
    """
    base_delay = 5.0
    for attempt in range(max_retries):
        try:
            return model.generate_content(content)
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

    text = text.replace('\r\n', '\n').replace('\r', '\n')

    # Replace underscores with spaces (common OCR artefact: "in_the" → "in the")
    text = text.replace('_', ' ')

    # Normalize mixed-case OCR noise for known event-type keywords
    text = re.sub(r'\biupc\b', 'IUPC', text, flags=re.IGNORECASE)
    text = re.sub(r'\biucc\b', 'IUCC', text, flags=re.IGNORECASE)
    text = re.sub(r'\bicpc\b', 'ICPC', text, flags=re.IGNORECASE)
    text = re.sub(r'\bNcell\b', 'NCELL', text, flags=re.IGNORECASE)
    text = re.sub(r'\bRnesents\b', 'presents', text, flags=re.IGNORECASE)
    text = re.sub(r'\bPresentes\b', 'presents', text, flags=re.IGNORECASE)

    # Remove standalone numbers that are likely OCR artifacts
    # e.g., "BEAR SUMMIT 2 AND NATIONAL 0" -> "BEAR SUMMIT AND NATIONAL"
    text = re.sub(r'\b[0-9]\b(?!\d)', ' ', text)
    
    # Fix common OCR mistakes in Bangladesh-related text
    text = re.sub(r'\bBoNGuADESH\b', 'BANGLADESH', text, flags=re.IGNORECASE)
    text = re.sub(r'\bBANGLADESIi\b', 'BANGLADESH', text, flags=re.IGNORECASE)
    text = re.sub(r'\bDHAI<A\b', 'DHAKA', text, flags=re.IGNORECASE)
    text = re.sub(r'\bindustral\b', 'industrial', text, flags=re.IGNORECASE)
    text = re.sub(r'\bdvelopment\b', 'development', text, flags=re.IGNORECASE)

    # Fix common glued OCR tokens around organization/date fragments
    text = re.sub(r'\b(ltd|limited|inc|corp|company)(?=held\b)', r'\1 ', text, flags=re.IGNORECASE)
    text = re.sub(r'\bdurationof\b', 'duration of', text, flags=re.IGNORECASE)
    text = re.sub(r'\bdateof\b', 'date of', text, flags=re.IGNORECASE)
    text = re.sub(r'\bissue:([A-Za-z])', r'issue: \1', text, flags=re.IGNORECASE)
    
    # Remove obvious garbage strings (random caps/symbols)
    text = re.sub(r'\b[A-Z]{2,}[a-z]{1,2}[A-Z]{2,}\b', ' ', text)  # e.g., "BoNGuADESH"
    text = re.sub(r'[=\-]{3,}', ' ', text)  # Remove long dashes/equals
    text = re.sub(r'\b[A-Z]{1,2}[a-z]{1,2}[A-Z]{1,2}\s+[A-Z]{2}\b', ' ', text)  # e.g., "LWAE UE"

    # Preserve line structure while normalizing whitespace
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r' *\n+ *', '\n', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    
    return text.strip()


def _deskew_image(gray: np.ndarray) -> np.ndarray:
    """Deskew document image slightly to improve OCR accuracy."""
    thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
    coords = np.column_stack(np.where(thresh > 0))
    if len(coords) == 0:
        return gray

    angle = cv2.minAreaRect(coords)[-1]
    if angle < -45:
        angle = -(90 + angle)
    else:
        angle = -angle

    if abs(angle) < 0.5 or abs(angle) > 15:
        return gray

    (height, width) = gray.shape[:2]
    center = (width // 2, height // 2)
    matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
    return cv2.warpAffine(
        gray,
        matrix,
        (width, height),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_REPLICATE,
    )


def _upscale_for_ocr(image: np.ndarray, min_width: int = 1200) -> np.ndarray:
    """Upscale smaller images to improve OCR readability."""
    height, width = image.shape[:2]
    if width >= min_width:
        return image

    scale = min_width / max(width, 1)
    return cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)


def _build_ocr_variants(img: np.ndarray) -> List[tuple[str, np.ndarray]]:
    """Generate multiple preprocessed variants and let OCR choose the best one."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    denoised = cv2.fastNlMeansDenoising(gray, None, 12, 7, 21)
    deskewed = _deskew_image(denoised)
    upscaled = _upscale_for_ocr(deskewed)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(upscaled)
    sharpened = cv2.filter2D(
        clahe,
        -1,
        np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]], dtype=np.float32),
    )
    adaptive = cv2.adaptiveThreshold(
        clahe,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        31,
        11,
    )
    otsu = cv2.threshold(sharpened, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]

    return [
        ("upscaled_gray", upscaled),
        ("clahe", clahe),
        ("sharpened", sharpened),
        ("adaptive", adaptive),
        ("otsu", otsu),
    ]


def _reconstruct_ocr_lines(results: List[list]) -> tuple[str, float]:
    """Rebuild line-oriented text from EasyOCR results while preserving reading order."""
    if not results:
        return "", 0.0

    items = []
    heights = []
    confidences = []
    for result in results:
        if len(result) < 3:
            continue
        bbox, text, confidence = result
        if not text or not text.strip():
            continue

        xs = [point[0] for point in bbox]
        ys = [point[1] for point in bbox]
        center_x = float(sum(xs) / len(xs))
        center_y = float(sum(ys) / len(ys))
        height = float(max(ys) - min(ys))
        heights.append(height)
        confidences.append(float(confidence))
        items.append({
            "text": text.strip(),
            "x": center_x,
            "y": center_y,
            "height": height,
        })

    if not items:
        return "", 0.0

    items.sort(key=lambda item: (item["y"], item["x"]))
    median_height = float(np.median(heights)) if heights else 20.0
    line_threshold = max(12.0, median_height * 0.65)

    lines: List[List[dict]] = []
    current_line: List[dict] = []
    current_line_y = None

    for item in items:
        if current_line_y is None or abs(item["y"] - current_line_y) <= line_threshold:
            current_line.append(item)
            current_line_y = item["y"] if current_line_y is None else (current_line_y + item["y"]) / 2.0
        else:
            lines.append(sorted(current_line, key=lambda entry: entry["x"]))
            current_line = [item]
            current_line_y = item["y"]

    if current_line:
        lines.append(sorted(current_line, key=lambda entry: entry["x"]))

    text_lines = [" ".join(entry["text"] for entry in line).strip() for line in lines]
    text_lines = [line for line in text_lines if line]
    avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0
    return "\n".join(text_lines), avg_confidence


def _score_ocr_text(text: str, confidence: float) -> float:
    """Score OCR output quality to choose the best preprocessing variant."""
    if not text:
        return 0.0

    token_count = len(re.findall(r'[A-Za-z]{3,}', text))
    line_count = len([line for line in text.split('\n') if line.strip()])
    keyword_hits = len(re.findall(
        r'certificate|competition|organizer|organized|university|institute|award|participant|winner|date',
        text,
        flags=re.IGNORECASE,
    ))
    noise_penalty = len(re.findall(r'[^A-Za-z0-9\s.,:&()\-/]', text))

    score = confidence * 0.55
    score += min(token_count / 40.0, 1.0) * 0.20
    score += min(line_count / 12.0, 1.0) * 0.10
    score += min(keyword_hits / 6.0, 1.0) * 0.20
    score -= min(noise_penalty / 40.0, 0.25)
    return score


def _build_orientation_candidates(img: np.ndarray) -> List[tuple[str, np.ndarray]]:
    """Create orientation variants with portrait-aware priority."""
    h, w = img.shape[:2]
    portrait = h > (w * 1.1)

    if portrait:
        # For vertical uploads, test landscape corrections first.
        return [
            ("rot90_cw", cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)),
            ("rot90_ccw", cv2.rotate(img, cv2.ROTATE_90_COUNTERCLOCKWISE)),
            ("rot0", img),
            ("rot180", cv2.rotate(img, cv2.ROTATE_180)),
        ]

    return [
        ("rot0", img),
        ("rot180", cv2.rotate(img, cv2.ROTATE_180)),
        ("rot90_cw", cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)),
        ("rot90_ccw", cv2.rotate(img, cv2.ROTATE_90_COUNTERCLOCKWISE)),
    ]


def preprocess_image_for_ocr(image: np.ndarray) -> np.ndarray:
    """Simple preprocessing pipeline: grayscale + binary threshold."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    thresh = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY)[1]
    return thresh


def _extract_text_with_tesseract(image: np.ndarray) -> str:
    """Run pytesseract OCR if available; otherwise return empty string."""
    if pytesseract is None:
        return ""
    try:
        processed = preprocess_image_for_ocr(image)
        text = pytesseract.image_to_string(processed)
        return _clean_ocr_text(text)
    except Exception:
        return ""


def extract_certificate_data(image_path):
    # ইমেজ লোড করা
    img = cv2.imread(image_path)
    if img is None:
        return ""

    best_text = ""
    best_score = -1.0

    orientation_candidates = _build_orientation_candidates(img)
    h, w = img.shape[:2]
    max_side = max(h, w)

    # For very large images, restrict attempts to reduce timeout risk.
    if max_side >= 2600:
        orientation_candidates = orientation_candidates[:2]
    else:
        orientation_candidates = orientation_candidates[:3]

    for orientation_idx, (_, oriented_img) in enumerate(orientation_candidates):
        variants = _build_ocr_variants(oriented_img)

        # Keep first orientation exhaustive; use lighter pass for fallbacks to avoid latency spikes.
        if orientation_idx > 0:
            variants = variants[:2]

        # On high-resolution images, keep only the strongest preprocessing variants.
        if max_side >= 2600:
            variants = variants[:1]

        for variant_idx, (_, variant) in enumerate(variants):
            try:
                results = reader.readtext(
                    variant,
                    detail=1,
                    paragraph=False,
                )
                variant_text, avg_confidence = _reconstruct_ocr_lines(results)
                cleaned_text = _clean_ocr_text(variant_text)
                score = _score_ocr_text(cleaned_text, avg_confidence)
                if score > best_score:
                    best_score = score
                    best_text = cleaned_text
                    if best_score >= 0.90:
                        return best_text.strip()
            except Exception:
                continue

            # Optional fallback OCR backend: Tesseract (only for top candidates to limit latency)
            if orientation_idx == 0 and variant_idx <= 1:
                tesseract_text = _extract_text_with_tesseract(variant)
                if tesseract_text:
                    tesseract_score = _score_ocr_text(tesseract_text, 0.45)
                    if tesseract_score > best_score:
                        best_score = tesseract_score
                        best_text = tesseract_text

        # Good-enough early return after primary orientation to avoid long waits.
        if orientation_idx == 0 and best_score >= 0.55 and len(best_text) >= 120:
            return best_text.strip()

    return best_text.strip()


def clean_ocr_text(text: str) -> str:
    """Public text cleaning utility for OCR output."""
    return _clean_ocr_text(text)


def _normalize_for_extraction(text: str) -> str:
    """Normalize OCR text for accurate regex extraction: replace noise, uppercase for matching."""
    t = clean_ocr_text(text)
    t = t.replace('_', ' ')
    t = re.sub(r'\s+', ' ', t)
    return t.upper()


def extract_information(text: str) -> dict:
    """
    Regex-based information extraction for event, organizer, and date.
    Works on uppercased + normalized text for noise-robust matching.
    Returns Not Found values for missing fields.
    """
    cleaned_original = clean_ocr_text(text)
    cleaned_original = re.sub(r'\s+', ' ', cleaned_original).strip()
    normalized = _normalize_for_extraction(text)

    # --- Competition patterns (priority order) ---
    # 1) Label-based extraction first: "Contest: inCSEption 2025"
    labeled_patterns = [
        r'(?:Contest|Event|Competition)\s*[:\-]?\s*([A-Za-z0-9][A-Za-z0-9&.\- ]{1,100}?\b20\d{2}\b)',
        r'(?:Contest|Event|Competition)\s*[:\-]?\s*([A-Za-z0-9][A-Za-z0-9&.\- ]{1,100}?(?:Fest|Festival|Summit|Challenge|Olympiad|Hackathon))',
    ]

    competition = None
    for pat in labeled_patterns:
        m = re.search(pat, cleaned_original, re.IGNORECASE)
        if m:
            competition = m.group(1).strip(' .,:;')
            break

    # 2) Keyword pattern fallback on normalized text
    competition_patterns = [
        # "KUET IUPC 2025" / "BITFEST 2025" / "ROBO CARNIVAL 2025"
        r'\b([A-Z]{2,}\s+IUPC\s+\d{4})\b',
        r'\b([A-Z]{2,}\s+ICPC\s+\d{4})\b',
        r'\b([A-Z]{2,}\s+IUCC\s+\d{4})\b',
        r'\b([A-Z][A-Z0-9& ]{2,40}\s+(?:HACKATHON|OLYMPIAD|CONTEST|COMPETITION|CHAMPIONSHIP|CARNIVAL|SUMMIT|FEST|FESTIVAL|CHALLENGE|BOOTCAMP|WORKSHOP|SEMINAR|CONFERENCE)\s+\d{4})\b',
        r'\b([A-Z][A-Z0-9& ]{2,40}\s+\d{4}\s+(?:HACKATHON|OLYMPIAD|CONTEST|COMPETITION|CHAMPIONSHIP))\b',
        r'\b([A-Z0-9\s]{8,120}(?:CONTEST|COMPETITION|HACKATHON|OLYMPIAD|FEST|FESTIVAL|SUMMIT|CHALLENGE)[A-Z0-9\s]{0,80})\b',
        r'\b([A-Z]{2,}\s+(?:IUPC|ICPC|IUCC)\s*\d{0,4})\b',
        r'\bIN\s+THE\s+([A-Z][A-Z0-9& ]{4,80})\s+EVENT\b',
    ]
    if not competition:
        for pat in competition_patterns:
            m = re.search(pat, normalized)
            if m:
                competition = m.group(1).strip()
                break

    # Prefer a fuller contest phrase when available (e.g., "... INTER UNIVERSITY PROGRAMMING CONTEST").
    if not competition:
        full_competition_match = re.search(
            r'\b([A-Z0-9\s]{8,160}(?:CONTEST|COMPETITION|HACKATHON|OLYMPIAD|FEST|FESTIVAL|SUMMIT|CHALLENGE)[A-Z0-9\s]{0,120}?)'
            r'(?=\s+(?:ORGANIZED|ORGANISED|ARRANGED|CONDUCTED|HOSTED|PRESENTED|DATE|ON|AT)\b|$)',
            normalized,
        )
        if full_competition_match:
            competition = full_competition_match.group(1).strip()

    # --- Organizer pattern: stop at first comma (prevents grabbing ", KUET on ...") ---
    organizer_patterns = [
        r'ORGANIZED BY\s+([^\n]{4,140}?)(?:\bON\b|\bAT\b|\bDATE\b|\bYEAR\b|\bEVENT\b|$)',
        r'ORGANISED BY\s+([^\n]{4,140}?)(?:\bON\b|\bAT\b|\bDATE\b|\bYEAR\b|\bEVENT\b|$)',
        r'CONDUCTED BY\s+([^\n]{4,140}?)(?:\bON\b|\bAT\b|\bDATE\b|\bYEAR\b|\bEVENT\b|$)',
        r'HOSTED BY\s+([^\n]{4,140}?)(?:\bON\b|\bAT\b|\bDATE\b|\bYEAR\b|\bEVENT\b|$)',
        r'ARRANGED BY\s+([^\n]{4,140}?)(?:\bON\b|\bAT\b|\bDATE\b|\bYEAR\b|\bEVENT\b|$)',
        r'PRESENTED BY\s+([^\n]{4,140}?)(?:\bON\b|\bAT\b|\bDATE\b|\bYEAR\b|\bEVENT\b|$)',
    ]
    organizer = None
    for pat in organizer_patterns:
        m = re.search(pat, normalized)
        if m:
            raw_organizer = m.group(1).strip().strip('., ')
            parts = [p.strip().strip('., ') for p in raw_organizer.split(',') if p.strip()]

            if len(parts) >= 2:
                second = re.sub(r'\s+', '', parts[1])
                if re.fullmatch(r'[A-Z]{2,12}', second):
                    organizer = f"{parts[0]}, {parts[1]}"
                else:
                    organizer = parts[0]
            else:
                organizer = parts[0] if parts else raw_organizer
            break

    # Fallback: capture institution-style organizer names when explicit "organized by" is missing.
    if not organizer:
        university_patterns = [
            r'\b((?:DEPT|DEPARTMENT)(?:\s+OF)?\s+[A-Z0-9& ]{2,100},?\s*(?:CUET|KUET|RUET|DUET|BUET|SUST|MIST|UIU|NSU|BRACU|IUT))\b',
            r'\b([A-Z][A-Z\s&]{4,100}\s+UNIVERSITY)\b',
            r'\b([A-Z][A-Z\s&]{4,100}\s+UNIVERSITY\s+OF\s+[A-Z\s]{2,50})\b',
            r'\b([A-Z][A-Z\s&]{4,100}\s+INSTITUTE\s+OF\s+[A-Z\s]{2,50})\b',
        ]
        for pat in university_patterns:
            m = re.search(pat, normalized)
            if m:
                organizer = m.group(1).strip().strip('., ')
                break

    # --- Date: use explicit month names to avoid matching acronyms like "IUPC 2025" ---
    _MONTHS = (
        r'(?:JANUARY|FEBRUARY|MARCH|APRIL|MAY|JUNE|JULY|AUGUST|SEPTEMBER'
        r'|OCTOBER|NOVEMBER|DECEMBER|JAN|FEB|MAR|APR|JUN|JUL|AUG|SEP|SEPT|OCT|NOV|DEC)'
    )
    date_patterns = [
        rf'(\d{{1,2}}\s+{_MONTHS}\s+\d{{4}})',          # 16 January 2025
        rf'({_MONTHS}\s+\d{{1,2}},?\s*\d{{4}})',         # January 16, 2025
        rf'({_MONTHS}\s+\d{{4}})',                        # January 2025
        r'(\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4})',            # 16-01-2025
        r'\b(20\d{2})\b',                                 # 2025 (year only fallback)
    ]
    date = None
    for pat in date_patterns:
        m = re.search(pat, normalized)
        if m:
            date = m.group(1).strip()
            break

    return {
        "Competition": competition if competition else "Not Found",
        "Organizer": organizer if organizer else "Not Found",
        "Date": date if date else "Not Found",
    }


def extract_info(text: str) -> dict:
    """
    Compatibility wrapper for simplified pipeline examples.
    Returns lowercase keys: competition_name, organizer_name, event_date.
    """
    extracted = extract_information(text)
    return {
        "competition_name": extracted.get("Competition", "Not Found"),
        "organizer_name": extracted.get("Organizer", "Not Found"),
        "event_date": extracted.get("Date", "Not Found"),
    }


def _get_spacy_nlp():
    global _SPACY_NLP, _SPACY_LOAD_ATTEMPTED
    if _SPACY_LOAD_ATTEMPTED:
        return _SPACY_NLP

    _SPACY_LOAD_ATTEMPTED = True
    if spacy is None:
        _SPACY_NLP = None
        return None

    for model_name in ("en_core_web_sm", "en_core_web_md"):
        try:
            _SPACY_NLP = spacy.load(model_name)
            return _SPACY_NLP
        except Exception:
            continue

    _SPACY_NLP = None
    return None


def extract_entities_spacy(text: str) -> dict:
    """
    Optional NER extraction for participant name and location.
    Falls back safely when spaCy model is unavailable.
    """
    cleaned = clean_ocr_text(text)
    result = {
        "participant_name": None,
        "location": None,
        "people": [],
        "locations": [],
        "ner_available": False,
    }

    nlp = _get_spacy_nlp()
    if nlp is not None:
        try:
            doc = nlp(cleaned)
            persons = []
            locations = []
            for ent in doc.ents:
                if ent.label_ == "PERSON":
                    persons.append(ent.text.strip())
                elif ent.label_ in {"GPE", "LOC", "FAC"}:
                    locations.append(ent.text.strip())

            dedup_people = list(dict.fromkeys([p for p in persons if len(p) >= 4]))
            dedup_locations = list(dict.fromkeys([l for l in locations if len(l) >= 2]))

            result["people"] = dedup_people
            result["locations"] = dedup_locations
            result["participant_name"] = dedup_people[0] if dedup_people else None
            result["location"] = dedup_locations[0] if dedup_locations else None
            result["ner_available"] = True
            return result
        except Exception:
            pass

    # Regex fallback if NER model is unavailable
    name_patterns = re.findall(r'\b[A-Z][a-z]+\s+[A-Z][a-z]+\b', cleaned)
    if name_patterns:
        result["participant_name"] = name_patterns[0]
        result["people"] = list(dict.fromkeys(name_patterns[:5]))

    location_patterns = [
        r'\bDhaka,?\s*Bangladesh\b',
        r'\bChattogram,?\s*Bangladesh\b',
        r'\bChittagong,?\s*Bangladesh\b',
        r'\bBangladesh\b',
    ]
    for pattern in location_patterns:
        m = re.search(pattern, cleaned, flags=re.IGNORECASE)
        if m:
            result["location"] = m.group(0)
            result["locations"] = [m.group(0)]
            break

    return result


def _preprocess_for_logo_ocr(img_region: np.ndarray) -> np.ndarray:
    """Preprocess logo region to improve OCR readability."""
    gray = cv2.cvtColor(img_region, cv2.COLOR_BGR2GRAY)
    denoised = cv2.fastNlMeansDenoising(gray, None, 10, 7, 21)
    scaled = cv2.resize(denoised, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
    _, thresh = cv2.threshold(scaled, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return thresh


def extract_logo_text(image_path: str) -> str:
    """
    Extract likely logo-area text from certificate image.
    Scans top regions where logos/organizer marks usually appear.
    """
    img = cv2.imread(image_path)
    if img is None:
        return ""

    h, w = img.shape[:2]

    regions = [
        img[: int(h * 0.30), :],  # top full
        img[: int(h * 0.35), : int(w * 0.40)],  # top-left
        img[: int(h * 0.35), int(w * 0.60):],  # top-right
        img[int(h * 0.10): int(h * 0.45), int(w * 0.20): int(w * 0.80)],  # top-center
    ]

    extracted_chunks: List[str] = []
    for region in regions:
        if region.size == 0:
            continue
        try:
            processed = _preprocess_for_logo_ocr(region)
            texts = reader.readtext(processed, detail=0)
            if texts:
                extracted_chunks.append(" ".join(texts))
        except Exception:
            continue

    merged = " ".join(extracted_chunks)
    merged = _clean_ocr_text(merged)

    # De-duplicate repeated tokens from overlapping regions
    tokens = [t for t in re.split(r'\s+', merged) if t]
    dedup_tokens: List[str] = []
    seen = set()
    for token in tokens:
        key = token.lower()
        if key not in seen:
            seen.add(key)
            dedup_tokens.append(token)

    return " ".join(dedup_tokens).strip()


def extract_logo_organizer_name(image_path: str) -> dict:
    """
    Extract organizer name candidate from logo area text.
    Logos often show acronyms (e.g., "BUET", "NSU") — this is detected and stored separately.
    Returns dict with logo_text, organizer_name, and organizer_acronym.
    """
    logo_text = extract_logo_text(image_path)
    organizer_candidate = _heuristic_extract_organizer_name(logo_text)

    # Detect prominent acronym in the first few tokens of the logo text.
    # Logos commonly lead with the institution's short-form (e.g., "BUET", "DU", "NSU").
    detected_acronym: str | None = None
    if logo_text:
        for tok in logo_text.split()[:6]:
            clean = re.sub(r'[\.\-]', '', tok)
            if re.fullmatch(r'[A-Z]{2,8}', clean):
                detected_acronym = clean
                break

    # If heuristic found nothing, try keyword-anchored pattern
    if not organizer_candidate and logo_text:
        org_hint_pattern = (
            r"(?:ICT|Ministry|Department|Division|University|Institute|Foundation|Society|"
            r"Association|Board|Council|Committee|College|Academy)"
            r"[A-Za-z0-9&.,\-/() ]{2,100}"
        )
        match = re.search(org_hint_pattern, logo_text, flags=re.IGNORECASE)
        if match:
            organizer_candidate = match.group(0).strip()

    # Last fallback: if we have an acronym but no full name, use the acronym as the candidate
    if not organizer_candidate and detected_acronym:
        organizer_candidate = detected_acronym

    return {
        "logo_text": logo_text,
        "organizer_name": organizer_candidate,
        "organizer_acronym": detected_acronym,
        "confidence": 1.0 if organizer_candidate else 0.0,
        "reasoning": "Heuristic logo OCR + pattern matching",
        "source": "logo_heuristic",
    }


def _parse_json_object(text: str) -> dict:
    """Parse a JSON object from model response text safely."""
    cleaned = text.strip()
    cleaned = re.sub(r'```json\s*', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'```\s*', '', cleaned, flags=re.IGNORECASE)
    cleaned = cleaned.strip()

    try:
        return json.loads(cleaned)
    except Exception:
        match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', cleaned, flags=re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except Exception:
                pass
    return {}


def extract_logo_organizer_with_model(image_path: str, model_name: str = "models/gemini-flash-latest") -> dict:
    """
    Use one AI model (Gemini Vision) to infer organizer name from certificate logo area.
    Returns dict with organizer_name, confidence, reasoning, and logo_text (fallback OCR text).
    """
    api_key = os.getenv("GEMINI_API_KEY")

    # Keep OCR-based extraction as fallback text source
    heuristic_result = extract_logo_organizer_name(image_path)

    if not api_key:
        return {
            "organizer_name": heuristic_result.get("organizer_name"),
            "confidence": 0.0,
            "reasoning": "GEMINI_API_KEY missing; used OCR fallback for logo area",
            "logo_text": heuristic_result.get("logo_text", ""),
            "source": "logo_ocr_fallback",
        }

    img = cv2.imread(image_path)
    if img is None:
        return {
            "organizer_name": heuristic_result.get("organizer_name"),
            "confidence": 0.0,
            "reasoning": "Image not readable; used OCR fallback for logo area",
            "logo_text": heuristic_result.get("logo_text", ""),
            "source": "logo_ocr_fallback",
        }

    h, w = img.shape[:2]
    top_region = img[: int(h * 0.38), :]
    rgb_region = cv2.cvtColor(top_region, cv2.COLOR_BGR2RGB)
    pil_region = Image.fromarray(rgb_region)

    prompt = """
You are analyzing only the logo/header area of a certificate.
Task: infer the organizer institution/organization name from visible logo text, emblem text, or branding.

Return ONLY valid JSON:
{
  "organizer_name": string or null,
  "confidence": number between 0 and 1,
  "reasoning": "short reason"
}

Rules:
- If unclear, set organizer_name to null.
- Do not add markdown or extra text.
"""

    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(model_name)
        response = _generate_with_retry(model, [prompt, pil_region])
        parsed = _parse_json_object(response.text)

        model_org = parsed.get("organizer_name")
        if isinstance(model_org, str):
            model_org = model_org.strip() or None

        confidence = parsed.get("confidence", 0.0)
        try:
            confidence = float(confidence)
        except Exception:
            confidence = 0.0
        confidence = max(0.0, min(1.0, confidence))

        reasoning = parsed.get("reasoning", "Model inference from logo area")

        # If model is uncertain, fallback to OCR logo candidate
        if (not model_org) and heuristic_result.get("organizer_name"):
            return {
                "organizer_name": heuristic_result.get("organizer_name"),
                "confidence": confidence,
                "reasoning": f"{reasoning}; fallback to OCR logo text",
                "logo_text": heuristic_result.get("logo_text", ""),
                "source": "logo_ocr_fallback",
            }

        return {
            "organizer_name": model_org,
            "confidence": confidence,
            "reasoning": reasoning,
            "logo_text": heuristic_result.get("logo_text", ""),
            "source": "gemini_logo_model",
        }
    except Exception as e:
        return {
            "organizer_name": heuristic_result.get("organizer_name"),
            "confidence": 0.0,
            "reasoning": f"Model extraction failed: {str(e)}; used OCR fallback",
            "logo_text": heuristic_result.get("logo_text", ""),
            "source": "logo_ocr_fallback",
        }


def _is_likely_acronym(s: str) -> bool:
    """True if s looks like an institution acronym: 2-8 uppercase letters (dots/hyphens optional)."""
    clean = re.sub(r'[\.\-]', '', (s or '').strip())
    return bool(re.fullmatch(r'[A-Z]{2,8}', clean))


def _acronym_could_match(short: str, long_name: str) -> bool:
    """
    True if 'short' could be an abbreviation/acronym of words in 'long_name'.
    e.g., _acronym_could_match("BUET", "Bangladesh University of Engineering and Technology") → True
    """
    clean_short = re.sub(r'[\.\-]', '', short.strip()).upper()
    if len(clean_short) < 2:
        return False
    skip = {'the', 'and', 'for', 'of', 'in', 'a', 'an', 'at', 'to', 'is', 'by', 'or'}
    words = [w for w in re.findall(r'[A-Za-z]+', long_name) if w.lower() not in skip]
    if len(words) < 2:
        return False
    initials = ''.join(w[0].upper() for w in words)
    # Accept if acronym is a prefix of initials, or initials starts with all acronym letters
    return initials.startswith(clean_short) or clean_short in initials


def _normalize_org_name(name: str | None) -> str:
    if not name:
        return ""
    normalized = name.lower().strip()
    normalized = re.sub(r'[^a-z0-9\s]', ' ', normalized)
    normalized = re.sub(r'\s+', ' ', normalized)
    return normalized


def _cleanup_org_candidate(candidate: str) -> str:
    cleaned = candidate.strip()
    cleaned = re.sub(r'^[\-:;,\s]+', '', cleaned)
    cleaned = re.sub(r'[\-:;,\s]+$', '', cleaned)
    cleaned = re.sub(r'\s+', ' ', cleaned)

    # Remove common trailing certificate context fragments
    cleaned = re.sub(
        r'\b(?:this certifies|certificate|awarded to|participant|winner|date|held on|venue)\b.*$',
        '',
        cleaned,
        flags=re.IGNORECASE,
    ).strip()

    # Strip trailing address/location fragments that follow the org name
    # e.g., "Military Institute of Science and Technology, Mirpur Cantonment; Dhaka"
    cleaned = re.sub(
        r'[,;]\s*\b(?:cantonment|dhaka|bangladesh|chittagong|sylhet|rajshahi|khulna|'
        r'mirpur|tongi|gazipur|narayanganj|city|country|district|division|'
        r'thana|upazila|road|avenue|street|lane|floor|building|campus)\b.*$',
        '',
        cleaned,
        flags=re.IGNORECASE,
    ).strip()

    # Strip trailing pure numeric / postcode fragments
    cleaned = re.sub(r'[,;\s]+\d{4,}$', '', cleaned).strip()

    return cleaned


def _clean_competition_candidate(candidate: str | None) -> str | None:
    """Normalize noisy competition/event candidates into a concise event title."""
    if not candidate:
        return None

    value = _clean_ocr_text(candidate).strip()
    if not value:
        return None

    # If the text includes organized-by sentence with a quoted event title, prefer quoted title.
    quoted = re.search(
        r"organized by[^\"']*[\"']([^\"']{4,140})[\"']",
        value,
        flags=re.IGNORECASE,
    )
    if quoted:
        value = quoted.group(1).strip()

    # Remove presenter prefixes (e.g., "DSI presents BUP CSE TECH CARNIVAL 2025").
    value = re.sub(r"^[A-Za-z0-9&.\- ]{2,30}\s+presents\s+", "", value, flags=re.IGNORECASE)

    # Remove long sentence lead-ins frequently produced by OCR/LLM extraction.
    value = re.sub(
        r"^(?:this certificate is awarded to|for becoming\s+the\s+champion\s+in\s+the|"
        r"for becoming\s+the|for becoming|organized by)\s*",
        "",
        value,
        flags=re.IGNORECASE,
    )

    # Remove common certificate sentence fragments before the actual event title.
    value = re.sub(r"^for\s+participating\s+in\s+(?:the\s+)?", "", value, flags=re.IGNORECASE)

    # Remove trailing sponsor/chairman/noise fragments.
    value = re.split(
        r"\b(?:title sponsor|co-sponsor|sponsor|chairman|awarded|award|participant|winner)\b",
        value,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0].strip()

    # Drop noisy suffixes often appended by OCR context windows.
    value = re.sub(r"\bevent\s+at\s*$", "", value, flags=re.IGNORECASE).strip()
    value = re.sub(r"\bevent\s*$", "", value, flags=re.IGNORECASE).strip()

    # If text still has a presenter lead-in, keep the event part after "presents".
    value = re.sub(r"^[A-Za-z0-9&.\- ]{2,40}\s+presents\s+", "", value, flags=re.IGNORECASE)

    value = re.sub(r"\s+", " ", value).strip(" .,:;-'\"")

    if len(value) < 4:
        return None
    return value


def _is_weak_organizer_candidate(value: str | None) -> bool:
    """Detect generic/noisy organizer fragments that are likely not real organizers."""
    if not value:
        return True

    normalized = _normalize_org_name(value)
    if not normalized:
        return True

    if normalized in {"inter university", "intra university", "university programming"}:
        return True

    if normalized in {"organizing committee", "organising committee", "committee"}:
        return True

    sentence_starters = (
        "in recognition",
        "this certificate",
        "we applaud",
        "presented to",
        "awarded to",
        "of team",
    )
    if any(normalized.startswith(prefix) for prefix in sentence_starters):
        return True

    sentence_noise = {
        "recognition", "enthusiastic", "commendable", "dedication",
        "contribution", "participation", "effort",
    }
    if sum(1 for token in sentence_noise if token in normalized) >= 2:
        return True

    tokens = [tok for tok in normalized.split() if tok]
    if len(tokens) <= 2 and "university" in tokens and "of" not in tokens:
        return True

    event_like_keywords = {
        "contest", "competition", "hackathon", "olympiad", "championship",
        "festival", "summit", "challenge", "programming", "event",
    }
    strong_org_markers = {
        "ministry", "department", "division", "university", "institute",
        "foundation", "association", "board", "council", "committee",
        "college", "academy", "authority", "commission", "directorate", "faculty",
    }

    has_event_like = any(kw in normalized for kw in event_like_keywords)
    has_strong_org = any(kw in normalized for kw in strong_org_markers)

    if has_event_like and not has_strong_org:
        return True

    if has_event_like and ("university" in normalized and "university of" not in normalized):
        if not any(kw in normalized for kw in {"department", "faculty", "committee", "institute"}):
            return True

    return False


def _competition_name_quality(name: str | None) -> float:
    if not name:
        return 0.0

    value = name.strip()
    if not value:
        return 0.0

    tokens = re.findall(r"[A-Za-z0-9]+", value)
    if not tokens:
        return 0.0

    token_count = len(tokens)
    score = 0.25

    if 2 <= token_count <= 12:
        score += 0.25
    elif token_count > 20:
        score -= 0.20

    keyword_hits = sum(
        1
        for kw in [
            "competition", "contest", "challenge", "summit", "conference",
            "workshop", "hackathon", "symposium", "olympiad", "expo",
            "festival", "tournament", "camp", "program", "programme",
            "championship", "event", "seminar", "bootcamp", "carnival",
        ]
        if re.search(rf"\b{kw}\b", value, flags=re.IGNORECASE)
    )
    score += min(keyword_hits * 0.18, 0.45)

    # Penalize sentence-like overlong phrases.
    if re.search(r"\b(?:this certificate|for becoming|organized by|awarded to)\b", value, flags=re.IGNORECASE):
        score -= 0.25
    if re.search(r"\bprogramming\b", value, flags=re.IGNORECASE) and not re.search(
        r"\b(?:contest|competition|hackathon|olympiad|championship|festival|summit|challenge)\b",
        value,
        flags=re.IGNORECASE,
    ):
        score -= 0.18
    if len(value) > 90:
        score -= 0.20

    return max(0.0, min(1.0, score))


def _clean_organizer_field(candidate: str | None) -> str | None:
    """Clean organizer candidate and remove sponsor/noise fragments."""
    if not candidate:
        return None

    value = _cleanup_org_candidate(candidate)
    if not value:
        return None

    # If sentence-style phrase contains explicit organizer marker, keep the tail entity only.
    marker_split = re.split(
        r"\b(?:conducted by|organized by|organised by|hosted by|presented by)\b",
        value,
        maxsplit=1,
        flags=re.IGNORECASE,
    )
    if len(marker_split) == 2:
        tail = marker_split[1].strip(" :-")
        if tail:
            value = tail

    parts = [p.strip() for p in re.split(r"[,;|]+", value) if p.strip()]
    if not parts:
        return None

    noise_words = {"ltd", "innovators", "sponsor", "co-sponsor", "title", "gaic", "presents"}
    filtered_parts = []
    for part in parts:
        lower = part.lower()
        if any(word in lower for word in noise_words):
            continue
        filtered_parts.append(part)

    parts = filtered_parts or parts

    # If we have a department/faculty part followed by institution part, combine both.
    if len(parts) >= 2:
        first = parts[0].lower()
        second = parts[1].lower()
        if ("department" in first or "faculty" in first) and any(
            k in second for k in ["university", "institute", "college", "academy", "professionals"]
        ):
            combined = f"{parts[0]}, {parts[1]}"
            return combined.strip()

    best = max(parts, key=_organization_name_quality)
    best = best.strip(" .,:;-'\"")
    if not best or _is_weak_organizer_candidate(best):
        return None
    return best


def _pick_better(primary: str | None, secondary: str | None, scorer) -> str | None:
    if primary and not secondary:
        return primary
    if secondary and not primary:
        return secondary
    if not primary and not secondary:
        return None

    p_score = scorer(primary)
    s_score = scorer(secondary)
    return primary if p_score >= s_score else secondary


def _extract_parent_institution(raw_text: str) -> str | None:
    """Extract likely parent institution from raw OCR text."""
    if not raw_text:
        return None

    text = _clean_ocr_text(raw_text)

    # Strong pattern: explicit Bangladesh University of ...
    match = re.search(
        r"(Bangladesh\s+University\s+of\s+[A-Za-z][A-Za-z0-9&.,\-/() ]{2,80})",
        text,
        flags=re.IGNORECASE,
    )
    if match:
        parent = _cleanup_org_candidate(match.group(1))
        parent = re.split(
            r"\b(?:title sponsor|co-sponsor|sponsor)\b",
            parent,
            maxsplit=1,
            flags=re.IGNORECASE,
        )[0].strip(" .,:;-'\"")
        return parent or None

    # Generic institution line
    match = re.search(
        r"((?:[A-Za-z][A-Za-z\-]+\s+){0,3}(?:University|Institute|College|Academy)\s+"
        r"(?:of\s+)?[A-Za-z][A-Za-z0-9&.,\-/() ]{2,80})",
        text,
        flags=re.IGNORECASE,
    )
    if match:
        parent = _cleanup_org_candidate(match.group(1))
        parent = re.split(
            r"\b(?:title sponsor|co-sponsor|sponsor)\b",
            parent,
            maxsplit=1,
            flags=re.IGNORECASE,
        )[0].strip(" .,:;-'\"")
        return parent or None

    return None


def _sanitize_extracted_fields(raw_text: str, fields: dict) -> dict:
    """Reconcile AI/heuristic fields and return cleaner extraction output."""
    heuristic = _extract_fields_heuristic(raw_text)

    ai_comp = _clean_competition_candidate(fields.get("competition_name"))
    h_comp = _clean_competition_candidate(heuristic.get("competition_name"))
    competition_name = _pick_better(ai_comp, h_comp, _competition_name_quality)

    ai_org = _clean_organizer_field(fields.get("organizer_name"))
    h_org = _clean_organizer_field(heuristic.get("organizer_name"))
    organizer_name = _pick_better(ai_org, h_org, _organization_name_quality)
    organizer_name = _canonicalize_organizer_name(organizer_name)

    # If organizer only has a department/faculty, attach parent institution from OCR text.
    if organizer_name and re.search(r"\b(department|faculty|division)\b", organizer_name, flags=re.IGNORECASE):
        parent_org = _extract_parent_institution(raw_text)
        if parent_org and parent_org.lower() not in organizer_name.lower():
            organizer_name = f"{organizer_name}, {parent_org}"

    ai_date = (fields.get("event_date") or "").strip() if fields.get("event_date") else None
    h_date = heuristic.get("event_date")
    event_date = ai_date or h_date

    return {
        "competition_name": competition_name,
        "organizer_name": organizer_name,
        "event_date": event_date,
    }


def _organization_name_quality(name: str | None) -> float:
    if not name:
        return 0.0

    value = name.strip()
    if not value:
        return 0.0

    tokens = re.findall(r'[A-Za-z0-9]+', value)
    if not tokens:
        return 0.0

    token_count = len(tokens)
    # Pure acronyms (e.g., "BUET", "NSU", "DU") are specific identifiers — rate them fairly
    if token_count == 1 and _is_likely_acronym(value):
        return 0.55
    if token_count < 2:
        return 0.1

    score = 0.35

    if 2 <= token_count <= 10:
        score += 0.20

    org_keywords = {
        'ministry', 'department', 'division', 'university', 'institute', 'foundation',
        'society', 'association', 'board', 'council', 'committee', 'college',
        'academy', 'authority', 'commission', 'secretariat', 'school', 'center', 'centre',
        'faculty', 'directorate', 'polytechnic', 'technical',
    }

    normalized = _normalize_org_name(value)
    if any(k in normalized for k in org_keywords):
        score += 0.35

    generic_noise = {
        'certificate', 'competition', 'contest', 'event', 'award', 'winner', 'participation', 'programming'
    }
    if any(word in normalized for word in generic_noise):
        score -= 0.20

    if normalized in {'inter university', 'intra university'}:
        score -= 0.45

    if normalized in {'organizing committee', 'organising committee', 'committee'}:
        score -= 0.40

    if re.search(r'\b(?:contest|competition|hackathon|olympiad|championship|festival|summit|challenge)\b', normalized):
        if not any(k in normalized for k in {'committee', 'department', 'faculty', 'institute'}):
            score -= 0.22

    # Penalize overly long fragments that are likely sentence chunks
    if len(value) > 90:
        score -= 0.20

    return max(0.0, min(1.0, score))


def reconcile_organizer_name(
    ocr_organizer: str | None,
    logo_organizer: str | None,
    logo_acronym: str | None = None,
) -> dict:
    """
    Reconcile organizer names from OCR text and logo text.
    Handles the common case where the logo shows an acronym (e.g., "BUET") while
    the OCR body text may contain the full name.
    Returns final organizer, match metadata, and organizer_acronym if detected.
    """
    raw_ocr_clean = (ocr_organizer or "").strip()
    raw_logo_clean = (logo_organizer or "").strip()
    ocr_clean = _canonicalize_organizer_name(raw_ocr_clean) or raw_ocr_clean
    logo_clean = _canonicalize_organizer_name(raw_logo_clean) or raw_logo_clean
    # Normalise the provided acronym or derive it if logo_clean itself is one
    effective_acronym = logo_acronym or (raw_logo_clean if _is_likely_acronym(raw_logo_clean) else None)

    ocr_valid = bool(ocr_clean) and ocr_clean.lower() != "unknown"
    logo_valid = bool(logo_clean) and logo_clean.lower() != "unknown"

    if not ocr_valid and not logo_valid:
        return {
            "organizer_name": None,
            "organizer_acronym": effective_acronym,
            "source": "none",
            "match_score": 0.0,
            "matched": False,
        }

    if ocr_valid and not logo_valid:
        return {
            "organizer_name": ocr_clean,
            "organizer_acronym": effective_acronym,
            "source": "ocr_only",
            "match_score": 1.0,
            "matched": True,
        }

    if logo_valid and not ocr_valid:
        return {
            "organizer_name": logo_clean,
            "organizer_acronym": effective_acronym,
            "source": "logo_only",
            "match_score": 1.0,
            "matched": True,
        }

    # --- Acronym ↔ full-name matching ---
    # Logo acronym matches OCR full name (most common: logo="BUET", OCR="Bangladesh Univ...")
    if effective_acronym and _acronym_could_match(effective_acronym, ocr_clean):
        return {
            "organizer_name": ocr_clean,       # keep the full name for display
            "organizer_acronym": effective_acronym,
            "source": "ocr_logo_acronym_matched",
            "match_score": 0.9,
            "matched": True,
        }
    # OCR is an acronym that matches the logo full name
    if _is_likely_acronym(ocr_clean) and _acronym_could_match(ocr_clean, logo_clean):
        return {
            "organizer_name": logo_clean,
            "organizer_acronym": ocr_clean,
            "source": "ocr_logo_acronym_matched",
            "match_score": 0.9,
            "matched": True,
        }

    # --- Standard string similarity ---
    normalized_ocr = _normalize_org_name(ocr_clean)
    normalized_logo = _normalize_org_name(logo_clean)
    similarity = SequenceMatcher(None, normalized_ocr, normalized_logo).ratio()

    if similarity >= 0.65:
        final_name = ocr_clean if len(ocr_clean) >= len(logo_clean) else logo_clean
        return {
            "organizer_name": final_name,
            "organizer_acronym": effective_acronym,
            "source": "ocr_logo_matched",
            "match_score": round(similarity, 3),
            "matched": True,
        }

    # Conflict case: choose the higher-quality candidate
    ocr_quality = _organization_name_quality(ocr_clean)
    logo_quality = _organization_name_quality(logo_clean)
    if logo_quality > ocr_quality + 0.1:
        return {
            "organizer_name": logo_clean,
            "organizer_acronym": effective_acronym,
            "source": "logo_preferred_conflict",
            "match_score": round(similarity, 3),
            "matched": False,
        }

    return {
        "organizer_name": ocr_clean,
        "organizer_acronym": effective_acronym,
        "source": "ocr_preferred_conflict",
        "match_score": round(similarity, 3),
        "matched": False,
    }


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
        r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s*\d{4}\b",
        r"\b\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\s+\d{4}\b",
        r"\b\d{1,2}[-]\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\s+\d{4}\b",
        r"\b(?:Date of Issue|Issue Date|Date|Dated|Held on|Event Date)[:\s]+(?:[A-Za-z]+\s+\d{1,2},?\s*\d{4}|\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4})\b",
        r"\b(?:Date|Dated|Held on|Event Date)[:\s]+([\d\-/.\s]+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)?[\w\s,\-]+\d{4})\b",
        r"\b202[0-9]\b",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return match.group(1) if match.lastindex else match.group(0)

    return None


# Compile once — used by _heuristic_extract_organizer_name
_LOCATION_LINE_RE = re.compile(
    r'\b(?:cantonment|dhaka|bangladesh|chittagong|sylhet|rajshahi|khulna|'
    r'mirpur|tongi|gazipur|narayanganj|city|country|district|division|'
    r'thana|upazila|road|avenue|street|lane|floor|building|campus)\b'
    r'|[;]',  # semicolons typically indicate address lines
    re.IGNORECASE,
)
_CERT_STOP_RE = re.compile(
    r'\b(?:certificate|awarded|award|participant|winner|date|held|venue|signature|authorized|seal)\b',
    re.IGNORECASE,
)


_ORGANIZER_ALIAS_MAP = {
    "buet": "Bangladesh University of Engineering and Technology",
    "du": "University of Dhaka",
    "nsu": "North South University",
    "uiu": "United International University",
    "bracu": "BRAC University",
    "iut": "Islamic University of Technology",
    "mist": "Military Institute of Science and Technology",
    "ruet": "Rajshahi University of Engineering and Technology",
    "cuet": "Chittagong University of Engineering and Technology",
    "kuet": "Khulna University of Engineering and Technology",
    "sust": "Shahjalal University of Science and Technology",
}

_ALIASES_CACHE: dict[str, str] | None = None
_ALIASES_CACHE_MTIME: float | None = None


def _get_organizer_alias_file_path() -> str:
    configured = os.getenv("ORGANIZER_ALIAS_DATASET", "").strip()
    if configured:
        return configured
    return os.path.join(os.path.dirname(__file__), "datasets", "organizer_aliases.csv")


def _load_organizer_aliases_from_csv(file_path: str) -> dict[str, str]:
    if not file_path or not os.path.exists(file_path):
        return {}

    loaded: dict[str, str] = {}
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            reader_obj = csv.DictReader(f)
            for row in reader_obj:
                alias = (row.get("alias") or "").strip()
                canonical = (row.get("canonical_name") or "").strip()
                if not alias or not canonical:
                    continue

                normalized_alias = _normalize_org_name(alias)
                condensed_alias = re.sub(r"\s+", "", normalized_alias)

                if normalized_alias:
                    loaded[normalized_alias] = canonical
                if condensed_alias:
                    loaded[condensed_alias] = canonical
    except Exception:
        return {}

    return loaded


def _get_organizer_alias_map() -> dict[str, str]:
    global _ALIASES_CACHE, _ALIASES_CACHE_MTIME

    alias_file = _get_organizer_alias_file_path()
    file_mtime = os.path.getmtime(alias_file) if os.path.exists(alias_file) else None

    if _ALIASES_CACHE is not None and _ALIASES_CACHE_MTIME == file_mtime:
        return _ALIASES_CACHE

    merged = dict(_ORGANIZER_ALIAS_MAP)
    csv_aliases = _load_organizer_aliases_from_csv(alias_file)
    merged.update(csv_aliases)

    _ALIASES_CACHE = merged
    _ALIASES_CACHE_MTIME = file_mtime
    return merged


def _canonicalize_organizer_name(name: str | None) -> str | None:
    if not name:
        return None

    cleaned = _clean_organizer_field(name)
    if not cleaned:
        return None

    normalized = _normalize_org_name(cleaned)
    condensed = re.sub(r"\s+", "", normalized)
    alias_map = _get_organizer_alias_map()

    if condensed in alias_map:
        return alias_map[condensed]

    if normalized in alias_map:
        return alias_map[normalized]

    best_alias = None
    best_score = 0.0
    for alias in alias_map:
        score = SequenceMatcher(None, condensed, re.sub(r"\s+", "", alias)).ratio()
        if score > best_score:
            best_alias = alias
            best_score = score

    if best_alias and best_score >= 0.90:
        return alias_map[best_alias]

    return cleaned


def _line_title_score(line: str) -> float:
    if not line:
        return 0.0

    compact = line.strip()
    if len(compact) < 6 or len(compact) > 130:
        return 0.0

    lowered = compact.lower()
    event_keywords = [
        "competition", "contest", "challenge", "summit", "conference",
        "workshop", "hackathon", "symposium", "olympiad", "expo",
        "festival", "tournament", "camp", "program", "programme",
        "championship", "event", "seminar", "bootcamp", "carnival",
    ]
    noise_tokens = ["this certificate", "awarded to", "organized by", "organised by", "presented by"]

    score = 0.20
    keyword_hits = sum(1 for kw in event_keywords if re.search(rf"\b{kw}\b", lowered))
    score += min(keyword_hits * 0.22, 0.55)

    if re.search(r"\b20\d{2}\b", compact):
        score += 0.10

    letters = re.findall(r"[A-Za-z]", compact)
    if letters:
        upper_ratio = sum(1 for ch in letters if ch.isupper()) / len(letters)
        if upper_ratio >= 0.60:
            score += 0.10

    if any(tok in lowered for tok in noise_tokens):
        score -= 0.25

    return max(0.0, min(1.0, score))


def _heuristic_extract_organizer_name(text: str) -> str | None:
    if not text:
        return None

    # Clean the text first
    text = _clean_ocr_text(text)

    candidates: List[str] = []

    # --- Strategy 0: Explicit organizing committee phrases ---
    for match in re.finditer(
        r'([A-Za-z][A-Za-z0-9&.,\-/() ]{3,140}\b(?:Organizing|Organising|Organzing|Organzing)\s+Committee)\b',
        text,
        flags=re.IGNORECASE,
    ):
        cleaned = _cleanup_org_candidate(match.group(1))
        if len(cleaned) >= 4 and not _is_weak_organizer_candidate(cleaned):
            candidates.append(cleaned)

    for match in re.finditer(
        r'(?:convenor|convener)[^\n]{0,100}[;:,]\s*'
        r'([A-Za-z][A-Za-z0-9&.,\-/() ]{3,140}\b(?:Organizing|Organising|Organzing|Organzing)\s+Committee)\b',
        text,
        flags=re.IGNORECASE,
    ):
        cleaned = _cleanup_org_candidate(match.group(1))
        if len(cleaned) >= 4 and not _is_weak_organizer_candidate(cleaned):
            candidates.append(cleaned)

    # --- Strategy 1: Multi-line capture after "organized by" ---
    # Organizer often spans multiple lines:
    #   "Organized by\nFaculty of Mechanical Engineering\nMilitary Institute of Science and Technology"
    # We grab up to 3 lines after the trigger, stopping at location/certificate lines.
    trigger_match = re.search(
        r'(?:organized by|organised by|organizer|organiser|presented by|hosted by|conducted by)[:\s\-]*',
        text, flags=re.IGNORECASE,
    )
    if trigger_match:
        after_trigger = text[trigger_match.end():]
        lines = [l.strip() for l in after_trigger.split('\n')]
        good_lines: List[str] = []
        for line in lines:
            if not line:
                continue
            if _LOCATION_LINE_RE.search(line) or _CERT_STOP_RE.search(line):
                break
            good_lines.append(line)
            if len(good_lines) >= 3:
                break
        if good_lines:
            combined = ', '.join(good_lines)
            cleaned = _cleanup_org_candidate(combined)
            if len(cleaned) >= 4 and not _is_weak_organizer_candidate(cleaned):
                candidates.append(cleaned)

    # --- Strategy 2: "in collaboration with" / "in association with" ---
    for match in re.finditer(
        r'(?:in collaboration with|in association with)[:\s\-]*'
        r'([A-Za-z][A-Za-z0-9&.,\-/() ]{3,140}?)'
        r'(?=\b(?:date|competition|contest|event|certificate|award|held|venue|for)\b|$)',
        text, flags=re.IGNORECASE,
    ):
        cleaned = _cleanup_org_candidate(match.group(1))
        if len(cleaned) >= 4 and not _is_weak_organizer_candidate(cleaned):
            candidates.append(cleaned)

    # --- Strategy 2.5: direct conducted/presented/hosted by with relaxed stop words ---
    for match in re.finditer(
        r'(?:conducted by|organized by|organised by|hosted by|presented by)[:\s\-]*'
        r'([A-Za-z][A-Za-z0-9&.,\-/() ]{3,140}?)'
        r'(?=\s+(?:held|from|to|with|duration|date|on|at|for)\b|$)',
        text,
        flags=re.IGNORECASE,
    ):
        cleaned = _cleanup_org_candidate(match.group(1))
        if len(cleaned) >= 4 and not _is_weak_organizer_candidate(cleaned):
            candidates.append(cleaned)

    # --- Strategy 2.6: explicit company/org suffix phrases ---
    for match in re.finditer(
        r'([A-Za-z][A-Za-z0-9&.,\-/() ]{2,100}\b(?:Ltd|Limited|Inc|Corporation|Company|University|Institute|College)\b)',
        text,
        flags=re.IGNORECASE,
    ):
        cleaned = _cleanup_org_candidate(match.group(1))
        if len(cleaned) >= 4 and not _is_weak_organizer_candidate(cleaned):
            candidates.append(cleaned)

    # --- Strategy 3: Institution keyword with 0–2 optional qualifier words before it ---
    # Captures "Military Institute", "National University", "Faculty of Engineering", etc.
    # The qualifier allows words like "Military", "National", "Federal" that precede the keyword.
    for match in re.finditer(
        r'((?:[A-Za-z][A-Za-z\-]+ ){0,2}'
        r'(?:Faculty|ICT|Ministry|Department|Division|University|Institute|Foundation|'
        r'Society|Association|Board|Council|Committee|College|Academy|'
        r'Authority|Commission|Directorate|Polytechnic)'
        r'\s+(?:of\s+)?[A-Za-z][A-Za-z0-9&.,\-/() ]{2,100})',
        text, flags=re.IGNORECASE,
    ):
        cleaned = _cleanup_org_candidate(match.group(1))
        if len(cleaned) >= 4 and not _is_weak_organizer_candidate(cleaned):
            candidates.append(cleaned)

    candidates = [c for c in candidates if not _is_weak_organizer_candidate(c)]
    if not candidates:
        return None

    best_candidate = max(candidates, key=_organization_name_quality)
    if _organization_name_quality(best_candidate) < 0.30:
        return None
    return best_candidate


def _heuristic_extract_competition_name(text: str) -> str | None:
    if not text:
        return None
    
    # Clean the text first
    text = _clean_ocr_text(text)
    one_line = re.sub(r'\s+', ' ', text).strip()

    # --- Strategy 0: Prefer explicit "Contest: <title>" style labels ---
    label_match = re.search(
        r'(?:contest|competition|event)\s*[:\-]\s*([A-Za-z0-9][A-Za-z0-9&.,\-/() ]{2,80}(?:\b20\d{2}\b)?)',
        one_line,
        flags=re.IGNORECASE,
    )
    if label_match:
        title = _clean_competition_candidate(label_match.group(1))
        prefix = re.search(
            r'((?:inter|intra)\s+university\s+[A-Za-z0-9&.,\-/() ]{0,80}\b(?:contest|competition)\b)',
            one_line,
            flags=re.IGNORECASE,
        )
        if title and prefix:
            combined = _clean_competition_candidate(f"{prefix.group(1)}: {title}")
            if combined:
                return combined
        if title:
            return title

    # --- Strategy 1: High-confidence contest/competition phrase patterns ---
    high_conf_patterns = [
        r'((?:inter|intra)\s+university\s+[A-Za-z0-9&.,\-/() ]{0,80}\b(?:contest|competition)\b(?:\s*[:\-]\s*[A-Za-z0-9][A-Za-z0-9&.,\-/() ]{2,70})?(?:\s+20\d{2})?)',
        r'([A-Za-z][A-Za-z0-9&.,\-/() ]{4,120}\b(?:contest|competition|hackathon|olympiad|festival|summit|challenge)\b(?:\s*[:\-]\s*[A-Za-z0-9][A-Za-z0-9&.,\-/() ]{2,70})?(?:\s+20\d{2})?)',
    ]
    for pattern in high_conf_patterns:
        match = re.search(pattern, one_line, flags=re.IGNORECASE)
        if match:
            candidate = _clean_competition_candidate(match.group(1))
            if candidate:
                return candidate

    keywords = (
        "competition", "contest", "challenge", "summit", "conference",
        "workshop", "hackathon", "symposium", "olympiad", "expo",
        "festival", "tournament", "camp", "award", "program", "programme",
        "championship", "event", "seminar", "bootcamp", "training", "course", "completion"
    )

    lines = [ln.strip() for ln in text.split('\n') if ln.strip()]
    header_candidates = []
    for ln in lines[:12]:
        cleaned = _clean_competition_candidate(ln)
        if not cleaned:
            continue
        s = _line_title_score(cleaned)
        if s >= 0.42:
            header_candidates.append((cleaned, s))

    if header_candidates:
        header_candidates.sort(key=lambda x: x[1], reverse=True)
        return header_candidates[0][0]

    # High-confidence direct patterns for training/certificate style text
    direct_patterns = [
        r"training on\s+[\"']?([^\"'\n]{4,120})[\"']?(?=\s+(?:in|at|by|conducted|held|from|with)\b|$)",
        r"completed\s+(?:the\s+)?[\"']?([^\"'\n]{4,140}?(?:training|course|program|programme|workshop|bootcamp|certification)[^\"'\n]{0,50})[\"']?(?=\s+(?:in|at|by|conducted|held|from|with)\b|$)",
        r"organized by[^\"']*[\"']([^\"']{4,140})[\"']",
    ]

    for pattern in direct_patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            candidate = _clean_competition_candidate(match.group(1))
            if candidate:
                return candidate

    # Try to find the largest text block containing keywords
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

    return _clean_competition_candidate(best_match)


def _extract_fields_heuristic(raw_text: str) -> dict:
    raw_fields = {
        "competition_name": _heuristic_extract_competition_name(raw_text),
        "organizer_name": _heuristic_extract_organizer_name(raw_text),
        "event_date": _heuristic_extract_event_date(raw_text),
    }
    # Reuse sanitizer for consistent output quality between heuristic and AI paths.
    return {
        "competition_name": _clean_competition_candidate(raw_fields.get("competition_name")),
        "organizer_name": _clean_organizer_field(raw_fields.get("organizer_name")),
        "event_date": raw_fields.get("event_date"),
    }


def extract_certificate_fields_heuristic(raw_text: str) -> dict:
    """
    Heuristic-only extraction (no AI). Always returns a dict with
    competition_name, organizer_name, and event_date keys.
    """
    primary = _extract_fields_heuristic(raw_text)
    regex_info = extract_information(raw_text)

    regex_comp = _clean_competition_candidate(None if regex_info.get("Competition") == "Not Found" else regex_info.get("Competition"))
    regex_org = _clean_organizer_field(None if regex_info.get("Organizer") == "Not Found" else regex_info.get("Organizer"))
    regex_date = None if regex_info.get("Date") == "Not Found" else regex_info.get("Date")

    competition_name = _pick_better(primary.get("competition_name"), regex_comp, _competition_name_quality)
    organizer_name = _pick_better(primary.get("organizer_name"), regex_org, _organization_name_quality)
    organizer_name = _canonicalize_organizer_name(organizer_name)
    event_date = primary.get("event_date") or regex_date

    return {
        "competition_name": competition_name,
        "organizer_name": organizer_name,
        "event_date": event_date,
    }


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
        parsed = _parse_gemini_json(response.text)
        return _sanitize_extracted_fields(raw_text, parsed)
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

    collected_info = ""
    if search_results:
        collected_info += f"Found {len(search_results)} search results:\n"
        for i, url in enumerate(search_results[:10], 1):
            collected_info += f"{i}. {url}\n"
    else:
        collected_info += "No search results found.\n"

    if scraped_content:
        collected_info += f"\n--- SCRAPED WEB CONTENT (from {len(scraped_content)} websites) ---\n"
        for i, data in enumerate(scraped_content[:3], 1):
            collected_info += f"\nSource {i}: {data['url']}\n"
            collected_info += f"{data['content'][:1000]}...\n"
    else:
        collected_info += "\nNo web content was scraped.\n"

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
        response = _generate_with_retry(model, verification_prompt)
        result = parse_ai_response(response.text)

        if "status" not in result:
            result["status"] = "Suspicious"
        if "accuracy_score" not in result:
            result["accuracy_score"] = 0
        if "reasoning" not in result:
            result["reasoning"] = "Unable to verify certificate authenticity"
        if "match_found" not in result:
            result["match_found"] = False

        result["probability"] = result["accuracy_score"] / 100.0
        result["is_authentic"] = result["status"] == "Verified"
        result["reasons"] = [result["reasoning"]]
        result["ai_available"] = True
        return json.dumps(result, indent=2)

    except Exception as e:
        error_text = str(e)
        if _is_leaked_or_blocked_api_key_error(error_text):
            reasoning = "Gemini API key is blocked/leaked. AI verification disabled; using rule-based verification."
            reasons = ["Gemini API key issue", "Rotate key and update .env GEMINI_API_KEY"]
        else:
            reasoning = "AI verification is temporarily unavailable; using rule-based verification."
            reasons = [f"Error: {error_text}"]

        fallback_result = {
            "status": "Suspicious",
            "accuracy_score": 0,
            "reasoning": reasoning,
            "match_found": False,
            "probability": 0.0,
            "is_authentic": False,
            "reasons": reasons,
            "ai_available": False,
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

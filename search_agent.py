from urllib.parse import urlparse
import requests
from bs4 import BeautifulSoup
import time
import os
import re
from dotenv import load_dotenv

try:
	from trafilatura import fetch_url, extract
	TRAFILATURA_AVAILABLE = True
except:
	TRAFILATURA_AVAILABLE = False

# Load environment variables
load_dotenv()

try:
	import google.generativeai as genai
	GEMINI_AVAILABLE = True
except:
	GEMINI_AVAILABLE = False

try:
	from googlesearch import search as google_search
	GOOGLE_SEARCH_AVAILABLE = True
except:
	GOOGLE_SEARCH_AVAILABLE = False

try:
	from exa_py import Exa
	EXA_AVAILABLE = True
except:
	EXA_AVAILABLE = False

try:
	from serpapi import GoogleSearch as SerpApiGoogleSearch
	SERPAPI_AVAILABLE = True
except:
	SERPAPI_AVAILABLE = False


def _search_serpapi(query: str, num_results: int = 5) -> list[str]:
	"""
	Search using SerpAPI Google engine.
	Requires SERPAPI_API_KEY or SERP_API_KEY in environment.
	"""
	urls = []
	print(f"   🔍 Trying SerpAPI...")

	if not SERPAPI_AVAILABLE:
		print("   ⚠️ SerpAPI package not available (install: google-search-results)")
		return urls

	api_key = os.getenv('SERPAPI_API_KEY') or os.getenv('SERP_API_KEY')
	if not api_key:
		print("   ⚠️ SerpAPI key not found (set SERPAPI_API_KEY or SERP_API_KEY)")
		return urls

	try:
		params = {
			"q": query,
			"api_key": api_key,
			"engine": "google",
			"num": num_results,
		}
		search = SerpApiGoogleSearch(params)
		results = search.get_dict()

		for item in results.get("organic_results", [])[:num_results]:
			link = item.get("link")
			if link and link.startswith("http"):
				urls.append(link)

		if urls:
			print(f"   ✅ SerpAPI found {len(urls)} results")
	except Exception as e:
		print(f"   ⚠️ SerpAPI failed: {e}")

	return list(dict.fromkeys(urls))


def web_search(query: str, max_results: int = 5) -> list[str]:
	"""
	Simple query-based web search helper.
	Priority: SerpAPI -> Serper -> DuckDuckGo/Google fallback.
	"""
	if not query or not query.strip():
		return []

	results = _search_serpapi(query, num_results=max_results)
	if results:
		return results[:max_results]

	results = _search_serper(query, num_results=max_results)
	if results:
		return results[:max_results]

	results = _search_duckduckgo(query, num_results=max_results)
	return list(dict.fromkeys(results))[:max_results]


def _search_serper(query: str, num_results: int = 5) -> list[str]:
	"""
	Search using Serper API (Google Search API)
	Fast, reliable, no blocking. Get API key from: https://serper.dev
	
	Args:
		query (str): Search query
		num_results (int): Number of results to fetch
	
	Returns:
		list[str]: List of URLs from Google search
	"""
	urls = []
	print(f"   🔍 Trying Serper API (Google Search)...")
	
	try:
		api_key = os.getenv('SERPER_API_KEY')
		if not api_key:
			print(f"   ⚠️ Serper API key not found (set SERPER_API_KEY in .env)")
			return urls
		
		headers = {
			'X-API-KEY': api_key,
			'Content-Type': 'application/json'
		}
		
		payload = {
			'q': query,
			'num': num_results
		}
		
		response = requests.post(
			'https://google.serper.dev/search',
			headers=headers,
			json=payload,
			timeout=10
		)
		
		if response.status_code == 200:
			data = response.json()
			
			# Extract URLs from organic results
			if 'organic' in data:
				for result in data['organic'][:num_results]:
					if 'link' in result:
						urls.append(result['link'])
			
			if urls:
				print(f"   ✅ Serper found {len(urls)} results")
			else:
				print(f"   ⚠️ Serper returned no results")
		else:
			print(f"   ⚠️ Serper API error: {response.status_code}")
			
	except Exception as e:
		print(f"   ⚠️ Serper API failed: {e}")
	
	return urls


def _search_gemini_grounded(query: str, num_results: int = 5) -> list[str]:
	"""
	Search using Gemini with Google Search Grounding.
	Gemini automatically searches the web and returns grounded results.
	
	Args:
		query (str): Search query
		num_results (int): Number of results to fetch
	
	Returns:
		list[str]: List of URLs from grounded search
	"""
	urls = []
	print(f"   🔍 Trying Gemini with Google Search Grounding...")
	
	if not GEMINI_AVAILABLE:
		print(f"   ⚠️ Gemini not available (install: pip install google-generativeai)")
		return urls
	
	try:
		api_key = os.getenv('GEMINI_API_KEY')
		if not api_key:
			print(f"   ⚠️ Gemini API key not found (set GEMINI_API_KEY environment variable)")
			return urls
		
		genai.configure(api_key=api_key)
		
		# Use Gemini with Google Search grounding
		model = genai.GenerativeModel(
			model_name='gemini-2.5-flash',
			tools='google_search_retrieval'  # Enable Google Search grounding
		)
		
		prompt = f"""
		Search for information about: {query}
		
		Find relevant websites, pages, or sources that mention this organization, event, or competition.
		Return a list of URLs that are relevant.
		"""
		
		response = model.generate_content(prompt)
		
		# Extract URLs from grounded search results
		if hasattr(response, 'candidates') and response.candidates:
			for candidate in response.candidates:
				if hasattr(candidate, 'grounding_metadata'):
					metadata = candidate.grounding_metadata
					if hasattr(metadata, 'grounding_chunks'):
						for chunk in metadata.grounding_chunks:
							if hasattr(chunk, 'web') and hasattr(chunk.web, 'uri'):
								urls.append(chunk.web.uri)
		
		# Also extract URLs from the response text
		if response.text:
			url_pattern = r'https?://[^\s<>"\)\]]+'
			found_urls = re.findall(url_pattern, response.text)
			urls.extend(found_urls)
		
		# Remove duplicates
		urls = list(dict.fromkeys(urls))
		
		if urls:
			print(f"   ✅ Gemini grounded search found {len(urls)} results")
			return urls[:num_results]
		
	except Exception as e:
		print(f"   ⚠️ Gemini grounded search failed: {e}")
	
	return urls


def _search_exa(query: str, num_results: int = 5) -> list[str]:
	"""
	Search using Exa.ai neural search API (AI-powered semantic search)
	
	Args:
		query (str): Search query
		num_results (int): Number of results to fetch
	
	Returns:
		list[str]: List of URLs
	"""
	urls = []
	print(f"   🔍 Trying Exa.ai neural search...")
	
	if not EXA_AVAILABLE:
		print(f"   ⚠️ Exa.ai not available (install: pip install exa-py)")
		return urls
	
	try:
		# Get API key from environment or use default
		api_key = os.getenv('EXA_API_KEY')
		if not api_key:
			print(f"   ⚠️ Exa.ai API key not found (set EXA_API_KEY environment variable)")
			return urls
		
		exa = Exa(api_key=api_key)
		
		# Perform neural search optimized for events/organizations
		results = exa.search(
			query,
			num_results=num_results,
			type="neural",  # Use neural search for semantic understanding
			use_autoprompt=True  # Let Exa optimize the query
		)
		
		for result in results.results:
			if result.url and result.url.startswith('http'):
				urls.append(result.url)
		
		if urls:
			print(f"   ✅ Exa.ai found {len(urls)} results")
		return urls
		
	except Exception as e:
		print(f"   ⚠️ Exa.ai search failed: {e}")
	
	return urls


def _search_duckduckgo(query: str, num_results: int = 10) -> list[str]:
	"""
	Multi-engine search: Gemini Grounded → Exa.ai → Google → DuckDuckGo API → Bing scraping
	"""
	urls = []
	
	# Try Method 0: Gemini with Google Search Grounding (PRIMARY - Most Accurate)
	gemini_results = _search_gemini_grounded(query, num_results=5)
	if gemini_results:
		return gemini_results
	
	# Try Method 1: Exa.ai Neural Search (SECONDARY - Best quality)
	exa_results = _search_exa(query, num_results=5)
	if exa_results:
		return exa_results
	
	# Try Method 2: Google Search (FALLBACK)
	if GOOGLE_SEARCH_AVAILABLE:
		try:
			print(f"   🔍 Trying Google search...")
			search_count = 0
			for url in google_search(query, num_results=num_results, sleep_interval=1):
				# Filter valid URLs
				if url and url.startswith('http'):
					urls.append(url)
					search_count += 1
					if search_count >= num_results:
						break
			
			if urls:
				print(f"   ✅ Google found {len(urls)} results")
				return urls
				
		except Exception as e:
			print(f"   ⚠️ Google search failed: {e}")
	
	# Try Method 2: DuckDuckGo API
	try:
		print(f"   🔍 Trying DuckDuckGo API...")
		headers = {
			'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
		}
		
		from urllib.parse import quote
		encoded_query = quote(query)
		
		search_url = f"https://api.duckduckgo.com/?q={encoded_query}&format=json"
		response = requests.get(search_url, headers=headers, timeout=10)
		response.raise_for_status()
		
		data = response.json()
		
		# Extract URLs from Results
		if 'Results' in data:
			for result in data['Results'][:num_results]:
				if 'FirstURL' in result:
					urls.append(result['FirstURL'])
				elif 'URL' in result:
					urls.append(result['URL'])
		
		# Also check RelatedTopics
		if 'RelatedTopics' in data and len(urls) < num_results:
			for topic in data['RelatedTopics']:
				if isinstance(topic, dict) and 'FirstURL' in topic:
					urls.append(topic['FirstURL'])
				if len(urls) >= num_results:
					break
		
		if urls:
			print(f"   ✅ DuckDuckGo found {len(urls)} results")
			return urls
			
	except Exception as e:
		print(f"   ⚠️ DuckDuckGo failed: {e}")
	
	# Try Method 3: Bing search (extract actual URLs, not Bing redirect links)
	try:
		print(f"   🔍 Trying Bing search...")
		from urllib.parse import quote, urlparse, parse_qs
		encoded_query = quote(query)
		
		headers = {
			'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
		}
		
		search_url = f"https://www.bing.com/search?q={encoded_query}"
		response = requests.get(search_url, headers=headers, timeout=10)
		
		if response.status_code == 200:
			soup = BeautifulSoup(response.content, 'html.parser')
			
			# Find actual result links (not Bing tracking URLs)
			for link in soup.find_all('a', href=True):
				href = link['href']
				
				# Extract actual URL from Bing redirect
				if '/ck/a?' in href and '&u=' in href:
					try:
						# Parse Bing URL
						parsed = urlparse(href)
						params = parse_qs(parsed.query)
						if 'u' in params:
							actual_url = params['u'][0]
							# Decode URL if needed
							if actual_url.startswith('a1'):
								import base64
								actual_url = base64.b64decode(actual_url[2:]).decode('utf-8')
							
							if actual_url.startswith('http'):
								urls.append(actual_url)
					except:
						continue
				
				# Also check for direct http links
				elif href.startswith('http') and 'bing.com' not in href and 'microsoft.com' not in href:
					urls.append(href)
				
				if len(urls) >= num_results:
					break
			
			# Remove duplicates while preserving order
			urls = list(dict.fromkeys(urls))
			
			if urls:
				print(f"   ✅ Bing found {len(urls)} results")
				return urls
				
	except Exception as e:
		print(f"   ⚠️ Bing search failed: {e}")
	
	print(f"   ❌ All search methods exhausted")
	return urls


def _extract_main_keywords(text: str) -> list[str]:
	"""
	Extract main keywords using progressive phrase lengths.
	Starts with 2 words, then 3 words, then increases word count.
	"""
	if not text:
		return []
	
	import re
	
	keywords = []
	text = text.strip()
	
	# Extract year if present
	year_match = re.search(r'\b(202\d|201\d)\b', text)
	year = year_match.group(1) if year_match else None
	
	# Remove common filler words
	text_clean = text.replace(" AND ", " ").replace(" OF ", " ").replace(" THE ", " ")
	
	# Split into words
	words = text_clean.split()
	
	# Strategy: Start with 2 words, then 3 words, then increase word count
	max_len = min(len(words), 6)
	for n in range(2, max_len + 1):
		phrase = " ".join(words[:n])
		keywords.append(phrase)
		if year and year not in phrase:
			keywords.append(f"{phrase} {year}")
	
	# If there are multiple parts (separated by AND), try second part progressively too
	parts = text.split(" AND ")
	if len(parts) > 1:
		second_words = parts[1].strip().split()
		if len(second_words) >= 2:
			second_max_len = min(len(second_words), 6)
			for n in range(2, second_max_len + 1):
				phrase = " ".join(second_words[:n])
				keywords.append(phrase)
				if year and year not in phrase:
					keywords.append(f"{phrase} {year}")
	
	# Remove duplicates while preserving order
	seen = set()
	unique_keywords = []
	for kw in keywords:
		kw_lower = kw.lower()
		if kw_lower not in seen:
			seen.add(kw_lower)
			unique_keywords.append(kw)
	
	return unique_keywords


def _is_target_domain(url: str) -> bool:
	try:
		netloc = urlparse(url).netloc.lower()
	except Exception:
		return False

	if netloc.startswith("www."):
		netloc = netloc[4:]

	return (
		netloc.endswith("facebook.com")
		or netloc.endswith("linkedin.com")
		or netloc.endswith(".gov")
		or netloc.endswith(".edu")
	)


def _is_bangladesh_domain(url: str) -> bool:
	try:
		netloc = urlparse(url).netloc.lower()
	except Exception:
		return False

	if netloc.startswith("www."):
		netloc = netloc[4:]

	bd_suffixes = (
		".bd",
		".gov.bd",
		".edu.bd",
		".org.bd",
		".com.bd",
		".net.bd",
		".ac.bd",
	)

	return netloc.endswith(bd_suffixes)


def search_competition_sources(competition_name: str, organizer: str, max_results: int = 10) -> list[str]:
	"""
	Search Google for competition-related sources and return matching URLs.

	Targets: Facebook, LinkedIn, .gov, .edu
	"""
	query = f"\"{competition_name}\" \"{organizer}\""
	results = []
	seen = set()

	if not GOOGLE_SEARCH_AVAILABLE:
		return results

	for url in google_search(query, num_results=max_results, sleep_interval=1):
		if url in seen:
			continue
		seen.add(url)

		if _is_target_domain(url):
			results.append(url)

	return results


def _normalize_search_text(text: str) -> str:
	text = re.sub(r'[^A-Za-z0-9\s&.-]', ' ', text or '')
	text = re.sub(r'\s+', ' ', text).strip()
	return text


def _extract_institution_focus(name: str | None) -> str:
	"""Pick the most institution-like segment from a noisy organizer string."""
	if not name:
		return ""

	raw = re.sub(r'[\r\n]+', ' | ', name)
	raw_parts = [p.strip() for p in re.split(r'[,|/;]+', raw) if p.strip()]
	parts = [_normalize_search_text(p) for p in raw_parts if _normalize_search_text(p)]
	if not parts:
		fallback = _normalize_search_text(name)
		parts = [fallback] if fallback else []
	if not parts:
		return ""

	strong_keywords = {
		"institute", "university", "college", "academy", "school",
		"ministry", "department", "directorate", "authority", "commission",
		"board", "council", "society", "association", "foundation",
		"secretariat", "polytechnic", "technical",
	}
	weak_keywords = {"faculty", "division", "center", "centre", "committee"}

	def _score(part: str) -> int:
		lower = part.lower()
		score = 0
		if re.fullmatch(r'[A-Z]{2,8}', part.strip()):
			score += 7
		if any(k in lower for k in strong_keywords):
			score += 4
		if any(k in lower for k in weak_keywords):
			score += 1
		if "department" in lower and not any(k in lower for k in {"institute", "university", "college", "academy"}):
			score -= 2
		# Prefer pure institution chunk over department/faculty heading
		if "faculty" in lower and not any(k in lower for k in {"institute", "university", "college"}):
			score -= 1
		tok_count = len(part.split())
		if 2 <= tok_count <= 10:
			score += 2
		if tok_count > 12:
			score -= 2
		return score

	best = max(parts, key=_score)
	best = re.sub(r'^\s*(?:by\s+the|by)\s+', '', best, flags=re.IGNORECASE)
	return " ".join(best.split()[:8])


_NON_INSTITUTION_ACRONYMS = {
	"CSE", "EEE", "BBA", "MBA", "IT", "ICT", "AI", "ML", "CS", "EE", "ME", "CE",
}

_EVENT_OR_NOISE_ACRONYMS = {
	"TECH", "CARNIVAL", "CONTEST", "CP", "PC", "EVENT", "FEST", "FESTIVAL",
	"TITLE", "SPONSOR", "PRESENTS", "PRESENTED", "CHAMPION", "WINNER", "AWARD",
}

_PREPOSITION_WORDS = {
	"ON", "OF", "IN", "AT", "BY", "TO", "FOR", "AND", "OR", "THE", "IS", "BE",
	"IT", "OR", "UP", "DO", "GO", "NO", "IF", "AS", "WE", "HE", "SO", "MY", "AN",
}

_PREFERRED_INSTITUTION_ACRONYMS = {
	"BUP", "BUET", "KUET", "RUET", "CUET", "MIST", "DU", "JU", "CU", "SUST",
	"IUT", "NSU", "DIU", "AIUB", "BRAC", "IUB", "UIU", "AUST", "EWU", "UAP",
}

_KNOWN_INSTITUTION_NAME_TO_ACRONYM = {
	"military institute of science and technology": "MIST",
	"bangladesh university of engineering and technology": "BUET",
	"khulna university of engineering and technology": "KUET",
	"chittagong university of engineering and technology": "CUET",
	"rajshahi university of engineering and technology": "RUET",
	"university of dhaka": "DU",
	"united international university": "UIU",
	"north south university": "NSU",
	"brac university": "BRAC",
	"islamic university of technology": "IUT",
	"american international university bangladesh": "AIUB",
	"daffodil international university": "DIU",
}


def _is_generic_organizer_label(name: str | None) -> bool:
	if not name:
		return True
	lower = name.lower().strip()
	return bool(re.fullmatch(r'(department|dept|faculty|division)(?:\s+of\s+[a-z0-9& ]+)?', lower))


def _extract_parent_identity_from_competition(competition_name: str | None) -> tuple[str | None, str | None]:
	"""Infer parent institution acronym/name from competition title (e.g. 'BUP CSE TECH CARNIVAL 2025')."""
	if not competition_name:
		return None, None

	tokens = re.findall(r'\b[A-Z]{2,8}\b', competition_name.upper())
	preferred = [tok for tok in tokens if tok in _PREFERRED_INSTITUTION_ACRONYMS]
	if preferred:
		acronym = preferred[0]
		return acronym, acronym

	# Fallback: first non-noise acronym-like token in the competition name.
	# Filter out prepositions, short words, and other noise
	for tok in tokens:
		if (tok not in _NON_INSTITUTION_ACRONYMS 
			and tok not in _EVENT_OR_NOISE_ACRONYMS 
			and tok not in _PREPOSITION_WORDS
			and not re.fullmatch(r'20\d{2}', tok)):
			return tok, tok

	return None, None


def _extract_explicit_acronym(text: str | None) -> str | None:
	"""Extract explicit uppercase acronym token from noisy text, preferring right-most token (often parent institution)."""
	if not text:
		return None

	candidates = re.findall(r'\b[A-Z]{2,8}\b', text)
	if not candidates:
		return None

	# Strong preference for common institution acronyms.
	preferred_hits = [token for token in candidates if token in _PREFERRED_INSTITUTION_ACRONYMS]
	if preferred_hits:
		return preferred_hits[-1]

	filtered = [
		token for token in candidates
		if token not in _NON_INSTITUTION_ACRONYMS
		and token not in _EVENT_OR_NOISE_ACRONYMS
		and not re.fullmatch(r'20\d{2}', token)
	]
	if filtered:
		return filtered[-1]
	return None


def _derive_acronym_from_name(name: str | None) -> str | None:
	"""Derive acronym from multi-word institution name (e.g., Military Institute of Science and Technology -> MIST)."""
	if not name:
		return None

	words = re.findall(r'[A-Za-z]+', name)
	if len(words) < 2:
		return None

	skip = {"the", "and", "for", "of", "in", "a", "an", "at", "to", "by"}
	initials = [w[0].upper() for w in words if w.lower() not in skip and len(w) > 1]
	if len(initials) < 2:
		return None

	acronym = "".join(initials)
	if 2 <= len(acronym) <= 8:
		return acronym
	return None


def _infer_known_acronym_from_name(name: str | None) -> str | None:
	"""Infer acronym from known institution full names embedded in noisy organizer text."""
	if not name:
		return None

	lowered = re.sub(r'\s+', ' ', name.lower()).strip()
	
	# First try exact substring match
	for full_name, acronym in _KNOWN_INSTITUTION_NAME_TO_ACRONYM.items():
		if full_name in lowered:
			return acronym
	
	# Fallback: check for key phrase patterns (first 3+ words + critical words)
	# This handles truncated names like "Military Institute of Science" -> matches "military institute of science and technology"
	key_patterns = {
		"military institute of science": "MIST",
		"bangladesh university of engineering": "BUET",
		"khulna university of engineering": "KUET",
		"chittagong university of engineering": "CUET",
		"rajshahi university of engineering": "RUET",
		"university of dhaka": "DU",
		"united international": "UIU",
		"north south": "NSU",
		"brac university": "BRAC",
		"islamic university of": "IUT",
		"american international": "AIUB",
		"daffodil international": "DIU",
	}
	
	for key_phrase, acronym in key_patterns.items():
		if key_phrase in lowered:
			return acronym
	
	return None


def _probe_url_reachable(url: str, timeout: int = 4) -> str | None:
	"""Return final URL if reachable, else None."""
	try:
		resp = requests.get(url, timeout=timeout, allow_redirects=True)
		if resp.status_code < 400 and resp.url:
			return resp.url
	except Exception:
		return None
	return None


def _discover_official_domain_candidates(acronym: str | None) -> list[str]:
	"""Guess likely Bangladesh institutional domains from acronym and keep reachable ones."""
	if not acronym:
		return []

	base = acronym.strip().lower()
	if not re.fullmatch(r'[a-z]{2,10}', base):
		return []

	guesses = [
		f"https://{base}.ac.bd",
		f"https://www.{base}.ac.bd",
		f"https://{base}.edu.bd",
		f"https://www.{base}.edu.bd",
		f"https://{base}.org.bd",
		f"https://www.{base}.org.bd",
	]

	found = []
	seen = set()
	for url in guesses:
		resolved = _probe_url_reachable(url)
		if resolved and resolved not in seen:
			seen.add(resolved)
			found.append(resolved)

	return found


def _build_official_domain_guesses(acronym: str | None) -> list[str]:
	"""Build likely institutional domains from acronym without network probing."""
	if not acronym:
		return []

	base = acronym.strip().lower()
	if not re.fullmatch(r'[a-z]{2,10}', base):
		return []

	guesses = [
		f"https://{base}.edu.bd",
		f"https://www.{base}.edu.bd",
  		f"https://{base}.ac.bd",
		f"https://www.{base}.ac.bd",
		f"https://{base}.org.bd",
		f"https://www.{base}.org.bd",
	]
	return list(dict.fromkeys(guesses))


def _identity_tokens_from_organizer(name: str | None) -> list[str]:
	"""Extract strong organizer-identity tokens for URL filtering."""
	if not name:
		return []

	stop = {
		"the", "and", "for", "of", "in", "a", "an", "at", "to", "by",
		"department", "faculty", "division", "center", "centre", "committee",
		"official", "bangladesh", "ltd", "limited", "company",
		"business", "technology", "engineering", "training", "academy", "international",
	}
	tokens = [t.lower() for t in re.findall(r"[A-Za-z]{3,}", name)]
	strong = [t for t in tokens if t not in stop]

	# Keep only top distinct tokens to avoid over-constraining.
	seen = set()
	result = []
	for token in strong:
		if token not in seen:
			seen.add(token)
			result.append(token)
		if len(result) >= 5:
			break
	return result


def _filter_urls_by_identity(
	urls: list[str],
	organizer_name: str | None,
	competition_name: str | None,
	acronym: str | None,
) -> list[str]:
	"""Remove unrelated URLs by requiring organizer/acronym identity signals."""
	if not urls:
		return []

	def _is_irrelevant_commercial_url(url: str) -> bool:
		url_lower = url.lower()
		try:
			netloc = urlparse(url).netloc.lower().replace("www.", "")
		except Exception:
			netloc = ""
		noise_signals = [
			"/forex", "/remittance", "/personal-banking", "/global-markets",
			"aftermarket", "lasercare", "leathers", "-display", "display.com",
			"/shop", "ecommerce", "addressbazar", "dhl",
		]
		if any(signal in url_lower for signal in noise_signals):
			return True
		if re.search(r"(^|[.-])(shop|store|market|bazar|bank)([.-]|$)", netloc):
			return True
		return False

	organizer_tokens = _identity_tokens_from_organizer(organizer_name)
	acronym_token = (acronym or "").strip().lower()
	weak_acronym = bool(acronym_token) and len(acronym_token) <= 2
	competition_noise_tokens = {
		"inter", "intra", "university", "programming", "programminc", "contest", "competition",
		"event", "we", "applaud", "dedication", "contribution", "prestigious", "certificate",
		"presented", "participation", "enthusiastic", "your", "this", "that", "with", "from",
	}
	competition_tokens = [
		t.lower()
		for t in re.findall(r"[A-Za-z]{4,}", competition_name or "")
		if t.lower() not in {"competition", "contest", "event", "program", "programme", "training", "course"}
		and t.lower() not in competition_noise_tokens
	][:4]

	filtered = []
	for url in urls:
		url_lower = url.lower()
		if _is_irrelevant_commercial_url(url):
			continue

		organizer_match_count = sum(1 for tok in organizer_tokens if tok in url_lower)
		organizer_match = organizer_match_count >= 2 or any(
			(tok in url_lower and len(tok) >= 8) for tok in organizer_tokens
		)
		acronym_match = bool(acronym_token and acronym_token in url_lower)
		strong_acronym_match = bool(acronym_token and len(acronym_token) >= 3 and acronym_token in url_lower)
		competition_match_count = sum(1 for tok in competition_tokens if tok in url_lower)
		competition_match = competition_match_count > 0
		has_event_path_hint = any(h in url_lower for h in ("event", "contest", "competition", "iupc", "icpc", "bitfest"))

		try:
			netloc = urlparse(url).netloc.lower().replace("www.", "")
		except Exception:
			netloc = ""

		is_bd_trusted = netloc.endswith((".ac.bd", ".edu.bd", ".gov.bd", ".org.bd"))
		is_social_event = any(domain in netloc for domain in ("facebook.com", "linkedin.com", "youtube.com", "youtu.be"))

		# Reject weak 2-letter acronym-only matches unless there is additional evidence.
		if weak_acronym and acronym_match and not (organizer_match or competition_match or is_bd_trusted):
			continue

		# Strong keep: organizer token appears in URL.
		if organizer_match:
			filtered.append(url)
			continue

		# Acronym-only keep can be noisy on generic commercial domains.
		if strong_acronym_match and (is_bd_trusted or is_social_event or competition_match_count >= 2 or has_event_path_hint):
			filtered.append(url)
			continue

		# For weak acronym (e.g., HL), require competition context or trusted Bangladesh domain.
		if weak_acronym and acronym_match and (competition_match or is_bd_trusted):
			filtered.append(url)
			continue

		# Soft keep for Bangladesh academic/government domains only with stronger event evidence.
		# One weak token (e.g., "inter") must not pass this check.
		if is_bd_trusted and (competition_match_count >= 2 or has_event_path_hint):
			filtered.append(url)
			continue

		# Keep social/event pages when they clearly match competition keywords.
		if is_social_event and competition_match:
			filtered.append(url)

	# If strict filter is too harsh, keep only weakly relevant URLs rather than unrelated first-page noise.
	if filtered:
		return list(dict.fromkeys(filtered))

	weak = []
	for url in urls:
		url_lower = url.lower()
		if _is_irrelevant_commercial_url(url):
			continue
		if any(tok in url_lower for tok in competition_tokens if len(tok) >= 4):
			weak.append(url)
			continue
		# Do not trust short acronyms alone in fallback (e.g., HL) — too noisy.
		if acronym_token and len(acronym_token) >= 3 and acronym_token in url_lower:
			weak.append(url)

	if weak:
		return list(dict.fromkeys(weak))[: min(5, len(weak))]
	return []


_CERT_STOPWORDS = frozenset({
	# Generic certificate words — useless for org search
	"certificate", "participation", "achievement", "completion", "recognition",
	"award", "awarded", "presented", "honors", "honour", "honor",
	# Generic event/competition words
	"national", "international", "contest", "competition", "programming",
	"hackathon", "olympiad", "tournament", "festival", "summit", "conference",
	"workshop", "seminar", "event", "annual", "first", "second", "third",
	# Generic location/date words
	"bangladesh", "dhaka", "held", "organized", "hosted", "venue", "date",
	"january", "february", "march", "april", "june", "july", "august",
	"september", "october", "november", "december",
	# Short filler
	"this", "that", "with", "from", "have", "been", "will", "your",
})


def _extract_logo_query_candidates(
	logo_text: str | None,
	logo_organizer: str | None,
	logo_acronym: str | None = None,
) -> list[str]:
	"""Generate search query candidates from logo OCR data, filtering certificate noise."""
	if not logo_text and not logo_organizer and not logo_acronym:
		return []

	queries = []

	# Acronym is usually the best signal — leads directly to the official site
	# (e.g., "BUET" → buet.ac.bd; "NSU" → northsouth.edu)
	effective_acronym = logo_acronym
	if not effective_acronym and logo_organizer:
		# Detect if logo_organizer itself is an acronym
		clean = re.sub(r'[.\-]', '', logo_organizer.strip())
		if re.fullmatch(r'[A-Z]{2,8}', clean):
			effective_acronym = clean

	if effective_acronym:
		queries.extend([
			f"{effective_acronym} official website",
			f"{effective_acronym} Bangladesh",
		])

	# Use logo organizer full name (if it's not a bare acronym)
	if logo_organizer and logo_organizer not in ("Unknown", "") and logo_organizer != effective_acronym:
		organizer_clean = _normalize_search_text(" ".join(logo_organizer.split()[:6]))
		if organizer_clean:
			queries.extend([
				f"{organizer_clean} official website",
				f"{organizer_clean} Bangladesh",
			])

	# Use logo text tokens — filter out certificate-specific stopwords
	if logo_text:
		logo_clean = _normalize_search_text(logo_text)
		raw_tokens = [t for t in logo_clean.split() if len(t) >= 3]
		# Remove certificate stopwords and year-like tokens
		filtered_tokens = [
			t for t in raw_tokens
			if t.lower() not in _CERT_STOPWORDS
			and not re.fullmatch(r'20\d{2}', t)
		]
		filtered_tokens = list(dict.fromkeys(filtered_tokens))[:6]
		# Single-token acronym in logo text — treat it like an explicit acronym
		if len(filtered_tokens) == 1:
			tok_clean = re.sub(r'[.\-]', '', filtered_tokens[0])
			if re.fullmatch(r'[A-Z]{2,8}', tok_clean) and tok_clean != effective_acronym:
				queries.extend([
					f"{tok_clean} official website",
					f"{tok_clean} Bangladesh",
				])
		elif len(filtered_tokens) >= 2:
			phrase = " ".join(filtered_tokens[:4])
			queries.extend([
				f"{phrase} official website",
				f"{phrase} Bangladesh",
			])

	return list(dict.fromkeys([q for q in queries if q]))


def search_competition(
	competition_name: str,
	organizer_name: str,
	max_results: int = 15,
	logo_text: str | None = None,
	logo_organizer: str | None = None,
	organizer_acronym: str | None = None,
) -> list[str]:
	"""
	Search using Gemini Grounded Search (with Bangladesh domain preference)
	Falls back to Google search if Gemini unavailable.

	Args:
		competition_name: Name of the competition
		organizer_name: Name of the organizer
		max_results: Maximum number of search results to fetch
		logo_text: OCR text extracted from logo/header region
		logo_organizer: Organizer candidate extracted from logo region
		organizer_acronym: Short-form/acronym of the organizer (e.g., "BUET", "NSU")

	Returns:
		list[str]: List of unique URLs prioritized by relevance
	"""
	all_urls = []
	seen = set()

	def _add_ranked(urls: list[str]):
		bd_urls = [u for u in urls if _is_bangladesh_domain(u)]
		non_bd_urls = [u for u in urls if not _is_bangladesh_domain(u)]
		for url in bd_urls + non_bd_urls:
			if url not in seen:
				seen.add(url)
				all_urls.append(url)
			if len(all_urls) >= max_results:
				break
	
	try:
		organizer_valid = bool(organizer_name and organizer_name != "Unknown")
		competition_valid = bool(competition_name and competition_name != "Unknown")
		organizer_focus = _extract_institution_focus(organizer_name) if organizer_valid else ""
		explicit_org_acronym = _extract_explicit_acronym(organizer_name if organizer_valid else None)
		explicit_logo_acronym = _extract_explicit_acronym(logo_organizer)
		competition_parent_acronym, competition_parent_name = _extract_parent_identity_from_competition(competition_name if competition_valid else None)
		known_name_acronym = _infer_known_acronym_from_name(organizer_focus or organizer_name)
		effective_acronym = (
			organizer_acronym
			or explicit_org_acronym
			or explicit_logo_acronym
			or known_name_acronym
			or competition_parent_acronym
			or _derive_acronym_from_name(organizer_focus)
		)

		if _is_generic_organizer_label(organizer_focus):
			organizer_focus = competition_parent_name or organizer_focus

		# Pre-seed with direct official-domain guesses (high precision for institution acronyms)
		official_guesses = _discover_official_domain_candidates(effective_acronym)
		if official_guesses:
			_add_ranked(official_guesses)

		logo_query_candidates = _extract_logo_query_candidates(logo_text, logo_organizer, logo_acronym=effective_acronym)

		if not organizer_valid and not competition_valid and not logo_query_candidates:
			print("❌ Organizer, competition, and logo identity not provided")
			return []

		organizer_short = " ".join((organizer_focus or organizer_name).split()[:6]) if organizer_valid else ""
		competition_short = " ".join(competition_name.split()[:6]) if competition_valid else ""

		query_candidates = []
		priority_queries = []
		# When we have an acronym it's the single best search token — add it first
		if effective_acronym:
			priority_queries.extend([
				f'"{effective_acronym}" official website Bangladesh',
				f'{effective_acronym} official website Bangladesh',
				f'{effective_acronym} institute Bangladesh',
			])

		if organizer_short and competition_short:
			priority_queries.extend([
				f'"{competition_short}" "{organizer_short}" Bangladesh',
				f'"{competition_short}" {organizer_short}',
				f'"{competition_short}" Bangladesh',
			])
			query_candidates.extend([
				# Most specific: exact competition + organizer
				f'{competition_short} {organizer_short} Bangladesh',
				f'{competition_short} {organizer_short} site:.ac.bd',
				f'{competition_short} {organizer_short} site:.edu.bd',
				# Organizer official site (best for finding the actual website)
				f'{organizer_short} official website Bangladesh',
				f'{organizer_short} Bangladesh',
				# Fallback: competition alone
				f'{competition_short} Bangladesh',
			])
		elif organizer_short:
			priority_queries.extend([
				f'"{organizer_short}" official website Bangladesh',
			])
			query_candidates.extend([
				f'{organizer_short} official website Bangladesh',
				f'{organizer_short} Bangladesh',
				organizer_short,
			])
		else:
			priority_queries.extend([
				f'"{competition_short}" Bangladesh',
			])
			query_candidates.extend([
				f'{competition_short} official website Bangladesh',
				f'{competition_short} Bangladesh',
				competition_short,
			])

		query_candidates = priority_queries + query_candidates
		query_candidates.extend(logo_query_candidates)

		# De-duplicate while preserving order
		query_candidates = list(dict.fromkeys([q.strip() for q in query_candidates if q.strip()]))

		# Priority 1: Serper API
		for query in query_candidates[:8]:
			print(f"🔍 Searching (Serper): {query}")
			serper_results = _search_serper(query, num_results=min(10, max_results))
			if serper_results:
				_add_ranked(serper_results)
				if len(all_urls) >= max_results:
					break

		# Priority 2: Gemini Grounded Search
		if len(all_urls) < 5:
			for query in query_candidates[:8]:
				print(f"🔍 Trying Gemini Grounded Search: {query}")
				gemini_results = _search_gemini_grounded(query, num_results=min(10, max_results))
				if gemini_results:
					_add_ranked(gemini_results)
					if len(all_urls) >= max_results:
						break

		# Priority 3: Google search fallback
		if len(all_urls) < 3 and GOOGLE_SEARCH_AVAILABLE:
			fallback_queries = []
			for q in query_candidates[:3]:
				fallback_queries.extend([
					f'{q} site:.ac.bd',
					f'{q} site:.edu.bd',
					f'{q} site:.bd',
				])

			for query_google in list(dict.fromkeys(fallback_queries))[:6]:
				print(f"🔍 Trying Google search (fallback): {query_google}")
				try:
					google_urls = []
					for url in google_search(query_google, num_results=min(8, max_results), sleep_interval=1):
						if url and url.startswith("http"):
							google_urls.append(url)
							if len(google_urls) >= min(8, max_results):
								break
					if google_urls:
						_add_ranked(google_urls)
						if len(all_urls) >= max_results:
							break
				except Exception as e:
					print(f"   ⚠️ Google error: {e}")

	except Exception as e:
		print(f"❌ Search error: {e}")
		return []
	
	# If still no results from search engines, attempt emergency identity fallback.
	if not all_urls:
		print(f"⚠️ No URLs found from search methods; attempting emergency identity fallback")
		emergency_urls = []

		identity_acronyms = [
			effective_acronym,
			_infer_known_acronym_from_name(organizer_name),
			_infer_known_acronym_from_name(logo_organizer),
		]
		identity_acronyms = [a for a in identity_acronyms if a]

		for ac in identity_acronyms:
			for guessed in _build_official_domain_guesses(ac):
				resolved = _probe_url_reachable(guessed, timeout=3)
				emergency_urls.append(resolved or guessed)

		emergency_urls = [u for u in dict.fromkeys(emergency_urls) if u]
		if emergency_urls:
			return _prioritize_urls(emergency_urls, min(max_results, 8))

		return []

	pre_filter_urls = list(dict.fromkeys(all_urls))

	# Apply organizer-identity filtering before final prioritization.
	all_urls = _filter_urls_by_identity(
		pre_filter_urls,
		organizer_name=organizer_short or organizer_name,
		competition_name=competition_short or competition_name,
		acronym=effective_acronym,
	)

	# Safety fallback: when strict filtering removes everything, keep top prioritized raw URLs.
	# This avoids false "No results" in UI when search engines actually returned relevant links.
	if not all_urls and pre_filter_urls:
		print("⚠️ Identity filter removed all URLs; applying safe fallback selection")
		fallback_urls = []
		organizer_fallback_tokens = _identity_tokens_from_organizer(organizer_short or organizer_name)
		acronym_fallback = (effective_acronym or "").strip().lower()
		competition_fallback_tokens = [
			t.lower()
			for t in re.findall(r"[A-Za-z]{4,}", competition_short or competition_name or "")
			if t.lower() not in {
				"competition", "contest", "event", "program", "programme", "training", "course",
				"conference", "international", "mechanical", "engineering", "applied", "sciences",
			}
		][:3]

		for url in pre_filter_urls:
			url_lower = url.lower()
			try:
				parsed = urlparse(url)
				netloc = parsed.netloc.lower().replace("www.", "")
				path = parsed.path.lower()
			except Exception:
				netloc = ""
				path = ""

			is_social = any(domain in netloc for domain in ("facebook.com", "linkedin.com", "youtube.com", "youtu.be"))
			is_bd_official = netloc.endswith((".ac.bd", ".edu.bd", ".gov.bd", ".org.bd"))
			is_edu_academic = netloc.endswith((".ac.bd", ".edu.bd"))
			organizer_hint = any(tok in url_lower for tok in organizer_fallback_tokens if len(tok) >= 5)
			acronym_hint = bool(acronym_fallback and len(acronym_fallback) >= 3 and acronym_fallback in url_lower)
			competition_hint = any(tok in url_lower for tok in competition_fallback_tokens if len(tok) >= 4)
			has_event_hint = any(h in url_lower for h in ("event", "contest", "competition", "conference", "seminar", "workshop", "notice"))
			is_document = (
				path.endswith((".pdf", ".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx"))
				or "/storage/pdfs/" in url_lower
			)

			# Drop unrelated document dump links unless there is explicit identity evidence.
			if is_document and not (is_bd_official or organizer_hint or acronym_hint):
				continue

			identity_match = organizer_hint or acronym_hint or competition_hint

			# Social links are noisy; keep only when identity is explicit.
			if is_social and not identity_match:
				continue

			# Generic .gov/.org links are noisy; keep only with identity/event evidence.
			if is_bd_official and not is_edu_academic and not (identity_match and (has_event_hint or acronym_hint)):
				continue

			if is_bd_official or is_social or identity_match:
				fallback_urls.append(url)

		if fallback_urls:
			return _prioritize_urls(fallback_urls, min(max_results, 8))
		return []
	
	# Prioritize and return URLs
	return _prioritize_urls(all_urls, max_results)


def _prioritize_urls(urls: list[str], max_results: int = 15) -> list[str]:
	"""
	Prioritize URLs by domain type (websites > official > social media)
	
	Args:
		urls (list[str]): List of URLs to prioritize
		max_results (int): Maximum number of results to return
	
	Returns:
		list[str]: Prioritized and deduplicated list of URLs
	"""
	edu_urls = []
	gov_urls = []
	org_urls = []
	website_urls = []
	facebook_urls = []
	linkedin_urls = []
	other_urls = []
	
	for url in urls:
		try:
			netloc = urlparse(url).netloc.lower()
			if netloc.startswith("www."):
				netloc = netloc[4:]
			
			if "facebook.com" in netloc or "fb.com" in netloc:
				facebook_urls.append(url)
			elif "linkedin.com" in netloc:
				linkedin_urls.append(url)
			elif netloc.endswith((".edu", ".edu.bd", ".ac.bd")):
				edu_urls.append(url)
			elif netloc.endswith((".gov", ".gov.bd")):
				gov_urls.append(url)
			elif netloc.endswith((".org", ".org.bd")):
				org_urls.append(url)
			elif len(netloc) < 50:
				website_urls.append(url)
			else:
				other_urls.append(url)
		except Exception:
			continue
	
	# Return order: EDU > GOV > ORG > Website > Facebook > LinkedIn > Others
	prioritized = edu_urls + gov_urls + org_urls + website_urls + facebook_urls + linkedin_urls + other_urls
	
	return list(dict.fromkeys(prioritized))[:max_results]


def scrape_url_content(url: str, max_length: int = 5000) -> dict:
	"""
	Scrape the content from a URL using multiple strategies.
	Tries: Trafilatura → BeautifulSoup with paragraphs → Simple text extraction
	
	Args:
		url (str): The URL to scrape
		max_length (int): Maximum content length to return
	
	Returns:
		dict: {
			'url': str,
			'content': str (main text content),
			'success': bool
		}
	"""
	result = {
		'url': url,
		'content': '',
		'success': False
	}
	
	try:
		# Better headers to avoid blocking
		headers = {
			'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
			'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
			'Accept-Language': 'en-US,en;q=0.5',
			'Accept-Encoding': 'gzip, deflate',
			'Connection': 'keep-alive',
			'Upgrade-Insecure-Requests': '1'
		}
		
		# Try Trafilatura first (best for extracting main content)
		if TRAFILATURA_AVAILABLE:
			try:
				downloaded = fetch_url(url, timeout=10)
				if downloaded:
					content = extract(downloaded, include_comments=False, include_tables=False)
					if content and len(content) > 50:
						result['content'] = content[:max_length]
						result['success'] = True
						return result
			except Exception as e:
				print(f"   ℹ️ Trafilatura failed: {str(e)[:50]}")
		
		# Strategy 1: Try with requests + BeautifulSoup (extract paragraphs)
		try:
			response = requests.get(url, headers=headers, timeout=10)
			response.encoding = 'utf-8'
			
			if response.status_code == 200:
				soup = BeautifulSoup(response.text, 'html.parser')
				
				# Try to get main content from common containers
				main_content = None
				for selector in ['main', 'article', '[role="main"]', '.content', '.post', '.entry']:
					element = soup.select_one(selector)
					if element:
						main_content = element
						break
				
				if not main_content:
					main_content = soup.body if soup.body else soup
				
				# Remove unwanted elements
				for tag in main_content(['script', 'style', 'nav', 'footer', 'aside', 'noscript', 'meta']):
					tag.decompose()
				
				# Try to get paragraphs first (better quality)
				paragraphs = main_content.find_all(['p', 'article', 'div', 'section'])
				if paragraphs:
					content_text = ' '.join([p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True)])
					content_text = re.sub(r'\s+', ' ', content_text).strip()
					
					if len(content_text) > 50:
						result['content'] = content_text[:max_length]
						result['success'] = True
						return result
				
				# Fallback: get all text
				text = main_content.get_text(separator=' ', strip=True)
				text = re.sub(r'\s+', ' ', text)
				
				if len(text) > 50:
					result['content'] = text[:max_length]
					result['success'] = True
					return result
		
		except Exception as e:
			print(f"   ℹ️ BeautifulSoup strategy failed: {str(e)[:50]}")
		
		# Strategy 2: Simple GET request with basic parsing
		try:
			response = requests.get(url, headers=headers, timeout=8)
			response.encoding = 'utf-8'
			
			if response.status_code == 200:
				# Remove common junk patterns
				html = response.text
				html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
				html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL | re.IGNORECASE)
				
				soup = BeautifulSoup(html, 'html.parser')
				text = soup.get_text(separator=' ', strip=True)
				text = re.sub(r'\s+', ' ', text)
				
				# Get meaningful portion (skip very long texts that are likely lists)
				if 50 < len(text) < 50000:
					result['content'] = text[:max_length]
					result['success'] = True
					return result
		
		except Exception as e:
			print(f"   ℹ️ Simple strategy failed: {str(e)[:50]}")
		
	except Exception as e:
		print(f"   ⚠️ Scraping {url[:40]}... failed: {str(e)[:50]}")
	
	return result


def scrape_search_results(urls: list[str], max_urls: int = 5) -> list[dict]:
	"""
	Scrape content from multiple URLs with improved retry logic.
	
	Args:
		urls (list[str]): List of URLs to scrape
		max_urls (int): Maximum number of URLs to scrape
	
	Returns:
		list[dict]: List of scraped content dictionaries
	"""
	scraped_data = []
	attempted = 0
	successful = 0
	
	# Adjust max_urls to ensure we try enough
	target_urls = min(len(urls), max_urls)
	
	for i, url in enumerate(urls):
		if successful >= max_urls:
			break
		
		if attempted >= target_urls * 2:  # Don't try too many times
			break
		
		attempted += 1
		
		print(f"   🌐 Scraping ({attempted}) {url[:50]}...")
		result = scrape_url_content(url)
		
		if result['success']:
			scraped_data.append(result)
			successful += 1
			char_count = len(result['content'])
			print(f"      ✅ Success ({successful}/{max_urls}): {char_count} chars")
		else:
			print(f"      ❌ Failed - trying next URL...")
		
		# Be polite - add delay between requests
		if i < len(urls) - 1:
			time.sleep(0.3)
	
	print(f"   📊 Scraping complete: {successful} successful out of {attempted} attempts")
	
	return scraped_data


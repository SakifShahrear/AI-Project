from urllib.parse import urlparse
import requests
from bs4 import BeautifulSoup
import time
import os
import re
from dotenv import load_dotenv

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

	for url in search(query, num_results=max_results):
		if url in seen:
			continue
		seen.add(url)

		if _is_target_domain(url):
			results.append(url)

	return results


def search_competition(competition_name: str, organizer_name: str, max_results: int = 15) -> list[str]:
	"""
	Search using Gemini Grounded Search (with Bangladesh domain preference)
	Falls back to Google search if Gemini unavailable.
	
	Args:
		competition_name (str): Name of the competition
		organizer_name (str): Name of the organizer
		max_results (int): Maximum number of search results to fetch (default: 15)
	
	Returns:
		list[str]: List of unique URLs prioritized by relevance
	"""
	all_urls = []
	seen = set()
	
	try:
		if not organizer_name or organizer_name == "Unknown":
			print("❌ Organizer name not provided")
			return []

		organizer_short = " ".join(organizer_name.split()[:4])
		
		# Priority 1: Serper API (Google Search - fast, reliable, no blocking)
		query = f'{organizer_short} Bangladesh'
		print(f"🔍 Searching: {query}")
		
		serper_results = _search_serper(query, num_results=max_results)
		
		if serper_results:
			for url in serper_results:
				if _is_bangladesh_domain(url) and url not in seen:
					seen.add(url)
					all_urls.append(url)
			
			if all_urls:
				print(f"✅ Found {len(all_urls)} Bangladesh URLs from Serper")
				# Return immediately if Serper found results
				return _prioritize_urls(all_urls, max_results)
			else:
				print(f"   ⚠️ Serper results had no .bd domains")
		
		# Priority 2: Gemini Grounded Search (if Serper found nothing)
		if not all_urls:
			query_gemini = f'{organizer_short} Bangladesh'
			print(f"🔍 Trying Gemini Grounded Search...")
			
			gemini_results = _search_gemini_grounded(query_gemini, num_results=10)
			
			if gemini_results:
				for url in gemini_results:
					if _is_bangladesh_domain(url) and url not in seen:
						seen.add(url)
						all_urls.append(url)
				
				if all_urls:
					print(f"✅ Found {len(all_urls)} Bangladesh URLs from Gemini")
					return _prioritize_urls(all_urls, max_results)
		
		# Priority 3: Google search (last resort - often blocked)
		if not all_urls and GOOGLE_SEARCH_AVAILABLE:
			query_google = f'{organizer_short} Bangladesh site:.bd'
			print(f"🔍 Trying Google search (fallback)...")
			
			try:
				for url in google_search(query_google, num_results=max_results, sleep_interval=1):
					if url and url.startswith("http") and _is_bangladesh_domain(url):
						if url not in seen:
							seen.add(url)
							all_urls.append(url)
							if len(all_urls) >= 5:
								break
				
				if all_urls:
					print(f"✅ Found {len(all_urls)} Bangladesh URLs from Google")
				else:
					print(f"   ⚠️ Google search blocked or no results")
			except Exception as e:
				print(f"   ⚠️ Google error: {e}")

	except Exception as e:
		print(f"❌ Search error: {e}")
		return []
	
	# If still no results, return empty
	if not all_urls:
		print(f"⚠️ No Bangladesh URLs found from any search method")
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
	website_urls = []
	facebook_urls = []
	linkedin_urls = []
	official_urls = []
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
			elif netloc.endswith(".gov") or netloc.endswith(".edu") or netloc.endswith(".org"):
				official_urls.append(url)
			elif len(netloc) < 50:
				website_urls.append(url)
			else:
				other_urls.append(url)
		except Exception:
			continue
	
	# Return: Website > Official > Facebook > LinkedIn > Others
	prioritized = website_urls + official_urls + facebook_urls + linkedin_urls + other_urls
	
	return list(dict.fromkeys(prioritized))[:max_results]


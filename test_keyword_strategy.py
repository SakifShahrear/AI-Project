#!/usr/bin/env python
"""
Test improved search with 2-4 word strategy
"""

from search_agent import _extract_main_keywords, _search_duckduckgo

def test_keywords():
    print("=" * 70)
    print("Testing Keyword Extraction Strategy")
    print("=" * 70)
    
    test_texts = [
        "BEAR SUMMIT AND NATIONAL SEMICONDUCTOR SYMPOSIUM 2025",
        "AI Hackathon Competition Bangladesh 2025",
        "Python Programming Workshop"
    ]
    
    for text in test_texts:
        print(f"\nOriginal: {text}")
        keywords = _extract_main_keywords(text)
        print(f"Keywords (in order):")
        for i, kw in enumerate(keywords, 1):
            print(f"  {i}. {kw}")
        print("-" * 70)

def test_search():
    print("\n" + "=" * 70)
    print("Testing Search with Short Keywords")
    print("=" * 70)
    
    # Test with BEAR SUMMIT
    print("\nTest: BEAR SUMMIT 2025")
    print("-" * 70)
    results = _search_duckduckgo("BEAR SUMMIT 2025", num_results=3)
    print(f"Found {len(results)} results:")
    for i, url in enumerate(results, 1):
        print(f"  {i}. {url}")

if __name__ == "__main__":
    test_keywords()
    test_search()

#!/usr/bin/env python
"""
Test script to verify DuckDuckGo search functionality
"""

from search_agent import _search_duckduckgo, _extract_main_keywords

def test_search():
    print("=" * 70)
    print("🔍 Testing DuckDuckGo Search Functionality")
    print("=" * 70)
    
    # Test cases
    test_queries = [
        {
            "competition": "BEAR SUMMIT AND NATIONAL SEMICONDUCTOR SYMPOSIUM 2025",
            "organizer": "ICT DIVISION"
        },
        {
            "competition": "BEAR SUMMIT 2025",
            "organizer": "Bangladesh"
        },
        {
            "competition": "Python Hackathon 2025",
            "organizer": "Tech University"
        }
    ]
    
    for i, test in enumerate(test_queries, 1):
        print(f"\n{'─' * 70}")
        print(f"Test {i}: {test['competition']}")
        print(f"Organizer: {test['organizer']}")
        print('─' * 70)
        
        # Extract keywords
        keywords = _extract_main_keywords(test['competition'])
        print(f"\n📌 Extracted Keywords: {keywords}")
        
        # Try search with competition + organizer
        query = f"{test['competition']} {test['organizer']}"
        print(f"\n🔎 Searching: {query}")
        results = _search_duckduckgo(query, num_results=5)
        
        if results:
            print(f"\n✅ Found {len(results)} results:")
            for j, url in enumerate(results, 1):
                print(f"   {j}. {url}")
        else:
            print(f"❌ No results found")
        
        # Try search with just competition name
        if not results and keywords:
            print(f"\n🔎 Fallback: Searching just: {keywords[0]}")
            results = _search_duckduckgo(keywords[0], num_results=5)
            
            if results:
                print(f"\n✅ Fallback found {len(results)} results:")
                for j, url in enumerate(results, 1):
                    print(f"   {j}. {url}")
            else:
                print(f"❌ Fallback: No results found")
    
    print(f"\n{'=' * 70}")
    print("✅ Test completed!")
    print("=" * 70)

if __name__ == "__main__":
    test_search()

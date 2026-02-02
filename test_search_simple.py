#!/usr/bin/env python
"""
Simple test script for search functionality
"""

from search_agent import _search_duckduckgo, _extract_main_keywords

def test_search():
    print("=" * 70)
    print("Testing Search Functionality")
    print("=" * 70)
    
    # Test 1
    print("\nTest 1: BEAR SUMMIT 2025")
    print("-" * 70)
    results = _search_duckduckgo("BEAR SUMMIT 2025", num_results=5)
    print(f"Results found: {len(results)}")
    for i, url in enumerate(results, 1):
        print(f"  {i}. {url}")
    
    # Test 2
    print("\nTest 2: Bangladesh Hackathon")
    print("-" * 70)
    results = _search_duckduckgo("Bangladesh Hackathon", num_results=5)
    print(f"Results found: {len(results)}")
    for i, url in enumerate(results, 1):
        print(f"  {i}. {url}")
    
    # Test 3
    print("\nTest 3: Python Conference 2025")
    print("-" * 70)
    results = _search_duckduckgo("Python Conference 2025", num_results=5)
    print(f"Results found: {len(results)}")
    for i, url in enumerate(results, 1):
        print(f"  {i}. {url}")
    
    print("\n" + "=" * 70)
    print("Test completed!")
    print("=" * 70)

if __name__ == "__main__":
    test_search()

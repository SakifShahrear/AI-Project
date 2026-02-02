#!/usr/bin/env python
"""
Debug script to test if Google Search is working
"""

from googlesearch import search
import time

def test_search():
    """Test basic Google search functionality"""
    
    print("=" * 60)
    print("🔍 Google Search Debug Test")
    print("=" * 60)
    
    test_queries = [
        "BEAR SUMMIT 2025",
        "BEAR SUMMIT",
        "National Semiconductor Symposium",
        "ICT Division Bangladesh",
        "python google",
    ]
    
    for query in test_queries:
        print(f"\n🔎 Testing query: '{query}'")
        print("-" * 60)
        
        try:
            results = []
            count = 0
            
            # Try to get results with shorter timeout
            for url in search(query, num_results=5, sleep_interval=1):
                results.append(url)
                count += 1
                print(f"  Result {count}: {url}")
                
                if count >= 5:
                    break
            
            if count == 0:
                print("  ❌ No results found for this query")
            else:
                print(f"  ✅ Found {count} results")
            
            # Add delay between queries to avoid rate limiting
            time.sleep(2)
            
        except Exception as e:
            print(f"  ❌ Error: {e}")
            print("  💡 This might be a rate limit or connection issue")
    
    print("\n" + "=" * 60)
    print("Test completed. Check results above.")
    print("=" * 60)

if __name__ == "__main__":
    test_search()

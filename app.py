import streamlit as st
import os
from PIL import Image
import io
import json
import pandas as pd
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Import custom modules
from ocr_handler import (
    extract_certificate_data, 
    ai_extract_structured_info,
    ai_verify_validity
)
from search_agent import search_competition, scrape_search_results
from database import (
    save_verification_result,
    get_all_verification_results
)
from utils import calculate_accuracy

# --- Streamlit UI Configuration ---
st.set_page_config(
    page_title="🛡️ AI Certificate Authenticator", 
    layout="wide"
)

# --- Custom CSS ---
st.markdown("""
<style>
    .main-header {
        font-size: 3rem;
        font-weight: bold;
        text-align: center;
        background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        padding: 1rem;
    }
    .metric-card {
        background-color: #f0f2f6;
        padding: 1rem;
        border-radius: 0.5rem;
        text-align: center;
    }
</style>
""", unsafe_allow_html=True)

# --- Title ---
st.markdown('<h1 class="main-header">🛡️ AI Certificate Authenticator</h1>', unsafe_allow_html=True)
st.markdown("### Upload a certificate image to verify its authenticity using AI and web search.")
st.markdown("---")

# --- Main Content ---
st.header("📤 Upload Certificate")

# --- File Uploader ---
uploaded_file = st.file_uploader(
    "Upload Certificate Image (JPG/PNG)", 
    type=['jpg', 'png', 'jpeg'],
    help="Upload a clear image of the certificate to verify"
)

if uploaded_file is not None:
    # Display uploaded image
    st.image(uploaded_file, caption="Uploaded Certificate", width=700)
    st.markdown("---")
    
    # Save temporary file
    temp_file_path = "temp_certificate.jpg"
    with open(temp_file_path, "wb") as f:
        f.write(uploaded_file.getbuffer())
    
    # Processing indicator
    with st.spinner('🔄 Analyzing certificate... Please wait.'):
        try:
            # --- Step 1: Extract raw text using OCR ---
            st.info("📸 Step 1: Extracting text with OCR...")
            raw_text = extract_certificate_data(temp_file_path)
            
            if not raw_text or len(raw_text.strip()) < 10:
                st.error("❌ Could not extract sufficient text from the image. Please upload a clearer image.")
                os.remove(temp_file_path)
                st.stop()
            
            st.success(f"✅ Extracted {len(raw_text)} characters of text")
            
            with st.expander("📄 View Raw OCR Text"):
                st.text(raw_text[:500] + "..." if len(raw_text) > 500 else raw_text)
            
            # --- Step 2: Extract structured info using AI ---
            st.info("🤖 Step 2: Extracting structured data with AI...")
            try:
                extracted_info = ai_extract_structured_info(raw_text)
            except Exception as e:
                st.warning("⚠️ AI quota reached. Falling back to heuristic extraction.")
                from ocr_handler import extract_certificate_fields_heuristic
                extracted_info = extract_certificate_fields_heuristic(raw_text)
            
            competition_name = extracted_info.get('competition_name') or "Unknown"
            organizer_name = extracted_info.get('organizer_name') or "Unknown"
            event_date = extracted_info.get('event_date') or "Unknown"
            
            st.success("✅ Structured data extracted successfully")
            
            # Display extracted information with debug info
            st.markdown("### 📋 Extracted Information")
            
            # Show extracted data
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("🏆 Competition Name", competition_name)
            with col2:
                st.metric("🏢 Organizer", organizer_name)
            with col3:
                st.metric("📅 Event Date", event_date)
            
            # Debug expander to see raw AI response
            with st.expander("🔧 Debug: View AI Extraction Details"):
                st.json(extracted_info)
                if competition_name == "Unknown" or organizer_name == "Unknown":
                    st.warning("⚠️ AI couldn't extract some fields. This might affect search accuracy.")
            
            st.markdown("---")
            
            # --- Step 3: Search online for verification ---
            st.info("🔍 Step 3: Searching online for verification...")
            
            # Show what we're searching for
            with st.expander("🔎 Search Query Details"):
                st.write(f"**Competition Name:** `{competition_name}`")
                st.write(f"**Organizer Name:** `{organizer_name}`")
                st.write("**Search Strategy:** Will try multiple keyword variations and fallback queries")
            
            scraped_data = []  # Initialize scraped data
            
            if competition_name != "Unknown" and organizer_name != "Unknown":
                with st.spinner(f'Searching Google for "{competition_name} {organizer_name}"...'):
                    search_results = search_competition(competition_name, organizer_name)
                
                if len(search_results) > 0:
                    st.success(f"✅ Found {len(search_results)} search results")
                    
                    # NEW: Scrape web content from search results
                    with st.spinner(f'🌐 Scraping content from {min(len(search_results), 5)} websites...'):
                        scraped_data = scrape_search_results(search_results, max_urls=5)
                    
                    if scraped_data:
                        st.success(f"✅ Successfully scraped {len(scraped_data)} websites")
                    else:
                        st.warning("⚠️ Could not scrape content from websites")
                else:
                    st.warning("⚠️ No search results found.")
                
                with st.expander("🌐 View Search Results"):
                    if search_results:
                        for i, url in enumerate(search_results, 1):
                            st.write(f"{i}. [{url}]({url})")
                    else:
                        st.info("**Why no results?**")
                        st.write("• Google search may be rate limited (try again in a few minutes)")
                        st.write("• Competition might be very new or local")
                        st.write("• Organizer name might be incomplete/incorrect")
                        st.write("• This doesn't mean the certificate is fake - AI analysis will still verify text quality")
                        st.info("No results found. Possible reasons:")
                        st.write("• Competition name not found online")
                        st.write("• Organizer name is incorrect or too generic")
                        st.write("• Google search rate limit reached")
                        st.write("• Certificate might be fake")
            else:
                st.warning("⚠️ Insufficient information extracted for online search")
                st.write(f"Competition: `{competition_name}` | Organizer: `{organizer_name}`")
                search_results = []
            
            st.markdown("---")
            
            # --- NEW: OCR vs Web Data Comparison ---
            st.header("🔍 OCR vs Web Data Comparison")
            st.write("This is what the AI is comparing to verify authenticity:")
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.markdown("### 📄 Data from Certificate (OCR)")
                st.info("Information extracted from the uploaded image")
                
                ocr_data = {
                    "Competition Name": competition_name,
                    "Organizer": organizer_name,
                    "Event Date": event_date
                }
                
                for key, value in ocr_data.items():
                    if value and value != "Unknown":
                        st.markdown(f"**{key}:** `{value}`")
                    else:
                        st.markdown(f"**{key}:** ❌ Not found")
                
                # Show sample of raw OCR text
                with st.expander("📝 Raw OCR Text Sample"):
                    st.text(raw_text[:500] + "..." if len(raw_text) > 500 else raw_text)
            
            with col2:
                st.markdown("### 🌐 Data from Web (Search + Scraping)")
                st.info("Information found online")
                
                if search_results:
                    st.markdown(f"**Search Results:** ✅ {len(search_results)} URLs found")
                    
                    # Show domains
                    if search_results:
                        from urllib.parse import urlparse
                        domains = []
                        for url in search_results[:5]:
                            try:
                                domain = urlparse(url).netloc
                                domains.append(domain)
                            except:
                                pass
                        
                        if domains:
                            st.markdown("**Top Domains:**")
                            for i, domain in enumerate(domains[:3], 1):
                                st.markdown(f"{i}. `{domain}`")
                    
                    if scraped_data:
                        st.markdown(f"**Scraped Content:** ✅ {len(scraped_data)} websites")
                        
                        # Show content preview
                        with st.expander("📖 Web Content Preview"):
                            for i, data in enumerate(scraped_data[:2], 1):
                                st.markdown(f"**Source {i}:** [{urlparse(data['url']).netloc}]({data['url']})")
                                content_preview = data['content'][:300]
                                st.text(content_preview + "..." if len(data['content']) > 300 else content_preview)
                                st.markdown("---")
                    else:
                        st.markdown(f"**Scraped Content:** ❌ No content scraped")
                else:
                    st.markdown("**Search Results:** ❌ No results found")
                    st.markdown("**Scraped Content:** ❌ N/A")
            
            # Visual comparison summary
            st.markdown("### 🎯 Comparison Summary")
            comparison_col1, comparison_col2, comparison_col3 = st.columns(3)
            
            with comparison_col1:
                has_competition = competition_name != "Unknown"
                st.metric(
                    "Competition Match",
                    "✅ Found" if has_competition and search_results else "❌ Missing",
                    help="Is the competition name extractable and searchable?"
                )
            
            with comparison_col2:
                has_organizer = organizer_name != "Unknown"
                st.metric(
                    "Organizer Match",
                    "✅ Found" if has_organizer and search_results else "❌ Missing",
                    help="Is the organizer name extractable and verifiable?"
                )
            
            with comparison_col3:
                has_web_evidence = len(search_results) > 0 and len(scraped_data) > 0
                st.metric(
                    "Web Evidence",
                    "✅ Strong" if has_web_evidence else "❌ Weak",
                    help="Is there substantial online evidence?"
                )
            
            st.markdown("---")
            
            # --- Step 4: Calculate basic accuracy score ---
            st.info("📊 Step 4: Calculating accuracy score...")
            
            # Note: calculate_accuracy now returns (score, status) tuple
            result = calculate_accuracy(raw_text, search_results)
            if isinstance(result, tuple):
                score, status = result
            else:
                # Fallback for old format
                score = result.get('score', 0)
                status = result.get('status', 'Fake')
            
            # Display scoring breakdown
            with st.expander("📈 Scoring Breakdown"):
                st.write("**How the score is calculated:**")
                col1, col2 = st.columns(2)
                
                with col1:
                    st.write("**With Search Results:**")
                    st.write("• Official domains (.gov/.edu/.org): +40 pts")
                    st.write("• Social media events: +30 pts")
                    st.write("• Text consistency: +20 pts")
                
                with col2:
                    st.write("**Without Search Results:**")
                    st.write("• OCR text clarity: +10 pts")
                    st.write("• Recent/future event: +10 pts")
                    st.write("• High confidence text: +5 pts")
                
                st.write(f"**Current Score:** `{score}/100` - Found {len(search_results)} online results")
            
            st.markdown("---")
            
            # --- Step 5: Get AI verification verdict ---
            st.info("🧠 Step 5: Running AI Forensic Verification...")
            st.write("AI is now comparing OCR data with web content to make a verdict...")
            
            try:
                # Pass scraped_data to the new verification function
                ai_verdict_json = ai_verify_validity(raw_text, search_results, scraped_data)
                ai_verdict = json.loads(ai_verdict_json)
                
                # NEW FORMAT: status, accuracy_score, reasoning, match_found
                status = ai_verdict.get('status', 'Suspicious')
                accuracy_score = ai_verdict.get('accuracy_score', 0)
                reasoning = ai_verdict.get('reasoning', 'Unable to verify')
                match_found = ai_verdict.get('match_found', False)
                
                # Legacy compatibility
                ai_probability = ai_verdict.get('probability', accuracy_score / 100)
                ai_reasons = ai_verdict.get('reasons', [reasoning])
                is_authentic = ai_verdict.get('is_authentic', status == 'Verified')
                
                st.success("✅ AI verification complete")
            except Exception as e:
                st.warning(f"⚠️ AI verification unavailable: {str(e)}")
                status = 'Suspicious'
                accuracy_score = score
                reasoning = "AI analysis failed - using basic score"
                match_found = len(search_results) > 0
                ai_probability = score / 100
                ai_reasons = [reasoning]
                is_authentic = score >= 60
            
            st.markdown("---")
            # --- Display Results Dashboard ---
            st.header("🎯 Verification Results")
            
            # Show warning if no search results
            if len(search_results) == 0:
                st.error("❌ **No online verification found** - Cannot confirm authenticity")
                st.write("**Recommendation:** Certificate could not be verified through web search. It may be fake, too new, or from a local/unindexed source.")
            else:
                st.info(f"✅ **Found {len(search_results)} verification sources** - Checking authenticity")
            
            # Metrics
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.metric(
                    "📊 Accuracy Score", 
                    f"{accuracy_score}/100",
                    help="AI-calculated score based on OCR vs Web Data comparison"
                )
            
            with col2:
                st.metric(
                    "🤖 AI Probability", 
                    f"{ai_probability * 100:.1f}%",
                    help="AI-calculated probability of authenticity"
                )
            
            with col3:
                status_emoji = {"Verified": "✅", "Suspicious": "⚠️", "Fake": "❌", "Authentic": "✅"}
                st.metric(
                    "🏷️ Status", 
                    f"{status_emoji.get(status, '❓')} {status}"
                )
            
            # Show match status
            if match_found:
                st.success("✅ **Match Found:** Event details verified online")
            else:
                st.error("❌ **No Match:** Could not verify event details online")
            
            # AI Reasoning
            st.markdown("### 🧠 AI Forensic Analysis Report")
            
            # Create a nice visual card for the verdict
            if status == "Verified" or is_authentic:
                st.success("✅ **AI Verdict: VERIFIED/AUTHENTIC**")
                st.write("Certificate text appears legitimate and matches online data")
            elif status == "Suspicious" or ai_probability >= 0.5:
                st.warning("⚠️ **AI Verdict: SUSPICIOUS** (Cannot fully verify without online evidence)")
                st.write("Text quality is acceptable, but online verification is limited")
            else:
                st.error("❌ **AI Verdict: FAKE/NOT AUTHENTIC**")
            
            # Detailed comparison table
            st.markdown("#### 📋 Detailed Comparison")
            
            comparison_data = []
            
            # Competition Name comparison
            if competition_name != "Unknown":
                web_found = "Yes" if len(search_results) > 0 else "No"
                comparison_data.append({
                    "Field": "Competition Name",
                    "From Certificate": competition_name,
                    "Found on Web": web_found,
                    "Status": "✅" if web_found == "Yes" else "❌"
                })
            
            # Organizer comparison
            if organizer_name != "Unknown":
                web_found = "Yes" if len(search_results) > 0 else "No"
                comparison_data.append({
                    "Field": "Organizer",
                    "From Certificate": organizer_name,
                    "Found on Web": web_found,
                    "Status": "✅" if web_found == "Yes" else "❌"
                })
            
            # Event Date comparison
            if event_date != "Unknown":
                web_found = "Yes" if len(search_results) > 0 else "No"
                comparison_data.append({
                    "Field": "Event Date",
                    "From Certificate": event_date,
                    "Found on Web": web_found,
                    "Status": "✅" if web_found == "Yes" else "❌"
                })
            
            # Web Evidence
            comparison_data.append({
                "Field": "Web Evidence",
                "From Certificate": "N/A",
                "Found on Web": f"{len(search_results)} URLs, {len(scraped_data)} scraped",
                "Status": "✅" if len(search_results) > 0 else "❌"
            })
            
            if comparison_data:
                df = pd.DataFrame(comparison_data)
                st.dataframe(df, use_container_width=True, hide_index=True)
            
            st.markdown("**Analysis Details:**")
            st.write(f"📝 {reasoning}")
            
            if ai_reasons:
                for i, reason in enumerate(ai_reasons, 1):
                    st.write(f"{i}. {reason}")
            
            st.markdown("---")
            
            # --- Save to Database Button ---
            st.header("💾 Save Results")
            
            col1, col2 = st.columns([3, 1])
            
            with col1:
                st.write("Save this verification result to the database for future reference.")
            
            with col2:
                if st.button("💾 Save to Database", type="primary", use_container_width=True):
                    try:
                        # For now, using a placeholder file_url since we're not uploading to storage
                        file_url = f"local_file_{os.path.basename(temp_file_path)}"
                        
                        save_verification_result(
                            file_url=file_url,
                            competition_name=competition_name,
                            organizer=organizer_name,
                            accuracy_score=accuracy_score,  # Use new accuracy_score
                            status=status  # Use new status format
                        )
                        
                        st.success("✅ Verification result saved successfully!")
                        st.balloons()
                    except Exception as e:
                        st.error(f"❌ Error saving result: {str(e)}")
            
            # Cleanup
            try:
                if os.path.exists(temp_file_path):
                    os.remove(temp_file_path)
            except Exception:
                pass
        
        except Exception as e:
            st.error(f"❌ An error occurred: {str(e)}")
            if os.path.exists(temp_file_path):
                os.remove(temp_file_path)

# --- History Section ---
st.markdown("---")
st.header("📜 Verification History")

try:
    history = get_all_verification_results(limit=50)
    
    if history:
        st.write(f"Showing latest {len(history)} verification results")
        st.dataframe(
            history,
            use_container_width=True,
            hide_index=False
        )
        
        # Download option
        st.download_button(
            label="📥 Download History (JSON)",
            data=json.dumps(history, indent=2),
            file_name="verification_history.json",
            mime="application/json"
        )
    else:
        st.info("📭 No verification results found in the database.")

except Exception as e:
    st.error(f"❌ Error fetching history: {str(e)}")

# --- Footer ---
st.markdown("---")
st.markdown(
    """
    <div style='text-align: center; color: #666;'>
        <p>🛡️ AI Certificate Authenticator | Powered by Google Gemini & Supabase</p>
    </div>
    """,
    unsafe_allow_html=True
)

import streamlit as st
import cloudscraper # Changed from requests to cloudscraper
from bs4 import BeautifulSoup
import google.generativeai as genai
from google.api_core.exceptions import ResourceExhausted
import pandas as pd
import json
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# --- Page Configuration ---
st.set_page_config(page_title="Jumia AI Assistant", page_icon="🛒", layout="wide")

# --- Sidebar Configuration ---
st.sidebar.title("⚙️ Configuration")
st.sidebar.markdown("Get your [Gemini API Key here](https://aistudio.google.com/app/apikey).")

# Try to get API key from environment first, then try Streamlit secrets
env_api_key = os.getenv("GEMINI_API_KEY")
if not env_api_key:
    try:
        env_api_key = st.secrets.get("GEMINI_API_KEY")
    except Exception:
        pass

if env_api_key:
    st.sidebar.success("✅ API Key loaded successfully!")
    api_key = env_api_key
else:
    api_key = st.sidebar.text_input("Enter Gemini API Key", type="password")

if api_key:
    genai.configure(api_key=api_key)

# --- Helper Functions ---

def extract_search_term(user_query):
    """Uses Gemini to extract a clean search keyword from a natural language prompt."""
    model = genai.GenerativeModel('gemini-2.5-flash')
    prompt = f"""
    Extract the core product search term from the following user request. 
    Only return the search term, nothing else. No quotes, no extra text.
    User request: "{user_query}"
    """
    try:
        response = model.generate_content(prompt)
        return response.text.strip()
    except ResourceExhausted:
        st.error("⏳ **Google Gemini API rate limit reached.** The free tier allows limited requests per minute. Please wait 60 seconds and try again.")
        st.stop()
    except Exception as e:
        st.error(f"⚠️ An error occurred: {e}")
        st.stop()

def fetch_jumia_products(search_term, limit=10):
    """
    Acts as our 'Jumia API'. 
    Scrapes Jumia using cloudscraper to bypass 403 blocks.
    """
    formatted_query = search_term.replace(' ', '+')
    url = f"https://www.jumia.com.ng/catalog/?q={formatted_query}"
    
    # Initialize CloudScraper
    scraper = cloudscraper.create_scraper(
        browser={
            'browser': 'chrome',
            'platform': 'windows',
            'desktop': True
        }
    )
    
    try:
        # Using the scraper instead of requests
        response = scraper.get(url, timeout=15)
        response.raise_for_status()
    except Exception as e:
        st.error(f"Failed to connect to Jumia. They might be blocking cloud IPs. Error: {e}")
        return []

    soup = BeautifulSoup(response.content, 'html.parser')
    products = []
    
    articles = soup.find_all('article', class_='prd _fb col c-prd')
    
    for article in articles[:limit]:
        try:
            name_elem = article.find('h3', class_='name')
            price_elem = article.find('div', class_='prc')
            link_elem = article.find('a', class_='core')
            
            if name_elem and price_elem:
                name = name_elem.text.strip()
                price = price_elem.text.strip()
                link = "https://www.jumia.com.ng" + link_elem['href'] if link_elem else "No link available"
                
                products.append({
                    "Product Name": name,
                    "Price": price,
                    "Link": link
                })
        except AttributeError:
            continue
            
    return products

def get_ai_recommendation(user_query, products):
    """Asks Gemini to analyze the fetched products and recommend the best option."""
    if not products:
        return "No products found to analyze."
        
    model = genai.GenerativeModel('gemini-2.5-flash')
    products_str = json.dumps(products, indent=2)
    
    prompt = f"""
    You are an expert shopping assistant. A user asked for: "{user_query}"
    
    Here are the top real-time results fetched from Jumia:
    {products_str}
    
    Analyze these options based on the user's request. Consider the prices and specifications implied in the names.
    Provide a concise recommendation of the best 1 or 2 options for the user. Explain why they are good deals. 
    Format your response cleanly using Markdown.
    """
    
    try:
        response = model.generate_content(prompt)
        return response.text
    except ResourceExhausted:
        return "⏳ **Analysis failed:** Google Gemini API rate limit reached. Please wait a minute before making another search."
    except Exception as e:
        return f"⚠️ **Analysis failed:** {e}"

# --- Main App UI ---

st.title("🛒 Jumia AI Price Checker & Assistant")
st.markdown("Ask for a product in plain English, and AI will find and analyze the best real-time deals from Jumia.")

user_query = st.text_input("What are you looking to buy?", placeholder="e.g., I need a short within range 30,000 naira to 40,000")

if st.button("Search Jumia", type="primary"):
    if not api_key:
        st.warning("⚠️ Please enter your Gemini API Key in the sidebar first.")
    elif not user_query:
        st.warning("⚠️ Please enter a product to search for.")
    else:
        with st.spinner("🧠 Extracting search intent..."):
            search_term = extract_search_term(user_query)
            st.info(f"**Target Search Term:** `{search_term}`")
            
        with st.spinner(f"🌐 Fetching live prices from Jumia for '{search_term}'..."):
            products = fetch_jumia_products(search_term, limit=10)
            
        if not products:
            st.error("No products found or Jumia blocked the request. Try a different search term.")
        else:
            st.success(f"Found {len(products)} products!")
            
            col1, col2 = st.columns([1, 1])
            
            with col1:
                st.subheader("📋 Raw Jumia Results")
                df = pd.DataFrame(products)
                st.dataframe(
                    df, 
                    column_config={"Link": st.column_config.LinkColumn("Product Link")},
                    hide_index=True
                )
                
            with col2:
                st.subheader("✨ Gemini AI Recommendation")
                with st.spinner("Analyzing deals..."):
                    recommendation = get_ai_recommendation(user_query, products)
                    st.markdown(recommendation)

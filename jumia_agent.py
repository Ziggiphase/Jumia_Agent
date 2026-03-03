import streamlit as st
import requests
from bs4 import BeautifulSoup
import google.generativeai as genai
from google.api_core.exceptions import ResourceExhausted
import pandas as pd
import json
import os
from dotenv import load_dotenv

# Load environment variables from .env file (for local testing)
load_dotenv()

# --- Page Configuration ---
st.set_page_config(page_title="Jumia AI Assistant", page_icon="🛒", layout="wide")

# --- Sidebar Configuration ---
st.sidebar.title("⚙️ Configuration")
st.sidebar.markdown("Get your [Gemini API Key here](https://aistudio.google.com/app/apikey).")
st.sidebar.markdown("Get your [ScraperAPI Key here](https://www.scraperapi.com/).")

# 1. Load Gemini Key
env_api_key = os.getenv("GEMINI_API_KEY")
if not env_api_key:
    try:
        env_api_key = st.secrets.get("GEMINI_API_KEY")
    except Exception:
        pass

if env_api_key:
    st.sidebar.success("✅ Gemini Key loaded!")
    api_key = env_api_key
    genai.configure(api_key=api_key)
else:
    api_key = st.sidebar.text_input("Enter Gemini API Key", type="password")
    if api_key:
        genai.configure(api_key=api_key)

# 2. Load ScraperAPI Key
env_scraper_key = os.getenv("SCRAPER_API_KEY")
if not env_scraper_key:
    try:
        env_scraper_key = st.secrets.get("SCRAPER_API_KEY")
    except Exception:
        pass

if env_scraper_key:
    st.sidebar.success("✅ ScraperAPI Key loaded!")
    scraper_key = env_scraper_key
else:
    scraper_key = st.sidebar.text_input("Enter ScraperAPI Key", type="password")


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
        st.error("⏳ **Google Gemini API rate limit reached.** Please wait 60 seconds and try again.")
        st.stop()
    except Exception as e:
        st.error(f"⚠️ An error occurred: {e}")
        st.stop()

def fetch_jumia_products(search_term, limit=10):
    """
    Scrapes Jumia using ScraperAPI to completely bypass IP bans and 403 blocks.
    """
    if not scraper_key:
        st.error("Missing ScraperAPI Key. Cannot fetch products.")
        return []

    formatted_query = search_term.replace(' ', '+')
    target_url = f"https://www.jumia.com.ng/catalog/?q={formatted_query}"
    
    # Route the request through ScraperAPI
    payload = {
        'api_key': scraper_key, 
        'url': target_url,
        'render': 'false' # Set to true only if the site requires JS to load products
    }
    
    try:
        # We hit the ScraperAPI endpoint instead of Jumia directly
        response = requests.get('http://api.scraperapi.com', params=payload, timeout=60)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        st.error(f"ScraperAPI failed to fetch the page. Error: {e}")
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

user_query = st.text_input("What are you looking to buy?", placeholder="e.g., I need a cheap smart watch under 20000 naira")

if st.button("Search Jumia", type="primary"):
    if not api_key or not scraper_key:
        st.warning("⚠️ Please ensure both Gemini and ScraperAPI keys are provided.")
    elif not user_query:
        st.warning("⚠️ Please enter a product to search for.")
    else:
        with st.spinner("🧠 Extracting search intent..."):
            search_term = extract_search_term(user_query)
            st.info(f"**Target Search Term:** `{search_term}`")
            
        with st.spinner(f"🌐 Tunneling through ScraperAPI to fetch live prices for '{search_term}'... (This may take 10-20 seconds)"):
            products = fetch_jumia_products(search_term, limit=10)
            
        if not products:
            st.error("No products found. Jumia might have changed their layout, or the proxy timed out.")
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

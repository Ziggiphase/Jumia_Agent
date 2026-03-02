import streamlit as st
import requests
from bs4 import BeautifulSoup
import google.generativeai as genai
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

# Try to get API key from environment first
env_api_key = os.getenv("GEMINI_API_KEY")

if env_api_key:
    st.sidebar.success("✅ API Key loaded from .env file!")
    api_key = env_api_key
#else:
    #api_key = st.sidebar.text_input("Enter Gemini API Key", type="password")

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
    response = model.generate_content(prompt)
    return response.text.strip()

def fetch_jumia_products(search_term, limit=10):
    """
    Acts as our 'Jumia API'. 
    Scrapes Jumia.com.ng for the given search term and returns a list of products.
    """
    # Formatting query for Jumia search URL
    formatted_query = search_term.replace(' ', '+')
    url = f"https://www.jumia.com.ng/catalog/?q={formatted_query}"
    
    # Headers to mimic a real browser request and avoid being blocked
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        st.error(f"Failed to connect to Jumia: {e}")
        return []

    soup = BeautifulSoup(response.content, 'html.parser')
    products = []
    
    # Jumia's product cards are usually wrapped in this article class
    articles = soup.find_all('article', class_='prd _fb col c-prd')
    
    for article in articles[:limit]:
        try:
            name_elem = article.find('h3', class_='name')
            price_elem = article.find('div', class_='prc')
            link_elem = article.find('a', class_='core')
            
            if name_elem and price_elem:
                name = name_elem.text.strip()
                price = price_elem.text.strip()
                # Resolve relative URLs
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
    
    # Convert product list to a formatted string for the prompt
    products_str = json.dumps(products, indent=2)
    
    prompt = f"""
    You are an expert shopping assistant. A user asked for: "{user_query}"
    
    Here are the top real-time results fetched from Jumia:
    {products_str}
    
    Analyze these options based on the user's request. Consider the prices and specifications implied in the names.
    Provide a concise recommendation of the best 1 or 2 options for the user. Explain why they are good deals. 
    Format your response cleanly using Markdown.
    """
    
    response = model.generate_content(prompt)
    return response.text

# --- Main App UI ---

st.title("🛒 Jumia AI Price Checker & Assistant")
st.markdown("Ask for a product in plain English, and AI will find and analyze the best real-time deals from Jumia.")

user_query = st.text_input("What are you looking to buy?", placeholder="e.g., I need a cheap Samsung smartphone under 150k")

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
            
            # Create two columns for layout
            col1, col2 = st.columns([1, 1])
            
            with col1:
                st.subheader("📋 Raw Jumia Results")
                df = pd.DataFrame(products)
                # Display as an interactive dataframe
                st.dataframe(
                    df, 
                    column_config={
                        "Link": st.column_config.LinkColumn("Product Link")
                    },
                    hide_index=True
                )
                
            with col2:
                st.subheader("✨ Gemini AI Recommendation")
                with st.spinner("Analyzing deals..."):
                    recommendation = get_ai_recommendation(user_query, products)
                    st.markdown(recommendation)
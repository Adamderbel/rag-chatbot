import requests
import streamlit as st
from bs4 import BeautifulSoup
from langchain_ollama import OllamaLLM

#load AI model
llm = OllamaLLM(model="mistral:latest") 
# Function to scrape the web page
def scrape_web_page(url):
    try:
        st.write(f"Scraping {url}...")
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers)
        if response.status_code != 200:
            return f"Error: Unable to access {url} (status code: {response.status_code})"
        soup = BeautifulSoup(response.text, 'html.parser')
        paragraphs = soup.find_all('p')
        text = "\n".join([p.get_text() for p in paragraphs])
        return text[:2000]
    except Exception as e: 
        return f"Error: {str(e)}"
def summarize_text(text):
    st.write("Summarizing the text...")
    return llm.invoke(f"summarize this text: {text[:1000]}")
st.title("Web Scraper and Summarizer")
st.write("Enter a URL to scrape and summarize its content.")

url = st.text_input("Enter URL:")
if url:
    content = scrape_web_page(url)
    if "Failed" or "Error" in content:
        st.write(content)
    else:
        st.write("Content scraped successfully!")
        summary = summarize_text(content)
        st.subheader("Summary:")
        st.write(summary)


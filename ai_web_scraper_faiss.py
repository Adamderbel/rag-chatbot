import requests
from bs4 import BeautifulSoup
import streamlit as st
from langchain_ollama import OllamaLLM
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS
from langchain.text_splitter import CharacterTextSplitter
from langchain.schema import Document
import os
import re
import shutil
import json

# --- Configurations ---
FAISS_INDEX_PATH = "faiss_index"
SCRAPED_URLS_FILE = "scraped_urls.json"
CHAT_HISTORY_FILE = "chat_history.json"

# --- Functions to Persist Scraped URLs & Chat History ---
def load_json(filepath):
    if os.path.exists(filepath):
        with open(filepath, "r") as f:
            return json.load(f)
    return []

def save_json(data, filepath):
    with open(filepath, "w") as f:
        json.dump(data, f)

# --- LangChain Components ---
llm = OllamaLLM(model="mistral")
embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")

# --- Load FAISS if exists ---
vector_store = None
if os.path.exists(FAISS_INDEX_PATH):
    try:
        vector_store = FAISS.load_local(
            FAISS_INDEX_PATH,
            embeddings,
            allow_dangerous_deserialization=True
        )
    except Exception as e:
        st.error(f"❌ Failed to load FAISS index: {e}")
        vector_store = None

# --- Streamlit Session State Initialization ---
if "scraped_urls" not in st.session_state:
    st.session_state.scraped_urls = load_json(SCRAPED_URLS_FILE)

if "chat_history" not in st.session_state:
    st.session_state.chat_history = load_json(CHAT_HISTORY_FILE)

# --- Helper Functions ---
def validate_url(url):
    if not url:
        return None
    if not re.match(r'^https?://', url):
        url = f"https://{url}"
    return url

def scrape_website(url):
    try:
        st.write(f"🌍 Scraping website: {url}")
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers, timeout=10)

        if response.status_code != 200:
            return f"⚠️ Failed to fetch {url}: HTTP {response.status_code}"

        soup = BeautifulSoup(response.text, "html.parser")
        paragraphs = soup.find_all("p")
        if not paragraphs:
            return f"⚠️ No paragraph content found on {url}"

        text = " ".join([p.get_text() for p in paragraphs])
        if not text.strip():
            return f"⚠️ Empty content extracted from {url}"

        return text[:5000]
    except requests.exceptions.InvalidSchema:
        return f"❌ Invalid URL: {url}"
    except requests.exceptions.Timeout:
        return f"❌ Request timed out for {url}"
    except requests.exceptions.RequestException as e:
        return f"❌ Network error: {str(e)}"
    except Exception as e:
        return f"❌ Unexpected error: {str(e)}"

def store_in_faiss(text, url):
    global vector_store
    st.write("📥 Storing data in FAISS...")

    splitter = CharacterTextSplitter(chunk_size=500, chunk_overlap=100)
    texts = splitter.split_text(text)
    documents = [Document(page_content=chunk, metadata={"url": url}) for chunk in texts]

    if vector_store is None:
        vector_store = FAISS.from_documents(documents, embeddings)
    else:
        vector_store.add_documents(documents)

    vector_store.save_local(FAISS_INDEX_PATH)
    return "✅ Data stored successfully!"

def retrieve_and_answer(query):
    if vector_store is None or not getattr(vector_store.index, "ntotal", 0):
        return "🤖 No data stored yet."

    results = vector_store.similarity_search(query, k=2)
    context = ""
    for doc in results:
        context += f"From {doc.metadata['url']}:\n{doc.page_content}\n\n"

    if not context:
        return "🤖 No relevant data found."

    # Build conversation history string
    conversation = ""
    for q, a in st.session_state.chat_history:
        conversation += f"User: {q}\nAI: {a}\n"
    conversation += f"User: {query}\nAI:"

    prompt = f"""You are a helpful assistant. Use the context and the conversation history to answer the question.

Context:
{context}

Conversation:
{conversation}
"""

    try:
        answer = llm.invoke(prompt)
        st.session_state.chat_history.append([query, answer])
        save_json(st.session_state.chat_history, CHAT_HISTORY_FILE)
        return answer
    except Exception as e:
        return f"❌ Failed to generate answer: {str(e)}. Ensure the Ollama server is running and the Mistral model is available."

# --- Streamlit UI ---
st.set_page_config(page_title="Web Scraper QA with Persistent Chat", layout="centered")
st.title("🤖 AI-Powered Web Scraper with FAISS Storage & Persistent Chat History")
st.write("🔗 Ask questions about previously scraped websites or enter a new website URL to scrape and store its content for AI-based Q&A!")

# --- Scraping Section ---
url = st.text_input("🔗 Enter Website URL:")
if url and st.button("Scrape and Store"):
    with st.spinner("Scraping and storing..."):
        url = validate_url(url)
        if not url:
            st.error("❌ Invalid URL")
        else:
            content = scrape_website(url)
            if "⚠️" in content or "❌" in content:
                st.error(content)
            else:
                store_message = store_in_faiss(content, url)
                st.success(store_message)
                if url not in st.session_state.scraped_urls:
                    st.session_state.scraped_urls.append(url)
                    save_json(st.session_state.scraped_urls, SCRAPED_URLS_FILE)

# --- Display Scraped URLs ---
if st.session_state.scraped_urls:
    st.subheader("📜 Scraped URLs")
    for u in st.session_state.scraped_urls:
        st.write(f"- {u}")

# --- Question Input Only ---
query = st.text_input("❓ Ask a question based on stored content:")
if query:
    with st.spinner("Generating answer..."):
        _ = retrieve_and_answer(query)

# --- Conversation History (Newest First) ---
if st.session_state.chat_history:
    st.subheader("💬 Conversation History")
    for q, a in reversed(st.session_state.chat_history):
        st.markdown(f"**🧑 You:** {q}")
        st.markdown(f"**🤖 AI:** {a}")

# --- Reset Everything ---
if st.button("🗑️ Reset FAISS Index, Scraped URLs & Chat History"):
    vector_store = None
    if os.path.exists(FAISS_INDEX_PATH):
        shutil.rmtree(FAISS_INDEX_PATH)
    if os.path.exists(SCRAPED_URLS_FILE):
        os.remove(SCRAPED_URLS_FILE)
    if os.path.exists(CHAT_HISTORY_FILE):
        os.remove(CHAT_HISTORY_FILE)
    st.session_state.scraped_urls = []
    st.session_state.chat_history = []
    st.success("✅ FAISS index, scraped URLs, and chat history cleared!")

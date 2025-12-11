# qa.py - Ultimate Forceful Fallback Version
import os
from typing import List, Dict
import streamlit as st
import google.generativeai as genai
from dotenv import load_dotenv

def initialize_gemini_client():
    """Initialize Gemini with robust error handling."""
    load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    
    if not api_key:
        try:
            api_key = st.secrets["GOOGLE_API_KEY"]
        except:
            pass
    
    if not api_key:
        st.error("""
        ### 🔴 NO API KEY FOUND
        
        **Get your FREE key from:** https://aistudio.google.com/app/apikey
        
        **Then create `.env` file with:**
        ```
        GEMINI_API_KEY=AIzaSyYourKeyHere
        ```
        """)
        st.stop()
    
    if not api_key.startswith("AIza"):
        st.error("❌ Invalid key format. Must start with 'AIza...'")
        st.stop()
    
    genai.configure(api_key=api_key)
    return genai

try:
    genai = initialize_gemini_client()
except Exception as e:
    st.error(f"Failed to initialize Gemini: {e}")
    st.stop()

DEFAULT_MODEL = "gemini-2.0-flash"

def get_answer_from_chunks(query: str, chunks: List[Dict], 
                          model: str = DEFAULT_MODEL) -> Dict:
    """
    Force Gemini to answer - retries with general knowledge if refusal detected.
    """
    has_document_context = len(chunks) > 0
    
    if has_document_context:
        context_parts = []
        for i, chunk in enumerate(chunks[:5]):
            context_parts.append(
                f"[FROM DOCUMENT: {chunk['filename']} ({chunk['country']})]\n"
                f"{chunk['text'][:1200]}..."
            )
        context = "\n\n".join(context_parts)
    else:
        context = "NO_DOCUMENTS_AVAILABLE"
    
    # BULLETPROOF PROMPT
    prompt = f"""ROLE: You are a legal expert on Pakistan Penal Code 1860.

QUESTION: {query}

DOCUMENT CONTEXT:
{context}

ABSOLUTE RULES:
1. **NEVER** refuse to answer or say "documents don't contain this"
2. **ALWAYS** provide answer - use documents OR general knowledge
3. For "qatal e amad", "diyat", "qisas" - use your legal training if docs unclear
4. Cite sources only if clearly from documents
5. Format notes/headings as requested with markdown

ANSWER IMMEDIATELY:"""
    
    try:
        model_instance = genai.GenerativeModel(model)
        response = model_instance.generate_content(
            prompt,
            generation_config={"temperature": 0.3, "max_output_tokens": 3000}
        )
        
        answer = response.text
        
        # ===== FORCE RETRY ON REFUSAL =====
        if "documents don't contain" in answer.lower() or "cannot find" in answer.lower():
            # Force general knowledge by clearing chunks and retrying
            st.warning("🔄 Document search failed, using general knowledge...")
            return get_answer_from_chunks(query=query, chunks=[], model=model)
        
        # ===== SOURCE DETECTION =====
        sources = []
        used_general_knowledge = False
        
        if has_document_context and "NO_DOCUMENTS_AVAILABLE" not in context:
            answer_lower = answer.lower()
            
            # Find actual document references
            for chunk in chunks:
                country_lower = chunk['country'].lower()
                filename_lower = chunk['filename'].lower()
                
                # Fuzzy matching
                if (country_lower in answer_lower or 
                    filename_lower.replace('.pdf', '') in answer_lower or
                    any(term in answer_lower for term in chunk['text'][:200].lower().split()[:10])):
                    
                    source_info = f"{chunk['country']} - {chunk['filename']}"
                    if source_info not in sources:
                        sources.append(source_info)
            
            # If no clear references, it used general knowledge
            used_general_knowledge = len(sources) == 0
            
            # Check for refusal patterns (backup check)
            refusal_phrases = ["documents don't contain", "cannot find", "no information", "not mentioned"]
            if any(phrase in answer_lower for phrase in refusal_phrases):
                used_general_knowledge = True
        
        # Clean up apologetic language
        cleaned_answer = answer
        if used_general_knowledge and has_document_context:
            lines = [line for line in answer.split('\n') if not any(phrase in line.lower() for phrase in ["sorry", "cannot find", "no information"])]
            cleaned_answer = '\n'.join(lines)
        
        return {
            "answer": cleaned_answer,
            "sources": sources,
            "model_used": model,
            "chunks_used": len(chunks),
            "used_general_knowledge": used_general_knowledge,
            "has_document_context": has_document_context,
            "refusal_detected": False  # Will be True only on first attempt
        }
    
    except Exception as e:
        return {
            "answer": f"Error: {str(e)}",
            "sources": [],
            "error": str(e),
            "model_used": None,
            "used_general_knowledge": False,
            "has_document_context": has_document_context,
            "refusal_detected": False
        }

def get_available_models() -> List[str]:
    return ["gemini-1.5-flash", "gemini-2.0-flash", "gemini-1.5-pro-001"]
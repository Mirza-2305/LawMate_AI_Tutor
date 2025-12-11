# app.py - Completely Error-Free Version
import streamlit as st
from pathlib import Path
import sys
import os
from datetime import datetime
from io import BytesIO

# CRITICAL: Add path and import ALL dependencies FIRST
sys.path.append(str(Path(__file__).parent))

# ALL IMPORTS AT THE VERY TOP
from file_upload import FileManager
from text_extraction import extract_text, get_preview_text
from chunking import chunk_text, find_relevant_chunks
from qa import get_answer_from_chunks, get_available_models, DEFAULT_MODEL
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from docx import Document

# NOW initialize session state (after imports)
if 'file_manager' not in st.session_state:
    st.session_state.file_manager = FileManager()

if 'qa_history' not in st.session_state:
    st.session_state.qa_history = []

# NOW set page config (after session state)
st.set_page_config(
    page_title="Your LawMate AI Tutor - Document AI Q&A Platform",
    page_icon="📄",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Font optimization (AFTER page config)
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Source+Sans+Pro:wght@400;600;700&display=swap');
</style>
""", unsafe_allow_html=True)

# --- EXPORT FUNCTIONS (defined after imports but before main logic) ---
def create_pdf_export(data: dict) -> bytes:
    """Create PDF from Q&A response."""
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=72, leftMargin=72, topMargin=72, bottomMargin=72)
    
    styles = getSampleStyleSheet()
    story = []
    
    title_style = ParagraphStyle('Title', parent=styles['Heading1'], fontSize=18, spaceAfter=20)
    story.append(Paragraph("Document Q&A Response", title_style))
    story.append(Spacer(1, 12))
    
    normal_style = ParagraphStyle('Normal', parent=styles['Normal'], fontSize=10, spaceBefore=6, spaceAfter=6)
    story.append(Paragraph(f"Date: {data['timestamp']}", normal_style))
    story.append(Paragraph(f"Model: {data['model']}", normal_style))
    
    if data.get('used_general_knowledge', False):
        response_type = "General Knowledge + Document Context"
    elif not data.get('has_document_context', True):
        response_type = "General Knowledge"
    else:
        response_type = "Document-Based"
    
    story.append(Paragraph(f"Type: {response_type}", normal_style))
    story.append(Spacer(1, 20))
    
    heading_style = ParagraphStyle('Heading', parent=styles['Heading2'], fontSize=12, spaceBefore=15, spaceAfter=8)
    story.append(Paragraph("Question:", heading_style))
    story.append(Paragraph(data['question'], normal_style))
    story.append(Spacer(1, 12))
    
    story.append(Paragraph("Answer:", heading_style))
    for line in data['answer'].split('\n'):
        if line.strip():
            story.append(Paragraph(line.strip(), normal_style))
        else:
            story.append(Spacer(1, 6))
    
    if data['sources']:
        story.append(Spacer(1, 12))
        story.append(Paragraph("Sources:", heading_style))
        for source in data['sources']:
            story.append(Paragraph(f"• {source}", normal_style))
    
    doc.build(story)
    buffer.seek(0)
    return buffer.read()

def create_docx_export(data: dict) -> bytes:
    """Create DOCX from Q&A response."""
    buffer = BytesIO()
    doc = Document()
    
    title = doc.add_heading('Document Q&A Response', 0)
    title.alignment = 1
    
    doc.add_paragraph(f'Date: {data["timestamp"]}')
    doc.add_paragraph(f'Model: {data["model"]}')
    
    if data.get('used_general_knowledge', False):
        response_type = "General Knowledge + Document Context"
    elif not data.get('has_document_context', True):
        response_type = "General Knowledge"
    else:
        response_type = "Document-Based"
    
    doc.add_paragraph(f'Type: {response_type}')
    doc.add_paragraph()
    
    doc.add_heading('Question:', level=1)
    doc.add_paragraph(data['question'])
    
    doc.add_heading('Answer:', level=1)
    for line in data['answer'].split('\n'):
        if line.strip():
            doc.add_paragraph(line.strip())
    
    if data['sources']:
        doc.add_heading('Sources:', level=1)
        for source in data['sources']:
            doc.add_paragraph(f'• {source}', style='List Bullet')
    
    doc.save(buffer)
    buffer.seek(0)
    return buffer.read()

# --- MAIN APP LOGIC ---
# Sidebar
st.sidebar.title("📤 Upload Document")
uploaded_file = st.sidebar.file_uploader(
    "Choose a file",
    type=['pdf', 'docx', 'txt', 'png', 'jpg', 'jpeg']
)

countries = ["Pakistan", "India", "USA", "UK", "Canada", "UAE"]
country = st.sidebar.selectbox("Select Country", options=countries)

doc_types = ["Ordinance", "Act", "Course Material", "Student Material", "Policy", "Report", "Other"]
doc_type = st.sidebar.selectbox("Select Document Type", options=doc_types)

st.sidebar.markdown("---")
st.sidebar.subheader("🔑 Gemini API Key")
api_key_input = st.sidebar.text_input("Enter key (if not in .env):", type="password")
if api_key_input:
    os.environ["GOOGLE_API_KEY"] = api_key_input
    st.sidebar.success("✅ Key set!")

if st.sidebar.button("Upload Document", type="primary"):
    if uploaded_file is not None:
        try:
            with st.spinner('Processing...'):
                file_manager = st.session_state.file_manager
                file_path, doc_id = file_manager.save_uploaded_file(uploaded_file, country, doc_type)
                
                text = extract_text(file_path, Path(uploaded_file.name).suffix)
                
                if not text:
                    st.sidebar.error("Failed to extract text.")
                    os.remove(file_path)
                else:
                    chunks = chunk_text(text, doc_id, chunk_size=800, overlap=100)
                    file_manager.add_document(doc_id, uploaded_file.name, country, doc_type, file_path, chunks)
                    st.sidebar.success(f"✅ Uploaded! ID: {doc_id[:8]}...")
                    st.sidebar.info(f"Extracted {len(chunks)} chunks")
                    st.sidebar.text_area("Preview", get_preview_text(text), height=150)
        
        except Exception as e:
            st.sidebar.error(f"❌ Upload failed: {str(e)}")
    else:
        st.sidebar.warning("Please select a file first.")

st.title("📄 LawMater AI Tutor - Document AI Q&A Platform")
st.info(f"Using **{DEFAULT_MODEL}** - Free tier: 15 req/min, 1,500 req/day")

# Filters
col1, col2, col3 = st.columns([2, 2, 3])
with col1:
    filter_country = st.selectbox("Filter by Country", options=["All"] + countries, key="country_filter")
with col2:
    filter_type = st.selectbox("Filter by Document Type", options=["All"] + doc_types, key="type_filter")
with col3:
    search_keyword = st.text_input("Search Documents", placeholder="Enter keyword...")

# Display documents
st.markdown("### 📚 Uploaded Documents")
file_manager = st.session_state.file_manager

if search_keyword:
    documents = file_manager.search_documents(search_keyword)
    st.info(f"Found {len(documents)} documents matching '{search_keyword}'")
else:
    documents = file_manager.get_documents(filter_country, filter_type)

if not documents:
    st.info("No documents uploaded yet.")
else:
    for doc in documents:
        with st.expander(f"📄 {doc['filename']} ({doc['country']} - {doc['doc_type']})"):
            col1, col2 = st.columns([4, 1])
            with col1:
                if doc.get('chunks'):
                    preview = get_preview_text(doc['chunks'][0]['text'], 300)
                    st.text_area("Preview", preview, height=100, key=f"preview_{doc['id']}")
                st.caption(f"ID: {doc['id'][:12]}...")
                st.caption(f"Chunks: {len(doc.get('chunks', []))}")
            with col2:
                if st.button("🗑️ Delete", key=f"del_{doc['id']}", type="secondary"):
                    if file_manager.delete_document(doc['id']):
                        st.success(f"Deleted {doc['filename']}")
                        st.rerun()

# Q&A Section
st.markdown("---")
st.markdown("### 🙋 Ask a Question")
available_models = get_available_models()
selected_model = st.selectbox("Select AI Model", options=available_models, index=0)

question = st.text_area(
    "Enter your question:",
    placeholder="e.g., What are requirements? Or: Make notes on this topic",
    height=100
)

if st.button("Get Answer", type="primary"):
    if not question.strip():
        st.warning("Please enter a question.")
    else:
        try:
            with st.spinner('Generating answer with Gemini...'):
                all_chunks = file_manager.get_all_chunks()
                relevant_chunks = find_relevant_chunks(question, all_chunks, top_k=5)
                
                # Try once with documents
                result = get_answer_from_chunks(query=question, chunks=relevant_chunks, model=selected_model)
                
                # If refusal detected, retry with pure general knowledge
                if result.get('refusal_detected', False) or "cannot find" in result['answer'].lower():
                    st.warning("⚠️ Document search unclear, using general knowledge...")
                    result = get_answer_from_chunks(query=question, chunks=[], model=selected_model)
                
                # Display answer
                st.markdown("#### 🤖 AI Answer")
                
                # Show response type badge
                if result.get('has_document_context', False):
                    if result.get('used_general_knowledge', False):
                        st.info("ℹ️ **General Knowledge Response** (used legal training data)")
                    elif len(result.get('sources', [])) > 0:
                        st.success("📄 **Document-Based Answer**")
                    else:
                        st.info("ℹ️ **Mixed Response** (documents + knowledge)")
                else:
                    st.info("ℹ️ **Pure General Knowledge**")
                
                st.markdown(result['answer'])
                
                # Show sources if available
                if result.get('sources'):
                    st.markdown("#### 📖 Sources")
                    for src in result['sources']:
                        st.caption(f"- **{src}**")
                
                # Debug info (expanded by default if refusal happened)
                with st.expander("🔍 Debug Info", expanded=result.get('refusal_detected', False)):
                    st.write(f"Chunks used: {result.get('chunks_used', 0)}")
                    st.write(f"Model: {result.get('model_used')}")
                    st.write(f"General knowledge used: {result.get('used_general_knowledge')}")
                    st.write(f"Refusal detected: {result.get('refusal_detected')}")
                    if result.get('refusal_detected'):
                        st.warning("Model initially refused. Rephrase question for better document matching.")
                
                # Export data
                export_data = {
                    "question": question,
                    "answer": result['answer'],
                    "sources": result.get('sources', []),
                    "model": result.get('model_used', selected_model),
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "used_general_knowledge": result.get('used_general_knowledge', False),
                    "has_document_context": result.get('has_document_context', False)
                }
                
                # Export buttons
                st.markdown("---")
                st.markdown("#### 💾 Export Answer")
                
                col1, col2 = st.columns(2)
                with col1:
                    pdf_data = create_pdf_export(export_data)
                    st.download_button(
                        label="📄 Download as PDF",
                        data=pdf_data,
                        file_name=f"qa_response_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
                        mime="application/pdf",
                        type="secondary"
                    )
                
                with col2:
                    docx_data = create_docx_export(export_data)
                    st.download_button(
                        label="📝 Download as DOCX",
                        data=docx_data,
                        file_name=f"qa_response_{datetime.now().strftime('%Y%m%d_%H%M%S')}.docx",
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        type="secondary"
                    )
                
                st.session_state.qa_history.append(export_data)
        
        except Exception as e:
            st.error(f"❌ Error: {str(e)}")

# History
if st.session_state.qa_history:
    st.sidebar.markdown("---")
    st.sidebar.markdown("### 💬 Recent Questions")
    for i, qa in enumerate(reversed(st.session_state.qa_history[-5:])):
        with st.sidebar.expander(f"Q{len(st.session_state.qa_history)-i}", expanded=False):
            st.caption(f"**Q:** {qa['question'][:50]}...")
            st.caption(f"**A:** {qa['answer'][:100]}...")

st.sidebar.markdown("---")
st.sidebar.info("✅ **All features active**: Fallback, Notes, Export")
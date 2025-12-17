# app.py - Comprehensive final working version
import streamlit as st
from pathlib import Path
import sys
import os
import uuid
from datetime import datetime
from io import BytesIO

# Add path and imports
sys.path.append(str(Path(__file__).parent))

from supabase_client import SupabaseManager
from text_extraction import extract_text, get_preview_text
from chunking import chunk_text, find_relevant_chunks
from qa import get_answer_from_chunks, get_available_models, DEFAULT_MODEL
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from docx import Document

# --- CONFIGURE STREAMLIT ---
st.set_page_config(
    page_title="LawMate AI Tutor - Document Q&A",
    page_icon="📄",
    layout="wide",
    initial_sidebar_state="expanded"
)
# Allow large files (max 1GB)
st.set_option('server.maxUploadSize', 1024)

# --- EXPORT FUNCTIONS ---
def create_pdf_export(data: dict) -> bytes:
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
    buffer = BytesIO()
    doc = Document()
    
    doc.add_heading('Document Q&A Response', 0).alignment = 1
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


# === AUTHENTICATION ===
def login_user():
    st.sidebar.title("🔐 User Login")
    if 'user' not in st.session_state:
        st.session_state.user = None
    
    if st.session_state.user is None:
        username = st.sidebar.text_input("Username")
        password = st.sidebar.text_input("Password", type="password")
        if st.sidebar.button("Login"):
            file_manager = st.session_state.file_manager
            user = file_manager.verify_user(username, password)
            if user:
                st.session_state.user = user
                st.sidebar.success(f"✅ Welcome, {user['username']} ({user['role']})!")
                st.rerun()
            else:
                st.sidebar.error("❌ Invalid credentials")
        st.sidebar.info("Default admin login: username='admin', password='admin123'")
    else:
        st.sidebar.success(f"Logged in: {st.session_state.user['username']} ({st.session_state.user['role']})")
        if st.sidebar.button("Logout"):
            st.session_state.user = None
            st.rerun()


# === MAIN FUNCTION ===
def main():
    # Font optimization
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Source+Sans+Pro:wght@400;600;700&display=swap');
    </style>
    """, unsafe_allow_html=True)
    
    # Initialize session state
    if 'file_manager' not in st.session_state:
        st.session_state.file_manager = SupabaseManager()
    if 'qa_history' not in st.session_state:
        st.session_state.qa_history = []
    
    # Login system
    login_user()
    
    # User context
    is_admin = False
    user_id = "guest"
    user_role = "guest"
    if st.session_state.user:
        is_admin = st.session_state.user['role'] == 'admin'
        user_id = st.session_state.user['user_id']
        user_role = st.session_state.user['role']
    
    # Mode indicator
    if is_admin:
        st.success("👑 Admin Mode")
    elif st.session_state.user:
        st.info("👤 User Mode")
    else:
        st.warning("👥 Guest Mode")
    
    # --- UPLOAD SECTION ---
    st.sidebar.title("📤 Upload Document")
    uploaded_file = st.sidebar.file_uploader("Choose a file", type=['pdf', 'docx', 'txt', 'png', 'jpg', 'jpeg'])
    
    countries = ["Pakistan", "India", "USA", "UK", "Canada", "UAE"]
    country = st.sidebar.selectbox("Select Country", options=countries)
    doc_types = ["Ordinance", "Act", "Course Material", "Student Material", "Policy", "Report", "Other"]
    doc_type = st.sidebar.selectbox("Select Document Type", options=doc_types)
    
    if st.sidebar.button("Upload Document"):
        if uploaded_file is None:
            st.sidebar.warning("Please select a file first")
        else:
            try:
                with st.spinner('Processing upload...'):
                    file_content = uploaded_file.read()
                    if not file_content:
                        st.sidebar.error("❌ File is empty")
                        st.stop()
                    
                    # Extract text
                    text = extract_text(file_content, Path(uploaded_file.name).suffix)
                    if not text or len(text.strip()) < 50:
                        st.sidebar.error("❌ Failed to extract text. Document may be scanned images.")
                        st.sidebar.info("Tip: Upload text-based PDF or DOCX")
                    else:
                        chunks = chunk_text(text, str(uuid.uuid4()), chunk_size=800, overlap=100)
                        owner_role = "admin" if is_admin else "user"
                        
                        st.sidebar.write(f"Uploading {uploaded_file.name} ({len(file_content)} bytes)...")
                        
                        doc_id = st.session_state.file_manager.add_document(
                            uploaded_file.name, country, doc_type,
                            user_id, owner_role, file_content, chunks
                        )
                        if doc_id:
                            st.sidebar.success(f"✅ Uploaded successfully! ID: {doc_id[:8]}...")
                            st.rerun()
                        else:
                            st.sidebar.error("❌ Upload failed")
            except Exception as e:
                st.sidebar.error(f"❌ Upload error: {str(e)}")
                st.sidebar.code(str(e))
    
    # --- DOCUMENTS DISPLAY & Q&A ---
    st.title("📄 LawMate AI Tutor - Document Q&A Platform")
    st.info(f"Using AI Model: {DEFAULT_MODEL}")
    
    col1, col2, col3 = st.columns([2,2,3])
    filter_country = st.selectbox("Filter by Country", options=["All"] + countries, key="country_filter")
    filter_type = st.selectbox("Filter by Document Type", options=["All"] + doc_types, key="type_filter")
    search_keyword = st.text_input("Search Documents", placeholder="Enter keyword...")
    
    file_manager = st.session_state.file_manager
    if search_keyword:
        documents = file_manager.search_documents(user_id, user_role, search_keyword)
        st.info(f"Found {len(documents)} documents for '{search_keyword}'")
    else:
        documents = file_manager.get_documents_by_filters(user_id, user_role, filter_country, filter_type)
    
    if not documents:
        st.info("No documents uploaded yet.")
    else:
        for doc in documents:
            with st.expander(f"{doc['filename']} ({doc['country']} - {doc['doc_type']})"):
                col1, col2 = st.columns([4,1])
                with col1:
                    if doc.get('chunks'):
                        preview = get_preview_text(doc['chunks'][0]['text'], 300)
                        st.text_area("Preview", preview, height=100, key=f"preview_{doc['id']}")
                    st.caption(f"ID: {doc['id'][:12]}...")
                    st.caption(f"Chunks: {len(doc.get('chunks', []))}")
                    st.caption(f"Owner: {doc['owner_role']}")
                with col2:
                    if is_admin and st.button("🗑️ Delete", key=f"del_{doc['id']}"):
                        if file_manager.delete_document(doc['id'], user_id, user_role):
                            st.success(f"Deleted {doc['filename']}")
                            st.rerun()
    
    # --- Q&A SECTION ---
    st.markdown("---")
    st.markdown("### 🙋 Ask a Question")
    available_models = get_available_models()
    selected_model = st.selectbox("Select AI Model", options=available_models, index=0)
    question = st.text_area("Enter your question:", placeholder="Type your question here", height=100)
    
    if st.button("Get Answer"):
        if not question.strip():
            st.warning("Please enter a question")
        else:
            try:
                with st.spinner('Generating answer...'):
                    all_chunks = file_manager.get_all_chunks(user_id, user_role)
                    relevant_chunks = find_relevant_chunks(question, all_chunks, top_k=5)
                    result = get_answer_from_chunks(query=question, chunks=relevant_chunks, model=selected_model)
                    
                    st.markdown("#### 🤖 AI Answer")
                    st.markdown(result['answer'])
                    if result.get('sources'):
                        st.markdown("#### 📖 Sources")
                        for src in result['sources']:
                            st.caption(f"- {src}")
                    
                    export_data = {
                        "question": question,
                        "answer": result['answer'],
                        "sources": result.get('sources', []),
                        "model": result.get('model_used', selected_model),
                        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "used_general_knowledge": result.get('used_general_knowledge', False),
                        "has_document_context": result.get('has_document_context', False)
                    }
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        pdf_data = create_pdf_export(export_data)
                        st.download_button("📄 Download as PDF", pdf_data,
                                           file_name=f"qa_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
                                           mime="application/pdf")
                    with col2:
                        docx_data = create_docx_export(export_data)
                        st.download_button("📝 Download as DOCX", docx_data,
                                           file_name=f"qa_{datetime.now().strftime('%Y%m%d_%H%M%S')}.docx",
                                           mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
                    
                    st.session_state.qa_history.append(export_data)
            except Exception as e:
                st.error(f"❌ Q&A error: {str(e)}")
    
    # --- HISTORY ---
    if st.session_state.qa_history:
        st.sidebar.markdown("---")
        st.sidebar.markdown("### 💬 Recent Questions")
        for i, qa in enumerate(reversed(st.session_state.qa_history[-5:])):
            with st.sidebar.expander(f"Q{len(st.session_state.qa_history)-i}", expanded=False):
                st.caption(f"Q: {qa['question'][:50]}...")
                st.caption(f"A: {qa['answer'][:100]}...")


# === ENTRY POINT ===
if __name__ == "__main__":
    main()

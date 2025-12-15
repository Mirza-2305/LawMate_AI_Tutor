# app.py - Complete Access Control & Authentication Version
import streamlit as st
from pathlib import Path
import sys
import os
import uuid
from datetime import datetime
from io import BytesIO

# Add path and imports
sys.path.append(str(Path(__file__).parent))

from file_upload import FileManager
from text_extraction import extract_text, get_preview_text
from chunking import chunk_text, find_relevant_chunks
from qa import get_answer_from_chunks, get_available_models, DEFAULT_MODEL
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from docx import Document

# --- EXPORT FUNCTIONS ---
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

# === AUTHENTICATION SYSTEM ===
def login_user():
    """Handle user login and session management."""
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
        
        # Show default credentials hint
        st.sidebar.info("Default admin login: username='admin', password='admin123'")
    else:
        st.sidebar.success(f"Logged in: {st.session_state.user['username']} ({st.session_state.user['role']})")
        if st.sidebar.button("Logout"):
            st.session_state.user = None
            st.rerun()

# === MAIN APP FUNCTION ===
def main():
    """Complete main application function."""
    
    # CRITICAL: Page config must be FIRST
    st.set_page_config(
        page_title="Your LawMate AI Tutor - Document AI Q&A Platform",
        page_icon="📄",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    # Font optimization
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Source+Sans+Pro:wght@400;600;700&display=swap');
    </style>
    """, unsafe_allow_html=True)
    
    # Initialize session state
    if 'file_manager' not in st.session_state:
        st.session_state.file_manager = FileManager()
    
    if 'qa_history' not in st.session_state:
        st.session_state.qa_history = []
    
    # === LOGIN SYSTEM ===
    login_user()
    
    # Determine user context
    is_admin = False
    user_id = "guest"
    user_role = "guest"
    if st.session_state.user:
        is_admin = st.session_state.user['role'] == 'admin'
        user_id = st.session_state.user['user_id']
        user_role = st.session_state.user['role']
    
    # Show mode indicator
    if is_admin:
        st.success("👑 **Admin Mode** - You can see ALL documents and delete any")
    elif st.session_state.user:
        st.info(f"👤 **User Mode** - You see your docs + admin docs")
    else:
        st.warning("👥 **Guest Mode** - You can only see admin documents")
    
    # === UPLOAD SECTION (Available to ALL) ===
    st.sidebar.title("📤 Upload Document")
    uploaded_file = st.sidebar.file_uploader(
        "Choose a file",
        type=['pdf', 'docx', 'txt', 'png', 'jpg', 'jpeg']
    )
    
    countries = ["Pakistan", "India", "USA", "UK", "Canada", "UAE"]
    country = st.sidebar.selectbox("Select Country", options=countries)
    
    doc_types = ["Ordinance", "Act", "Course Material", "Student Material", "Policy", "Report", "Other"]
    doc_type = st.sidebar.selectbox("Select Document Type", options=doc_types)
    
    if st.sidebar.button("Upload Document", type="primary"):
        if uploaded_file is not None:
            try:
                with st.spinner('Processing...'):
                    file_manager = st.session_state.file_manager
                    
                    # ✅ FIX 1: Read file content as bytes FIRST
                    file_content = uploaded_file.getvalue()
                    
                    # ✅ FIX 2: Generate ID without saving to disk
                    doc_id = str(uuid.uuid4())
                    
                    # ✅ FIX 3: Extract text directly from bytes
                    text = extract_text(file_content, Path(uploaded_file.name).suffix)
                    
                    if not text or len(text.strip()) < 50:
                        st.sidebar.error("❌ Failed to extract meaningful text. Document may be scanned images.")
                    else:
                        # ✅ FIX 4: Generate chunks
                        chunks = chunk_text(text, doc_id, chunk_size=800, overlap=100)
                        
                        # ✅ FIX 5: Determine ownership
                        owner_role = "admin" if is_admin else "user"
                        
                        # ✅ FIX 6: Save to database with BLOB
                        file_manager.add_document(
                            doc_id, uploaded_file.name, country, doc_type,
                            user_id, owner_role, file_content, chunks
                        )
                        
                        st.sidebar.success(f"✅ Uploaded! {len(chunks)} chunks extracted")
                        st.sidebar.text_area("Preview", get_preview_text(text), height=150)
                        st.rerun()
            
            except Exception as e:
                st.sidebar.error(f"❌ Upload failed: {str(e)}")
                st.sidebar.error(f"Debug: {type(e).__name__}")
        else:
            st.sidebar.warning("Please select a file first.")
    
    # === FILTERS ===
    st.title("📄 Your LawMate AI Tutor - Document AI Q&A Platform")
    st.info(f"Using **{DEFAULT_MODEL}** - Free tier: 15 req/min, 1,500 req/day")
    
    col1, col2, col3 = st.columns([2, 2, 3])
    with col1:
        filter_country = st.selectbox("Filter by Country", options=["All"] + countries, key="country_filter")
    with col2:
        filter_type = st.selectbox("Filter by Document Type", options=["All"] + doc_types, key="type_filter")
    with col3:
        search_keyword = st.text_input("Search Documents", placeholder="Enter keyword...")
    
    # === DISPLAY DOCUMENTS (with access control) ===
    st.markdown("### 📚 Uploaded Documents")
    file_manager = st.session_state.file_manager
    
    if search_keyword:
        documents = file_manager.search_documents(user_id, user_role, search_keyword)
        st.info(f"Found {len(documents)} documents matching '{search_keyword}'")
    else:
        documents = file_manager.get_documents(user_id, user_role, filter_country, filter_type)
    
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
                    st.caption(f"Owner: {'👑 Admin' if doc['owner_role'] == 'admin' else '👤 User'}")
                
                with col2:
                    # Delete button (admin ONLY)
                    if is_admin:
                        if st.button("🗑️ Delete", key=f"del_{doc['id']}", type="secondary"):
                            if file_manager.delete_document(doc['id'], user_id, user_role):
                                st.success(f"Deleted {doc['filename']}")
                                st.rerun()
    
    # === Q&A SECTION ===
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
                    all_chunks = file_manager.get_all_chunks(user_id, user_role)
                    relevant_chunks = find_relevant_chunks(question, all_chunks, top_k=5)
                    
                    result = get_answer_from_chunks(query=question, chunks=relevant_chunks, model=selected_model)
                    
                    st.markdown("#### 🤖 AI Answer")
                    
                    if result.get('has_document_context', False):
                        if result.get('used_general_knowledge', False):
                            st.info("ℹ️ General knowledge enhanced with document context")
                        elif len(result.get('sources', [])) > 0:
                            st.success("📄 Answer based on uploaded documents")
                        else:
                            st.info("ℹ️ General knowledge response (document reference unclear)")
                    else:
                        st.info("ℹ️ Pure general knowledge response")
                    
                    st.markdown(result['answer'])
                    
                    if result.get('sources'):
                        st.markdown("#### 📖 Sources")
                        for src in result['sources']:
                            st.caption(f"- **{src}**")
                    
                    # Export buttons
                    st.markdown("---")
                    st.markdown("#### 💾 Export Answer")
                    
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
                    
                    with st.expander("🔍 Debug Info"):
                        st.write(f"Chunks used: {result.get('chunks_used', 0)}")
                        st.write(f"Model: {result.get('model_used')}")
                        st.write(f"General knowledge used: {result.get('used_general_knowledge')}")
            
            except Exception as e:
                st.error(f"❌ Error: {str(e)}")
    
    # === HISTORY SECTION ===
    if st.session_state.qa_history:
        st.sidebar.markdown("---")
        st.sidebar.markdown("### 💬 Recent Questions")
        for i, qa in enumerate(reversed(st.session_state.qa_history[-5:])):
            with st.sidebar.expander(f"Q{len(st.session_state.qa_history)-i}", expanded=False):
                st.caption(f"**Q:** {qa['question'][:50]}...")
                st.caption(f"**A:** {qa['answer'][:100]}...")

# === ENTRY POINT ===
if __name__ == "__main__":
    main()
import os
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from database import DocumentDatabase

# File manager for handling uploads and storage
class FileManager:
    def __init__(self, upload_dir: str = "/tmp/uploaded_docs", use_database: bool = True):
        """Use /tmp for Streamlit Cloud"""
        self.upload_dir = Path(upload_dir)
        self.upload_dir.mkdir(exist_ok=True)
        self.db = DocumentDatabase() if use_database else None
        self.documents = []  # In-memory storage if DB not used
    
    def save_uploaded_file(self, uploaded_file, country: str, 
                          doc_type: str) -> Tuple[str, str]:
        """
        Save uploaded file to disk and return file path and doc ID.
        
        Args:
            uploaded_file: Streamlit uploaded file object
            country: Selected country
            doc_type: Selected document type
        
        Returns:
            Tuple of (file_path, doc_id)
        """
        # Generate unique filename
        file_extension = Path(uploaded_file.name).suffix
        doc_id = f"{country.lower()}_{doc_type.lower()}_{os.urandom(4).hex()}"
        filename = f"{doc_id}{file_extension}"
        file_path = self.upload_dir / filename
        
        # Save file
        with open(file_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
        
        return str(file_path), doc_id
    
    def add_document(self, doc_id: str, filename: str, country: str, 
                    doc_type: str, file_path: str, chunks: List[Dict]):
        """Add document to storage (DB or memory)."""
        if self.db:
            return self.db.add_document(filename, country, doc_type, 
                                       file_path, chunks)
        else:
            # In-memory storage
            doc = {
                'id': doc_id,
                'filename': filename,
                'country': country,
                'doc_type': doc_type,
                'file_path': file_path,
                'chunks': chunks
            }
            self.documents.append(doc)
            return doc_id
    
    def get_documents(self, country: Optional[str] = None, 
                     doc_type: Optional[str] = None) -> List[Dict]:
        """Get documents with optional filtering."""
        if self.db:
            return self.db.get_documents_by_filters(country, doc_type)
        else:
            # Filter in-memory documents
            docs = self.documents
            if country and country != "All":
                docs = [d for d in docs if d['country'] == country]
            if doc_type and doc_type != "All":
                docs = [d for d in docs if d['doc_type'] == doc_type]
            return docs
    
    def delete_document(self, doc_id: str) -> bool:
        """Delete document from storage and disk."""
        if self.db:
            # Get document info first
            docs = self.db.get_all_documents()
            doc_to_delete = next((d for d in docs if d['id'] == doc_id), None)
            
            if doc_to_delete:
                # Delete file
                try:
                    os.remove(doc_to_delete['file_path'])
                except FileNotFoundError:
                    pass
                
                # Delete from DB
                return self.db.delete_document(doc_id)
        else:
            # In-memory deletion
            doc_to_delete = next((d for d in self.documents if d['id'] == doc_id), None)
            if doc_to_delete:
                try:
                    os.remove(doc_to_delete['file_path'])
                except FileNotFoundError:
                    pass
                self.documents = [d for d in self.documents if d['id'] != doc_id]
                return True
        
        return False
    
    def search_documents(self, keyword: str) -> List[Dict]:
        """Search documents by keyword."""
        if self.db:
            return self.db.search_documents(keyword)
        else:
            # Simple in-memory search
            keyword_lower = keyword.lower()
            results = []
            for doc in self.documents:
                if (keyword_lower in doc['filename'].lower() or 
                    any(keyword_lower in chunk['text'].lower() 
                        for chunk in doc['chunks'])):
                    results.append(doc)
            return results
    
    def get_all_chunks(self) -> List[Dict]:
        """Get all chunks from all documents."""
        chunks = []
        docs = self.get_documents()
        for doc in docs:
            for chunk in doc.get('chunks', []):
                # Add document metadata to chunk
                chunk_with_meta = chunk.copy()
                chunk_with_meta.update({
                    'filename': doc['filename'],
                    'country': doc['country'],
                    'doc_type': doc['doc_type']
                })
                chunks.append(chunk_with_meta)
        return chunks
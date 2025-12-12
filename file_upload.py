# file_upload.py - Handles file content (bytes)
import os
import uuid
from pathlib import Path
from typing import Dict, List, Optional
from database import DocumentDatabase

class FileManager:
    def __init__(self, db_path: str = "/tmp/documents.db"):
        self.db = DocumentDatabase(db_path)
    
    def add_document(self, doc_id: str, filename: str, country: str, 
                    doc_type: str, owner_id: str, owner_role: str, 
                    file_content: bytes, chunks: List[Dict]):
        """Add document to database with ownership."""
        return self.db.add_document(filename, country, doc_type, owner_id, 
                                   owner_role, file_content, chunks)
    
    def get_documents(self, user_id: str, user_role: str, 
                     country: Optional[str] = None, 
                     doc_type: Optional[str] = None) -> List[Dict]:
        return self.db.get_documents_by_filters(user_id, user_role, country, doc_type)
    
    def search_documents(self, user_id: str, user_role: str, keyword: str) -> List[Dict]:
        return self.db.search_documents(user_id, user_role, keyword)
    
    def delete_document(self, doc_id: str, user_id: str, user_role: str) -> bool:
        return self.db.delete_document(doc_id, user_id, user_role)
    
    def get_all_chunks(self, user_id: str, user_role: str) -> List[Dict]:
        return self.db.get_all_chunks(user_id, user_role)
    
    def verify_user(self, username: str, password: str) -> Optional[Dict]:
        return self.db.verify_user(username, password)
    
    def create_user(self, username: str, password: str, role: str = "user") -> Optional[str]:
        return self.db.create_user(username, password, role)
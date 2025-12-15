# file_upload.py - Complete working version
import sqlite3
import json
import uuid
from pathlib import Path
from typing import Dict, List, Optional
import platform

class FileManager:
    def __init__(self, db_path: str = None):
        """Auto-detect OS and set appropriate database path."""
        if db_path is None:
            if platform.system() == "Windows":
                db_path = str(Path(__file__).parent / "documents.db")
            else:
                db_path = "/tmp/documents.db"
        
        self.db_path = db_path
        self.init_database()  # ✅ This method is now defined below
    
    def init_database(self):
        """Initialize database with BLOB support."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS documents (
                    id TEXT PRIMARY KEY,
                    filename TEXT NOT NULL,
                    country TEXT NOT NULL,
                    doc_type TEXT NOT NULL,
                    upload_date TEXT NOT NULL,
                    owner_id TEXT NOT NULL,
                    owner_role TEXT NOT NULL,
                    file_content BLOB NOT NULL,
                    chunks TEXT NOT NULL
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id TEXT PRIMARY KEY,
                    username TEXT UNIQUE NOT NULL,
                    password TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'user'
                )
            """)
            
            # Create default admin user
            cursor = conn.execute("SELECT COUNT(*) FROM users WHERE role='admin'")
            if cursor.fetchone()[0] == 0:
                conn.execute(
                    "INSERT INTO users VALUES (?, ?, ?, ?)",
                    ("admin_001", "admin", "admin123", "admin")
                )
            
            conn.commit()
    
    def save_uploaded_file(self, uploaded_file, country: str, doc_type: str) -> str:
        """Generate document ID (no actual file save - we use BLOBs)."""
        return str(uuid.uuid4())
    
    def add_document(self, doc_id: str, filename: str, country: str, 
                    doc_type: str, owner_id: str, owner_role: str, 
                    file_content: bytes, chunks: List[Dict]) -> str:
        """Save document with BLOB to database."""
        from datetime import datetime
        upload_date = datetime.now().isoformat()
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """INSERT INTO documents 
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (doc_id, filename, country, doc_type, upload_date,
                 owner_id, owner_role, file_content, json.dumps(chunks))
            )
            conn.commit()
        return doc_id
    
    def get_documents_by_filters(self, user_id: str, user_role: str,
                                 country: Optional[str] = None, 
                                 doc_type: Optional[str] = None) -> List[Dict]:
        """Get documents with access control."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT * FROM documents ORDER BY upload_date DESC")
            all_docs = [dict(row) for row in cursor.fetchall()]
            
            # Apply access control
            filtered_docs = []
            for doc in all_docs:
                doc['chunks'] = json.loads(doc['chunks'])
                
                if user_role == "admin" or doc['owner_role'] == "admin" or doc['owner_id'] == user_id:
                    if country and country != "All" and doc['country'] != country:
                        continue
                    if doc_type and doc_type != "All" and doc['doc_type'] != doc_type:
                        continue
                    filtered_docs.append(doc)
            
            return filtered_docs
    
    def search_documents(self, user_id: str, user_role: str, keyword: str) -> List[Dict]:
        """Search documents with access control."""
        search_term = f"%{keyword.lower()}%"
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                """SELECT * FROM documents 
                   WHERE (LOWER(filename) LIKE ? OR LOWER(chunks) LIKE ?)
                   ORDER BY upload_date DESC""",
                (search_term, search_term)
            )
            documents = []
            for row in cursor.fetchall():
                doc = dict(row)
                doc['chunks'] = json.loads(doc['chunks'])
                
                if user_role == "admin" or doc['owner_role'] == "admin" or doc['owner_id'] == user_id:
                    documents.append(doc)
            return documents
    
    def delete_document(self, doc_id: str, user_id: str, user_role: str) -> bool:
        """Delete document (admin only)."""
        if user_role != "admin":
            return False
            
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
            conn.commit()
            return cursor.rowcount > 0
    
    def get_all_chunks(self, user_id: str, user_role: str) -> List[Dict]:
        """Get all accessible chunks."""
        chunks = []
        docs = self.get_documents_by_filters(user_id, user_role)
        for doc in docs:
            for chunk in doc.get('chunks', []):
                chunk_with_meta = chunk.copy()
                chunk_with_meta.update({
                    'filename': doc['filename'],
                    'country': doc['country'],
                    'doc_type': doc['doc_type']
                })
                chunks.append(chunk_with_meta)
        return chunks
    
    def verify_user(self, username: str, password: str) -> Optional[Dict]:
        """Verify user credentials."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT user_id, username, role FROM users WHERE username = ? AND password = ?",
                (username, password)
            )
            user = cursor.fetchone()
            return dict(user) if user else None
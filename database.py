# database.py - Complete with authentication & access control
import sqlite3
import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional
import uuid

class DocumentDatabase:
    def __init__(self, db_path: str = "/tmp/documents.db"):
        """Initialize SQLite database connection."""
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """Create tables if they don't exist."""
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
            
            # Create users table for authentication
            conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id TEXT PRIMARY KEY,
                    username TEXT UNIQUE NOT NULL,
                    password TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'user'
                )
            """)
            
            # Create default admin user if not exists
            cursor = conn.execute("SELECT COUNT(*) FROM users WHERE role='admin'")
            if cursor.fetchone()[0] == 0:
                conn.execute(
                    "INSERT INTO users VALUES (?, ?, ?, ?)",
                    ("admin_001", "admin", "admin123", "admin")
                )
            
            conn.commit()
    
    def add_document(self, filename: str, country: str, doc_type: str, 
                     owner_id: str, owner_role: str, file_content: bytes, 
                     chunks: List[Dict]) -> str:
        """Add a document to the database."""
        doc_id = str(uuid.uuid4())
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
    
    def get_all_documents(self, user_id: str, user_role: str) -> List[Dict]:
        """Retrieve all documents with access control."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT * FROM documents ORDER BY upload_date DESC")
            documents = []
            for row in cursor.fetchall():
                doc = dict(row)
                doc['chunks'] = json.loads(doc['chunks'])
                
                # Access control: admin sees all, users see admin docs + their own
                if user_role == "admin" or doc['owner_role'] == "admin" or doc['owner_id'] == user_id:
                    documents.append(doc)
            
        return documents
    
    def get_documents_by_filters(self, user_id: str, user_role: str,
                                 country: Optional[str] = None, 
                                 doc_type: Optional[str] = None) -> List[Dict]:
        """Filter documents with access control."""
        query = "SELECT * FROM documents WHERE 1=1"
        params = []
        
        if country and country != "All":
            query += " AND country = ?"
            params.append(country)
        
        if doc_type and doc_type != "All":
            query += " AND doc_type = ?"
            params.append(doc_type)
        
        query += " ORDER BY upload_date DESC"
        
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(query, params)
            documents = []
            for row in cursor.fetchall():
                doc = dict(row)
                doc['chunks'] = json.loads(doc['chunks'])
                
                # Access control
                if user_role == "admin" or doc['owner_role'] == "admin" or doc['owner_id'] == user_id:
                    documents.append(doc)
                    
        return documents
    
    def search_documents(self, user_id: str, user_role: str, keyword: str) -> List[Dict]:
        """Search documents by keyword with access control."""
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
                
                # Access control
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
        """Get all chunks with access control."""
        chunks = []
        docs = self.get_all_documents(user_id, user_role)
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
    
    def create_user(self, username: str, password: str, role: str = "user") -> Optional[str]:
        """Create a new user."""
        user_id = str(uuid.uuid4())
        with sqlite3.connect(self.db_path) as conn:
            try:
                conn.execute(
                    "INSERT INTO users VALUES (?, ?, ?, ?)",
                    (user_id, username, password, role)
                )
                conn.commit()
                return user_id
            except sqlite3.IntegrityError:
                return None  # Username already exists
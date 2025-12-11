import sqlite3
import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional
import uuid

# Database manager for persistent document storage using SQLite
class DocumentDatabase:
    def __init__(self, db_path: str = "documents.db"):
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
                    file_path TEXT NOT NULL,
                    chunks TEXT NOT NULL  -- JSON serialized list of chunks
                )
            """)
            conn.commit()
    
    def add_document(self, filename: str, country: str, doc_type: str, 
                     file_path: str, chunks: List[Dict]) -> str:
        """Add a document to the database."""
        doc_id = str(uuid.uuid4())
        upload_date = datetime.now().isoformat()
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO documents VALUES (?, ?, ?, ?, ?, ?, ?)",
                (doc_id, filename, country, doc_type, upload_date, 
                 file_path, json.dumps(chunks))
            )
            conn.commit()
        return doc_id
    
    def get_all_documents(self) -> List[Dict]:
        """Retrieve all documents from database."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT * FROM documents ORDER BY upload_date DESC")
            documents = []
            for row in cursor.fetchall():
                doc = dict(row)
                doc['chunks'] = json.loads(doc['chunks'])
                documents.append(doc)
        return documents
    
    def get_documents_by_filters(self, country: Optional[str] = None, 
                                 doc_type: Optional[str] = None) -> List[Dict]:
        """Filter documents by country and/or document type."""
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
                documents.append(doc)
        return documents
    
    def delete_document(self, doc_id: str) -> bool:
        """Delete a document from database."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
            conn.commit()
            return cursor.rowcount > 0
    
    def search_documents(self, keyword: str) -> List[Dict]:
        """Search documents by keyword in filename or chunks."""
        search_term = f"%{keyword.lower()}%"
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                """SELECT * FROM documents 
                   WHERE LOWER(filename) LIKE ? OR LOWER(chunks) LIKE ?
                   ORDER BY upload_date DESC""",
                (search_term, search_term)
            )
            documents = []
            for row in cursor.fetchall():
                doc = dict(row)
                doc['chunks'] = json.loads(doc['chunks'])
                documents.append(doc)
        return documents
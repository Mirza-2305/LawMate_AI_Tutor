# supabase_client.py - Complete with table creation and error handling
import os
import streamlit as st
from supabase import create_client, Client
from typing import List, Dict, Optional
import json
import uuid
from datetime import datetime

class SupabaseManager:
    def __init__(self):
        """Initialize Supabase connection and ensure all infrastructure exists."""
        # Get credentials from Streamlit Cloud Secrets
        self.supabase_url = os.getenv("SUPABASE_URL") or st.secrets.get("SUPABASE_URL")
        self.supabase_key = os.getenv("SUPABASE_KEY") or st.secrets.get("SUPABASE_KEY")
        
        if not self.supabase_url or not self.supabase_key:
            raise ValueError("❌ Supabase credentials not found in secrets or environment variables")
        
        self.client: Client = create_client(self.supabase_url, self.supabase_key)
        
        # Ensure infrastructure exists
        self._ensure_tables_exist()
        self._ensure_storage_bucket_exists()
        
        st.sidebar.success("✅ Connected to Supabase")
    
    def _ensure_tables_exist(self):
        """Create documents and users tables if they don't exist."""
        try:
            # Check if documents table exists by attempting a simple query
            self.client.table("documents").select("id").limit(1).execute()
        except Exception as e:
            if "does not exist" in str(e).lower() or "404" in str(e):
                st.info("📦 Creating documents table...")
                self._create_documents_table()
            else:
                st.error(f"❌ Unexpected error checking documents table: {e}")
        
        try:
            # Check if users table exists
            self.client.table("users").select("user_id").limit(1).execute()
        except Exception as e:
            if "does not exist" in str(e).lower() or "404" in str(e):
                st.info("📦 Creating users table...")
                self._create_users_table()
            else:
                st.error(f"❌ Unexpected error checking users table: {e}")
        
        # Create default admin if no users exist
        self._create_default_admin()
    
    def _create_documents_table(self):
        """Create documents table with correct schema."""
        try:
            # Use raw SQL to create table
            self.client.rpc("exec", {
                "sql": """
                    CREATE TABLE documents (
                        id TEXT PRIMARY KEY,
                        filename TEXT NOT NULL,
                        country TEXT NOT NULL,
                        doc_type TEXT NOT NULL,
                        owner_id TEXT NOT NULL,
                        owner_role TEXT NOT NULL DEFAULT 'user',
                        file_path TEXT,
                        public_url TEXT,
                        chunks JSONB,
                        upload_date TIMESTAMPTZ DEFAULT NOW()
                    );
                    
                    CREATE INDEX idx_documents_owner ON documents(owner_id);
                    CREATE INDEX idx_documents_role ON documents(owner_role);
                    CREATE INDEX idx_documents_country ON documents(country);
                    CREATE INDEX idx_documents_doc_type ON documents(doc_type);
                """
            }).execute()
            st.success("✅ Documents table created")
        except Exception as e:
            st.error(f"❌ Failed to create documents table: {e}")
            st.info("Please create manually in Supabase SQL Editor")
    
    def _create_users_table(self):
        """Create users table with correct schema."""
        try:
            self.client.rpc("exec", {
                "sql": """
                    CREATE TABLE users (
                        user_id TEXT PRIMARY KEY,
                        username TEXT UNIQUE NOT NULL,
                        password TEXT NOT NULL,
                        role TEXT NOT NULL DEFAULT 'user'
                    );
                    
                    CREATE INDEX idx_users_username ON users(username);
                    CREATE INDEX idx_users_role ON users(role);
                """
            }).execute()
            st.success("✅ Users table created")
        except Exception as e:
            st.error(f"❌ Failed to create users table: {e}")
            st.info("Please create manually in Supabase SQL Editor")
    
    def _create_default_admin(self):
        """Create default admin user if none exists."""
        try:
            result = self.client.table("users").select("*").limit(1).execute()
            if not result.data:
                st.info("👑 Creating default admin user...")
                self.client.table("users").insert({
                    "user_id": "admin_001",
                    "username": "admin",
                    "password": "admin123",
                    "role": "admin"
                }).execute()
                st.success("✅ Default admin user created (admin/admin123)")
        except Exception as e:
            st.error(f"❌ Failed to create default admin: {e}")
    
    def _ensure_storage_bucket_exists(self):
        """Ensure 'documents' storage bucket exists."""
        try:
            self.client.storage.from_("documents").list()
        except Exception as e:
            if "not found" in str(e).lower() or "404" in str(e):
                st.info("📂 Creating documents storage bucket...")
                st.warning("⚠️ Storage bucket must be created manually in Supabase Dashboard")
                st.info("Go to: Storage → New Bucket → Name: 'documents' → Create")
            else:
                st.error(f"❌ Storage error: {e}")
    
    def add_document(self, filename: str, country: str, doc_type: str,
                     owner_id: str, owner_role: str, file_content: bytes,
                     chunks: List[Dict]) -> str:
        """
        Upload to Supabase Storage and save metadata.
        """
        doc_id = str(uuid.uuid4())
        
        # Upload file to Supabase Storage
        file_path = f"{owner_id}/{doc_id}_{filename}"
        try:
            self.client.storage.from_("documents").upload(
                file_path,
                file_content,
                {"content-type": "application/octet-stream"}
            )
        except Exception as e:
            if "already exists" in str(e):
                # File already exists, skip upload
                pass
            else:
                raise e
        
        # Get public URL
        public_url = self.client.storage.from_("documents").get_public_url(file_path)
        
        # Save metadata to Supabase DB
        metadata = {
            "id": doc_id,
            "filename": filename,
            "country": country,
            "doc_type": doc_type,
            "owner_id": owner_id,
            "owner_role": owner_role,
            "file_path": file_path,
            "public_url": public_url,
            "chunks": chunks,
            "upload_date": datetime.now().isoformat()
        }
        
        try:
            result = self.client.table("documents").insert(metadata).execute()
            return doc_id
        except Exception as e:
            st.error(f"❌ Failed to insert document metadata: {e}")
            raise
    
    def get_documents_by_filters(self, user_id: str, user_role: str,
                                 country: Optional[str] = None,
                                 doc_type: Optional[str] = None) -> List[Dict]:
        """Fetch documents with access control."""
        try:
            query = self.client.table("documents").select("*")
            
            # Access control: admin sees all, users see their own + admin docs
            if user_role != "admin":
                query = query.or_(f"owner_id.eq.{user_id},owner_role.eq.admin")
            
            if country and country != "All":
                query = query.eq("country", country)
            
            if doc_type and doc_type != "All":
                query = query.eq("doc_type", doc_type)
            
            result = query.order("upload_date", desc=True).execute()
            return result.data
        
        except Exception as e:
            error_msg = str(e)
            if "does not exist" in error_msg:
                st.error("❌ Supabase tables not found. Please run table creation.")
            else:
                st.error(f"❌ Supabase error: {error_msg}")
            return []
    
    def search_documents(self, user_id: str, user_role: str, keyword: str) -> List[Dict]:
        """Search documents with access control."""
        try:
            search_term = f"%{keyword.lower()}%"
            query = self.client.table("documents") \
                .select("*") \
                .or_(f"filename.ilike.{search_term},chunks.cs.{search_term}") \
                .order("upload_date", desc=True)
            
            if user_role != "admin":
                query = query.or_(f"owner_id.eq.{user_id},owner_role.eq.admin")
            
            result = query.execute()
            return result.data
        except Exception as e:
            st.error(f"❌ Search error: {e}")
            return []
    
    def delete_document(self, doc_id: str, user_id: str, user_role: str) -> bool:
        """Delete document (admin only)."""
        if user_role != "admin":
            return False
        
        try:
            # Delete from storage
            doc = self.client.table("documents").select("file_path").eq("id", doc_id).execute()
            if doc.data:
                file_path = doc.data[0]['file_path']
                self.client.storage.from_("documents").remove([file_path])
            
            # Delete metadata
            result = self.client.table("documents").delete().eq("id", doc_id).execute()
            return len(result.data) > 0
        except Exception as e:
            st.error(f"❌ Delete error: {e}")
            return False
    
    def get_all_chunks(self, user_id: str, user_role: str) -> List[Dict]:
        """Get all accessible chunks."""
        try:
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
        except Exception as e:
            st.error(f"❌ Chunks error: {e}")
            return []
    
    def verify_user(self, username: str, password: str) -> Optional[Dict]:
        """Verify user credentials."""
        try:
            result = self.client.table("users") \
                .select("user_id, username, role") \
                .eq("username", username) \
                .eq("password", password) \
                .execute()
            
            return result.data[0] if result.data else None
        except Exception as e:
            st.error(f"❌ Auth error: {e}")
            return None
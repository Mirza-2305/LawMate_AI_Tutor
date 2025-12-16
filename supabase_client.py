# supabase_client.py - Permanent solution with RLS handling
import os
import streamlit as st
from supabase import create_client, Client
from typing import List, Dict, Optional
import hashlib
import uuid
from datetime import datetime
import requests

class SupabaseManager:
    def __init__(self):
        """Initialize with proper error handling and RLS checks."""
        self.supabase_url = os.getenv("SUPABASE_URL") or st.secrets.get("SUPABASE_URL")
        self.supabase_key = os.getenv("SUPABASE_KEY") or st.secrets.get("SUPABASE_KEY")
        self.service_key = os.getenv("SUPABASE_SERVICE_KEY") or st.secrets.get("SUPABASE_SERVICE_KEY")
        
        if not self.supabase_url or not self.supabase_key:
            raise ValueError("❌ Supabase credentials not found in secrets")
        
        # Use service role key for admin operations (bypasses RLS)
        self.client: Client = create_client(self.supabase_url, self.supabase_key)
        self.admin_client: Client = create_client(self.supabase_url, self.service_key) if self.service_key else self.client
        
        # Validate infrastructure
        self._validate_setup()
        st.sidebar.success("✅ Connected to Supabase")
    
    def _validate_setup(self):
        """Check tables, bucket, and RLS status."""
        # Check users table
        try:
            result = self.client.table("users").select("*").limit(1).execute()
            # Check RLS status
            self._check_rls_status()
        except Exception as e:
            if "does not exist" in str(e).lower():
                self._show_setup_instructions()
                st.stop()
            else:
                st.error(f"❌ Users table error: {e}")
                st.stop()
        
        # Check documents table
        try:
            self.client.table("documents").select("id").limit(1).execute()
        except Exception as e:
            if "does not exist" in str(e).lower():
                st.error("❌ Documents table missing")
                self._show_setup_instructions()
                st.stop()
        
        # Check storage bucket
        try:
            self.client.storage.from_("documents").list()
        except Exception as e:
            if "not found" in str(e).lower():
                st.error("📂 Storage bucket 'documents' not found!")
                st.info("**Quick Fix:** Run this SQL:")
                st.code("ALTER TABLE documents DISABLE ROW LEVEL SECURITY;", language="sql")
                st.info("Or create the bucket manually in Dashboard → Storage")
                st.stop()
    
    def _check_rls_status(self):
        """Check if RLS is enabled and show appropriate message."""
        try:
            result = self.client.rpc("get_rls_status", {
                "table_name": "documents"
                }).execute()
        except:
            # If RPC doesn't exist, just check via SQL
            result = self.client.rpc("exec", {
                "sql": """
                    SELECT relrowsecurity 
                    FROM pg_class 
                    WHERE relname = 'documents'
                """
            }).execute()
        
        if result.data and result.data[0].get('relrowsecurity'):
            st.info("🔒 RLS is enabled. Using service role for admin operations.")
            # If using RLS, we need service key
            if not self.service_key:
                st.warning("⚠️ Service role key not found! Add SUPABASE_SERVICE_KEY to secrets.")
    
    def _show_setup_instructions(self):
        """Display SQL setup instructions."""
        st.error("📋 INFRASTRUCTURE MISSING!")
        st.info("Run this in Supabase SQL Editor:")
        st.code("""
        -- Create tables
        CREATE TABLE users (
            user_id TEXT PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'user'
        );
        
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
        
        -- Create indexes
        CREATE INDEX idx_users_username ON users(username);
        CREATE INDEX idx_documents_owner ON documents(owner_id);
        
        -- Insert admin (password: admin123)
        INSERT INTO users (user_id, username, password, role) VALUES 
        ('admin_001', 'admin', 
         '0192023a7bbd73250516f069df18b500', 'admin');
        
        -- Disable RLS for simplicity (or create policies below)
        ALTER TABLE documents DISABLE ROW LEVEL SECURITY;
        ALTER TABLE users DISABLE ROW LEVEL SECURITY;
        """, language="sql")
        st.stop()
    
    def verify_user(self, username: str, password: str) -> Optional[Dict]:
        """Debug version that shows exactly what's happening."""
        try:
            st.sidebar.markdown("### 🔍 DEBUG: Login Attempt")
            
            # Clean inputs
            username_clean = username.strip().lower()
            password_clean = password.strip()
            
            # Generate hash
            hashed_pw = hashlib.sha256(password_clean.encode()).hexdigest()
            
            st.sidebar.write(f"**Input username (clean):** `{username_clean}`")
            st.sidebar.write(f"**Input password hash:** `{hashed_pw}`")
            
            # Show ALL users in DB
            all_users = self.client.table("users").select("*").execute()
            st.sidebar.write(f"**All users in DB:** {all_users.data}")
            
            # Show query details
            st.sidebar.write(f"**Query condition:** username='{username_clean}' AND password='{hashed_pw}'")
            
            # Query with case-insensitive match
            result = self.client.table("users") \
                .select("user_id, username, role") \
                .ilike("username", username_clean) \
                .eq("password", hashed_pw) \
                .execute()
            
            st.sidebar.write(f"**Query result:** {result.data}")
            
            if result.data:
                st.sidebar.success("✅ Login successful!")
                return result.data[0]
            else:
                st.sidebar.error("❌ No matching user found")
                
                # Show users with matching username (any password)
                user_check = self.client.table("users") \
                    .select("*") \
                    .ilike("username", username_clean) \
                    .execute()
                st.sidebar.write(f"**Users with matching username (any password):** {user_check.data}")
                
                return None
                
        except Exception as e:
            st.sidebar.error(f"❌ Exception: {str(e)}")
            return None
    
    def add_document(self, filename: str, country: str, doc_type: str,
                     owner_id: str, owner_role: str, file_content: bytes,
                     chunks: List[Dict]) -> str:
        """Upload file and save metadata."""
        doc_id = str(uuid.uuid4())
        
        # Upload to storage
        file_path = f"{owner_id}/{doc_id}_{filename}"
        try:
            self.client.storage.from_("documents").upload(
                file_path, file_content, {"content-type": "application/octet-stream"}
            )
        except Exception as e:
            if "already exists" not in str(e).lower():
                raise e
        
        public_url = self.client.storage.from_("documents").get_public_url(file_path)
        
        # Save metadata
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
        
        # Use admin client for insert (bypasses RLS if enabled)
        insert_client = self.admin_client if self.service_key else self.client
        
        result = insert_client.table("documents").insert(metadata).execute()
        return doc_id
    
    def delete_document(self, doc_id: str, user_id: str, user_role: str) -> bool:
        """Delete document (admin only)."""
        if user_role != "admin":
            return False
        
        try:
            # Get file path
            doc = self.client.table("documents").select("file_path").eq("id", doc_id).execute()
            if doc.data:
                file_path = doc.data[0]['file_path']
                # Delete from storage using admin client
                self.admin_client.storage.from_("documents").remove([file_path])
            
            # Delete metadata
            result = self.admin_client.table("documents").delete().eq("id", doc_id).execute()
            return len(result.data) > 0
        except Exception as e:
            st.error(f"❌ Delete error: {e}")
            return False
    
    # === REMAINING METHODS STAY THE SAME ===
    def get_documents_by_filters(self, user_id: str, user_role: str,
                                 country: Optional[str] = None,
                                 doc_type: Optional[str] = None) -> List[Dict]:
        """Fetch documents with access control."""
        try:
            query = self.client.table("documents").select("*")
            
            if user_role != "admin":
                query = query.or_(f"owner_id.eq.{user_id},owner_role.eq.admin")
            
            if country and country != "All":
                query = query.eq("country", country)
            
            if doc_type and doc_type != "All":
                query = query.eq("doc_type", doc_type)
            
            result = query.order("upload_date", desc=True).execute()
            return result.data
        
        except Exception as e:
            st.error(f"❌ Supabase error: {str(e)}")
            return []
    
    def search_documents(self, user_id: str, user_role: str, keyword: str) -> List[Dict]:
        """Search documents."""
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
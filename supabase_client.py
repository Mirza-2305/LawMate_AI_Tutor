# supabase_client.py - Final robust version for Streamlit Cloud
import os
import streamlit as st
from supabase import create_client, Client
from typing import List, Dict, Optional
import uuid
from datetime import datetime
import hashlib

class SupabaseManager:
    def __init__(self):
        """Initialize Supabase clients with service key for admin operations."""
        # Get secrets from Streamlit secrets or environment
        self.supabase_url = os.getenv("SUPABASE_URL") or st.secrets.get("SUPABASE_URL")
        self.supabase_key = os.getenv("SUPABASE_KEY") or st.secrets.get("SUPABASE_KEY")
        self.service_key = os.getenv("SUPABASE_SERVICE_KEY") or st.secrets.get("SUPABASE_SERVICE_KEY")
        
        if not self.supabase_url or not self.supabase_key:
            raise ValueError("❌ SUPABASE_URL or SUPABASE_KEY missing in environment/secrets")
        
        # Normal client (limited by RLS)
        self.client: Client = create_client(self.supabase_url, self.supabase_key)
        
        # Admin client (service key bypasses RLS)
        if self.service_key:
            self.admin_client: Client = create_client(self.supabase_url, self.service_key)
            st.sidebar.success("✅ Using service key for admin operations")
        else:
            self.admin_client = self.client
            st.sidebar.warning("⚠️ No SUPABASE_SERVICE_KEY provided; admin ops may fail")
        
        # Ensure bucket exists
        self._check_storage_bucket()

    def _check_storage_bucket(self):
        try:
            self.client.storage.from_("documents").list()
            st.sidebar.info("📂 Storage bucket 'documents' ready")
        except Exception as e:
            st.error(f"❌ Storage bucket check failed: {str(e)}")
            st.stop()

    # --- USER AUTH ---
    def verify_user(self, username: str, password: str) -> Optional[Dict]:
        """Verify user credentials using service client."""
        try:
            username_clean = username.strip().lower()
            password_hash = hashlib.sha256(password.strip().encode()).hexdigest()

            result = self.admin_client.table("users") \
                .select("*") \
                .eq("username", username_clean) \
                .eq("password", password_hash) \
                .limit(1) \
                .execute()
            
            if result.data and len(result.data) == 1:
                return result.data[0]
            return None
        except Exception as e:
            st.error(f"❌ User verification error: {str(e)}")
            return None

    # --- DOCUMENT UPLOAD ---
    def add_document(
        self,
        filename: str,
        country: str,
        doc_type: str,
        owner_id: str,
        owner_role: str,
        file_content: bytes,
        chunks: list
    ) -> str | None:
        try:
            st.sidebar.write("📤 Uploading document...")

            # Generate document ID
            doc_id = str(uuid.uuid4())
            file_path = f"{owner_id}/{doc_id}_{filename}"

            # ✅ Upload file (NO upsert keyword)
            self.client.storage.from_("documents").upload(
                file_path,
                file_content,
                file_options={
                    "content-type": "application/octet-stream",
                    "x-upsert": "true"
                }
            )

            # Get public URL
            public_url = self.client.storage.from_("documents").get_public_url(file_path)

            # Prepare metadata (matches YOUR table schema)
            document_row = {
                "id": doc_id,
                "filename": filename,
                "country": country,
                "doc_type": doc_type,
                "owner_id": owner_id,
                "owner_role": owner_role,
                "file_path": file_path,
                "public_url": public_url,
                "chunks": chunks,
                "upload_date": datetime.utcnow().isoformat()
            }

            # Insert metadata (use service key if available)
            client = self.admin_client if self.service_key else self.client
            result = client.table("documents").insert(document_row).execute()

            if result.data:
                st.sidebar.success("✅ Document uploaded successfully")
                return doc_id

            st.sidebar.error("❌ Failed to save document metadata")
            return None

        except Exception as e:
            st.sidebar.error(f"❌ Document upload error: {e}")
            st.sidebar.exception(e)
            return None

    # --- GET DOCUMENTS ---
    def get_documents_by_filters(self, user_id: str, user_role: str,
                                 country: Optional[str] = None,
                                 doc_type: Optional[str] = None) -> List[Dict]:
        """Fetch documents based on filters and role access."""
        try:
            query = self.client.table("documents").select("*")

            if user_role != "admin":
                query = query.or_(f"owner_role.eq.admin,owner_id.eq.\"{user_id}\"")
            
            if country and country != "All":
                query = query.eq("country", country)
            if doc_type and doc_type != "All":
                query = query.eq("doc_type", doc_type)
            
            result = query.order("upload_date", desc=True).execute()
            return result.data or []
        except Exception as e:
            st.error(f"❌ Get documents error: {str(e)}")
            return []

    # --- SEARCH DOCUMENTS ---
    def search_documents(self, user_id: str, user_role: str, keyword: str) -> List[Dict]:
        try:
            search_term = f"%{keyword.lower()}%"
            query = self.client.table("documents") \
                .select("*") \
                .or_(f"filename.ilike.{search_term},chunks.cs.{search_term}") \
                .order("upload_date", desc=True)

            if user_role != "admin":
                query = query.or_(f"owner_role.eq.admin,owner_id.eq.\"{user_id}\"")
            
            result = query.execute()
            return result.data or []
        except Exception as e:
            st.error(f"❌ Search error: {str(e)}")
            return []

    # --- DELETE DOCUMENT ---
    def delete_document(self, doc_id: str, user_id: str, user_role: str) -> bool:
        """Delete document from storage and metadata. Admin only."""
        if user_role != "admin":
            st.warning("⚠️ Only admin can delete documents")
            return False
        try:
            doc = self.client.table("documents").select("file_path").eq("id", doc_id).execute()
            if doc.data:
                file_path = doc.data[0]['file_path']
                self.admin_client.storage.from_("documents").remove([file_path])
            
            result = self.admin_client.table("documents").delete().eq("id", doc_id).execute()
            return bool(result.data)
        except Exception as e:
            st.error(f"❌ Delete error: {str(e)}")
            return False

    # --- GET ALL CHUNKS ---
    def get_all_chunks(self, user_id: str, user_role: str) -> List[Dict]:
        """Return all chunks accessible by user."""
        try:
            chunks = []
            docs = self.get_documents_by_filters(user_id, user_role)
            for doc in docs:
                for chunk in doc.get('chunks', []):
                    chunk_copy = chunk.copy()
                    chunk_copy.update({
                        'filename': doc['filename'],
                        'country': doc['country'],
                        'doc_type': doc['doc_type']
                    })
                    chunks.append(chunk_copy)
            return chunks
        except Exception as e:
            st.error(f"❌ Get chunks error: {str(e)}")
            return []

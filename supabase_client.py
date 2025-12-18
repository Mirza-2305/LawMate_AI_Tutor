import os
import uuid
import hashlib
from datetime import datetime
from typing import List, Dict, Optional

import streamlit as st
from supabase import create_client, Client


class SupabaseManager:
    def __init__(self):
        # Load secrets
        self.supabase_url = st.secrets.get("SUPABASE_URL")
        self.supabase_key = st.secrets.get("SUPABASE_KEY")
        self.service_key = st.secrets.get("SUPABASE_SERVICE_KEY")

        # Validate credentials
        if not self.supabase_url:
            raise ValueError("❌ SUPABASE_URL missing in secrets")
        if not self.supabase_key:
            raise ValueError("❌ SUPABASE_KEY missing in secrets")
        if not self.service_key:
            st.warning("⚠️ SUPABASE_SERVICE_KEY not found - using anon key (RLS may block operations)")

        # Create clients
        self.client: Client = create_client(self.supabase_url, self.supabase_key)
        self.admin_client: Client = create_client(self.supabase_url, self.service_key or self.supabase_key)

        # Verify connection and bucket
        self._initialize_connection()

    def _initialize_connection(self):
        """Initialize and verify Supabase connection"""
        try:
            # Test bucket access
            self.admin_client.storage.from_("documents").list()
            st.sidebar.success("✅ Supabase connected")
        except Exception as e:
            st.error(f"❌ Storage bucket 'documents' not found or inaccessible: {e}")
            st.info("Please create a 'documents' bucket in Supabase Storage")
            st.stop()

    # -------------------------------------------------
    # AUTH
    # -------------------------------------------------
    def verify_user(self, username: str, password: str) -> Optional[Dict]:
        try:
            username = username.strip().lower()
            password_hash = hashlib.sha256(password.strip().encode()).hexdigest()

            result = (
                self.admin_client
                .table("users")
                .select("*")
                .eq("username", username)
                .eq("password", password_hash)
                .limit(1)
                .execute()
            )

            return result.data[0] if result.data else None

        except Exception as e:
            st.error(f"❌ Login error: {e}")
            return None

    # -------------------------------------------------
    # DOCUMENT UPLOAD (FIXED)
    # -------------------------------------------------
    def add_document(
        self,
        filename: str,
        country: str,
        doc_type: str,
        owner_id: str,
        owner_role: str,
        file_content: bytes,
        chunks: List[Dict],
    ) -> Optional[str]:
        """
        Upload document to Supabase Storage and insert metadata
        Uses admin_client for all operations to bypass RLS
        """
        try:
            # Generate unique document ID
            doc_id = str(uuid.uuid4())
            file_path = f"{owner_id}/{doc_id}_{filename}"

            # 1. Upload file to storage (using admin_client to bypass RLS)
            storage_response = self.admin_client.storage.from_("documents").upload(
                file_path,
                file_content
            )
            
            if not storage_response:
                st.error("❌ Storage upload failed")
                return None

            # Get public URL
            public_url = self.admin_client.storage.from_("documents").get_public_url(file_path)

            # Prepare document row
            document_row = {
                "id": doc_id,
                "filename": filename,
                "country": country,
                "doc_type": doc_type,
                "owner_id": owner_id,
                "owner_role": owner_role,
                "file_path": file_path,
                "public_url": public_url,
                "chunks": chunks,   # stored as JSONB
                "upload_date": datetime.utcnow().isoformat(),
            }

            # Insert metadata using SERVICE ROLE (admin_client)
            result = self.admin_client.table("documents").insert(document_row).execute()

            if result.data and len(result.data) > 0:
                return doc_id
            else:
                st.error(f"❌ Metadata insert failed: {result}")
                return None

        except Exception as e:
            st.error(f"❌ Document upload error: {str(e)}")
            st.info("💡 If this is an RLS error, disable RLS on the 'documents' table in Supabase")
            return None

    # -------------------------------------------------
    # FETCH DOCUMENTS
    # -------------------------------------------------
    def get_documents_by_filters(
        self,
        user_id: str,
        user_role: str,
        country: Optional[str] = None,
        doc_type: Optional[str] = None,
    ) -> List[Dict]:
        """Fetch documents with filters and role-based access"""
        try:
            query = self.client.table("documents").select("*")

            if user_role != "admin":
                query = query.or_(f"owner_role.eq.admin,owner_id.eq.{user_id}")

            if country and country != "All":
                query = query.eq("country", country)

            if doc_type and doc_type != "All":
                query = query.eq("doc_type", doc_type)

            # Execute query
            result = query.order("upload_date", desc=True).execute()
            return result.data if result.data else []

        except Exception as e:
            st.error(f"❌ Fetch error: {e}")
            return []

    # -------------------------------------------------
    # SEARCH
    # -------------------------------------------------
    def search_documents(self, user_id: str, user_role: str, keyword: str) -> List[Dict]:
        """Search documents by filename"""
        try:
            query = self.client.table("documents").select("*").ilike("filename", f"%{keyword}%")

            if user_role != "admin":
                query = query.or_(f"owner_role.eq.admin,owner_id.eq.{user_id}")

            result = query.execute()
            return result.data if result.data else []

        except Exception as e:
            st.error(f"❌ Search error: {e}")
            return []

    # -------------------------------------------------
    # DELETE
    # -------------------------------------------------
    def delete_document(self, doc_id: str, user_id: str, user_role: str) -> bool:
        """Delete document and its storage file (Admin only)"""
        if user_role != "admin":
            st.error("❌ Only admins can delete documents")
            return False

        try:
            # 1. Get file path
            doc = self.admin_client.table("documents")\
                .select("file_path")\
                .eq("id", doc_id)\
                .execute()

            if doc.data:
                # 2. Delete from storage
                file_path = doc.data[0]["file_path"]
                self.admin_client.storage.from_("documents").remove([file_path])
                
                # 3. Delete metadata
                self.admin_client.table("documents")\
                    .delete()\
                    .eq("id", doc_id)\
                    .execute()
                
                st.success("✅ Document deleted")
                return True
            else:
                st.error("❌ Document not found")
                return False

        except Exception as e:
            st.error(f"❌ Delete error: {e}")
            return False

    # -------------------------------------------------
    # CHUNKS ACCESS (FROM JSONB)
    # -------------------------------------------------
    def get_all_chunks(self, user_id: str, user_role: str) -> List[Dict]:
        """Extract all chunks from accessible documents"""
        chunks = []
        docs = self.get_documents_by_filters(user_id, user_role)

        for doc in docs:
            for ch in doc.get("chunks", []):
                ch.update({
                    "filename": doc["filename"],
                    "country": doc["country"],
                    "doc_type": doc["doc_type"],
                })
                chunks.append(ch)

        return chunks

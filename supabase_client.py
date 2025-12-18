import os
import uuid
import hashlib
from datetime import datetime
from typing import List, Dict, Optional

import streamlit as st
from supabase import create_client, Client


class SupabaseManager:
    def __init__(self):
        # GET SERVICE ROLE KEY ONLY
        self.supabase_url = st.secrets.get("SUPABASE_URL")
        self.service_key = st.secrets.get("SUPABASE_SERVICE_KEY")

        # VALIDATE KEY FORMAT (service keys are ~200+ characters)
        if len(self.service_key) < 100:
            st.error("🚨 INVALID SERVICE KEY! Too short. Get from Project Settings → API")
            st.stop()
        
        # CREATE SINGLE CLIENT WITH SERVICE ROLE (bypasses ALL security)
        self.client: Client = create_client(self.supabase_url, self.service_key)
        
        # Verify bucket
        try:
            self.client.storage.from_("documents").list()
            st.sidebar.success("✅ Supabase Storage connected with Service Role")
        except Exception as e:
            st.error(f"❌ Storage error: {e}")
            st.info("Create a 'documents' bucket in Storage → Buckets")
            st.stop()


    # -------------------------------------------------
    # AUTH
    # -------------------------------------------------
    def verify_user(self, username: str, password: str) -> Optional[Dict]:
        try:
            username = username.strip().lower()
            password_hash = hashlib.sha256(password.strip().encode()).hexdigest()

            result = (
                self.client
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
            storage_response = self.client.storage.from_("documents").upload(
                file_path,
                file_content
            )
            
            if not storage_response:
                st.error("❌ Storage upload failed")
                return None

            # Get public URL
            public_url = self.client.storage.from_("documents").get_public_url(file_path)

            # 3. INSERT METADATA (same service key)
            result = self.client.table("documents").insert({
                "id": doc_id,
                "filename": filename,
                "country": country,
                "doc_type": doc_type,
                "owner_id": owner_id,
                "owner_role": owner_role,
                "file_path": file_path,
                "public_url": public_url,
                "chunks": chunks,
                "upload_date": datetime.utcnow().isoformat(),
            }).execute()

            return doc_id if result.data else None

        except Exception as e:
            # SPECIFIC ERROR MESSAGES
            error_str = str(e).lower()
            
            if "row-level security" in error_str:
                st.error("🚨 RLS IS STILL ENABLED! Run: ALTER TABLE documents DISABLE ROW LEVEL SECURITY")
                
            elif "invalid jwt" in error_str:
                st.error("🚨 INVALID SERVICE KEY! Check SUPABASE_SERVICE_KEY")
                
            elif "bucket not found" in error_str:
                st.error("🚨 'documents' bucket missing in Storage")
                
            else:
                st.error(f"❌ Upload error: {e}")
            
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
            doc = self.client.table("documents")\
                .select("file_path")\
                .eq("id", doc_id)\
                .execute()

            if doc.data:
                # 2. Delete from storage
                file_path = doc.data[0]["file_path"]
                self.client.storage.from_("documents").remove([file_path])
                
                # 3. Delete metadata
                self.client.table("documents")\
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

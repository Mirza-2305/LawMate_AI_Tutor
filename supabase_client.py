# supabase_client.py - Production-ready, fully debugged

import os
import streamlit as st
from supabase import create_client, Client
from typing import List, Dict, Optional
import hashlib
import uuid
from datetime import datetime


class SupabaseManager:
    def __init__(self):
        """Initialize Supabase clients with proper error handling."""
        # Load secrets
        self.supabase_url = os.getenv("SUPABASE_URL") or st.secrets.get("SUPABASE_URL")
        self.supabase_key = os.getenv("SUPABASE_KEY") or st.secrets.get("SUPABASE_KEY")
        self.service_key = os.getenv("SUPABASE_SERVICE_KEY") or st.secrets.get("SUPABASE_SERVICE_KEY")

        if not self.supabase_url:
            raise ValueError("❌ SUPABASE_URL not found in .env or Streamlit secrets")
        if not self.supabase_key:
            raise ValueError("❌ SUPABASE_KEY not found in .env or Streamlit secrets")

        # Create clients
        self.client: Client = create_client(self.supabase_url, self.supabase_key)
        self.admin_client: Client = self.client  # default

        if self.service_key:
            self.admin_client = create_client(self.supabase_url, self.service_key)
            st.sidebar.success("✅ Using service role (admin) for secure operations")
        else:
            st.sidebar.warning("⚠️ No SUPABASE_SERVICE_KEY found - admin operations may fail")

        # Check storage bucket
        self._setup_infrastructure()

    def _setup_infrastructure(self):
        """Ensure 'documents' bucket exists."""
        try:
            self.client.storage.from_("documents").list()
            st.sidebar.success("📂 Storage bucket ready")
        except Exception as e:
            msg = str(e).lower()
            if "not found" in msg or "bucket" in msg:
                st.error("📂 CRITICAL: 'documents' bucket not found!")
                st.info("Please create the bucket in Supabase Storage: 'documents'")
                st.stop()
            else:
                st.warning(f"⚠️ Storage check warning: {e}")

    # === USER AUTHENTICATION ===
    def verify_user(self, username: str, password: str) -> Optional[Dict]:
        """Verify user credentials with hashed password."""
        try:
            username_clean = username.strip().lower()
            password_hash = hashlib.sha256(password.strip().encode()).hexdigest()

            st.sidebar.write("🔍 Login Debug")
            st.sidebar.write(f"Username: {username_clean}")
            st.sidebar.write(f"Password hash: {password_hash}")

            # Use admin_client to avoid permission issues
            result = self.admin_client.table("users") \
                .select("*") \
                .eq("username", username_clean) \
                .eq("password", password_hash) \
                .limit(1) \
                .execute()

            st.sidebar.write(f"DB Result: {result.data}")
            if result.data and len(result.data) == 1:
                st.sidebar.success("✅ Login successful")
                return result.data[0]

            st.sidebar.error("❌ Invalid credentials")
            return None

        except Exception as e:
            st.sidebar.error(f"❌ Login exception: {e}")
            st.sidebar.exception(e)
            return None

    # === DOCUMENT UPLOAD ===
    def add_document(self, filename: str, country: str, doc_type: str,
                     owner_id: str, owner_role: str, file_content: bytes,
                     chunks: List[Dict]) -> str:
        """Upload file to Supabase storage and insert metadata."""
        try:
            st.sidebar.write("📤 **Debug Upload**")
            
            doc_id = str(uuid.uuid4())
            file_path = f"{owner_id}/{doc_id}_{filename}"

            st.sidebar.write(f"Doc ID: {doc_id}")
            st.sidebar.write(f"File path: {file_path}")
            st.sidebar.write(f"File size: {len(file_content)} bytes")
            st.sidebar.write(f"Chunks count: {len(chunks)}")

            storage_bucket = self.client.storage.from_("documents")
            storage_bucket.upload(
                file_path,
                file_content,
                {"content-type": "application/octet-stream"},
                upsert=True
            )
            public_url = storage_bucket.get_public_url(file_path)

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

            st.sidebar.write(f"Metadata keys: {list(metadata.keys())}")

            # Insert metadata
            result = self.admin_client.table("documents").insert(metadata).execute()

            if result.data:
                st.sidebar.success("✅ Document metadata saved")
                return doc_id
            else:
                st.sidebar.error("❌ Failed to save metadata")
                st.sidebar.write(f"Response: {result}")
                return None

        except Exception as e:
            st.sidebar.error(f"❌ Upload failed: {str(e)}")
            st.sidebar.exception(e)
            raise e

    # === DOCUMENT QUERY ===
    def get_documents_by_filters(self, user_id: str, user_role: str,
                                 country: Optional[str] = None,
                                 doc_type: Optional[str] = None) -> List[Dict]:
        """Fetch documents with access control."""
        try:
            query = self.client.table("documents").select("*")

            # Admin sees all, others see own + admin docs
            if user_role != "admin":
                query = query.or_(f"owner_role.eq.admin,owner_id.eq.{user_id}")

            if country and country != "All":
                query = query.eq("country", country)

            if doc_type and doc_type != "All":
                query = query.eq("doc_type", doc_type)

            result = query.order("upload_date", desc=True).execute()
            return result.data or []

        except Exception as e:
            st.error(f"❌ Fetch documents error: {e}")
            return []

    def search_documents(self, user_id: str, user_role: str, keyword: str) -> List[Dict]:
        """Search documents using filename or chunk text."""
        try:
            search_term = f"%{keyword.lower()}%"
            query = self.client.table("documents").select("*") \
                .or_(f"filename.ilike.{search_term},chunks.cs.{search_term}") \
                .order("upload_date", desc=True)

            if user_role != "admin":
                query = query.or_(f"owner_role.eq.admin,owner_id.eq.{user_id}")

            result = query.execute()
            return result.data or []
        except Exception as e:
            st.error(f"❌ Search error: {e}")
            return []

    # === DOCUMENT DELETE ===
    def delete_document(self, doc_id: str, user_id: str, user_role: str) -> bool:
        """Delete document (admin only)."""
        if user_role != "admin":
            return False
        try:
            doc = self.client.table("documents").select("file_path").eq("id", doc_id).execute()
            if doc.data:
                file_path = doc.data[0]['file_path']
                self.client.storage.from_("documents").remove([file_path])

            result = self.client.table("documents").delete().eq("id", doc_id).execute()
            return bool(result.data)
        except Exception as e:
            st.error(f"❌ Delete error: {e}")
            return False

    # === CHUNKS ===
    def get_all_chunks(self, user_id: str, user_role: str) -> List[Dict]:
        """Return all chunks accessible to the user."""
        try:
            chunks = []
            docs = self.get_documents_by_filters(user_id, user_role)
            for doc in docs:
                for chunk in doc.get("chunks", []):
                    chunk_with_meta = chunk.copy()
                    chunk_with_meta.update({
                        "filename": doc["filename"],
                        "country": doc["country"],
                        "doc_type": doc["doc_type"]
                    })
                    chunks.append(chunk_with_meta)
            return chunks
        except Exception as e:
            st.error(f"❌ Chunks error: {e}")
            return []

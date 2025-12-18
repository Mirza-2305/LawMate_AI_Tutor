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

        if not self.supabase_url or not self.supabase_key:
            raise ValueError("❌ Supabase credentials missing")

        # Clients
        self.client: Client = create_client(self.supabase_url, self.supabase_key)

        if self.service_key:
            self.admin_client: Client = create_client(self.supabase_url, self.service_key)
        else:
            self.admin_client = self.client

        self._check_bucket()

    # -------------------------------------------------
    # STORAGE
    # -------------------------------------------------
    def _check_bucket(self):
        try:
            self.client.storage.from_("documents").list()
        except Exception:
            st.error("❌ Storage bucket 'documents' not found")
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
        try:
            # Generate unique document ID
            doc_id = str(uuid.uuid4())
            file_path = f"{owner_id}/{doc_id}_{filename}"

            # ✅ CORRECT Supabase upload (NO upsert, NO file_options)
            self.client.storage.from_("documents").upload(
                file_path,
                file_content
            )

            # Get public URL
            public_url = self.client.storage.from_("documents").get_public_url(file_path)

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

            if result.data:
                return doc_id

            st.error("❌ Failed to insert document metadata")
            return None

        except Exception as e:
            st.error(f"❌ Document upload error: {e}")
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

        try:
            query = self.client.table("documents").select("*")

            if user_role != "admin":
                query = query.or_(f"owner_role.eq.admin,owner_id.eq.{user_id}")

            if country and country != "All":
                query = query.eq("country", country)

            if doc_type and doc_type != "All":
                query = query.eq("doc_type", doc_type)

            return query.order("upload_date", desc=True).execute().data

        except Exception as e:
            st.error(f"❌ Fetch error: {e}")
            return []

    # -------------------------------------------------
    # SEARCH
    # -------------------------------------------------
    def search_documents(self, user_id: str, user_role: str, keyword: str) -> List[Dict]:
        try:
            query = self.client.table("documents").select("*").ilike("filename", f"%{keyword}%")

            if user_role != "admin":
                query = query.or_(f"owner_role.eq.admin,owner_id.eq.{user_id}")

            return query.execute().data

        except Exception as e:
            st.error(f"❌ Search error: {e}")
            return []

    # -------------------------------------------------
    # DELETE
    # -------------------------------------------------
    def delete_document(self, doc_id: str, user_id: str, user_role: str) -> bool:
        if user_role != "admin":
            return False

        try:
            doc = self.client.table("documents").select("file_path").eq("id", doc_id).execute()
            if doc.data:
                self.client.storage.from_("documents").remove([doc.data[0]["file_path"]])

            self.admin_client.table("documents").delete().eq("id", doc_id).execute()
            return True

        except Exception as e:
            st.error(f"❌ Delete error: {e}")
            return False

    # -------------------------------------------------
    # CHUNKS ACCESS (FROM JSONB)
    # -------------------------------------------------
    def get_all_chunks(self, user_id: str, user_role: str) -> List[Dict]:
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

# supabase_client.py - FINAL & COMPLETE
import os
import streamlit as st
from supabase import create_client, Client
from typing import List, Dict, Optional
import hashlib
import uuid
from datetime import datetime

class SupabaseManager:
    def __init__(self):
        self.supabase_url = os.getenv("SUPABASE_URL") or st.secrets.get("SUPABASE_URL")
        self.supabase_key = os.getenv("SUPABASE_KEY") or st.secrets.get("SUPABASE_KEY")
        self.service_key = os.getenv("SUPABASE_SERVICE_KEY") or st.secrets.get("SUPABASE_SERVICE_KEY")

        if not self.supabase_url or not self.supabase_key:
            raise ValueError("❌ Supabase credentials missing")

        self.client: Client = create_client(self.supabase_url, self.supabase_key)
        self.admin_client: Client = self.client

        if self.service_key:
            self.admin_client = create_client(self.supabase_url, self.service_key)

        self._setup_infrastructure()

    def _setup_infrastructure(self):
        try:
            self.client.storage.from_("documents").list()
        except Exception:
            st.error("❌ Supabase storage bucket 'documents' missing")
            st.stop()

    # ---------------- AUTH ----------------
    def verify_user(self, username: str, password: str) -> Optional[Dict]:
        password_hash = hashlib.sha256(password.encode()).hexdigest()
        res = self.client.table("users") \
            .select("*") \
            .eq("username", username.lower()) \
            .eq("password", password_hash) \
            .execute()
        return res.data[0] if res.data else None

    # ---------------- DOCUMENT UPLOAD ----------------
    def add_document(self, filename, country, doc_type,
                     owner_id, owner_role, file_content, chunks):
        doc_id = str(uuid.uuid4())
        file_path = f"{owner_id}/{doc_id}_{filename}"

        self.client.storage.from_("documents").upload(
            file_path, file_content, {"content-type": "application/octet-stream"}
        )

        public_url = self.client.storage.from_("documents").get_public_url(file_path)

        payload = {
            "id": doc_id,
            "filename": filename,
            "country": country,
            "doc_type": doc_type,
            "owner_id": owner_id,
            "owner_role": owner_role,
            "file_path": file_path,
            "public_url": public_url,
            "chunks": chunks,
            "created_at": datetime.utcnow().isoformat()
        }

        self.client.table("documents").insert(payload).execute()
        return doc_id

    # ---------------- DOCUMENT LISTING ----------------
    def get_documents_by_filters(self, user_id, user_role, country, doc_type):
        query = self.client.table("documents").select("*")

        if user_role != "admin":
            query = query.or_(f"owner_role.eq.admin,owner_id.eq.{user_id}")

        if country and country != "All":
            query = query.eq("country", country)

        if doc_type and doc_type != "All":
            query = query.eq("doc_type", doc_type)

        return query.order("created_at", desc=True).execute().data or []

    def search_documents(self, user_id, user_role, keyword):
        query = self.client.table("documents").select("*").ilike("filename", f"%{keyword}%")

        if user_role != "admin":
            query = query.or_(f"owner_role.eq.admin,owner_id.eq.{user_id}")

        return query.execute().data or []

    # ---------------- DELETE ----------------
    def delete_document(self, doc_id, user_id, user_role):
        doc = self.client.table("documents").select("*").eq("id", doc_id).execute().data
        if not doc:
            return False

        doc = doc[0]
        if user_role != "admin" and doc["owner_id"] != user_id:
            return False

        self.client.storage.from_("documents").remove([doc["file_path"]])
        self.client.table("documents").delete().eq("id", doc_id).execute()
        return True

    # ---------------- CHUNKS ----------------
    def get_all_chunks(self, user_id, user_role):
        docs = self.get_documents_by_filters(user_id, user_role, None, None)
        all_chunks = []
        for d in docs:
            all_chunks.extend(d.get("chunks", []))
        return all_chunks

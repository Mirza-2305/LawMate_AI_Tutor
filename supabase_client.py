# supabase_client.py - Persistent storage handler
import os
from supabase import create_client, Client
from typing import List, Dict, Optional
import json
import uuid

class SupabaseManager:
    def __init__(self):
        """Initialize Supabase connection from secrets."""
        # Get credentials from Streamlit Cloud Secrets
        self.supabase_url = os.getenv("SUPABASE_URL") or st.secrets.get("SUPABASE_URL")
        self.supabase_key = os.getenv("SUPABASE_KEY") or st.secrets.get("SUPABASE_KEY")
        
        if not self.supabase_url or not self.supabase_key:
            raise ValueError("❌ Supabase credentials not found in secrets")
        
        self.client: Client = create_client(self.supabase_url, self.supabase_key)
        self.init_storage_bucket()
    
    def init_storage_bucket(self):
        """Ensure 'documents' bucket exists."""
        try:
            # Try to access bucket
            self.client.storage.from_("documents").list()
        except:
            # Create bucket if it doesn't exist (requires service role key)
            print("⚠️ Documents bucket may need manual creation in Supabase dashboard")
    
    def add_document(self, filename: str, country: str, doc_type: str,
                     owner_id: str, owner_role: str, file_content: bytes,
                     chunks: List[Dict]) -> str:
        """
        Upload to Supabase Storage and save metadata.
        """
        doc_id = str(uuid.uuid4())
        
        # Upload file to Supabase Storage
        file_path = f"{owner_id}/{doc_id}_{filename}"
        self.client.storage.from_("documents").upload(
            file_path,
            file_content,
            {"content-type": "application/octet-stream"}
        )
        
        # Get public URL (optional, for direct download)
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
            "chunks": chunks
        }
        
        result = self.client.table("documents").insert(metadata).execute()
        return doc_id
    
    def get_documents_by_filters(self, user_id: str, user_role: str,
                                 country: Optional[str] = None,
                                 doc_type: Optional[str] = None) -> List[Dict]:
        """Fetch documents with access control."""
        query = self.client.table("documents").select("*")
        
        # Access control: admin sees all, users see their own + public
        if user_role != "admin":
            query = query.or_(f"owner_id.eq.{user_id},owner_role.eq.admin")
        
        if country and country != "All":
            query = query.eq("country", country)
        
        if doc_type and doc_type != "All":
            query = query.eq("doc_type", doc_type)
        
        result = query.order("upload_date", desc=True).execute()
        return result.data
    
    def search_documents(self, user_id: str, user_role: str, keyword: str) -> List[Dict]:
        """Search documents with access control."""
        search_term = f"%{keyword.lower()}%"
        
        query = self.client.table("documents") \
            .select("*") \
            .or_(f"filename.ilike.{search_term},chunks.cs.{search_term}") \
            .order("upload_date", desc=True)
        
        if user_role != "admin":
            query = query.or_(f"owner_id.eq.{user_id},owner_role.eq.admin")
        
        result = query.execute()
        return result.data
    
    def delete_document(self, doc_id: str, user_id: str, user_role: str) -> bool:
        """Delete document (admin only)."""
        if user_role != "admin":
            return False
        
        # Delete from storage
        doc = self.client.table("documents").select("file_path").eq("id", doc_id).execute()
        if doc.data:
            file_path = doc.data[0]['file_path']
            self.client.storage.from_("documents").remove([file_path])
        
        # Delete metadata
        result = self.client.table("documents").delete().eq("id", doc_id).execute()
        return len(result.data) > 0
    
    def get_all_chunks(self, user_id: str, user_role: str) -> List[Dict]:
        """Get all accessible chunks."""
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
    
    def verify_user(self, username: str, password: str) -> Optional[Dict]:
        """Verify user credentials."""
        result = self.client.table("users") \
            .select("user_id, username, role") \
            .eq("username", username) \
            .eq("password", password) \
            .execute()
        
        return result.data[0] if result.data else None
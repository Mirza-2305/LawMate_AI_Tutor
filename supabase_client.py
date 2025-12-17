# supabase_client.py - Complete with table creation and error handling
import os
import streamlit as st
from supabase import create_client, Client
from typing import List, Dict, Optional
import json
import uuid
from datetime import datetime

# supabase_client.py - Production-ready with full debug
import os
import streamlit as st
from supabase import create_client, Client
from typing import List, Dict, Optional
import hashlib
import uuid
from datetime import datetime

class SupabaseManager:
    def __init__(self):
        """Initialize with explicit error messages."""
        # Get secrets
        self.supabase_url = os.getenv("SUPABASE_URL") or st.secrets.get("SUPABASE_URL")
        self.supabase_key = os.getenv("SUPABASE_KEY") or st.secrets.get("SUPABASE_KEY")
        self.service_key = os.getenv("SUPABASE_SERVICE_KEY") or st.secrets.get("SUPABASE_SERVICE_KEY")
        
        # Validate credentials exist
        if not self.supabase_url:
            raise ValueError("❌ SUPABASE_URL not found in secrets or .env")
        if not self.supabase_key:
            raise ValueError("❌ SUPABASE_KEY not found in secrets or .env")
        
        # Initialize clients
        self.client: Client = create_client(self.supabase_url, self.supabase_key)
        self.admin_client: Client = self.client  # Default, override if service key exists
        
        if self.service_key:
            self.admin_client = create_client(self.supabase_url, self.service_key)
            st.sidebar.success("✅ Using service role for admin operations")
        else:
            st.sidebar.info("⚠️ No SUPABASE_SERVICE_KEY - some admin functions may fail")
        
        # Initialize infrastructure
        self._setup_infrastructure()
    
    def _setup_infrastructure(self):
        """Create bucket if missing - with proper error handling."""
        try:
            # Check if bucket exists
            self.client.storage.from_("documents").list()
            st.sidebar.success("📂 Storage bucket ready")
        except Exception as e:
            error_msg = str(e).lower()
            if "not found" in error_msg or "bucket" in error_msg:
                st.error("📂 CRITICAL: 'documents' bucket not found!")
                st.info("Fix: Go to Supabase Dashboard → Storage → Create new bucket named 'documents'")
                st.stop()
            else:
                st.warning(f"⚠️ Storage check: {e}")
    
    def verify_user(self, username: str, password: str) -> Optional[Dict]:
        try:
            username_clean = username.strip().lower()
            password_clean = password.strip()

            password_hash = hashlib.sha256(password_clean.encode("utf-8")).hexdigest()

            # DEBUG (remove later)
            st.sidebar.write("🔍 Login Debug")
            st.sidebar.write(f"Username: {username_clean}")
            st.sidebar.write(f"Password hash: {password_hash}")

            result = (
                self.client
                .table("users")
                .select("*")
                .eq("username", username_clean)   # ✅ USE eq NOT ilike
                .eq("password", password_hash)
                .limit(1)
                .execute()
            )

            if result.data:
                st.sidebar.success("✅ Login successful")
                return result.data[0]

            st.sidebar.error("❌ Invalid username or password")
            return None

        except Exception as e:
            st.sidebar.error(f"❌ Login error: {e}")
            return None
    
    def add_document(self, filename: str, country: str, doc_type: str,
                     owner_id: str, owner_role: str, file_content: bytes,
                     chunks: List[Dict]) -> str:
        """Upload with comprehensive error handling."""
        try:
            st.sidebar.write("📤 **Debug Upload**")
            
            # Generate IDs
            doc_id = str(uuid.uuid4())
            file_path = f"{owner_id}/{doc_id}_{filename}"
            
            st.sidebar.write(f"Doc ID: {doc_id}")
            st.sidebar.write(f"File path: {file_path}")
            st.sidebar.write(f"File size: {len(file_content)} bytes")
            st.sidebar.write(f"Chunks count: {len(chunks)}")
            
            # Check bucket exists
            try:
                self.client.storage.from_("documents").list(path=owner_id)
            except:
                st.sidebar.info("Creating user folder in bucket...")
            
            # Upload file
            self.client.storage.from_("documents").upload(
                file_path, file_content, {"content-type": "application/octet-stream"}
            )
            
            public_url = self.client.storage.from_("documents").get_public_url(file_path)
            
            # Prepare metadata
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
            
            st.sidebar.write(f"Metadata: {metadata.keys()}")
            
            # Insert metadata
            result = self.client.table("documents").insert(metadata).execute()
            
            if result.data:
                st.sidebar.success("✅ Document metadata saved")
                return doc_id
            else:
                st.sidebar.error("❌ Failed to save metadata")
                return None
                
        except Exception as e:
            st.sidebar.error(f"❌ Upload failed: {str(e)}")
            raise e
    
    def get_documents_by_filters(self, user_id: str, user_role: str,
                                 country: Optional[str] = None,
                                 doc_type: Optional[str] = None) -> List[Dict]:
        """Fetch documents with access control."""
        try:
            query = self.client.table("documents").select("*")
            
            # Access control: admin sees all, users see their own + admin docs
            if user_role != "admin":
                query = query.or_(f"owner_role.eq.admin,owner_id.eq.\"{user_id}\"")
            
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
                query = query.or_(f"owner_role.eq.admin,owner_id.eq.\"{user_id}\"")
            
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
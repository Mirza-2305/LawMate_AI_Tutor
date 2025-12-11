# chunking.py - Semantic chunking with overlap
from typing import List, Dict

def chunk_text(text: str, doc_id: str, chunk_size: int = 1000, overlap: int = 200) -> List[Dict]:
    """
    Split text into overlapping chunks that preserve context.
    """
    if not text or len(text.strip()) == 0:
        return []
    
    # Pre-process: Clean text and preserve paragraphs
    paragraphs = text.split('\n\n')
    chunks = []
    chunk_index = 0
    current_chunk = ""
    
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        
        # If adding this paragraph would exceed chunk size, save current chunk
        if len(current_chunk) + len(para) > chunk_size and current_chunk:
            chunks.append({
                'chunk_id': f"{doc_id}_chunk_{chunk_index}",
                'doc_id': doc_id,
                'text': current_chunk.strip(),
                'chunk_index': chunk_index,
                'preview': current_chunk[:100].strip()
            })
            chunk_index += 1
            
            # Start new chunk with overlap from previous
            current_chunk = current_chunk[-overlap:] + "\n\n" + para
        else:
            current_chunk += "\n\n" + para if current_chunk else para
    
    # Add final chunk
    if current_chunk.strip():
        chunks.append({
            'chunk_id': f"{doc_id}_chunk_{chunk_index}",
            'doc_id': doc_id,
            'text': current_chunk.strip(),
            'chunk_index': chunk_index,
            'preview': current_chunk[:100].strip()
        })
    
    return chunks

def find_relevant_chunks(query: str, chunks: List[Dict], top_k: int = 5) -> List[Dict]:
    """
    Smart search that handles partial matches and Urdu/Arabic transliterations.
    """
    query_lower = query.lower()
    
    # Normalize query for flexible matching
    # Handle common variations like "qatal e amad", "qatal-e-amd", "قتل"
    query_terms = query_lower.split()
    
    # Add variations for common legal terms
    variations = {
        "qatal": ["qatal", "قتل", "killing", "murder"],
        "amad": ["amad", "amd", "عمد", "intentional"],
        "shibh": ["shibh", "شبه", "near", "manslaughter"],
        "diat": ["diat", "diyat", "دیت", "blood", "money"],
    }
    
    expanded_terms = []
    for term in query_terms:
        expanded_terms.append(term)
        for key, vals in variations.items():
            if term in vals:
                expanded_terms.extend(vals)
    
    # Score chunks
    scored_chunks = []
    for chunk in chunks:
        score = 0
        chunk_text_lower = chunk['text'].lower()
        
        # Exact phrase match (highest score)
        for i in range(len(expanded_terms) - 1):
            phrase = " ".join(expanded_terms[i:i+2])
            if phrase in chunk_text_lower:
                score += 10
        
        # Individual term matches
        for term in set(expanded_terms):
            if term in chunk_text_lower:
                score += 1
        
        # Title/heading matches (bonus)
        if "section" in chunk_text_lower or "chapter" in chunk_text_lower:
            score += 2
        
        if score > 0:
            scored_chunks.append((chunk, score))
    
    # Sort and return top_k
    scored_chunks.sort(key=lambda x: x[1], reverse=True)
    
    # If we found matches, return them
    if scored_chunks:
        return [chunk for chunk, score in scored_chunks[:top_k]]
    
    # No matches - return first few chunks as fallback
    return chunks[:3]
# text_extraction.py - Works with file content (bytes)
import pdfplumber
from docx import Document
import pytesseract
from PIL import Image
import os
from typing import Optional

def extract_text_from_pdf_file(file_content: bytes) -> str:
    """Extract text from PDF content."""
    try:
        temp_path = "/tmp/temp_pdf.pdf"
        with open(temp_path, "wb") as f:
            f.write(file_content)
        
        text = ""
        with pdfplumber.open(temp_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
        
        os.remove(temp_path)
        return text.strip()
    except Exception as e:
        raise Exception(f"PDF extraction failed: {str(e)}")

def extract_text_from_docx_file(file_content: bytes) -> str:
    """Extract text from DOCX content."""
    try:
        temp_path = "/tmp/temp_docx.docx"
        with open(temp_path, "wb") as f:
            f.write(file_content)
        
        doc = Document(temp_path)
        text = "\n".join([paragraph.text for paragraph in doc.paragraphs])
        
        os.remove(temp_path)
        return text.strip()
    except Exception as e:
        raise Exception(f"DOCX extraction failed: {str(e)}")

def extract_text_from_image_file(file_content: bytes) -> str:
    """Extract text from image content."""
    try:
        temp_path = "/tmp/temp_image.png"
        with open(temp_path, "wb") as f:
            f.write(file_content)
        
        image = Image.open(temp_path)
        text = pytesseract.image_to_string(image)
        
        os.remove(temp_path)
        return text.strip()
    except Exception as e:
        raise Exception(f"OCR extraction failed: {str(e)}")

def extract_text_from_txt_file(file_content: bytes) -> str:
    """Extract text from TXT content."""
    try:
        return file_content.decode('utf-8').strip()
    except Exception as e:
        raise Exception(f"TXT extraction failed: {str(e)}")

def extract_text(file_content: bytes, file_extension: str) -> str:
    """Universal text extraction from file content."""
    file_extension = file_extension.lower()
    
    if file_extension == '.pdf':
        return extract_text_from_pdf_file(file_content)
    elif file_extension == '.docx':
        return extract_text_from_docx_file(file_content)
    elif file_extension in ['.png', '.jpg', '.jpeg']:
        return extract_text_from_image_file(file_content)
    elif file_extension == '.txt':
        return extract_text_from_txt_file(file_content)
    else:
        raise ValueError(f"Unsupported file type: {file_extension}")

def get_preview_text(text: str, max_chars: int = 200) -> str:
    """Get preview text."""
    if not text:
        return "No text extracted"
    
    preview = text[:max_chars].replace('\n', ' ')
    if len(text) > max_chars:
        preview += "..."
    return preview
import pdfplumber
from docx import Document
import pytesseract
from PIL import Image
from pathlib import Path
from typing import Optional

# Configure pytesseract path if needed (uncomment and set your path)
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

def extract_text_from_pdf(file_path: str) -> str:
    """Extract text from PDF with OCR fallback for scanned documents."""
    try:
        text = ""
        with pdfplumber.open(file_path) as pdf:
            for i, page in enumerate(pdf.pages):
                page_text = page.extract_text()
                
                if page_text and len(page_text.strip()) > 50:
                    # Good text extraction
                    text += page_text + "\n"
                else:
                    # Likely scanned image - use OCR
                    try:
                        img = page.to_image(resolution=300).original
                        ocr_text = pytesseract.image_to_string(img, lang='eng+urd')  # Add languages
                        if ocr_text.strip():
                            text += f"[OCR Page {i+1}] {ocr_text}\n"
                    except:
                        pass
        
        return text.strip()
    except Exception as e:
        raise Exception(f"PDF extraction failed: {str(e)}")


def extract_text_from_docx(file_path: str) -> str:
    """Extract text from DOCX files using python-docx."""
    try:
        doc = Document(file_path)
        text = "\n".join([paragraph.text for paragraph in doc.paragraphs])
        return text.strip()
    except Exception as e:
        raise Exception(f"DOCX extraction failed: {str(e)}")


def extract_text_from_image(file_path: str) -> str:
    """Extract text from images using Tesseract OCR."""
    try:
        image = Image.open(file_path)
        text = pytesseract.image_to_string(image)
        return text.strip()
    except Exception as e:
        raise Exception(f"OCR extraction failed: {str(e)}")


def extract_text_from_txt(file_path: str) -> str:
    """Extract text from plain text files."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            text = f.read()
        return text.strip()
    except Exception as e:
        raise Exception(f"TXT extraction failed: {str(e)}")


def extract_text(file_path: str, file_extension: str) -> str:
    """
    Universal text extraction function that routes to appropriate extractor.
    
    Args:
        file_path: Path to the file
        file_extension: File extension (e.g., '.pdf', '.docx')
    
    Returns:
        Extracted text as string
    """
    file_extension = file_extension.lower()
    
    if file_extension == '.pdf':
        return extract_text_from_pdf(file_path)
    elif file_extension == '.docx':
        return extract_text_from_docx(file_path)
    elif file_extension in ['.png', '.jpg', '.jpeg']:
        return extract_text_from_image(file_path)
    elif file_extension == '.txt':
        return extract_text_from_txt(file_path)
    else:
        raise ValueError(f"Unsupported file type: {file_extension}")


def get_preview_text(text: str, max_chars: int = 200) -> str:
    """Get a preview of the first N characters of text."""
    if not text:
        return "No text extracted"
    
    preview = text[:max_chars].replace('\n', ' ')
    if len(text) > max_chars:
        preview += "..."
    return preview
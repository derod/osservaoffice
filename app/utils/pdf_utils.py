"""PDF text extraction utilities."""
import os

# Maximum characters sent to OpenAI per request
CHUNK_SIZE = 3500
# Maximum total characters accepted (skip summarising enormous PDFs)
MAX_CHARS = 40_000


def extract_text(file_path: str) -> str:
    """
    Extract all text from a PDF file using pdfplumber.
    Returns the combined text string, or raises ValueError for non-PDFs
    or empty documents.
    """
    ext = os.path.splitext(file_path)[1].lower()
    if ext != ".pdf":
        raise ValueError("Only PDF files can be extracted.")

    try:
        import pdfplumber
    except ImportError:
        raise RuntimeError("pdfplumber is not installed. Run: pip install pdfplumber")

    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    pages_text = []
    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                pages_text.append(text.strip())

    combined = "\n\n".join(pages_text).strip()
    if not combined:
        raise ValueError("The PDF contains no extractable text (may be scanned/image-based).")

    return combined


def chunk_text(text: str, chunk_size: int = CHUNK_SIZE) -> list[str]:
    """Split text into chunks of at most chunk_size characters, breaking on newlines."""
    chunks = []
    while len(text) > chunk_size:
        split_at = text.rfind("\n", 0, chunk_size)
        if split_at == -1:
            split_at = chunk_size
        chunks.append(text[:split_at].strip())
        text = text[split_at:].strip()
    if text:
        chunks.append(text)
    return chunks


def prepare_text_for_summary(file_path: str) -> tuple[str, bool]:
    """
    Extract and truncate PDF text for summarisation.
    Returns (text, truncated).
    Raises ValueError / FileNotFoundError / RuntimeError on failure.
    """
    text = extract_text(file_path)
    truncated = False
    if len(text) > MAX_CHARS:
        text = text[:MAX_CHARS]
        truncated = True
    return text, truncated

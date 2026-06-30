"""
ZIP file handling for Google Drive sync.

When a ZIP file is detected (application/zip), extract internal PDFs,
compute their individual MD5 hashes, and validate against DB before parsing.

This prevents processing duplicate PDFs hidden inside ZIP files and ensures
each PDF is tracked independently.
"""

import io
import logging
import zipfile
import hashlib
from typing import List, Dict, Tuple, Optional

logger = logging.getLogger(__name__)


class ZipExtractionError(Exception):
    """Base exception for ZIP extraction failures."""
    pass


class PDFExtractor:
    """
    Extract and validate PDFs from ZIP files.
    """

    VALID_PDF_EXTENSIONS = ['.pdf']
    MAX_NESTED_DEPTH = 3  # Prevent zip-bombs
    MAX_EXTRACTION_SIZE = 500 * 1024 * 1024  # 500MB total max

    @staticmethod
    def compute_md5(data: bytes) -> str:
        """Compute MD5 hash of bytes."""
        return hashlib.md5(data).hexdigest()

    @staticmethod
    def is_pdf_file(filename: str) -> bool:
        """Check if filename is a PDF."""
        return filename.lower().endswith('.pdf')

    @classmethod
    def extract_pdfs_from_zip(cls, zip_data: bytes, zip_filename: str) -> List[Dict]:
        """
        Extract PDFs from a ZIP file.

        Args:
            zip_data: Binary data of ZIP file
            zip_filename: Name of ZIP file (for logging)

        Returns:
            List of dicts:
              {
                "filename": "invoice.pdf",
                "md5_checksum": "abc123...",
                "data": <bytes>,
                "size_bytes": 12345,
                "nested_in": "zip_name.zip"
              }

        Raises:
            ZipExtractionError: If ZIP is invalid or too large
        """
        pdfs = []
        total_size = 0

        try:
            zip_buffer = io.BytesIO(zip_data)
            with zipfile.ZipFile(zip_buffer, 'r') as zf:
                # Validate ZIP structure
                bad_file = zf.testzip()
                if bad_file:
                    raise ZipExtractionError(f"Corrupted ZIP file: {bad_file} failed CRC check")

                logger.info(f"[ZipExtractor] Extracting from {zip_filename}: {len(zf.namelist())} files")

                for file_info in zf.filelist:
                    filename = file_info.filename

                    # Skip directories
                    if filename.endswith('/'):
                        continue

                    # Check nesting depth
                    depth = filename.count('/')
                    if depth > cls.MAX_NESTED_DEPTH:
                        logger.warning(f"[ZipExtractor] Skipping deeply nested file (depth {depth}): {filename}")
                        continue

                    # Extract PDFs only
                    if not cls.is_pdf_file(filename):
                        logger.debug(f"[ZipExtractor] Skipping non-PDF: {filename}")
                        continue

                    try:
                        # Extract file
                        pdf_data = zf.read(filename)

                        # Check size limit
                        file_size = len(pdf_data)
                        total_size += file_size
                        if total_size > cls.MAX_EXTRACTION_SIZE:
                            raise ZipExtractionError(
                                f"ZIP extraction exceeds size limit ({total_size}>{cls.MAX_EXTRACTION_SIZE})"
                            )

                        # Validate it's actually a PDF
                        if not cls._is_valid_pdf(pdf_data):
                            logger.warning(f"[ZipExtractor] File looks like PDF but invalid magic: {filename}")

                        # Compute MD5
                        md5_hash = cls.compute_md5(pdf_data)

                        logger.info(f"[ZipExtractor] Extracted {filename} ({file_size} bytes) md5={md5_hash}")

                        pdfs.append({
                            "filename": filename,
                            "md5_checksum": md5_hash,
                            "data": pdf_data,
                            "size_bytes": file_size,
                            "nested_in": zip_filename
                        })

                    except Exception as e:
                        logger.error(f"[ZipExtractor] Error extracting {filename}: {e}")
                        continue

        except zipfile.BadZipFile as e:
            raise ZipExtractionError(f"Invalid ZIP file: {e}")
        except Exception as e:
            raise ZipExtractionError(f"ZIP extraction failed: {e}")

        logger.info(f"[ZipExtractor] Successfully extracted {len(pdfs)} PDFs from {zip_filename}")
        return pdfs

    @staticmethod
    def _is_valid_pdf(data: bytes) -> bool:
        """Check if bytes start with PDF magic number."""
        # PDF files start with %PDF
        return data.startswith(b'%PDF')

    @classmethod
    def extract_nested_zips(cls, zip_data: bytes, zip_filename: str, depth: int = 0) -> List[Dict]:
        """
        Recursively extract PDFs from nested ZIP files (up to MAX_NESTED_DEPTH).

        Args:
            zip_data: Binary data
            zip_filename: Name of file being extracted
            depth: Current recursion depth

        Returns:
            Flattened list of all extracted PDFs
        """
        if depth > cls.MAX_NESTED_DEPTH:
            logger.warning(f"[ZipExtractor] Max nesting depth reached")
            return []

        pdfs = []

        try:
            zip_buffer = io.BytesIO(zip_data)
            with zipfile.ZipFile(zip_buffer, 'r') as zf:
                for file_info in zf.filelist:
                    filename = file_info.filename

                    if filename.endswith('/'):
                        continue

                    if cls.is_pdf_file(filename):
                        # Extract PDF
                        pdf_data = zf.read(filename)
                        md5_hash = cls.compute_md5(pdf_data)
                        pdfs.append({
                            "filename": filename,
                            "md5_checksum": md5_hash,
                            "data": pdf_data,
                            "size_bytes": len(pdf_data),
                            "nested_in": zip_filename
                        })

                    elif filename.lower().endswith('.zip'):
                        # Recursively extract from nested ZIP
                        logger.info(f"[ZipExtractor] Found nested ZIP: {filename}")
                        nested_data = zf.read(filename)
                        nested_pdfs = cls.extract_nested_zips(nested_data, filename, depth + 1)
                        pdfs.extend(nested_pdfs)

        except Exception as e:
            logger.error(f"[ZipExtractor] Error processing nested files: {e}")

        return pdfs

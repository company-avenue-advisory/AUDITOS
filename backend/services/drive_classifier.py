"""
Recursive Drive folder walker + document classifier for the Sales pipeline.
Also used against zip-extracted local directories (see
local_directory_lister/classify_local_directory below) - the classification
rules are format-agnostic, only the "list this folder's children" call
differs between the Drive API and the local filesystem.

Verified against OneStack's real Drive tree (Sales > <N>. <Month Year>):
  - "Sales Invoice" / "Other Invoices" subfolders -> INVOICE
      (same OneStack PDF template; "Other Invoices" specifically holds the
      OMH/OHR adjustment series, but the template is identical)
  - "Credit Note" subfolder -> CREDIT_NOTE
  - "Sale Analysis" subfolder -> IGNORE (internal working files, not scanned)
  - loose files directly at the month-folder root -> classified by extension:
      .xlsx/.xls -> CLIENT_SHEET, .pdf -> INVOICE
  - any other/unrecognized subfolder name -> UNKNOWN (surfaced, not silently
    dropped, so a new folder type in a future month gets flagged for review
    instead of being invisibly ignored or invisibly processed)

Filenames are NEVER used to identify invoice/credit-note numbers - confirmed
unreliable (files in "Other Invoices" sometimes carry no invoice number at
all; one Credit Note file used a "PI" filename token while the document
itself read "Credit Note Number: CR26061002"). Numbers are always parsed
from document content downstream, by the extractor - this module only
decides WHICH extractor a file should go to.
"""

import enum
import os
from dataclasses import dataclass, field
from typing import Callable, List, Optional

FOLDER_MIME = "application/vnd.google-apps.folder"

_INVOICE_FOLDER_NAMES = {"sales invoice", "other invoices"}
_CREDIT_NOTE_FOLDER_NAMES = {"credit note"}
_IGNORE_FOLDER_NAMES = {"sale analysis"}


class DocumentType(str, enum.Enum):
    INVOICE = "invoice"
    CREDIT_NOTE = "credit_note"
    CLIENT_SHEET = "client_sheet"
    IGNORE = "ignore"
    UNKNOWN = "unknown"


@dataclass
class ClassifiedFile:
    id: str
    name: str
    mime_type: str
    document_type: DocumentType
    # folder names from the month-root down to this file's immediate parent;
    # [] means the file sits directly at the month-folder root
    path: List[str] = field(default_factory=list)
    # carried through from the raw Drive metadata for dedup tracking
    # downstream - optional since test fixtures don't always set them
    md5_checksum: Optional[str] = None
    modified_time: Optional[str] = None


def classify_folder_name(name: str) -> Optional[DocumentType]:
    """Returns the DocumentType every file inside this folder should get,
    or None if the folder itself needs no blanket classification (its
    files should fall through to per-file/root-level rules instead)."""
    key = name.strip().lower()
    if key in _INVOICE_FOLDER_NAMES:
        return DocumentType.INVOICE
    if key in _CREDIT_NOTE_FOLDER_NAMES:
        return DocumentType.CREDIT_NOTE
    if key in _IGNORE_FOLDER_NAMES:
        return DocumentType.IGNORE
    return None


def classify_root_file(name: str, mime_type: str) -> DocumentType:
    """Classifies a file sitting directly at the month-folder root (not
    inside any named subfolder) - the client sheet and the occasional
    loose invoice PDF both live here."""
    lower = name.lower()
    if mime_type == FOLDER_MIME:
        return DocumentType.UNKNOWN  # unrecognized subfolder, handled by caller
    if lower.endswith((".xlsx", ".xls")):
        return DocumentType.CLIENT_SHEET
    if lower.endswith(".pdf"):
        return DocumentType.INVOICE
    return DocumentType.UNKNOWN


def walk_and_classify(
    list_children_fn: Callable[[str], List[dict]],
    root_folder_id: str,
) -> List[ClassifiedFile]:
    """
    Recursively walks a Drive folder tree starting at root_folder_id and
    classifies every file found.

    list_children_fn(folder_id) -> list of Drive file-metadata dicts
    (each with at least "id", "name", "mimeType") for the direct children
    of that folder. Injected so this can be tested against a fixture
    (e.g. the exact tree already fetched and verified via MCP search)
    without needing live Drive credentials, and reused in production
    against GoogleDriveConnector.list_files(folder_id=...).

    One level of recursion is all OneStack's real tree needs (month folder
    -> named subfolders, no deeper nesting), but this walks arbitrarily deep
    so a client with an extra nesting level doesn't silently get skipped.
    """
    results: List[ClassifiedFile] = []

    def _walk(folder_id: str, path: List[str], forced_type: Optional[DocumentType]):
        for item in list_children_fn(folder_id):
            name = item["name"]
            mime = item["mimeType"]

            if mime == FOLDER_MIME:
                if forced_type is not None:
                    # a subfolder nested inside an already-classified folder
                    # (e.g. a stray folder inside "Credit Note") inherits it
                    _walk(item["id"], path + [name], forced_type)
                    continue
                sub_type = classify_folder_name(name)
                if sub_type == DocumentType.IGNORE:
                    continue  # don't even recurse into Sale Analysis
                _walk(item["id"], path + [name], sub_type)
                continue

            # it's a file
            if forced_type is not None:
                doc_type = forced_type
            elif path:
                # inside an unrecognized subfolder with no blanket rule -
                # surface it rather than guess
                doc_type = DocumentType.UNKNOWN
            else:
                doc_type = classify_root_file(name, mime)

            results.append(ClassifiedFile(
                id=item["id"], name=name, mime_type=mime,
                document_type=doc_type, path=list(path),
                md5_checksum=item.get("md5Checksum"),
                modified_time=item.get("modifiedTime"),
            ))

    _walk(root_folder_id, [], None)
    return results


def summarize(files: List[ClassifiedFile]) -> dict:
    """Small helper for verification runs: counts per document_type."""
    counts = {}
    for f in files:
        counts[f.document_type.value] = counts.get(f.document_type.value, 0) + 1
    return counts


def local_directory_lister(path: str) -> List[dict]:
    """
    Adapts a local directory (e.g. a zip extracted by upload_batch) into the
    same {"id", "name", "mimeType"} shape walk_and_classify expects from
    Drive, so a zip that mirrors the real folder structure (Sales Invoice /
    Credit Note / Other Invoices / Sale Analysis subfolders, or a client
    sheet + loose PDFs at the top level) gets classified identically to a
    live Drive sync - a credit note zipped up alongside regular invoices no
    longer gets silently misparsed as one.

    "id" is the file's own local path, since that's exactly what a caller
    needs to open/move the file next - no separate id-to-path lookup.
    """
    items = []
    for entry in os.scandir(path):
        if entry.is_dir():
            items.append({"id": entry.path, "name": entry.name, "mimeType": FOLDER_MIME})
        else:
            lower = entry.name.lower()
            if lower.endswith(".pdf"):
                mime = "application/pdf"
            elif lower.endswith((".xlsx", ".xls")):
                mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            else:
                mime = "application/octet-stream"
            items.append({"id": entry.path, "name": entry.name, "mimeType": mime})
    return items


def classify_local_directory(root_path: str) -> List[ClassifiedFile]:
    """Convenience wrapper: classify_local_directory(extract_dir) instead
    of walk_and_classify(local_directory_lister, extract_dir)."""
    return walk_and_classify(local_directory_lister, root_path)

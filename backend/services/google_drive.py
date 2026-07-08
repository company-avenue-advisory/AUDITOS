"""
Google Drive connector for auto-sync invoice pipeline.

Provides:
  - Authenticate via service account
  - List files from a shared folder
  - Download files
  - Track file metadata (id, md5Checksum, modifiedTime) for deduplication
"""

import os
import json
import logging
from typing import List, Dict, Optional
from io import BytesIO
from datetime import datetime

try:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaIoBaseDownload
    GOOGLE_DRIVE_AVAILABLE = True
except ImportError:
    GOOGLE_DRIVE_AVAILABLE = False
    logging.warning("Google Drive API libraries not installed. Install google-api-python-client, google-auth, google-auth-oauthlib.")

logger = logging.getLogger(__name__)


class GoogleDriveConnector:
    """
    Service account based Google Drive connector.
    Requires: GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON environment variable pointing to JSON key file.
    """

    def __init__(self, folder_id: str):
        """
        Initialize Google Drive connector.

        Args:
            folder_id: Google Drive folder ID to monitor for invoices
        """
        if not GOOGLE_DRIVE_AVAILABLE:
            raise RuntimeError("Google Drive API libraries not installed")

        self.folder_id = folder_id
        self.service = None
        self._authenticate()

    def _authenticate(self):
        """Authenticate using service account credentials."""
        service_account_json = os.getenv("GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON")
        if not service_account_json:
            raise ValueError("GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON environment variable not set")

        try:
            # Load credentials from JSON file or string
            if os.path.isfile(service_account_json):
                credentials = service_account.Credentials.from_service_account_file(
                    service_account_json,
                    scopes=["https://www.googleapis.com/auth/drive.readonly"]
                )
            else:
                # Try parsing as JSON string
                creds_dict = json.loads(service_account_json)
                credentials = service_account.Credentials.from_service_account_info(
                    creds_dict,
                    scopes=["https://www.googleapis.com/auth/drive.readonly"]
                )

            self.service = build("drive", "v3", credentials=credentials)
            logger.info("Google Drive authentication successful")
        except Exception as e:
            logger.error(f"Failed to authenticate with Google Drive: {e}")
            raise

    def list_files(self, file_types: List[str] = None, folder_id: str = None) -> List[Dict]:
        """
        List files in the monitored folder.

        Args:
            file_types: MIME types to filter (e.g., ["application/pdf"])
                       If None, returns all files (including subfolders,
                       whose mimeType is "application/vnd.google-apps.folder").
            folder_id: overrides self.folder_id for this one call - lets
                       callers recurse into subfolders without constructing
                       a new connector per folder level.

        Returns:
            List of file metadata dicts with keys:
              - id: Google Drive file ID (immutable)
              - name: filename
              - mimeType: MIME type
              - md5Checksum: MD5 hash of file content
              - modifiedTime: ISO format timestamp
              - webViewLink: URL to view file
        """
        if not self.service:
            raise RuntimeError("Not authenticated with Google Drive")

        target_folder_id = folder_id or self.folder_id
        files = []
        try:
            # Build query for files in the folder
            query = f"'{target_folder_id}' in parents and trashed=false"

            # Filter by MIME type if specified (PDFs only for invoices)
            if file_types:
                mime_filters = " or ".join([f"mimeType='{mime}'" for mime in file_types])
                query += f" and ({mime_filters})"

            page_token = None
            while True:
                results = self.service.files().list(
                    q=query,
                    spaces="drive",
                    pageSize=100,
                    fields="nextPageToken, files(id, name, mimeType, md5Checksum, modifiedTime, webViewLink, size)",
                    pageToken=page_token
                ).execute()

                files.extend(results.get("files", []))
                page_token = results.get("nextPageToken")
                if not page_token:
                    break

            logger.info(f"Found {len(files)} files in Google Drive folder {target_folder_id}")
            return files

        except Exception as e:
            logger.error(f"Error listing files from Google Drive: {e}")
            raise

    def download_file(self, file_id: str, file_name: str, output_path: str) -> bool:
        """
        Download a file from Google Drive.

        Args:
            file_id: Google Drive file ID
            file_name: Original filename (for logging)
            output_path: Local path to save the file

        Returns:
            True if successful, False otherwise
        """
        if not self.service:
            raise RuntimeError("Not authenticated with Google Drive")

        try:
            request = self.service.files().get_media(fileId=file_id)

            # Create directory if it doesn't exist
            os.makedirs(os.path.dirname(output_path), exist_ok=True)

            with open(output_path, "wb") as f:
                downloader = MediaIoBaseDownload(f, request)
                done = False
                while not done:
                    status, done = downloader.next_chunk()
                    if status:
                        progress = int(status.progress() * 100)
                        logger.debug(f"Download {file_name}: {progress}%")

            logger.info(f"Downloaded {file_name} from Google Drive to {output_path}")
            return True

        except Exception as e:
            logger.error(f"Error downloading {file_name} from Google Drive: {e}")
            return False

    def get_file_metadata(self, file_id: str) -> Optional[Dict]:
        """
        Get current metadata for a file (to check if it was updated).

        Returns:
            Dict with id, name, md5Checksum, modifiedTime or None if not found
        """
        if not self.service:
            raise RuntimeError("Not authenticated with Google Drive")

        try:
            result = self.service.files().get(
                fileId=file_id,
                fields="id, name, mimeType, md5Checksum, modifiedTime, size"
            ).execute()
            return result
        except Exception as e:
            logger.error(f"Error fetching metadata for file {file_id}: {e}")
            return None


class GoogleDriveFileTracker:
    """
    Track processed files using database to detect new/changed files.
    Implements deduplication logic: only process if file is new or md5Checksum changed.
    """

    def __init__(self, db_session):
        from models import GoogleDriveFileTracker as DBTracker
        self.db = db_session
        self.DBTracker = DBTracker

    def is_file_processed(self, google_drive_id: str, md5_checksum: str) -> bool:
        """
        Check if file was already processed.
        Returns False if:
          - File ID doesn't exist (new file)
          - File ID exists but md5Checksum changed (file was updated)
        """
        try:
            existing = self.db.query(self.DBTracker).filter(
                self.DBTracker.google_drive_id == google_drive_id
            ).first()

            if not existing:
                return False  # New file

            # Check if content changed (md5Checksum is different)
            if existing.md5_checksum != md5_checksum:
                logger.info(f"File {google_drive_id} was updated (md5 changed)")
                return False  # File was updated, needs reprocessing

            return True  # Already processed with same content

        except Exception as e:
            logger.error(f"Error checking if file processed: {e}")
            return False

    def mark_as_processing(self, google_drive_id: str, tenant_id: str, filename: str,
                          md5_checksum: str, modified_time: str) -> str:
        """
        Mark a file as being processed. Returns the record ID.
        """
        from models import GoogleDriveFileTracker as DBTracker

        try:
            # Check if exists and update, or create new
            existing = self.db.query(DBTracker).filter(
                DBTracker.google_drive_id == google_drive_id
            ).first()

            if existing:
                # Update existing record
                existing.processing_status = "processing"
                existing.md5_checksum = md5_checksum
                existing.modified_time = datetime.fromisoformat(modified_time.replace('Z', '+00:00'))
                existing.updated_at = datetime.utcnow()
            else:
                # Create new record
                existing = DBTracker(
                    id=google_drive_id,
                    tenant_id=tenant_id,
                    google_drive_id=google_drive_id,
                    md5_checksum=md5_checksum,
                    modified_time=datetime.fromisoformat(modified_time.replace('Z', '+00:00')),
                    filename=filename,
                    processing_status="processing"
                )
                self.db.add(existing)

            self.db.commit()
            return existing.id

        except Exception as e:
            logger.error(f"Error marking file as processing: {e}")
            raise

    def mark_as_completed(self, google_drive_id: str, task_id: str, excel_row_id: int = None):
        """
        Mark file as successfully processed.
        """
        try:
            existing = self.db.query(self.DBTracker).filter(
                self.DBTracker.google_drive_id == google_drive_id
            ).first()

            if existing:
                existing.processing_status = "completed"
                existing.task_id = task_id
                existing.excel_row_id = excel_row_id
                existing.processed_at = datetime.utcnow()
                existing.updated_at = datetime.utcnow()
                self.db.commit()

        except Exception as e:
            logger.error(f"Error marking file as completed: {e}")
            raise

    def mark_as_failed(self, google_drive_id: str, error_message: str):
        """
        Mark file as failed to process.
        """
        try:
            existing = self.db.query(self.DBTracker).filter(
                self.DBTracker.google_drive_id == google_drive_id
            ).first()

            if existing:
                existing.processing_status = "failed"
                existing.error_message = error_message
                existing.updated_at = datetime.utcnow()
                self.db.commit()

        except Exception as e:
            logger.error(f"Error marking file as failed: {e}")
            raise

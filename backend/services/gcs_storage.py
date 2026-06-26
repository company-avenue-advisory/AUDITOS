import os
from google.cloud import storage
from dotenv import load_dotenv

# Ensure dotenv is loaded from backend directory
env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
load_dotenv(dotenv_path=env_path)

class GCSStorageService:
    def __init__(self):
        self.client = None
        self.bucket = None
        self.bucket_name = os.getenv("GCS_BUCKET_NAME", "audit-bucket-caa")
        
        # Check if GCP_CREDS_JSON env variable is present (useful for cloud deployments like Render/Railway)
        gcp_creds_json = os.getenv("GCP_CREDS_JSON")
        if gcp_creds_json:
            temp_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "gcp_creds.json")
            try:
                with open(temp_path, "w", encoding="utf-8") as f:
                    f.write(gcp_creds_json.strip())
                os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = temp_path
                print(f"Successfully wrote GCP_CREDS_JSON to {temp_path}")
            except Exception as e:
                print(f"Failed to write GCP_CREDS_JSON to file: {e}")

        credentials_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        
        # If relative or absolute credentials path is specified, locate it
        if credentials_path:
            if not os.path.isabs(credentials_path):
                # Try finding it relative to the workspace root or current directory
                workspace_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
                test_paths = [
                    os.path.abspath(credentials_path),
                    os.path.join(workspace_root, credentials_path),
                    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), credentials_path)
                ]
                for p in test_paths:
                    if os.path.exists(p):
                        credentials_path = p
                        break
            
            if os.path.exists(credentials_path):
                try:
                    self.client = storage.Client.from_service_account_json(credentials_path)
                    self.bucket = self.client.bucket(self.bucket_name)
                    print(f"Initialized GCS Client with credentials from {credentials_path}")
                except Exception as e:
                    print(f"Failed to initialize GCS with credential file: {e}")
            else:
                print(f"Credentials file path does not exist: {credentials_path}")
        
        # Fallback to default application credentials if bucket is not yet initialized
        if not self.client:
            try:
                self.client = storage.Client()
                self.bucket = self.client.bucket(self.bucket_name)
                print("Initialized GCS Client with default credentials")
            except Exception as e:
                print(f"Failed to initialize GCS client with default credentials: {e}")

    def is_active(self) -> bool:
        """Returns True if the GCS bucket was successfully configured and initialized."""
        return self.bucket is not None

    def upload_file(self, local_path: str, blob_name: str) -> bool:
        """Uploads a local file to a GCS blob."""
        if not self.is_active():
            return False
        try:
            blob = self.bucket.blob(blob_name)
            blob.upload_from_filename(local_path)
            print(f"Successfully uploaded {local_path} to GCS as {blob_name}")
            return True
        except Exception as e:
            print(f"Error uploading file {local_path} to GCS blob {blob_name}: {e}")
            return False

    def download_file(self, blob_name: str, local_path: str) -> bool:
        """Downloads a GCS blob to a local path."""
        if not self.is_active():
            return False
        try:
            blob = self.bucket.blob(blob_name)
            if not blob.exists():
                print(f"GCS Blob {blob_name} does not exist")
                return False
            
            # Ensure local folder exists
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            blob.download_to_filename(local_path)
            print(f"Successfully downloaded GCS blob {blob_name} to {local_path}")
            return True
        except Exception as e:
            print(f"Error downloading GCS blob {blob_name} to {local_path}: {e}")
            return False

    def file_exists(self, blob_name: str) -> bool:
        """Checks if a blob exists in the GCS bucket."""
        if not self.is_active():
            return False
        try:
            blob = self.bucket.blob(blob_name)
            return blob.exists()
        except Exception as e:
            print(f"Error checking existence of GCS blob {blob_name}: {e}")
            return False

# Export a single global instance
gcs_storage = GCSStorageService()

import os
from google.cloud import storage

key_path = "c:\\Users\\yugvk\\Downloads\\antigravityaudit\\audit-os-production-6c207b0f55eb.json"
print("Key exists:", os.path.exists(key_path))

try:
    client = storage.Client.from_service_account_json(key_path)
    print("Project ID:", client.project)
    buckets = list(client.list_buckets())
    print("Found buckets:")
    for b in buckets:
        print(f" - {b.name}")
except Exception as e:
    print("Error listing GCS buckets:", e)

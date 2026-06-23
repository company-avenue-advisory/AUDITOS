import requests
import json
import os

API_URL = "http://localhost:8000"

def test_extraction():
    pdf_path = r"c:\Users\yugvk\Downloads\antigravityaudit\invoices\test_with_shah.pdf"
    if not os.path.exists(pdf_path):
        print(f"Error: Test file {pdf_path} not found.")
        return
        
    print(f"Uploading {pdf_path} to {API_URL}/api/extract...")
    with open(pdf_path, "rb") as f:
        files = [("files", (os.path.basename(pdf_path), f, "application/pdf"))]
        response = requests.post(f"{API_URL}/api/extract", files=files)
        
    if response.status_code != 200:
        print(f"Extraction failed with status {response.status_code}:")
        print(response.text)
        return None
        
    data = response.json()
    items = data.get("items", [])
    print(f"Successfully extracted {len(items)} items!")
    
    # Print summary of items and any validation errors
    for i, item in enumerate(items):
        print(f"Row {i+1}: Supplier: {item.get('party_ac_name')}, Inv: {item.get('supplier_inv')}, Date: {item.get('invoice_date')}, Amount: {item.get('amount')}, HSN: {item.get('hsn')}")
        if item.get("errors"):
            print(f"  -> Suspected Errors: {item.get('errors')}")
            
    return items

def test_export(items):
    if not items:
        return
    print(f"\nSending items to {API_URL}/api/export to generate Excel sheet...")
    response = requests.post(f"{API_URL}/api/export", json={"items": items})
    
    if response.status_code != 200:
        print(f"Export failed with status {response.status_code}:")
        print(response.text)
        return
        
    output_path = "test_api_output.xlsx"
    with open(output_path, "wb") as f:
        f.write(response.content)
    print(f"Export successful! Spreadsheet saved as {output_path} (exists: {os.path.exists(output_path)})")

if __name__ == "__main__":
    items = test_extraction()
    if items:
        test_export(items)

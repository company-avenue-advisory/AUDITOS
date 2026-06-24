from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
import os

def create_mock_sales_invoice(filename="mock_sales_b2b.pdf"):
    """
    Generates a realistic Indian B2B Tax Invoice PDF for testing Audit OS.
    """
    c = canvas.Canvas(filename, pagesize=A4)
    width, height = A4
    
    c.setFont("Helvetica-Bold", 16)
    c.drawCentredString(width / 2, height - 50, "TAX INVOICE")
    
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, height - 90, "Audit OS Tech Solutions Pvt Ltd")
    c.setFont("Helvetica", 10)
    c.drawString(50, height - 105, "123 Tech Park, Andheri East, Mumbai")
    c.drawString(50, height - 120, "State: Maharashtra | State Code: 27")
    c.drawString(50, height - 135, "GSTIN: 27AAAAA0000A1Z5")
    
    c.setFont("Helvetica-Bold", 11)
    c.drawString(50, height - 170, "Billed To:")
    c.setFont("Helvetica", 10)
    c.drawString(50, height - 185, "Acme Corp India Ltd")
    c.drawString(50, height - 200, "456 Startup Boulevard, Koramangala, Bengaluru")
    c.drawString(50, height - 215, "State: Karnataka | State Code: 29")
    c.setFont("Helvetica-Bold", 10)
    c.drawString(50, height - 230, "Buyer GSTIN: 29BBBBB1111B1Z5") # This triggers B2B routing
    
    c.setFont("Helvetica", 10)
    c.drawString(350, height - 185, "Invoice No: INV-2026-0042")
    c.drawString(350, height - 200, "Invoice Date: 15/06/2026")
    c.drawString(350, height - 215, "Place of Supply: Karnataka (29)")
    
    c.line(50, height - 250, 550, height - 250)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(55, height - 265, "Description of Services")
    c.drawString(280, height - 265, "HSN/SAC")
    c.drawString(350, height - 265, "Qty")
    c.drawString(400, height - 265, "Rate")
    c.drawString(480, height - 265, "Taxable Val")
    c.line(50, height - 275, 550, height - 275)
    
    c.setFont("Helvetica", 10)
    c.drawString(55, height - 295, "Annual Cloud Infrastructure SaaS")
    c.drawString(280, height - 295, "998311")
    c.drawString(350, height - 295, "1")
    c.drawString(400, height - 295, "2,00,000.00")
    c.drawString(480, height - 295, "2,00,000.00")

    c.drawString(55, height - 320, "Implementation Consulting")
    c.drawString(280, height - 320, "998311")
    c.drawString(350, height - 320, "1")
    c.drawString(400, height - 320, "50,000.00")
    c.drawString(480, height - 320, "50,000.00")
    
    c.line(50, height - 340, 550, height - 340)
    
    c.setFont("Helvetica-Bold", 10)
    c.drawString(350, height - 360, "Total Taxable Value:")
    c.drawString(480, height - 360, "2,50,000.00")
    
    c.drawString(350, height - 380, "IGST @ 18%:")
    c.drawString(480, height - 380, "45,000.00")
    
    c.drawString(350, height - 400, "CGST @ 9%:")
    c.drawString(480, height - 400, "0.00")
    
    c.drawString(350, height - 420, "SGST @ 9%:")
    c.drawString(480, height - 420, "0.00")
    
    c.line(350, height - 430, 550, height - 430)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(350, height - 445, "Grand Total (INR):")
    c.drawString(480, height - 445, "2,95,000.00")
    
    c.setFont("Helvetica-Bold", 10)
    c.drawString(50, height - 500, "Terms & Notes:")
    c.setFont("Helvetica", 10)
    c.drawString(50, height - 515, "1. Payment due within 30 days.")
    # This line tests if the AI catches standard 10% deduction assumptions
    c.drawString(50, height - 530, "2. Subject to 10% TDS deduction under Sec 194J.") 
    
    c.save()
    print(f"✅ Successfully generated B2B test invoice: {os.path.abspath(filename)}")

if __name__ == "__main__":
    create_mock_sales_invoice()

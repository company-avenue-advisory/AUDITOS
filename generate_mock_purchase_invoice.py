from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
import os

def create_mock_purchase_invoice(filename="mock_purchase_invoice.pdf"):
    c = canvas.Canvas(filename, pagesize=A4)
    width, height = A4
    
    c.setFont("Helvetica-Bold", 16)
    c.drawCentredString(width / 2, height - 50, "TAX INVOICE")
    
    # Vendor (Supplier)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, height - 90, "Global Office Supplies & Catering Ltd")
    c.setFont("Helvetica", 10)
    c.drawString(50, height - 105, "789 Commercial Road, Pune")
    c.drawString(50, height - 120, "State: Maharashtra | State Code: 27")
    c.drawString(50, height - 135, "GSTIN: 27XYZAB1234C1Z9")
    
    # Buyer (Our Client)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(50, height - 170, "Billed To:")
    c.setFont("Helvetica", 10)
    c.drawString(50, height - 185, "One Stack Solution Private Limited")
    c.drawString(50, height - 200, "123 Tech Park, Andheri East, Mumbai")
    c.drawString(50, height - 215, "State: Maharashtra | State Code: 27")
    c.setFont("Helvetica-Bold", 10)
    c.drawString(50, height - 230, "Buyer GSTIN: 27AAAAA0000A1Z5") 
    
    c.setFont("Helvetica", 10)
    c.drawString(350, height - 185, "Invoice No: GOSC-23-455")
    c.drawString(350, height - 200, "Invoice Date: 20/06/2026")
    c.drawString(350, height - 215, "Place of Supply: Maharashtra (27)")
    
    c.line(50, height - 250, 550, height - 250)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(55, height - 265, "Description")
    c.drawString(250, height - 265, "HSN")
    c.drawString(300, height - 265, "Qty")
    c.drawString(340, height - 265, "Rate")
    c.drawString(400, height - 265, "Taxable Val")
    c.drawString(480, height - 265, "CGST+SGST")
    c.line(50, height - 275, 550, height - 275)
    
    c.setFont("Helvetica", 10)
    # Item 1: Laptops (Eligible ITC)
    c.drawString(55, height - 295, "Office Laptops (Dell XPS)")
    c.drawString(250, height - 295, "8471")
    c.drawString(300, height - 295, "2")
    c.drawString(340, height - 295, "100000.00")
    c.drawString(400, height - 295, "200000.00")
    c.drawString(480, height - 295, "36000.00") # 18% total

    # Item 2: Food & Beverages (Blocked ITC)
    c.drawString(55, height - 320, "Staff Food & Beverages (Event)")
    c.drawString(250, height - 320, "9963")
    c.drawString(300, height - 320, "1")
    c.drawString(340, height - 320, "50000.00")
    c.drawString(400, height - 320, "50000.00")
    c.drawString(480, height - 320, "2500.00") # 5% total
    
    c.line(50, height - 340, 550, height - 340)
    
    c.setFont("Helvetica-Bold", 10)
    c.drawString(300, height - 360, "Total Taxable Value:")
    c.drawString(400, height - 360, "250000.00")
    
    c.drawString(300, height - 380, "CGST:")
    c.drawString(400, height - 380, "19250.00") # 18000 + 1250
    
    c.drawString(300, height - 400, "SGST:")
    c.drawString(400, height - 400, "19250.00")
    
    c.line(300, height - 410, 550, height - 410)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(300, height - 425, "Grand Total (INR):")
    c.drawString(400, height - 425, "288500.00")
    
    c.setFont("Helvetica", 9)
    c.drawString(50, height - 450, "* Math validation:")
    c.drawString(50, height - 465, "Item 1: 2,00,000 + (18,000 CGST + 18,000 SGST) = 2,36,000")
    c.drawString(50, height - 480, "Item 2: 50,000 + (1,250 CGST + 1,250 SGST) = 52,500")
    c.drawString(50, height - 495, "Total: 2,88,500")

    c.save()
    print(f"Successfully generated Purchase test invoice: {os.path.abspath(filename)}")

if __name__ == "__main__":
    create_mock_purchase_invoice()

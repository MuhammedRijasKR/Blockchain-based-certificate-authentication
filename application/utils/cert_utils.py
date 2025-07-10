import pdfplumber
from connection import contract
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image


def generate_certificate(output_path, uid, candidate_name, course_name, org_name, institute_logo_path, institute_email):
    # Create a PDF document
    doc = SimpleDocTemplate(output_path, pagesize=letter)

    # Create a list to hold the elements of the PDF
    elements = []

    # Add institute logo
    if institute_logo_path:
        logo = Image(institute_logo_path, width=150, height=150)
        elements.append(logo)

    # Add institute name
    institute_style = ParagraphStyle(
        "InstituteStyle",
        parent=getSampleStyleSheet()["Title"],
        fontName="Helvetica-Bold",
        fontSize=15,
        spaceAfter=10,
    )
    institute = Paragraph(org_name, institute_style)
    elements.append(institute)

    email_style = ParagraphStyle(
        "EmailStyle",
        parent=getSampleStyleSheet()["Normal"],
        fontName="Helvetica",
        fontSize=10,
        textColor="gray",
        spaceAfter=30,
    )
    email_paragraph = Paragraph(f"Email: {institute_email}", email_style)
    elements.extend([email_paragraph, Spacer(1, 12)])

    # Add title
    title_style = ParagraphStyle(
        "TitleStyle",
        parent=getSampleStyleSheet()["Title"],
        fontName="Helvetica-Bold",
        fontSize=25,
        spaceAfter=20,
    )
    title1 = Paragraph("Certificate of Completion", title_style)
    elements.extend([title1, Spacer(1, 6)])

    # Add recipient name, UID, and course name
    recipient_style = ParagraphStyle(
        "RecipientStyle",
        parent=getSampleStyleSheet()["BodyText"],
        fontSize=14,
        spaceAfter=6,
        leading=18,
        alignment=1
    )

    recipient_text = f"This is to certify that<br/><br/>\
                     <font color='red'> {candidate_name} </font><br/>\
                     with UID <br/> \
                     <font color='red'> {uid} </font> <br/><br/>\
                     has successfully completed the course:<br/>\
                     <font color='blue'> {course_name} </font>"

    recipient = Paragraph(recipient_text, recipient_style)
    elements.extend([recipient, Spacer(1, 12)])

    # Build the PDF document
    doc.build(elements)

    print(f"Certificate generated and saved at: {output_path}")


def extract_certificate(pdf_path):
    with pdfplumber.open(pdf_path) as pdf:
        # Extract text from each page
        text = ""
        for page in pdf.pages:
            text += page.extract_text()
        lines = text.splitlines()
        print(lines)

        org_name = lines[0]
        email = lines[1]
        candidate_name = lines[4]
        uid = lines[6]
        course_name = lines[-1]

        return uid, email, candidate_name, course_name, org_name


def get_certificate_id_ipfs_hash(ipfs_hash):
    certificate_ids = contract.functions.getAllCertificateIds().call()
    for certificate_id in certificate_ids:
        certificate = contract.functions.getCertificate(certificate_id).call()
        if certificate[4] == ipfs_hash:
            return certificate_id
    return None

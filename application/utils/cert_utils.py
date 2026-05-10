import pdfplumber
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image

from connection import contract
from utils.qr_utils import make_qr_image_buffer


def generate_certificate(output_path, uid, candidate_name, course_name, org_name, institute_logo_path, grade="", certificate_id=None):
    # Create a PDF document
    doc = SimpleDocTemplate(output_path, pagesize=letter)

    # Create a list to hold the elements of the PDF
    elements = []

    # Add institute logo and institute name
    if institute_logo_path:
        logo = Image(institute_logo_path, width=150, height=150)
        elements.append(logo)

    # Add institute name
    institute_style = ParagraphStyle(
        "InstituteStyle",
        parent=getSampleStyleSheet()["Title"],
        fontName="Helvetica-Bold",
        fontSize=15,
        spaceAfter=40,
    )
    institute = Paragraph(org_name, institute_style)
    elements.extend([institute, Spacer(1, 12)])

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

    # Add recipient name, UID, and course name with increased line space
    recipient_style = ParagraphStyle(
        "RecipientStyle",
        parent=getSampleStyleSheet()["BodyText"],
        fontSize=14,
        spaceAfter=6,
        leading=18,
        alignment=1
    )

    grade_text = f"<br/><br/>Grade: <font color='green'> {grade} </font>" if grade else ""

    recipient_text = f"This is to certify that<br/><br/>\
                     <font color='red'> {candidate_name} </font><br/>\
                     with UID <br/> \
                    <font color='red'> {uid} </font> <br/><br/>\
                     has successfully completed the course:<br/>\
                     <font color='blue'> {course_name} </font>{grade_text}"

    recipient = Paragraph(recipient_text, recipient_style)
    elements.extend([recipient, Spacer(1, 12)])

    # Embed a QR code encoding the certificate_id (used for verifier scan).
    # NOTE: only the image is added — no caption text — because
    # extract_certificate() parses the PDF's text content positionally,
    # so any extra Paragraph would shift the indices.
    if certificate_id:
        qr_buf = make_qr_image_buffer(certificate_id)
        qr_img = Image(qr_buf, width=110, height=110)
        elements.extend([Spacer(1, 18), qr_img])

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

        org_name = lines[0]
        candidate_name = lines[3]
        uid = lines[5]

        # Check if grade is present (last line starts with "Grade:")
        grade = ""
        if lines[-1].startswith("Grade:"):
            grade = lines[-1].replace("Grade:", "").strip()
            course_name = lines[-2]
        else:
            course_name = lines[-1]

        return uid, candidate_name, course_name, org_name, grade


def get_certificate_id_ipfs_hash(ipfs_hash):
    # First check individual certificates on-chain
    certificate_ids = contract.functions.getAllCertificateIds().call()
    for certificate_id in certificate_ids:
        certificate = contract.functions.getCertificate(certificate_id).call()
        if certificate[4] == ipfs_hash:
            return certificate_id

    # Also check pending individual certificates
    try:
        pending_ids = contract.functions.getAllPendingCertificateIds().call()
        for certificate_id in pending_ids:
            certificate = contract.functions.getCertificate(certificate_id).call()
            if certificate[4] == ipfs_hash:
                return certificate_id
    except:
        pass

    # Check Merkle proof store for batch certificates
    from utils.merkle_utils import _load_store
    store = _load_store()
    for batch_id, batch_data in store.items():
        for cert_id, cert in batch_data["certificates"].items():
            if cert.get("ipfs_hash") == ipfs_hash:
                return cert_id

    return None

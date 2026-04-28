import os
import email
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import imaplib
import smtplib
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

IMAP_SERVER = os.getenv("IMAP_SERVER", "imap.gmail.com")
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS", "your_email@example.com")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD", "your_app_password")

USER_EMAIL = os.getenv("USER_EMAIL", "your_personal_email")

def poll_for_new_emails(since_timestamp: float = None) -> list:
    try:
        mail = imaplib.IMAP4_SSL(IMAP_SERVER)
        mail.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        mail.select("INBOX")
        
        if since_timestamp:
            since_date = datetime.fromtimestamp(since_timestamp).strftime("%d-%b-%Y")
            search_criteria = f'SINCE {since_date} FROM "{USER_EMAIL}"'
        else:
            from datetime import timedelta
            since_date = (datetime.now() - timedelta(days=7)).strftime("%d-%b-%Y")
            search_criteria = f'SINCE {since_date} FROM "{USER_EMAIL}"'
        
        typ, messages = mail.search(None, search_criteria)
        email_ids = messages[0].split()
        
        new_emails = []
        for eid in email_ids[-5:]:
            typ, msg_data = mail.fetch(eid, "(RFC822)")
            for response_part in msg_data:
                if isinstance(response_part, tuple):
                    msg = email.message_from_bytes(response_part[1])
                    new_emails.append({
                        "subject": msg["subject"],
                        "from": msg["from"],
                        "date": msg["date"],
                        "body": get_message_body(msg)
                    })
        
        mail.logout()
        return new_emails
    except Exception as e:
        print(f"Error polling emails: {e}")
        return []

def get_message_body(msg) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                return part.get_payload(decode=True).decode()
    else:
        return msg.get_payload(decode=True).decode()
    return ""

def send_email(subject: str, body: str, to_address: str = None) -> bool:
    if to_address is None:
        to_address = USER_EMAIL
    
    try:
        msg = MIMEMultipart()
        msg["From"] = EMAIL_ADDRESS
        msg["To"] = to_address
        msg["Subject"] = subject
        
        msg.attach(MIMEText(body, "plain"))
        
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        server.send_message(msg)
        server.quit()
        
        return True
    except Exception as e:
        print(f"Error sending email: {e}")
        return False
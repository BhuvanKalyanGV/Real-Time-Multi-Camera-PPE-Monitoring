import smtplib
from email.message import EmailMessage
import os


SENDER_EMAIL = "ppe40507@gmail.com"
SENDER_PASSWORD = "rxwjtjvzusybsoqx"   # Use Gmail App Password
SUPERVISOR_EMAIL = ["22203003@rmd.ac.in"]

def send_alert_email(camera_id, zone, person_id, violation, timestamp, snapshot_path):

    msg = EmailMessage()
    msg["Subject"] = f"🚨 PPE Violation Alert - Camera {camera_id}"
    msg["From"] = SENDER_EMAIL
    msg["To"] = ", ".join(SUPERVISOR_EMAIL)

    msg.set_content(f"""
PPE VIOLATION DETECTED

Camera ID : {camera_id}
Zone      : {zone}
Person ID : {person_id}
Violation : {violation}
Time      : {timestamp}

Please take necessary action immediately.
""")

    
    with open(snapshot_path, "rb") as f:
        file_data = f.read()
        file_name = os.path.basename(snapshot_path)

    msg.add_attachment(file_data,
                       maintype="image",
                       subtype="jpeg",
                       filename=file_name)

    # Send Email
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(SENDER_EMAIL, SENDER_PASSWORD)
        smtp.send_message(msg)
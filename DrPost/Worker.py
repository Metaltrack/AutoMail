from smtplib import SMTP
import datetime
from urllib import response
from logger import logger, log_level
from email.message import EmailMessage

log = logger()

class DrMail:
    def __init__(self, sender_mail, app_password, host="smtp.gmail.com", port=587):
        try:
            log.log(log_level.WARNING, "Worker.py", f"Teaching doctor how to send mail....")
            self.sender_mail = sender_mail
            self.app_password = app_password
            self.host = host
            self.port = port

            self.smtp = SMTP(host, port)
            #self.smtp.connect(host, port)

            status_code, response = self.smtp.ehlo()
            log.log(log_level.INFO, "Worker.py", f"status_code: {status_code} | response: {response}")

            status_code, response = self.smtp.starttls()
            log.log(log_level.INFO, "Worker.py", f"status_code: {status_code} | response: {response}")

            self.smtp.login(sender_mail, app_password)
            log.log(log_level.INFO, "Worker.py", f"SMTP Login Done...")

            status_code, response = self.smtp.ehlo()
            log.log(log_level.INFO, "Worker.py", f"status_code: {status_code} | response: {response}")
        except Exception as err:
            log.log(log_level.CRITICAL, "Worker.py", f"__init__ function: {err}")
            raise Exception(err)
            return

    def SendMail(self, from_addr, to_addr, sub, msg_content):
        try:
            log.log(log_level.WARNING, "Worker.py", f"Doctor is trying his best to send the message...")
            msg = EmailMessage()
            msg["From"] = from_addr
            msg["To"] = to_addr
            msg["Subject"] = sub
            msg.set_content(msg_content)

            self.smtp.send_message(msg)
            log.log(log_level.INFO, "Worker.py", f"Message Sent...")
        except Exception as err:
            log.log(log_level.ERROR, "Worker.py", f"SendMail function: {err}")
            raise #Exception(err)
            return

    def SendMultipleMail(self, from_addr, *to_addr, sub, msg_content):
        try:
            log.log(log_level.WARNING, "Worker.py", f"Doctor is trying his best to send the message...")

            for addr in to_addr:
                print("atleast doing stuff")
                msg = EmailMessage()
                msg["From"] = from_addr
                msg["To"] = addr
                msg["Subject"] = sub
                msg.set_content(msg_content)
                self.smtp.send_message(msg)
                log.log(log_level.INFO, "Worker.py", f"Message Sent... to {addr}")
        except Exception as err:
            log.log(log_level.ERROR, "Worker.py", f"SendMail function: {err}")
            raise Exception(err)
            return

    def SendMultipleMailAPI(self, from_addr, to_addr, sub, msg_content):
        try:
            for address in to_addr:
                email = EmailMessage()
                email["From"] = from_addr
                email["To"] = address
                email["Subject"] = sub
                email.set_content(msg_content)

                self.smtp.send_message(email)
                log.log(log_level.INFO, "Worker.py", f"Message Sent... to {address}")

            return True

        except Exception as err:
            log.log(
                log_level.ERROR,
                "Worker.py",
                f"SendMultipleMail function: {err}"
            )
            raise Exception(err)

    def __exit__(self, exc_type, exc, tb):
        self.smtp.quit()
        log.log(log_level.CRITICAL, "Worker.py", f"Destroying Doctor.... *bang* *bang*")
        return
        
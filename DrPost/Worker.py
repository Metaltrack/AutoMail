from smtplib import SMTP
import datetime

host_name = "smtp.gmail.com"

smtp = SMTP()
smtp.connect(host_name, 67)
smtp.login("")

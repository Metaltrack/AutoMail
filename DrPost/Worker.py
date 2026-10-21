import ssl

from smtplib import (
    SMTP_SSL,
    SMTPException
)

from email.message import EmailMessage

from logger import logger, log_level


log = logger()


class DrMail:

    def __init__(
        self,
        sender_mail: str,
        app_password: str,
        host: str = "smtp.gmail.com",
        port: int = 465,
        timeout: int = 30
    ):
        """
        Configure the mail worker.

        Important:
        The constructor DOES NOT connect to Gmail.

        This allows the FastAPI application to start even if
        Gmail is temporarily unavailable.
        """

        self.sender_mail = sender_mail
        self.app_password = app_password.replace(" ", "")

        self.host = host
        self.port = port
        self.timeout = timeout

        log.log(
            log_level.INFO,
            "Worker.py",
            "DrMail initialized"
        )


    # ---------------------------------------------------------
    # SMTP CONNECTION
    # ---------------------------------------------------------

    def connect(self):
        """
        Creates a new SMTP connection and authenticates.

        A fresh connection is created for each send operation.
        """

        if not self.app_password:
            raise RuntimeError(
                "SMTP app password is not configured."
            )

        log.log(
            log_level.INFO,
            "Worker.py",
            "Connecting to SMTP server using SSL..."
        )

        context = ssl.create_default_context()

        smtp = SMTP_SSL(
            self.host,
            self.port,
            timeout=self.timeout,
            context=context
        )

        try:

            status_code, response = smtp.ehlo()

            log.log(
                log_level.INFO,
                "Worker.py",
                f"EHLO: {status_code} | {response}"
            )


            log.log(
                log_level.INFO,
                "Worker.py",
                "Beginning SMTP authentication..."
            )


            #
            # initial_response_ok=False is intentional.
            #
            # It makes Python perform the authentication
            # challenge/response in separate SMTP commands.
            #
            smtp.login(
                self.sender_mail,
                self.app_password,
                initial_response_ok=False
            )


            log.log(
                log_level.INFO,
                "Worker.py",
                "SMTP Login Done..."
            )

            return smtp


        except Exception:

            try:
                smtp.close()

            except Exception:
                pass

            raise


    # ---------------------------------------------------------
    # CLOSE CONNECTION
    # ---------------------------------------------------------

    def disconnect(self, smtp):

        if smtp is None:
            return

        try:

            smtp.quit()

        except Exception:

            try:
                smtp.close()

            except Exception:
                pass


    # ---------------------------------------------------------
    # BUILD EMAIL
    # ---------------------------------------------------------

    def build_message(
        self,
        from_addr: str,
        to_addr: str,
        sub: str,
        msg_content: str
    ) -> EmailMessage:

        email = EmailMessage()

        email["From"] = from_addr
        email["To"] = to_addr
        email["Subject"] = sub

        email.set_content(msg_content)

        return email


    # ---------------------------------------------------------
    # SEND SINGLE EMAIL
    # ---------------------------------------------------------

    def SendMail(
        self,
        from_addr: str,
        to_addr: str,
        sub: str,
        msg_content: str
    ):

        smtp = None

        try:

            smtp = self.connect()

            log.log(
                log_level.WARNING,
                "Worker.py",
                f"Sending mail to {to_addr}..."
            )


            message = self.build_message(
                from_addr,
                to_addr,
                sub,
                msg_content
            )


            refused = smtp.send_message(
                message
            )


            if refused:

                raise SMTPException(
                    f"Recipient refused: {refused}"
                )


            log.log(
                log_level.INFO,
                "Worker.py",
                f"Message sent to {to_addr}"
            )


            return True


        except Exception as err:

            log.log(
                log_level.ERROR,
                "Worker.py",
                f"SendMail: {err}"
            )

            raise


        finally:

            self.disconnect(
                smtp
            )


    # ---------------------------------------------------------
    # SEND MULTIPLE EMAILS
    # ---------------------------------------------------------

    def SendMultipleMailAPI(
        self,
        from_addr: str,
        to_addr: list,
        sub: str,
        msg_content: str
    ):

        if not to_addr:

            raise ValueError(
                "Recipient list cannot be empty."
            )


        smtp = None

        try:

            #
            # Only ONE SMTP connection is created
            # for the entire batch.
            #
            smtp = self.connect()


            sent_count = 0


            for address in to_addr:

                address = str(
                    address
                ).strip()


                if not address:
                    continue


                message = self.build_message(
                    from_addr,
                    address,
                    sub,
                    msg_content
                )


                refused = smtp.send_message(
                    message
                )


                if refused:

                    raise SMTPException(
                        f"Recipient refused: {refused}"
                    )


                sent_count += 1


                log.log(
                    log_level.INFO,
                    "Worker.py",
                    f"Message sent to {address}"
                )


            return sent_count


        except Exception as err:

            log.log(
                log_level.ERROR,
                "Worker.py",
                f"SendMultipleMailAPI: {err}"
            )

            raise


        finally:

            self.disconnect(
                smtp
            )


    # ---------------------------------------------------------
    # OLD MULTIPLE MAIL INTERFACE
    # ---------------------------------------------------------

    def SendMultipleMail(
        self,
        from_addr,
        *to_addr,
        sub,
        msg_content
    ):

        return self.SendMultipleMailAPI(
            from_addr,
            list(to_addr),
            sub,
            msg_content
        )


    # ---------------------------------------------------------
    # SMTP HEALTH CHECK
    # ---------------------------------------------------------

    def CheckConnection(self):
        """
        Only checks whether Gmail's SMTP server is reachable.

        This DOES NOT authenticate.
        """

        smtp = None

        try:

            context = ssl.create_default_context()

            smtp = SMTP_SSL(
                self.host,
                self.port,
                timeout=10,
                context=context
            )


            status_code, response = smtp.ehlo()


            return {
                "reachable": True,
                "status_code": status_code,
                "response": response.decode(
                    errors="replace"
                )
                if isinstance(response, bytes)
                else str(response)
            }


        except Exception as err:

            return {
                "reachable": False,
                "error": str(err)
            }


        finally:

            self.disconnect(
                smtp
            )
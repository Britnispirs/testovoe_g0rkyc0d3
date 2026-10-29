import os
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional

logger = logging.getLogger(__name__)

SMTP_HOST = (os.environ.get("SMTP_HOST") or "").strip()
raw_port = (os.environ.get("SMTP_PORT") or "587").strip()
SMTP_PORT = int(raw_port) if raw_port.isdigit() else 587
SMTP_USER = (os.environ.get("SMTP_USER") or "").strip()
SMTP_PASSWORD = (os.environ.get("SMTP_PASSWORD") or "").strip()
SMTP_FROM = (os.environ.get("SMTP_FROM") or "noreply@voiceassistant.local").strip()
SMTP_USE_TLS = (os.environ.get("SMTP_USE_TLS") or "true").lower() in ("true", "1", "yes")


def send_email(to_email: str, subject: str, body_text: str, body_html: Optional[str] = None) -> bool:
    """
    Sends an email using configured SMTP settings.
    If SMTP_HOST is not configured, logs the email content to stdout/logger
    as dev/demo emulation mode.
    """
    if not SMTP_HOST:
        separator = "=" * 60
        logger.info(
            f"\n{separator}\n"
            f"[EMAIL EMULATION] Mode: Console / Dev\n"
            f"To: {to_email}\n"
            f"Subject: {subject}\n"
            f"{'-' * 60}\n"
            f"{body_text}\n"
            f"{separator}"
        )
        print(
            f"\n{separator}\n"
            f"[EMAIL EMULATION] To: {to_email} | Subject: {subject}\n"
            f"{body_text}\n"
            f"{separator}\n",
            flush=True,
        )
        return True

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = SMTP_FROM
        msg["To"] = to_email

        part_text = MIMEText(body_text, "plain", "utf-8")
        msg.attach(part_text)

        if body_html:
            part_html = MIMEText(body_html, "html", "utf-8")
            msg.attach(part_html)

        if SMTP_PORT == 465:
            with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=10) as server:
                if SMTP_USER and SMTP_PASSWORD:
                    server.login(SMTP_USER, SMTP_PASSWORD)
                server.sendmail(SMTP_FROM, [to_email], msg.as_string())
        else:
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as server:
                if SMTP_USE_TLS:
                    server.starttls()
                if SMTP_USER and SMTP_PASSWORD:
                    server.login(SMTP_USER, SMTP_PASSWORD)
                server.sendmail(SMTP_FROM, [to_email], msg.as_string())

        logger.info(f"Email successfully sent to {to_email} via SMTP ({SMTP_HOST})")
        return True
    except Exception as e:
        logger.error(f"Failed to send email to {to_email} via SMTP: {e}")
        return False


def send_welcome_email(to_email: str) -> bool:
    subject = "Добро пожаловать в Ассистент Задач и Встреч"
    text = (
        f"Здравствуйте!\n\n"
        f"Ваш аккаунт ({to_email}) успешно зарегистрирован в Голосовом Ассистенте.\n"
        f"Теперь ваши задачи, встречи и голосовые заметки надежно сохранены в личном профиле.\n\n"
        f"Приятной работы!"
    )
    html = f"""
    <html>
      <body style="font-family: Arial, sans-serif; background-color: #0d0d0d; color: #ffffff; padding: 20px;">
        <div style="max-width: 500px; margin: auto; background: #1a1a1a; padding: 24px; border-radius: 8px; border: 1px solid #333;">
          <h2 style="color: #3b82f6; margin-top: 0;">Добро пожаловать в Ассистент!</h2>
          <p>Ваш аккаунт <b>{to_email}</b> успешно зарегистрирован.</p>
          <p>Управляйте своим расписанием голосом или текстом, создавайте встречи и задачи.</p>
        </div>
      </body>
    </html>
    """
    return send_email(to_email, subject, text, html)


def send_password_reset_code(to_email: str, code: str) -> bool:
    subject = "Код для сброса пароля — Ассистент"
    text = (
        f"Здравствуйте!\n\n"
        f"Поступил запрос на сброс пароля для аккаунта {to_email}.\n"
        f"Ваш проверочный код: {code}\n\n"
        f"Код действителен в течение 15 минут. Если вы не запрашивали сброс пароля, проигнорируйте это письмо."
    )
    html = f"""
    <html>
      <body style="font-family: Arial, sans-serif; background-color: #0d0d0d; color: #ffffff; padding: 20px;">
        <div style="max-width: 500px; margin: auto; background: #1a1a1a; padding: 24px; border-radius: 8px; border: 1px solid #333;">
          <h2 style="color: #ef4444; margin-top: 0;">Сброс пароля</h2>
          <p>Для вашего аккаунта запрошен сброс пароля.</p>
          <p>Ваш одноразовый проверочный код:</p>
          <div style="font-size: 28px; font-weight: bold; letter-spacing: 4px; color: #ffffff; background: #262626; padding: 12px; text-align: center; border-radius: 6px; margin: 16px 0;">
            {code}
          </div>
          <p style="color: #888; font-size: 12px;">Код действует 15 минут. Если вы не запрашивали сброс, проигнорируйте это письмо.</p>
        </div>
      </body>
    </html>
    """
    return send_email(to_email, subject, text, html)


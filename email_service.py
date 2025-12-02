"""
Email Service - SMTP Email Sending
====================================
Simple email service for sending:
- Welcome emails
- Password reset links
- Trade notifications
- Security alerts
"""

import os
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

logger = logging.getLogger(__name__)


class EmailService:
    """Simple SMTP email service."""

    def __init__(self):
        self.smtp_server = os.environ.get('SMTP_SERVER', 'smtp.gmail.com')
        self.smtp_port = int(os.environ.get('SMTP_PORT', 587))
        self.smtp_username = os.environ.get('SMTP_USERNAME')
        self.smtp_password = os.environ.get('SMTP_PASSWORD')
        self.email_from = os.environ.get('EMAIL_FROM', 'Trading Bot <noreply@tradingbot.com>')
        self.frontend_url = os.environ.get('FRONTEND_URL', 'http://localhost:5000')

        logger.info("EmailService initialized")

    def send_email(self, to_email, subject, html_body, text_body=None):
        """Send email via SMTP."""
        if not self.smtp_username or not self.smtp_password:
            logger.warning("SMTP credentials not configured, skipping email")
            return False

        try:
            msg = MIMEMultipart('alternative')
            msg['From'] = self.email_from
            msg['To'] = to_email
            msg['Subject'] = subject

            # Add text and HTML parts
            if text_body:
                msg.attach(MIMEText(text_body, 'plain'))
            msg.attach(MIMEText(html_body, 'html'))

            # Send email
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_username, self.smtp_password)
                server.send_message(msg)

            logger.info(f"Email sent to {to_email}: {subject}")
            return True

        except Exception as e:
            logger.error(f"Failed to send email: {e}")
            return False

    def send_welcome_email(self, to_email, full_name, verification_token):
        """Send welcome email with verification link."""
        subject = "Welcome to Trading Bot Pro!"

        html_body = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6;">
            <h2>Welcome to Trading Bot Pro, {full_name}!</h2>
            <p>Thank you for registering. Please verify your email address:</p>
            <p>
                <a href="{self.frontend_url}/verify-email/{verification_token}"
                   style="background: #6366F1; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px; display: inline-block;">
                    Verify Email
                </a>
            </p>
            <p>Or copy this link: {self.frontend_url}/verify-email/{verification_token}</p>
            <p>Best regards,<br>Trading Bot Pro Team</p>
        </body>
        </html>
        """

        return self.send_email(to_email, subject, html_body)

    def send_password_reset_email(self, to_email, full_name, reset_token):
        """Send password reset email."""
        subject = "Reset Your Password - Trading Bot Pro"

        html_body = f"""
        <html>
        <body style="font-family: Arial, sans-serif;">
            <h2>Password Reset Request</h2>
            <p>Hi {full_name},</p>
            <p>Click the link below to reset your password:</p>
            <p>
                <a href="{self.frontend_url}/reset-password/{reset_token}"
                   style="background: #6366F1; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px;">
                    Reset Password
                </a>
            </p>
            <p>Link expires in 1 hour.</p>
            <p>If you didn't request this, please ignore this email.</p>
        </body>
        </html>
        """

        return self.send_email(to_email, subject, html_body)

    def send_trade_notification(self, to_email, trade_data):
        """Send trade notification email."""
        subject = f"Trade Executed: {trade_data.get('symbol', 'Unknown')}"

        html_body = f"""
        <html>
        <body style="font-family: Arial, sans-serif;">
            <h2>Trade Notification</h2>
            <p><strong>Symbol:</strong> {trade_data.get('symbol')}</p>
            <p><strong>Type:</strong> {trade_data.get('type')}</p>
            <p><strong>Price:</strong> {trade_data.get('price')}</p>
            <p><strong>Quantity:</strong> {trade_data.get('quantity')}</p>
            <p><strong>Time:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        </body>
        </html>
        """

        return self.send_email(to_email, subject, html_body)


# Global instance
email_service = EmailService()

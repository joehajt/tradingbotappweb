"""
Notification Service - Trade Notifications via Telegram & Email
================================================================
Sends notifications for:
- Position opened/closed
- Take Profit hit
- Stop Loss hit
"""

import logging
from datetime import datetime
from email_service import EmailService

logger = logging.getLogger(__name__)


class NotificationService:
    """Service for sending trade notifications via Telegram and Email."""

    def __init__(self, email_service=None):
        self.email_service = email_service or EmailService()
        logger.info("NotificationService initialized")

    def format_position_notification(self, event_type, symbol, side, leverage, quantity,
                                     entry_price, opened_at, closed_at=None,
                                     exit_price=None, pnl=None, reason=None):
        """
        Format notification message for position events.

        Args:
            event_type: 'open', 'close', 'tp', 'sl'
            symbol: e.g. 'BTCUSDT'
            side: 'Buy' or 'Sell'
            leverage: e.g. 10
            quantity: position size
            entry_price: entry price
            opened_at: datetime of opening
            closed_at: datetime of closing (optional)
            exit_price: exit price (optional)
            pnl: profit/loss (optional)
            reason: close reason (optional)
        """

        # Emoji mapping
        emoji_map = {
            'open': '🟢',
            'close': '🔴',
            'tp': '✅',
            'sl': '❌'
        }

        emoji = emoji_map.get(event_type, '📊')

        # Format datetime
        open_time = opened_at.strftime('%Y-%m-%d %H:%M:%S') if isinstance(opened_at, datetime) else opened_at

        # Build message based on event type
        if event_type == 'open':
            title = f"{emoji} POZYCJA OTWARTA"
            message = f"""
{title}

📊 Para: {symbol}
📈 Kierunek: {side}
⚡ Lewar: {leverage}x
💰 Kwota: {quantity}
💵 Cena wejścia: {entry_price}
🕐 Godzina otwarcia: {open_time}
"""

        elif event_type in ['close', 'tp', 'sl']:
            close_time = closed_at.strftime('%Y-%m-%d %H:%M:%S') if isinstance(closed_at, datetime) else closed_at

            if event_type == 'tp':
                title = f"{emoji} TAKE PROFIT OSIĄGNIĘTY"
            elif event_type == 'sl':
                title = f"{emoji} STOP LOSS OSIĄGNIĘTY"
            else:
                title = f"{emoji} POZYCJA ZAMKNIĘTA"

            pnl_emoji = '💚' if pnl and pnl > 0 else '💔'
            pnl_text = f"{pnl_emoji} PNL: {pnl:.2f} USDT" if pnl is not None else ""
            reason_text = f"📝 Powód: {reason}" if reason else ""

            message = f"""
{title}

📊 Para: {symbol}
📈 Kierunek: {side}
⚡ Lewar: {leverage}x
💰 Kwota: {quantity}
💵 Cena wejścia: {entry_price}
💵 Cena wyjścia: {exit_price}
🕐 Godzina otwarcia: {open_time}
🕐 Godzina zamknięcia: {close_time}
{pnl_text}
{reason_text}
"""

        return message.strip()

    async def send_telegram_notification(self, bot, message):
        """Send notification via Telegram."""
        try:
            if hasattr(bot, 'send_telegram_message'):
                await bot.send_telegram_message(message)
                logger.info("Telegram notification sent")
                return True
        except Exception as e:
            logger.error(f"Error sending Telegram notification: {e}")
            return False

    def send_email_notification(self, user_email, subject, message):
        """Send notification via Email."""
        try:
            if not user_email:
                logger.warning("No email provided, skipping email notification")
                return False

            # Convert plain text message to HTML
            html_body = f"""
            <html>
            <body style="font-family: Arial, sans-serif; background-color: #f4f4f4; padding: 20px;">
                <div style="max-width: 600px; margin: 0 auto; background: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
                    <h2 style="color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 10px;">
                        {subject}
                    </h2>
                    <pre style="background: #ecf0f1; padding: 20px; border-radius: 5px; font-family: monospace; white-space: pre-wrap; word-wrap: break-word;">
{message}
                    </pre>
                    <div style="margin-top: 30px; padding-top: 20px; border-top: 1px solid #ecf0f1; text-align: center; color: #7f8c8d; font-size: 12px;">
                        <p>Trading Bot - Automated Notifications</p>
                        <p>Czas wysłania: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
                    </div>
                </div>
            </body>
            </html>
            """

            result = self.email_service.send_email(user_email, subject, html_body)
            if result:
                logger.info(f"Email notification sent to {user_email}")
            return result
        except Exception as e:
            logger.error(f"Error sending email notification: {e}")
            return False

    async def notify_position_opened(self, bot, user_email, symbol, side, leverage,
                                     quantity, entry_price, opened_at,
                                     telegram_enabled=True, email_enabled=True):
        """Send notification when position is opened."""
        message = self.format_position_notification(
            event_type='open',
            symbol=symbol,
            side=side,
            leverage=leverage,
            quantity=quantity,
            entry_price=entry_price,
            opened_at=opened_at
        )

        subject = f"🟢 Pozycja otwarta - {symbol}"

        # Send via Telegram
        if telegram_enabled:
            await self.send_telegram_notification(bot, message)

        # Send via Email
        if email_enabled:
            self.send_email_notification(user_email, subject, message)

    async def notify_position_closed(self, bot, user_email, symbol, side, leverage,
                                     quantity, entry_price, exit_price, opened_at,
                                     closed_at, pnl=None, reason=None, event_type='close',
                                     telegram_enabled=True, email_enabled=True):
        """Send notification when position is closed, TP hit, or SL hit."""
        message = self.format_position_notification(
            event_type=event_type,  # 'close', 'tp', or 'sl'
            symbol=symbol,
            side=side,
            leverage=leverage,
            quantity=quantity,
            entry_price=entry_price,
            opened_at=opened_at,
            closed_at=closed_at,
            exit_price=exit_price,
            pnl=pnl,
            reason=reason
        )

        # Subject based on event type
        if event_type == 'tp':
            subject = f"✅ Take Profit osiągnięty - {symbol}"
        elif event_type == 'sl':
            subject = f"❌ Stop Loss osiągnięty - {symbol}"
        else:
            subject = f"🔴 Pozycja zamknięta - {symbol}"

        # Send via Telegram
        if telegram_enabled:
            await self.send_telegram_notification(bot, message)

        # Send via Email
        if email_enabled:
            self.send_email_notification(user_email, subject, message)

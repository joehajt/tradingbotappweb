"""
Enhanced Risk Manager Module
Handles risk management including daily/weekly loss limits, margin monitoring, and cooling periods
"""

import os
import json
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# Risk tracking file path
RISK_TRACKING_FILE = "risk_tracking.json"


class EnhancedRiskManager:
    """ENHANCED Risk Management with margin level tracking"""

    def __init__(self, ws_logger=None):
        self.tracking_file = RISK_TRACKING_FILE
        self.ws_logger = ws_logger  # Optional WebSocket logger for real-time updates
        self.load_tracking()

    def load_tracking(self):
        """Wczytaj dane śledzenia ryzyka"""
        try:
            if os.path.exists(self.tracking_file):
                with open(self.tracking_file, 'r', encoding='utf-8') as f:
                    self.tracking = json.load(f)
            else:
                self.tracking = {
                    'daily_losses': {},
                    'weekly_losses': {},
                    'consecutive_losses': 0,
                    'total_trades_today': 0,
                    'last_trade_date': None,
                    'cooling_until': None,
                    'trade_history': [],
                    'margin_alerts': [],  # NEW
                    'last_margin_check': None  # NEW
                }
                self.save_tracking()
        except Exception as e:
            logger.error(f"❌ Błąd wczytywania tracking: {e}")
            self.tracking = {
                'daily_losses': {},
                'weekly_losses': {},
                'consecutive_losses': 0,
                'total_trades_today': 0,
                'last_trade_date': None,
                'cooling_until': None,
                'trade_history': [],
                'margin_alerts': [],
                'last_margin_check': None
            }

    def save_tracking(self):
        """Zapisz dane śledzenia ryzyka"""
        try:
            with open(self.tracking_file, 'w', encoding='utf-8') as f:
                json.dump(self.tracking, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            logger.error(f"❌ Błąd zapisu tracking: {e}")
            return False

    def check_margin_level(self, balance_info, min_margin_level=1.5):
        """NEW: Check margin level to prevent liquidation"""
        try:
            if not balance_info:
                return False, "No balance info"

            total_wallet = balance_info.get('totalWalletBalance', 0)
            total_margin = balance_info.get('totalMarginBalance', 0)
            available_balance = balance_info.get('totalAvailableBalance', 0)

            # Calculate margin level
            if total_margin > 0:
                margin_level = total_wallet / total_margin
            else:
                margin_level = 999  # No positions

            # Update tracking
            self.tracking['last_margin_check'] = {
                'timestamp': datetime.now().isoformat(),
                'margin_level': margin_level,
                'total_wallet': total_wallet,
                'total_margin': total_margin
            }

            # Check if margin level is safe
            if margin_level < min_margin_level:
                alert_msg = f"⚠️ LOW MARGIN LEVEL: {margin_level:.2f} (Min: {min_margin_level})"
                if self.ws_logger:
                    self.ws_logger.log(alert_msg, 'error')
                else:
                    logger.error(alert_msg)

                # Add to alerts
                self.tracking['margin_alerts'].append({
                    'timestamp': datetime.now().isoformat(),
                    'margin_level': margin_level,
                    'message': alert_msg
                })

                # Keep only last 100 alerts
                if len(self.tracking['margin_alerts']) > 100:
                    self.tracking['margin_alerts'] = self.tracking['margin_alerts'][-100:]

                self.save_tracking()
                return False, f"Margin level too low: {margin_level:.2f}"

            return True, f"Margin level safe: {margin_level:.2f}"

        except Exception as e:
            msg = f"❌ Error checking margin level: {e}"
            if self.ws_logger:
                self.ws_logger.log(msg, 'error')
            else:
                logger.error(msg)
            return False, str(e)

    def can_trade(self, daily_limit, weekly_limit, max_consecutive_losses, balance_info=None, min_margin_level=1.5):
        """ENHANCED: Check if trading is allowed based on risk limits and margin"""
        today = datetime.now().strftime('%Y-%m-%d')
        week = datetime.now().strftime('%Y-W%U')

        # NEW: Check margin level first
        if balance_info:
            margin_safe, margin_msg = self.check_margin_level(balance_info, min_margin_level)
            if not margin_safe:
                msg = f"🛑 Trading blocked: {margin_msg}"
                if self.ws_logger:
                    self.ws_logger.log(msg, 'error')
                else:
                    logger.error(msg)
                return False, f"Margin protection: {margin_msg}"

        # Check cooling period
        if self.tracking.get('cooling_until'):
            cooling_until = datetime.fromisoformat(self.tracking['cooling_until'])
            if datetime.now() < cooling_until:
                remaining = (cooling_until - datetime.now()).total_seconds() / 60
                msg = f"❄️ Cooling period aktywny jeszcze przez {remaining:.0f} minut"
                if self.ws_logger:
                    self.ws_logger.log(msg, 'warning')
                else:
                    logger.warning(msg)
                return False, f"Cooling period aktywny jeszcze przez {remaining:.0f} minut"

        # Check daily loss limit
        daily_loss = self.tracking['daily_losses'].get(today, 0)
        if abs(daily_loss) >= daily_limit:
            msg = f"🛑 Osiągnięto dzienny limit strat: ${abs(daily_loss):.2f} / ${daily_limit:.2f}"
            if self.ws_logger:
                self.ws_logger.log(msg, 'error')
            else:
                logger.error(msg)
            return False, f"Osiągnięto dzienny limit strat: ${abs(daily_loss):.2f}"

        # Check weekly loss limit
        weekly_loss = self.tracking['weekly_losses'].get(week, 0)
        if abs(weekly_loss) >= weekly_limit:
            msg = f"🛑 Osiągnięto tygodniowy limit strat: ${abs(weekly_loss):.2f} / ${weekly_limit:.2f}"
            if self.ws_logger:
                self.ws_logger.log(msg, 'error')
            else:
                logger.error(msg)
            return False, f"Osiągnięto tygodniowy limit strat: ${abs(weekly_loss):.2f}"

        # Check consecutive losses
        if self.tracking['consecutive_losses'] >= max_consecutive_losses:
            msg = f"🛑 Zbyt wiele strat z rzędu: {self.tracking['consecutive_losses']}"
            if self.ws_logger:
                self.ws_logger.log(msg, 'error')
            else:
                logger.error(msg)
            # Set cooling period for 1 hour
            self.tracking['cooling_until'] = (datetime.now() + timedelta(hours=1)).isoformat()
            self.save_tracking()
            return False, f"Zbyt wiele strat z rzędu ({self.tracking['consecutive_losses']}). Cooling period 1h."

        return True, "OK"

    def record_trade(self, profit_loss, symbol):
        """Zapisz wynik transakcji"""
        today = datetime.now().strftime('%Y-%m-%d')
        week = datetime.now().strftime('%Y-W%U')

        # Update daily losses
        if today not in self.tracking['daily_losses']:
            self.tracking['daily_losses'][today] = 0
        self.tracking['daily_losses'][today] += profit_loss

        # Update weekly losses
        if week not in self.tracking['weekly_losses']:
            self.tracking['weekly_losses'][week] = 0
        self.tracking['weekly_losses'][week] += profit_loss

        # Update consecutive losses
        if profit_loss < 0:
            self.tracking['consecutive_losses'] += 1
        else:
            self.tracking['consecutive_losses'] = 0

        # Add to history
        self.tracking['trade_history'].append({
            'timestamp': datetime.now().isoformat(),
            'symbol': symbol,
            'profit_loss': profit_loss,
            'consecutive_losses': self.tracking['consecutive_losses']
        })

        # Keep only last 100 trades
        if len(self.tracking['trade_history']) > 100:
            self.tracking['trade_history'] = self.tracking['trade_history'][-100:]

        self.tracking['last_trade_date'] = today
        self.tracking['total_trades_today'] = len([t for t in self.tracking['trade_history']
                                                    if t['timestamp'].startswith(today)])

        self.save_tracking()

        # Log status
        if self.ws_logger:
            self.ws_logger.log(f"📊 Trade recorded: {symbol} P/L: ${profit_loss:.2f}", 'info')
            self.ws_logger.log(f"📈 Daily P/L: ${self.tracking['daily_losses'][today]:.2f}", 'info')
            self.ws_logger.log(f"📅 Weekly P/L: ${self.tracking['weekly_losses'][week]:.2f}", 'info')
        else:
            logger.info(f"📊 Trade recorded: {symbol} P/L: ${profit_loss:.2f}")
            logger.info(f"📈 Daily P/L: ${self.tracking['daily_losses'][today]:.2f}")
            logger.info(f"📅 Weekly P/L: ${self.tracking['weekly_losses'][week]:.2f}")

        return True

    def get_stats(self):
        """Get enhanced risk statistics"""
        today = datetime.now().strftime('%Y-%m-%d')
        week = datetime.now().strftime('%Y-W%U')

        stats = {
            'daily_loss': self.tracking['daily_losses'].get(today, 0),
            'weekly_loss': self.tracking['weekly_losses'].get(week, 0),
            'consecutive_losses': self.tracking['consecutive_losses'],
            'total_trades_today': self.tracking['total_trades_today'],
            'cooling_until': self.tracking.get('cooling_until'),
            'last_trade': self.tracking.get('last_trade_date'),
            'last_margin_check': self.tracking.get('last_margin_check', {}),
            'recent_margin_alerts': self.tracking.get('margin_alerts', [])[-5:]  # Last 5 alerts
        }

        return stats

    def reset_daily_limits(self):
        """Reset daily limits (to be called at midnight)"""
        # Remove old days (older than 7 days)
        cutoff_date = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
        self.tracking['daily_losses'] = {
            date: loss for date, loss in self.tracking['daily_losses'].items()
            if date >= cutoff_date
        }
        self.save_tracking()

    def reset_weekly_limits(self):
        """Reset weekly limits"""
        # Remove old weeks (older than 4 weeks)
        current_week = int(datetime.now().strftime('%U'))
        current_year = int(datetime.now().strftime('%Y'))

        self.tracking['weekly_losses'] = {
            week: loss for week, loss in self.tracking['weekly_losses'].items()
            if self._parse_week(week)[0] == current_year and
               abs(self._parse_week(week)[1] - current_week) < 4
        }
        self.save_tracking()

    def _parse_week(self, week_str):
        """Parse week string format YYYY-WNN"""
        parts = week_str.split('-W')
        return int(parts[0]), int(parts[1])

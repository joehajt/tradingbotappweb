"""
Signal Parser Module

This module provides functions for parsing and analyzing trading signals from text.
Handles extraction of trading parameters (symbol, position type, entry price, targets, stop loss)
and provides risk/reward analysis.
"""

import re
import json
import logging

# Configure logging for this module
logger = logging.getLogger(__name__)


def parse_trading_signal(text):
    """
    Recognize and parse trading signal from text.

    Extracts trading parameters from signal text:
    - Symbol (e.g., BTCUSDT)
    - Position type (LONG/SHORT)
    - Entry price
    - Targets with numbers
    - Stop loss

    Args:
        text (str): Raw signal text to parse

    Returns:
        dict or None: Dictionary with keys:
            - symbol: Trading pair (str)
            - position_type: 'long' or 'short' (str)
            - entry_price: Entry price (float)
            - targets: Dict mapping target number to price (dict)
            - stop_loss: Stop loss price or None (float or None)
        Returns None if required elements are missing
    """
    try:
        logger.info("🔍 Analyzing text for signal...")

        # Remove emojis that might interfere
        text_clean = re.sub(r'[^\w\s\-\.\:,/@#]', ' ', text)
        text_clean = ' '.join(text_clean.split())

        # Regex patterns
        symbol_pattern = r'#?([A-Z0-9]+USDT?)\b'
        # Priority 1: Look for position type directly with Entry Zone (e.g., "Short Entry Zone")
        entry_with_position_pattern = r'\b(LONG|SHORT|Long|Short|long|short)\s+(?:Entry|entry|ENTRY)\s+(?:Zone|zone|ZONE)'
        # Priority 2: Look for position type, but exclude "-Term" context (avoid "Long-Term", "Short-Term")
        position_pattern = r'\b(LONG|SHORT|Long|Short|long|short)(?!\s*-\s*[Tt]erm)\b'
        entry_pattern = r'(?:Entry|entry|Wejście|ENTRY|Zone|zone|ZONE)[\s:]*([0-9]+\.?[0-9]*(?:\s*-\s*[0-9]+\.?[0-9]*)?)'
        target_pattern = r'(?:Target|target|TARGET|TP|tp|Cel|cel|CEL)[\s#]*(\d+)[\s:]*([0-9]+\.?[0-9]*)'
        sl_pattern = r'(?:Stop[\s-]?Loss|stop[\s-]?loss|SL|sl|STOP[\s-]?LOSS|Stop|stop|STOP)[\s:]*([0-9]+\.?[0-9]*)'

        # Find elements
        symbol_match = re.search(symbol_pattern, text_clean)
        # First try to find position type with Entry Zone
        entry_with_position_match = re.search(entry_with_position_pattern, text_clean)
        if entry_with_position_match:
            position_match = entry_with_position_match  # Use position from "Short/Long Entry Zone"
        else:
            position_match = re.search(position_pattern, text_clean)  # Fallback to general pattern
        entry_match = re.search(entry_pattern, text_clean)
        target_matches = re.findall(target_pattern, text_clean)
        sl_match = re.search(sl_pattern, text_clean)

        # Log found elements
        logger.info(f"📊 Symbol: {symbol_match.group(1) if symbol_match else 'Not found'}")
        logger.info(f"📈 Position: {position_match.group(1) if position_match else 'Not found'}")
        logger.info(f"💰 Entry: {entry_match.group(1) if entry_match else 'Not found'}")
        logger.info(f"🎯 Targets: {len(target_matches)} found")
        logger.info(f"🛑 Stop Loss: {sl_match.group(1) if sl_match else 'Not found'}")

        # Check if we have minimum required data
        if not symbol_match or not position_match or not entry_match:
            logger.error("❌ Missing required signal elements")
            return None

        # Prepare signal data
        symbol = symbol_match.group(1).upper()
        if not symbol.endswith('USDT'):
            symbol += 'USDT'

        position_type = position_match.group(1).lower()

        # Parse entry price
        entry_str = entry_match.group(1)
        if '-' in entry_str:
            # Price range - take average
            prices = [float(p.strip()) for p in entry_str.split('-')]
            entry_price = sum(prices) / len(prices)
            logger.info(f"📊 Entry range {prices[0]} - {prices[1]}, using average: {entry_price}")
        else:
            entry_price = float(entry_str)

        # Parse targets
        targets = {}
        for target_num, target_price in target_matches:
            targets[int(target_num)] = float(target_price)

        # Parse stop loss
        stop_loss = float(sl_match.group(1)) if sl_match else None

        # Basic validation
        if entry_price <= 0:
            logger.error("❌ Invalid entry price")
            return None

        # Create signal object
        signal = {
            'symbol': symbol,
            'position_type': position_type,
            'entry_price': entry_price,
            'targets': targets,
            'stop_loss': stop_loss
        }

        logger.info("✅ Signal recognized successfully!")
        logger.info(f"📋 {json.dumps(signal, indent=2)}")

        return signal

    except Exception as e:
        logger.error(f"❌ Error parsing signal: {e}")
        return None


def analyze_trading_signal(signal, auto_tp_sl=False, auto_breakeven=False, breakeven_after_target=None):
    """
    Analyze trading signal and calculate risk/reward metrics.

    Provides detailed analysis including:
    - Risk percentage to stop loss
    - Reward percentage for each target
    - Risk/Reward ratio for each target
    - Position management recommendations

    Args:
        signal (dict): Signal dictionary from parse_trading_signal() with keys:
            - symbol (str)
            - position_type (str): 'long' or 'short'
            - entry_price (float)
            - targets (dict): {target_number: price}
            - stop_loss (float or None)
        auto_tp_sl (bool): Whether automatic TP/SL is enabled (default: False)
        auto_breakeven (bool): Whether automatic breakeven is enabled (default: False)
        breakeven_after_target (int or None): Target number for breakeven activation

    Returns:
        str: Formatted analysis text with risk/reward calculations and recommendations
    """
    try:
        analysis = []

        # Basic analysis
        analysis.append(f"\n📊 SIGNAL ANALYSIS:")
        analysis.append(f"{'=' * 40}")

        # Risk/Reward if SL exists
        if signal['stop_loss']:
            entry = signal['entry_price']
            sl = signal['stop_loss']

            if signal['position_type'] == 'long':
                risk_percent = ((entry - sl) / entry) * 100
                analysis.append(f"📉 Risk (to SL): {risk_percent:.2f}%")

                for target_num, target_price in sorted(signal['targets'].items()):
                    reward_percent = ((target_price - entry) / entry) * 100
                    rr_ratio = reward_percent / risk_percent if risk_percent > 0 else 0
                    analysis.append(f"🎯 Target {target_num}: +{reward_percent:.2f}% (R:R = 1:{rr_ratio:.1f})")
            else:  # short
                risk_percent = ((sl - entry) / entry) * 100
                analysis.append(f"📉 Risk (to SL): {risk_percent:.2f}%")

                for target_num, target_price in sorted(signal['targets'].items()):
                    reward_percent = ((entry - target_price) / entry) * 100
                    rr_ratio = reward_percent / risk_percent if risk_percent > 0 else 0
                    analysis.append(f"🎯 Target {target_num}: +{reward_percent:.2f}% (R:R = 1:{rr_ratio:.1f})")
        else:
            # Without SL - just percentages to targets
            entry = signal['entry_price']

            for target_num, target_price in sorted(signal['targets'].items()):
                if signal['position_type'] == 'long':
                    reward_percent = ((target_price - entry) / entry) * 100
                    analysis.append(f"🎯 Target {target_num}: +{reward_percent:.2f}%")
                else:
                    reward_percent = ((entry - target_price) / entry) * 100
                    analysis.append(f"🎯 Target {target_num}: +{reward_percent:.2f}%")

        # Position management info
        analysis.append(f"\n💡 POSITION MANAGEMENT:")
        analysis.append(f"• Position size: According to settings")
        if auto_tp_sl:
            analysis.append(f"• TP/SL: Automatic setup ✅")
        if auto_breakeven and breakeven_after_target:
            analysis.append(f"• Breakeven: After reaching TP{breakeven_after_target} ✅")

        return '\n'.join(analysis)

    except Exception as e:
        logger.error(f"❌ Error analyzing signal: {e}")
        return "❌ Signal analysis error"

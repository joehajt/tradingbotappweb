"""
PositionManager Module - Enhanced Position Management with Customizable Breakeven Targets

This module provides the PositionManager class for managing trading positions,
including take profit and stop loss orders, with customizable breakeven activation.
"""

import time
import asyncio
import threading
from datetime import datetime

# Note: The following global variables are expected to be injected from the main app:
# - ws_logger: WebSocketLogger instance for logging
# - socketio: SocketIO instance for real-time communications
# These are imported from the parent application context


class PositionManager:
    """ENHANCED Position Management with customizable breakeven targets"""

    def __init__(self, bot):
        self.bot = bot
        self.active_positions = {}  # Symbol -> position info
        self.monitoring_active = False
        self.monitor_thread = None

    def add_position(self, symbol, signal, order_id):
        """Add position to monitoring"""
        try:
            position_info = {
                'symbol': symbol,
                'signal': signal,
                'order_id': order_id,
                'entry_price': signal['entry_price'],
                'position_type': signal['position_type'],
                'targets': signal.get('targets', {}),
                'stop_loss': signal.get('stop_loss'),
                'filled_targets': set(),
                'sl_moved_to_breakeven': False,
                'created_at': datetime.now(),
                'tp_orders': {},
                'sl_order_id': None,
                'last_price_check': None,
                'target_check_count': 0,
                'breakeven_target': self.bot.breakeven_after_target  # Configurable target
            }

            self.active_positions[symbol] = position_info
            ws_logger.log(f"✅ Position {symbol} added to monitoring", 'success')
            ws_logger.log(f"💡 Breakeven will be activated after TP{self.bot.breakeven_after_target}", 'info')

            # Emit position update via Socket.IO
            socketio.emit('message', {
                'type': 'position',
                'action': 'added',
                'position': self._position_to_dict(position_info)
            })

            # Auto setup TP and SL with delay
            time.sleep(2)  # Wait 2 seconds
            self.setup_tp_sl_orders(symbol)

            return True
        except Exception as e:
            ws_logger.log(f"❌ Error adding position to monitoring: {e}", 'error')
            return False

    def _position_to_dict(self, position_info):
        """Convert position info to dictionary for Socket.IO"""
        return {
            'symbol': position_info['symbol'],
            'type': position_info['position_type'],
            'entry': position_info['entry_price'],
            'targets': f"{len(position_info['filled_targets'])}/{len(position_info['targets'])}",
            'sl_breakeven': position_info['sl_moved_to_breakeven'],
            'created': position_info['created_at'].strftime('%H:%M:%S'),
            'last_price': position_info.get('last_price_check', 'Unknown'),
            'checks': position_info.get('target_check_count', 0),
            'breakeven_trigger': f"TP{position_info.get('breakeven_target', 1)}"
        }

    def check_target_reached_by_price(self, symbol):
        """Check if targets have been reached based on current price"""
        try:
            if symbol not in self.active_positions:
                return False

            position = self.active_positions[symbol]
            targets = position.get('targets', {})
            filled_targets = position.get('filled_targets', set())
            position_type = position['position_type'].lower()
            entry_price = position['entry_price']
            breakeven_target = position.get('breakeven_target', 1)

            if not targets:
                return False

            # Get current price
            current_price = self.get_current_price(symbol)
            if not current_price:
                ws_logger.log(f"⚠️ Cannot get current price for {symbol}", 'warning')
                return False

            # Update price check info
            position['last_price_check'] = current_price
            position['target_check_count'] += 1

            ws_logger.log(f"💹 Checking targets for {symbol}:")
            ws_logger.log(f"   📊 Position: {position_type.upper()}")
            ws_logger.log(f"   💰 Entry: {entry_price}")
            ws_logger.log(f"   💹 Current price: {current_price}")
            ws_logger.log(f"   🎯 Check #{position['target_check_count']}")

            newly_filled = []

            # Check each target
            for target_num, target_price in sorted(targets.items()):
                if target_num in filled_targets:
                    continue  # Target already reached

                # Check if target reached based on position type
                target_reached = False

                if position_type == "long":
                    # For LONG: target reached when price >= target_price
                    if current_price >= target_price:
                        target_reached = True
                        ws_logger.log(f"🎯 LONG TP{target_num} REACHED! Price {current_price} >= Target {target_price}", 'success')
                elif position_type == "short":
                    # For SHORT: target reached when price <= target_price
                    if current_price <= target_price:
                        target_reached = True
                        ws_logger.log(f"🎯 SHORT TP{target_num} REACHED! Price {current_price} <= Target {target_price}", 'success')

                if target_reached:
                    filled_targets.add(target_num)
                    newly_filled.append(target_num)
                    ws_logger.log(f"✅ Target {target_num} added to reached for {symbol}", 'success')
                else:
                    if position_type == "long":
                        distance = ((target_price - current_price) / current_price) * 100
                        ws_logger.log(f"⏳ TP{target_num}: Need +{distance:.2f}% to {target_price}")
                    else:
                        distance = ((current_price - target_price) / current_price) * 100
                        ws_logger.log(f"⏳ TP{target_num}: Need -{distance:.2f}% to {target_price}")

            # If new targets reached
            if newly_filled:
                ws_logger.log(f"🎉 NEW TARGETS REACHED for {symbol}: {newly_filled}", 'success')

                # Emit position update via Socket.IO
                socketio.emit('message', {
                    'type': 'position',
                    'action': 'targets_hit',
                    'symbol': symbol,
                    'targets': newly_filled,
                    'current_price': current_price
                })

                # Check if breakeven target is reached
                if breakeven_target in newly_filled and not position['sl_moved_to_breakeven'] and self.bot.auto_breakeven:
                    ws_logger.log(f"💡 Target {breakeven_target} reached for {symbol} - initiating breakeven", 'info')
                    breakeven_success = self.move_sl_to_breakeven(symbol)
                    if breakeven_success:
                        ws_logger.log(f"🎉 BREAKEVEN ACTIVATED for {symbol} after TP{breakeven_target}!", 'success')
                    else:
                        ws_logger.log(f"❌ Error activating breakeven for {symbol}", 'error')

                return True

            return False

        except Exception as e:
            ws_logger.log(f"❌ Error checking targets for {symbol}: {e}", 'error')
            return False

    def move_sl_to_breakeven(self, symbol):
        """Move SL to breakeven point"""
        try:
            if symbol not in self.active_positions:
                ws_logger.log(f"❌ Position {symbol} not in monitoring", 'error')
                return False

            position = self.active_positions[symbol]

            if position['sl_moved_to_breakeven']:
                ws_logger.log(f"ℹ️ SL already moved to breakeven for {symbol}")
                return True

            entry_price = position['entry_price']
            position_type = position['position_type'].lower()

            ws_logger.log(f"💡 Moving SL to breakeven for {symbol}")
            ws_logger.log(f"   📊 Position: {position_type.upper()}")
            ws_logger.log(f"   💰 Entry price (breakeven): {entry_price}")

            # STEP 1: Cancel old SL if exists
            if position['sl_order_id']:
                ws_logger.log(f"🗑️ Canceling old SL: {position['sl_order_id']}")
                cancel_success = self.cancel_sl_order(symbol, position['sl_order_id'])
                if cancel_success:
                    ws_logger.log(f"✅ Old SL canceled for {symbol}", 'success')
                else:
                    ws_logger.log(f"⚠️ Failed to cancel old SL for {symbol}, continuing...", 'warning')

                # Clear old SL ID
                position['sl_order_id'] = None

            # STEP 2: Set new SL at breakeven level
            ws_logger.log(f"📤 Setting new SL at breakeven: {entry_price}")
            success = self.set_stop_loss(symbol, entry_price)

            if success:
                position['sl_moved_to_breakeven'] = True
                ws_logger.log(f"🎉 SUCCESS! SL moved to breakeven for {symbol} at level {entry_price}", 'success')

                # Emit position update via Socket.IO
                socketio.emit('message', {
                    'type': 'position',
                    'action': 'breakeven',
                    'symbol': symbol,
                    'entry_price': entry_price
                })

                # Send Telegram notification
                if hasattr(self.bot, 'telegram_bot') and self.bot.telegram_bot and self.bot.telegram_chat_id:
                    try:
                        message = (
                            f"💡 BREAKEVEN ACTIVATED!\n"
                            f"📊 Symbol: {symbol}\n"
                            f"📈 Position: {position_type.upper()}\n"
                            f"🎯 Target {position.get('breakeven_target', 1)} reached!\n"
                            f"🛡️ Stop Loss moved to breakeven: {entry_price}\n"
                            f"✅ Position is now safe!"
                        )

                        # Run in new event loop
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                        loop.run_until_complete(self.bot.send_telegram_message(message))
                        loop.close()

                        ws_logger.log(f"📱 Breakeven notification sent for {symbol}", 'success')
                    except Exception as e:
                        ws_logger.log(f"⚠️ Failed to send breakeven notification: {e}", 'warning')

                return True
            else:
                ws_logger.log(f"❌ ERROR! Failed to set new SL at breakeven for {symbol}", 'error')
                return False

        except Exception as e:
            ws_logger.log(f"❌ Error moving SL to breakeven for {symbol}: {e}", 'error')
            return False

    def setup_tp_sl_orders(self, symbol):
        """Setup TP and SL orders for position"""
        try:
            if symbol not in self.active_positions:
                ws_logger.log(f"❌ Position {symbol} not in monitoring", 'error')
                return False

            position = self.active_positions[symbol]
            signal = position.get('signal', {})

            ws_logger.log(f"🔧 Setting up TP/SL for {symbol}...")

            # Check if position actually exists
            current_size = self.get_current_position_size(symbol)
            if current_size <= 0:
                ws_logger.log(f"❌ No active position for {symbol} - cannot set TP/SL", 'error')
                return False

            success_count = 0
            total_orders = 0

            # Set Take Profit orders
            targets = signal.get('targets', {})
            if targets:
                ws_logger.log(f"🎯 Setting {len(targets)} targets for {symbol}")

                # Sort targets by number
                sorted_targets = sorted(targets.items())

                for target_num, target_price in sorted_targets:
                    total_orders += 1
                    try:
                        success = self.set_take_profit(symbol, target_num, target_price)
                        if success:
                            success_count += 1
                            ws_logger.log(f"✅ TP{target_num} set for {symbol} @ {target_price}", 'success')
                        else:
                            ws_logger.log(f"❌ Error setting TP{target_num} for {symbol}", 'error')
                    except Exception as e:
                        ws_logger.log(f"❌ Exception TP{target_num} for {symbol}: {e}", 'error')

            # Set Stop Loss
            stop_loss = signal.get('stop_loss')
            if stop_loss:
                total_orders += 1
                try:
                    success = self.set_stop_loss(symbol, stop_loss)
                    if success:
                        success_count += 1
                        ws_logger.log(f"✅ SL set for {symbol} @ {stop_loss}", 'success')
                    else:
                        ws_logger.log(f"❌ Error setting SL for {symbol}", 'error')
                except Exception as e:
                    ws_logger.log(f"❌ Exception SL for {symbol}: {e}", 'error')

            # Report results
            if total_orders > 0:
                success_rate = (success_count / total_orders) * 100
                ws_logger.log(f"📊 TP/SL for {symbol}: {success_count}/{total_orders} ({success_rate:.0f}%)")
                return success_count > 0
            else:
                ws_logger.log(f"⚠️ No targets and SL to set for {symbol}", 'warning')
                return True

        except Exception as e:
            ws_logger.log(f"❌ Error setup_tp_sl_orders for {symbol}: {e}", 'error')
            return False

    def set_take_profit(self, symbol, target_num, target_price):
        """Set Take Profit order"""
        try:
            if not self.bot.bybit_client:
                ws_logger.log("❌ No Bybit client", 'error')
                return False

            position = self.active_positions.get(symbol)
            if not position:
                ws_logger.log(f"❌ No position {symbol} in monitoring", 'error')
                return False

            # Validate Take Profit
            entry_price = position['entry_price']
            position_type = position['position_type'].lower()

            ws_logger.log(f"🔍 Validating TP{target_num} for {symbol}:")
            ws_logger.log(f"   📊 Position: {position_type.upper()}")
            ws_logger.log(f"   💰 Entry: {entry_price}")
            ws_logger.log(f"   🎯 TP{target_num}: {target_price}")

            # Logical validation
            if position_type == "long":
                if target_price <= entry_price:
                    error_msg = f"❌ ERROR TP{target_num} for LONG {symbol}: TP ({target_price}) <= Entry ({entry_price})"
                    ws_logger.log(error_msg, 'error')
                    ws_logger.log("💡 For LONG: Take Profit must be ABOVE entry price!", 'warning')
                    return False
            elif position_type == "short":
                if target_price >= entry_price:
                    error_msg = f"❌ ERROR TP{target_num} for SHORT {symbol}: TP ({target_price}) >= Entry ({entry_price})"
                    ws_logger.log(error_msg, 'error')
                    ws_logger.log("💡 For SHORT: Take Profit must be BELOW entry price!", 'warning')
                    return False

            ws_logger.log(f"✅ TP{target_num} validation PASSED for {position_type.upper()} {symbol}", 'success')

            # Get current position size
            current_position_size = self.get_current_position_size(symbol)
            if not current_position_size or current_position_size <= 0:
                ws_logger.log(f"❌ No current position for {symbol}", 'error')
                return False

            # Calculate size for this target
            total_targets = len(position['targets'])
            if total_targets == 0:
                ws_logger.log(f"❌ No targets for {symbol}", 'error')
                return False

            tp_qty = current_position_size / total_targets

            # Get symbol info for formatting
            symbol_info = self.bot.get_symbol_info(symbol)
            if not symbol_info:
                ws_logger.log(f"❌ Cannot get symbol info for {symbol}", 'error')
                return False

            # Format quantity according to requirements
            tp_qty_formatted = self.bot.format_quantity(tp_qty, symbol_info)
            if not tp_qty_formatted:
                ws_logger.log(f"❌ Error formatting quantity {tp_qty}", 'error')
                return False

            side = "Sell" if position_type == "long" else "Buy"

            # Format price with full precision
            target_price_str = f"{target_price:.8f}".rstrip('0').rstrip('.')

            # TP order parameters
            tp_params = {
                'category': "linear",
                'symbol': symbol,
                'side': side,
                'orderType': "Limit",
                'qty': str(tp_qty_formatted),
                'price': target_price_str,
                'positionIdx': self.bot.get_position_idx(position['position_type']),
                'reduceOnly': True,
                'timeInForce': "GTC"
            }

            ws_logger.log(f"📤 Setting TP{target_num} for {symbol}: {tp_params}")

            if self.bot.use_demo_account:
                ws_logger.log(f"🎮 DEMO: TP{target_num} {symbol} @ {target_price_str}")
                tp_response = {
                    'retCode': 0,
                    'retMsg': 'Demo TP order simulated',
                    'result': {
                        'orderId': f'DEMO_TP{target_num}_{symbol}_{int(time.time())}',
                        'orderLinkId': f'demo_tp_{target_num}'
                    }
                }
            else:
                ws_logger.log(f"💰 LIVE: TP{target_num} {symbol} @ {target_price_str}")
                tp_response = self.bot.bybit_client.place_order(**tp_params)

            if tp_response.get('retCode') == 0:
                tp_order_id = tp_response.get('result', {}).get('orderId')
                position['tp_orders'][target_num] = tp_order_id
                ws_logger.log(f"✅ TP{target_num} set for {symbol}: Order ID {tp_order_id}", 'success')
                return True
            else:
                error_msg = tp_response.get('retMsg', 'Unknown error')
                ws_logger.log(f"❌ Error TP{target_num} for {symbol}: {error_msg}", 'error')
                return False

        except Exception as e:
            ws_logger.log(f"❌ Error set_take_profit for {symbol} TP{target_num}: {e}", 'error')
            return False

    def set_stop_loss(self, symbol, sl_price):
        """Set Stop Loss order"""
        try:
            if not self.bot.bybit_client:
                ws_logger.log("❌ No Bybit client", 'error')
                return False

            position = self.active_positions.get(symbol)
            if not position:
                ws_logger.log(f"❌ No position {symbol} in monitoring", 'error')
                return False

            # Validate SL
            entry_price = position['entry_price']
            position_type = position['position_type'].lower()

            ws_logger.log(f"🔍 Validating SL for {symbol}:")
            ws_logger.log(f"   📊 Position: {position_type.upper()}")
            ws_logger.log(f"   💰 Entry: {entry_price}")
            ws_logger.log(f"   🛑 SL: {sl_price}")

            # Logical validation
            if position_type == "long":
                if sl_price >= entry_price:
                    error_msg = f"❌ ERROR SL for LONG {symbol}: SL ({sl_price}) >= Entry ({entry_price})"
                    ws_logger.log(error_msg, 'error')
                    ws_logger.log("💡 For LONG: Stop Loss must be BELOW entry price!", 'warning')
                    return False
            elif position_type == "short":
                if sl_price <= entry_price:
                    error_msg = f"❌ ERROR SL for SHORT {symbol}: SL ({sl_price}) <= Entry ({entry_price})"
                    ws_logger.log(error_msg, 'error')
                    ws_logger.log("💡 For SHORT: Stop Loss must be ABOVE entry price!", 'warning')
                    return False

            ws_logger.log(f"✅ SL validation PASSED for {position_type.upper()} {symbol}", 'success')

            # Get current position size
            current_position_size = self.get_current_position_size(symbol)
            if not current_position_size or current_position_size <= 0:
                ws_logger.log(f"❌ No current position for {symbol}", 'error')
                return False

            # METHOD 1: Set Trading Stop (recommended for SL)
            success = self.set_trading_stop(symbol, sl_price, position_type)
            if success:
                return True

            # METHOD 2: Fallback - conditional order "Stop"
            ws_logger.log(f"🔄 Fallback: conditional Stop order for {symbol}", 'warning')
            return self.set_conditional_stop(symbol, sl_price, current_position_size, position_type)

        except Exception as e:
            ws_logger.log(f"❌ Error set_stop_loss for {symbol}: {e}", 'error')
            return False

    def set_trading_stop(self, symbol, sl_price, position_type):
        """Set Trading Stop"""
        try:
            # Format price with full precision
            sl_price_str = f"{sl_price:.8f}".rstrip('0').rstrip('.')

            trading_stop_params = {
                'category': "linear",
                'symbol': symbol,
                'stopLoss': sl_price_str,
                'positionIdx': self.bot.get_position_idx(position_type)
            }

            ws_logger.log(f"📤 Set Trading Stop for {symbol}: {trading_stop_params}")

            if self.bot.use_demo_account:
                ws_logger.log(f"🎮 DEMO: Trading Stop {symbol} @ {sl_price_str}")
                response = {
                    'retCode': 0,
                    'retMsg': 'Demo trading stop set',
                    'result': {}
                }
            else:
                ws_logger.log(f"💰 LIVE: Trading Stop {symbol} @ {sl_price_str}")
                response = self.bot.bybit_client.set_trading_stop(**trading_stop_params)

            if response.get('retCode') == 0:
                position = self.active_positions[symbol]
                position['sl_order_id'] = f'TRADING_STOP_{symbol}'
                ws_logger.log(f"✅ Trading Stop set for {symbol} @ {sl_price_str}", 'success')
                return True
            else:
                error_msg = response.get('retMsg', 'Unknown error')
                ws_logger.log(f"❌ Trading Stop error for {symbol}: {error_msg}", 'error')
                return False

        except Exception as e:
            ws_logger.log(f"❌ Error set_trading_stop for {symbol}: {e}", 'error')
            return False

    def set_conditional_stop(self, symbol, sl_price, position_size, position_type):
        """Conditional Stop Order (fallback)"""
        try:
            side = "Sell" if position_type == "long" else "Buy"

            # Format price with full precision
            sl_price_str = f"{sl_price:.8f}".rstrip('0').rstrip('.')
            position_size_str = str(position_size)

            # Parameters for Bybit Linear
            stop_params = {
                'category': "linear",
                'symbol': symbol,
                'side': side,
                'orderType': "Stop",
                'qty': position_size_str,
                'stopPrice': sl_price_str,
                'positionIdx': self.bot.get_position_idx(position_type),
                'reduceOnly': True,
                'timeInForce': "GTC",
                'triggerDirection': 1 if position_type == "long" else 2
            }

            ws_logger.log(f"📤 Conditional Stop for {symbol}: {stop_params}")

            if self.bot.use_demo_account:
                ws_logger.log(f"🎮 DEMO: Conditional Stop {symbol} @ {sl_price_str}")
                response = {
                    'retCode': 0,
                    'retMsg': 'Demo conditional stop simulated',
                    'result': {'orderId': f'DEMO_STOP_{symbol}_{int(time.time())}'}
                }
            else:
                ws_logger.log(f"💰 LIVE: Conditional Stop {symbol} @ {sl_price_str}")
                response = self.bot.bybit_client.place_order(**stop_params)

            if response.get('retCode') == 0:
                sl_order_id = response.get('result', {}).get('orderId', 'CONDITIONAL_STOP')
                position = self.active_positions[symbol]
                position['sl_order_id'] = sl_order_id
                ws_logger.log(f"✅ Conditional Stop set for {symbol}: {sl_order_id}", 'success')
                return True
            else:
                error_msg = response.get('retMsg', 'Unknown error')
                ws_logger.log(f"❌ Conditional Stop error for {symbol}: {error_msg}", 'error')
                return False

        except Exception as e:
            ws_logger.log(f"❌ Error set_conditional_stop for {symbol}: {e}", 'error')
            return False

    def cancel_sl_order(self, symbol, order_id):
        """Cancel Stop Loss order"""
        try:
            if not self.bot.bybit_client:
                ws_logger.log("❌ No Bybit client", 'error')
                return False

            # Check if it's trading stop or conditional order
            if order_id.startswith('TRADING_STOP_'):
                ws_logger.log(f"🗑️ Canceling Trading Stop for {symbol}")
                return self.cancel_trading_stop(symbol)
            else:
                ws_logger.log(f"🗑️ Canceling conditional order: {order_id}")
                return self.cancel_order(symbol, order_id)

        except Exception as e:
            ws_logger.log(f"❌ Error cancel_sl_order for {symbol}: {e}", 'error')
            return False

    def cancel_trading_stop(self, symbol):
        """Cancel Trading Stop"""
        try:
            position = self.active_positions.get(symbol)
            if not position:
                return False

            position_type = position['position_type']

            # Remove trading stop by setting empty stopLoss
            trading_stop_params = {
                'category': "linear",
                'symbol': symbol,
                'stopLoss': "",  # Empty string removes SL
                'positionIdx': self.bot.get_position_idx(position_type)
            }

            ws_logger.log(f"📤 Removing Trading Stop for {symbol}")

            if self.bot.use_demo_account:
                ws_logger.log(f"🎮 DEMO: Removing Trading Stop {symbol}")
                response = {
                    'retCode': 0,
                    'retMsg': 'Demo trading stop removed',
                    'result': {}
                }
            else:
                ws_logger.log(f"💰 LIVE: Removing Trading Stop {symbol}")
                response = self.bot.bybit_client.set_trading_stop(**trading_stop_params)

            if response.get('retCode') == 0:
                ws_logger.log(f"✅ Trading Stop removed for {symbol}", 'success')
                return True
            else:
                error_msg = response.get('retMsg', 'Unknown error')
                ws_logger.log(f"❌ Error removing Trading Stop for {symbol}: {error_msg}", 'error')
                return False

        except Exception as e:
            ws_logger.log(f"❌ Error cancel_trading_stop for {symbol}: {e}", 'error')
            return False

    def cancel_order(self, symbol, order_id):
        """Cancel order"""
        try:
            if not self.bot.bybit_client:
                return False

            if self.bot.use_demo_account:
                ws_logger.log(f"🎮 DEMO: Simulating cancel {order_id}")
                return True

            cancel_params = {
                'category': "linear",
                'symbol': symbol,
                'orderId': order_id
            }

            ws_logger.log(f"📤 Canceling order {order_id} for {symbol}")
            response = self.bot.bybit_client.cancel_order(**cancel_params)

            if response.get('retCode') == 0:
                ws_logger.log(f"✅ Order {order_id} canceled", 'success')
                return True
            else:
                error_msg = response.get('retMsg', 'Unknown error')
                ws_logger.log(f"⚠️ Cancel {order_id}: {error_msg}", 'warning')
                return True

        except Exception as e:
            ws_logger.log(f"❌ Error cancel_order: {e}", 'error')
            return False

    def get_current_position_size(self, symbol):
        """Get current position size"""
        try:
            if not self.bot.bybit_client:
                ws_logger.log(f"❌ No Bybit client for {symbol}", 'error')
                return 0

            if self.bot.use_demo_account:
                # For demo return simulated size
                position = self.active_positions.get(symbol)
                if position:
                    # Calculate based on entry price and trading parameters
                    entry_price = position['entry_price']
                    amount_to_use = self.bot.default_amount

                    if self.bot.use_percentage:
                        # Get balance and calculate
                        balance_info = self.bot.get_wallet_balance()
                        if balance_info and balance_info.get('success'):
                            available = balance_info.get('totalAvailableBalance', 0)
                            amount_to_use = available * (self.bot.default_amount / 100.0)

                    # Calculate position size
                    position_value_usdt = amount_to_use * self.bot.default_leverage
                    qty = position_value_usdt / entry_price

                    # Format according to symbol requirements
                    symbol_info = self.bot.get_symbol_info(symbol)
                    if symbol_info:
                        qty_formatted = self.bot.format_quantity(qty, symbol_info)
                        return qty_formatted if qty_formatted else 0

                    return round(qty, 6)
                return 0

            # Get real position from API
            try:
                positions_response = self.bot.bybit_client.get_positions(
                    category="linear",
                    symbol=symbol
                )

                if positions_response.get('retCode') == 0:
                    position_list = positions_response.get('result', {}).get('list', [])

                    for pos in position_list:
                        if pos.get('symbol') == symbol:
                            size = float(pos.get('size', '0'))
                            if size > 0:
                                ws_logger.log(f"📊 Current position {symbol}: {size}")
                                return size

                    ws_logger.log(f"⚠️ No active position for {symbol}", 'warning')
                    return 0
                else:
                    error_msg = positions_response.get('retMsg', 'Unknown error')
                    ws_logger.log(f"❌ Error getting position {symbol}: {error_msg}", 'error')
                    return 0

            except Exception as e:
                ws_logger.log(f"❌ API error get_positions for {symbol}: {e}", 'error')
                return 0

        except Exception as e:
            ws_logger.log(f"❌ Error get_current_position_size for {symbol}: {e}", 'error')
            return 0

    def get_current_price(self, symbol):
        """Get current symbol price"""
        try:
            if not self.bot.bybit_client:
                return None

            if self.bot.use_demo_account:
                # In demo mode simulate price close to entry price
                position = self.active_positions.get(symbol)
                if position:
                    entry_price = position['entry_price']
                    # Simulate slight fluctuations (±2%)
                    import random
                    variation = random.uniform(-0.02, 0.02)
                    simulated_price = entry_price * (1 + variation)
                    return round(simulated_price, 8)
                return None

            # Get real price from API
            try:
                ticker_response = self.bot.bybit_client.get_tickers(
                    category="linear",
                    symbol=symbol
                )

                if ticker_response.get('retCode') == 0:
                    ticker_list = ticker_response.get('result', {}).get('list', [])

                    if ticker_list:
                        ticker = ticker_list[0]
                        last_price = float(ticker.get('lastPrice', '0'))
                        return last_price

                return None

            except Exception as e:
                ws_logger.log(f"❌ API error get_tickers for {symbol}: {e}", 'error')
                return None

        except Exception as e:
            ws_logger.log(f"❌ Error get_current_price for {symbol}: {e}", 'error')
            return None

    def check_filled_orders(self, symbol):
        """Check filled orders"""
        try:
            if symbol not in self.active_positions:
                return

            position = self.active_positions[symbol]

            # Check targets based on current price
            price_check_result = self.check_target_reached_by_price(symbol)
            if price_check_result:
                ws_logger.log(f"✅ New targets detected by price check for {symbol}", 'success')

            # Check TP orders (as backup)
            for target_num, order_id in position['tp_orders'].items():
                if target_num not in position['filled_targets']:
                    if self.is_order_filled(symbol, order_id):
                        position['filled_targets'].add(target_num)
                        ws_logger.log(f"🎯 TP{target_num} reached for {symbol} (by order status)!", 'success')

                        # If it's trigger target, move SL to breakeven
                        breakeven_target = position.get('breakeven_target', 1)
                        if target_num == breakeven_target and not position['sl_moved_to_breakeven'] and self.bot.auto_breakeven:
                            ws_logger.log(f"💡 Target {breakeven_target} by order - activating breakeven for {symbol}")
                            self.move_sl_to_breakeven(symbol)

            # Check SL
            if position['sl_order_id']:
                if self.is_order_filled(symbol, position['sl_order_id']):
                    ws_logger.log(f"🛑 Stop Loss executed for {symbol}")
                    self.remove_position(symbol)

        except Exception as e:
            ws_logger.log(f"❌ Error check_filled_orders for {symbol}: {e}", 'error')

    def is_order_filled(self, symbol, order_id):
        """Check if order is filled"""
        try:
            if not self.bot.bybit_client:
                return False

            if self.bot.use_demo_account:
                # For demo check price
                return self.simulate_order_fill_improved(symbol, order_id)

            # Check order status in live
            try:
                order_history = self.bot.bybit_client.get_order_history(
                    category="linear",
                    symbol=symbol,
                    orderId=order_id
                )

                if order_history.get('retCode') == 0:
                    orders = order_history.get('result', {}).get('list', [])
                    for order in orders:
                        if order.get('orderId') == order_id:
                            status = order.get('orderStatus')
                            if status in ['Filled', 'PartiallyFilled']:
                                ws_logger.log(f"✅ Order {order_id} filled (status: {status})", 'success')
                                return True
                            else:
                                ws_logger.log(f"⏳ Order {order_id} status: {status}")
                                return False

                return False

            except Exception as e:
                ws_logger.log(f"❌ Error checking order status {order_id}: {e}", 'error')
                return False

        except Exception as e:
            ws_logger.log(f"❌ Error is_order_filled: {e}", 'error')
            return False

    def simulate_order_fill_improved(self, symbol, order_id):
        """Improved order fill simulation for demo"""
        try:
            if symbol not in self.active_positions:
                return False

            position = self.active_positions[symbol]
            targets = position.get('targets', {})
            current_price = self.get_current_price(symbol)

            if not current_price:
                return False

            # Check if it's TP order
            for target_num, tp_order_id in position['tp_orders'].items():
                if tp_order_id == order_id:
                    target_price = targets.get(target_num)
                    if target_price:
                        position_type = position['position_type'].lower()

                        # Check if target reached
                        if position_type == "long" and current_price >= target_price:
                            ws_logger.log(f"🎮 DEMO: TP{target_num} simulated fill @ {current_price}")
                            return True
                        elif position_type == "short" and current_price <= target_price:
                            ws_logger.log(f"🎮 DEMO: TP{target_num} simulated fill @ {current_price}")
                            return True

            # Check if it's SL
            if position['sl_order_id'] == order_id and position.get('stop_loss'):
                sl_price = position['stop_loss']
                position_type = position['position_type'].lower()

                if position_type == "long" and current_price <= sl_price:
                    ws_logger.log(f"🎮 DEMO: SL simulated fill @ {current_price}")
                    return True
                elif position_type == "short" and current_price >= sl_price:
                    ws_logger.log(f"🎮 DEMO: SL simulated fill @ {current_price}")
                    return True

            return False

        except Exception as e:
            ws_logger.log(f"❌ Error simulate_order_fill_improved: {e}", 'error')
            return False

    def remove_position(self, symbol):
        """Remove position from monitoring"""
        try:
            if symbol in self.active_positions:
                del self.active_positions[symbol]
                ws_logger.log(f"✅ Position {symbol} removed from monitoring", 'success')

                # Emit position update via Socket.IO
                socketio.emit('message', {
                    'type': 'position',
                    'action': 'removed',
                    'symbol': symbol
                })
        except Exception as e:
            ws_logger.log(f"❌ Error remove_position: {e}", 'error')

    def start_monitoring(self):
        """Start position monitoring"""
        if not self.monitoring_active:
            self.monitoring_active = True
            self.monitor_thread = threading.Thread(target=self._monitor_positions, daemon=True)
            self.monitor_thread.start()
            ws_logger.log("✅ Position monitoring started", 'success')

            # Emit status update
            socketio.emit('status_update', {'monitoring': True})

    def stop_monitoring(self):
        """Stop position monitoring"""
        self.monitoring_active = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=1)
        ws_logger.log("🛑 Position monitoring stopped")

        # Emit status update
        socketio.emit('status_update', {'monitoring': False})

    def _monitor_positions(self):
        """Position monitoring thread"""
        ws_logger.log("🔄 Position monitoring thread started")

        while self.monitoring_active:
            try:
                active_symbols = list(self.active_positions.keys())

                if active_symbols:
                    ws_logger.log(f"👀 Monitoring {len(active_symbols)} positions: {', '.join(active_symbols)}")

                    for symbol in active_symbols:
                        try:
                            self.check_filled_orders(symbol)

                            # Additional logging for debugging
                            position = self.active_positions.get(symbol)
                            if position:
                                filled_count = len(position.get('filled_targets', set()))
                                total_targets = len(position.get('targets', {}))
                                breakeven_status = "✅" if position.get('sl_moved_to_breakeven') else "❌"
                                breakeven_trigger = position.get('breakeven_target', 1)

                                ws_logger.log(f"📊 {symbol}: Targets {filled_count}/{total_targets}, Breakeven {breakeven_status} (trigger: TP{breakeven_trigger})")

                        except Exception as e:
                            ws_logger.log(f"❌ Monitoring error {symbol}: {e}", 'error')
                            continue
                else:
                    ws_logger.log("💤 No positions to monitor")

                # Check every 15 seconds
                time.sleep(15)

            except Exception as e:
                ws_logger.log(f"❌ Error in main monitoring loop: {e}", 'error')
                time.sleep(60)  # Wait longer on error

        ws_logger.log("🛑 Position monitoring thread ended")

    def get_positions_summary(self):
        """Get positions summary"""
        summary = []
        for symbol, position in self.active_positions.items():
            filled_targets = len(position['filled_targets'])
            total_targets = len(position['targets'])

            # Additional info
            last_price = position.get('last_price_check', 'Unknown')
            check_count = position.get('target_check_count', 0)
            breakeven_trigger = position.get('breakeven_target', 1)

            summary.append({
                'symbol': symbol,
                'type': position['position_type'],
                'entry': position['entry_price'],
                'targets': f"{filled_targets}/{total_targets}",
                'sl_breakeven': position['sl_moved_to_breakeven'],
                'created': position['created_at'].strftime('%H:%M:%S'),
                'last_price': last_price,
                'checks': check_count,
                'breakeven_trigger': f"TP{breakeven_trigger}"
            })

        return summary

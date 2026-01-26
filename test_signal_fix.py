"""
Test dla poprawki rozpoznawania typu pozycji Short/Long
"""
import sys
import os

# Dodaj ścieżkę do modułów
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.signal_parser import parse_trading_signal

def test_short_position_with_long_term():
    """
    Test sygnału z Long-Term w nagłówku i Short Entry Zone
    Powinien rozpoznać SHORT, nie LONG
    """
    signal_text = """
📩 #CRVUSDT 4h | Long-Term
📉 Short Entry Zone: 0.356-0.401

🎯 - Strategy Accuracy:  98.12%
Last 5 signals:  100.0%
Last 10 signals:  100.0%
Last 20 signals:  100.0%

⏳ - Signal details:
Target 1:  0.332
Target 2:  0.308
Target 3:  0.284
Target 4:  0.212
_____
🧲Trend-Line: 0.401
[ERROR]Stop-Loss: 0.428
💡After reaching the first target you can put the rest of the position to breakeven

#ID20000036363
    """

    result = parse_trading_signal(signal_text)

    print("\n" + "="*60)
    print("TEST: Short Entry Zone z Long-Term w nagłówku")
    print("="*60)

    if result is None:
        print("[ERROR] BŁĄD: Sygnał nie został rozpoznany!")
        return False

    print(f"\n Rozpoznany sygnał:")
    print(f"Symbol: {result.get('symbol')}")
    print(f"Position Type: {result.get('position_type')}")
    print(f"Entry Price: {result.get('entry_price')}")
    print(f"Targets: {result.get('targets')}")
    print(f"Stop Loss: {result.get('stop_loss')}")

    # Sprawdź, czy typ pozycji to SHORT
    if result.get('position_type') == 'short':
        print("\n[OK] SUKCES: Poprawnie rozpoznano SHORT!")
        return True
    else:
        print(f"\n[ERROR] BŁĄD: Oczekiwano 'short', otrzymano '{result.get('position_type')}'")
        return False


def test_long_entry_zone():
    """
    Test sygnału z Long Entry Zone
    Powinien rozpoznać LONG
    """
    signal_text = """
#BTCUSDT 4h | Short-Term
📈 Long Entry Zone: 45000-46000

Target 1: 47000
Target 2: 48000
Target 3: 49000

Stop-Loss: 44000
    """

    result = parse_trading_signal(signal_text)

    print("\n" + "="*60)
    print("TEST: Long Entry Zone z Short-Term w nagłówku")
    print("="*60)

    if result is None:
        print("[ERROR] BŁĄD: Sygnał nie został rozpoznany!")
        return False

    print(f"\n Rozpoznany sygnał:")
    print(f"Symbol: {result.get('symbol')}")
    print(f"Position Type: {result.get('position_type')}")
    print(f"Entry Price: {result.get('entry_price')}")
    print(f"Targets: {result.get('targets')}")
    print(f"Stop Loss: {result.get('stop_loss')}")

    # Sprawdź, czy typ pozycji to LONG
    if result.get('position_type') == 'long':
        print("\n[OK] SUKCES: Poprawnie rozpoznano LONG!")
        return True
    else:
        print(f"\n[ERROR] BŁĄD: Oczekiwano 'long', otrzymano '{result.get('position_type')}'")
        return False


def test_simple_short():
    """
    Test prostego sygnału SHORT bez Long-Term/Short-Term
    """
    signal_text = """
#ETHUSDT
SHORT
Entry: 2500

Target 1: 2400
Target 2: 2300

Stop-Loss: 2600
    """

    result = parse_trading_signal(signal_text)

    print("\n" + "="*60)
    print("TEST: Prosty sygnał SHORT")
    print("="*60)

    if result is None:
        print("[ERROR] BŁĄD: Sygnał nie został rozpoznany!")
        return False

    print(f"\n Rozpoznany sygnał:")
    print(f"Symbol: {result.get('symbol')}")
    print(f"Position Type: {result.get('position_type')}")
    print(f"Entry Price: {result.get('entry_price')}")

    # Sprawdź, czy typ pozycji to SHORT
    if result.get('position_type') == 'short':
        print("\n[OK] SUKCES: Poprawnie rozpoznano SHORT!")
        return True
    else:
        print(f"\n[ERROR] BŁĄD: Oczekiwano 'short', otrzymano '{result.get('position_type')}'")
        return False


if __name__ == "__main__":
    print("\nUruchamianie testow poprawki rozpoznawania typu pozycji...\n")

    test1 = test_short_position_with_long_term()
    test2 = test_long_entry_zone()
    test3 = test_simple_short()

    print("\n" + "="*60)
    print("PODSUMOWANIE TESTÓW")
    print("="*60)
    print(f"Test 1 (Short Entry Zone + Long-Term): {'[OK] PASS' if test1 else '[ERROR] FAIL'}")
    print(f"Test 2 (Long Entry Zone + Short-Term): {'[OK] PASS' if test2 else '[ERROR] FAIL'}")
    print(f"Test 3 (Prosty SHORT): {'[OK] PASS' if test3 else '[ERROR] FAIL'}")

    if test1 and test2 and test3:
        print("\n[SUCCESS] Wszystkie testy przeszły pomyślnie!")
        sys.exit(0)
    else:
        print("\n[WARNING]  Niektóre testy nie przeszły.")
        sys.exit(1)

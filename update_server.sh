#!/bin/bash

###############################################################################
# Script do aktualizacji Trading Bot na serwerze Vultr
# Użycie: ./update_server.sh
###############################################################################

echo "=========================================="
echo "Trading Bot - Aktualizacja serwera"
echo "=========================================="
echo ""

# Kolory
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Funkcja do sprawdzania czy komenda się powiodła
check_status() {
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✓ OK${NC}"
    else
        echo -e "${RED}✗ BŁĄD${NC}"
        exit 1
    fi
}

# 1. Sprawdź czy jesteśmy w odpowiednim katalogu
echo -n "Sprawdzanie katalogu... "
if [ ! -d ".git" ]; then
    echo -e "${RED}✗ BŁĄD: Nie jesteś w katalogu git repo${NC}"
    echo "Przejdź do katalogu aplikacji (np. cd ~/tradingbotappweb)"
    exit 1
fi
check_status

# 2. Sprawdź status git
echo ""
echo "Status Git:"
git status --short

# 3. Wykryj metodę uruchamiania aplikacji
echo ""
echo -n "Wykrywanie metody uruchamiania... "
if command -v pm2 &> /dev/null; then
    RUN_METHOD="pm2"
    echo -e "${GREEN}PM2${NC}"
elif systemctl list-units --type=service | grep -q "trading-bot"; then
    RUN_METHOD="systemd"
    echo -e "${GREEN}systemd${NC}"
else
    RUN_METHOD="manual"
    echo -e "${YELLOW}manual${NC}"
fi

# 4. Zatrzymaj aplikację
echo ""
echo "Zatrzymywanie aplikacji..."
case $RUN_METHOD in
    pm2)
        pm2 stop all
        check_status
        ;;
    systemd)
        sudo systemctl stop trading-bot
        check_status
        ;;
    manual)
        echo -e "${YELLOW}! Musisz ręcznie zatrzymać aplikację${NC}"
        echo "Znalezione procesy Python:"
        ps aux | grep python | grep -v grep
        read -p "Zatrzym proces ręcznie, potem naciśnij Enter..."
        ;;
esac

# 5. Pobierz najnowsze zmiany
echo ""
echo "Pobieranie zmian z Git..."
git pull origin main
check_status

# 6. Sprawdź czy są nowe zależności
echo ""
if [ -f "requirements.txt" ]; then
    echo "Sprawdzanie zależności..."
    pip install -r requirements.txt --quiet
    check_status
fi

# 7. Uruchom aplikację
echo ""
echo "Uruchamianie aplikacji..."
case $RUN_METHOD in
    pm2)
        pm2 start all
        check_status
        pm2 save
        ;;
    systemd)
        sudo systemctl start trading-bot
        check_status
        ;;
    manual)
        echo -e "${YELLOW}! Musisz ręcznie uruchomić aplikację${NC}"
        echo "Przykłady:"
        echo "  python main.py &"
        echo "  python app.py &"
        ;;
esac

# 8. Pokaż status
echo ""
echo "=========================================="
echo -e "${GREEN}Aktualizacja zakończona!${NC}"
echo "=========================================="
echo ""

case $RUN_METHOD in
    pm2)
        echo "Status aplikacji:"
        pm2 status
        echo ""
        echo "Aby zobaczyć logi: pm2 logs"
        ;;
    systemd)
        echo "Status aplikacji:"
        sudo systemctl status trading-bot --no-pager -l
        echo ""
        echo "Aby zobaczyć logi: sudo journalctl -u trading-bot -f"
        ;;
    manual)
        echo "Sprawdź proces ręcznie: ps aux | grep python"
        ;;
esac

echo ""
echo "Commit zaktualizowany:"
git log -1 --oneline
echo ""
echo -e "${GREEN}Gotowe!${NC}"

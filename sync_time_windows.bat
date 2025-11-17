@echo off
REM ========================================================================
REM  SKRYPT SYNCHRONIZACJI CZASU - Windows
REM  Rozwiązuje problem błędów timestamp (ErrCode: 10002) w Bybit API
REM ========================================================================

echo.
echo ========================================================================
echo   SYNCHRONIZACJA CZASU SYSTEMOWEGO
echo ========================================================================
echo.
echo Ten skrypt zsynchronizuje zegar systemowy z serwerami czasu w internecie.
echo Jest to WYMAGANE aby naprawić błędy timestamp w Bybit API.
echo.
echo UWAGA: Skrypt wymaga uprawnień ADMINISTRATORA!
echo.
pause

echo.
echo [1/4] Sprawdzanie uprawnień...
net session >nul 2>&1
if %errorLevel% == 0 (
    echo      OK - Uruchomiono jako Administrator
) else (
    echo      BLAD - Brak uprawnien Administratora!
    echo.
    echo      INSTRUKCJA:
    echo      1. Kliknij prawym na ten plik
    echo      2. Wybierz "Uruchom jako administrator"
    echo.
    pause
    exit /b 1
)

echo.
echo [2/4] Konfigurowanie serwisu Windows Time...
w32tm /config /manualpeerlist:"time.windows.com time.nist.gov pool.ntp.org" /syncfromflags:manual /reliable:YES /update
if %errorLevel% == 0 (
    echo      OK - Serwisy czasu skonfigurowane
) else (
    echo      OSTRZEZENIE - Nie udalo sie skonfigurowac serwisow
)

echo.
echo [3/4] Restartowanie serwisu Windows Time...
net stop w32time >nul 2>&1
net start w32time
if %errorLevel% == 0 (
    echo      OK - Serwis uruchomiony
) else (
    echo      OSTRZEZENIE - Problem z serwisem
)

echo.
echo [4/4] Synchronizowanie czasu...
w32tm /resync /force
if %errorLevel% == 0 (
    echo      OK - Czas zsynchronizowany!
) else (
    echo      BLAD - Nie udalo sie zsynchronizowac
    echo.
    echo      Sprobuj recznej synchronizacji:
    echo      1. Otworz Ustawienia ^> Czas i jezyk
    echo      2. Kliknij "Synchronizuj teraz"
)

echo.
echo [WERYFIKACJA] Sprawdzanie offsetu czasu...
echo.

REM Create temporary PowerShell script to check time
echo $local = (Get-Date).ToUniversalTime() > %TEMP%\check_time.ps1
echo $url = "http://worldtimeapi.org/api/timezone/Etc/UTC" >> %TEMP%\check_time.ps1
echo try { >> %TEMP%\check_time.ps1
echo     $response = Invoke-RestMethod -Uri $url -TimeoutSec 5 >> %TEMP%\check_time.ps1
echo     $server = [DateTime]::Parse($response.datetime) >> %TEMP%\check_time.ps1
echo     $diff = ($local - $server).TotalSeconds >> %TEMP%\check_time.ps1
echo     Write-Host "Czas lokalny: $local" >> %TEMP%\check_time.ps1
echo     Write-Host "Czas serwera: $server" >> %TEMP%\check_time.ps1
echo     Write-Host "Roznica: $diff sekund" >> %TEMP%\check_time.ps1
echo     if ([Math]::Abs($diff) -lt 1) { >> %TEMP%\check_time.ps1
echo         Write-Host "STATUS: OK - Czas zsynchronizowany!" -ForegroundColor Green >> %TEMP%\check_time.ps1
echo     } elseif ([Math]::Abs($diff) -lt 3) { >> %TEMP%\check_time.ps1
echo         Write-Host "STATUS: OSTRZEZENIE - Offset $diff s (moze dzialac)" -ForegroundColor Yellow >> %TEMP%\check_time.ps1
echo     } else { >> %TEMP%\check_time.ps1
echo         Write-Host "STATUS: BLAD - Offset $diff s (za duzy!)" -ForegroundColor Red >> %TEMP%\check_time.ps1
echo     } >> %TEMP%\check_time.ps1
echo } catch { >> %TEMP%\check_time.ps1
echo     Write-Host "Nie mozna sprawdzic czasu serwera (brak internetu?)" -ForegroundColor Yellow >> %TEMP%\check_time.ps1
echo } >> %TEMP%\check_time.ps1

powershell -ExecutionPolicy Bypass -File %TEMP%\check_time.ps1
del %TEMP%\check_time.ps1 >nul 2>&1

echo.
echo ========================================================================
echo   GOTOWE!
echo ========================================================================
echo.
echo Mozesz teraz uruchomic bota trading:
echo    python app.py
echo.
echo Jesli nadal widzisz bledy timestamp:
echo   1. Sprawdz czy czas w Windowsie jest poprawny
echo   2. Sprawdz ustawienia strefy czasowej
echo   3. Wylacz "Ustaw czas automatycznie" i wlacz ponownie
echo   4. Uruchom ten skrypt ponownie
echo.
pause

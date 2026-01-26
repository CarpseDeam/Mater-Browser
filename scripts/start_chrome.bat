@echo off
echo Starting Chrome with debug port...
taskkill /F /IM chrome.exe >nul 2>&1
timeout /t 2 /nobreak >nul

start "" "C:\Program Files\Google\Chrome\Application\chrome.exe" ^
    --remote-debugging-port=9333 ^
    --user-data-dir="C:\Projects\Mater-Browser\.chrome-profile" ^
    --no-first-run ^
    --no-default-browser-check ^
    --disable-session-crashed-bubble ^
    --hide-crash-restore-bubble ^
    --disable-features=TranslateUI ^
    --start-maximized

echo Chrome started on port 9333

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
    --window-position=-2400,-2400 ^
    --window-size=1920,1080

echo Chrome started off-screen on port 9333
echo To view: Win+Shift+Arrow to move window back, or use virtual desktop

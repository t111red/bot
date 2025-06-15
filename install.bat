@echo off
chcp 65001 >nul
echo 🐟 Установка системы 'Золотая рыбка' v2.0
echo ==========================================

REM Проверка Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ Python не найден. Пожалуйста, установите Python 3.7 или выше.
    echo    Скачать можно с https://www.python.org/downloads/
    pause
    exit /b 1
)

echo ✅ Python найден
python --version

REM Установка зависимостей Python
echo 📦 Установка зависимостей Python...
pip install -r requirements.txt

if %errorlevel% neq 0 (
    echo ❌ Ошибка при установке зависимостей Python
    pause
    exit /b 1
)

echo ✅ Зависимости Python установлены успешно

REM Проверка cloudflared
cloudflared --version >nul 2>&1
if %errorlevel% equ 0 (
    echo ✅ Cloudflared найден
    cloudflared --version
) else (
    echo ⚠️ Cloudflared не найден. Рекомендуется установить для автоматического создания публичных URL.
    echo    Установка: winget install --id Cloudflare.cloudflared
    echo    Или скачайте с https://github.com/cloudflare/cloudflared/releases
)

echo.
echo 🎉 Установка завершена!
echo.
echo 📝 Следующие шаги:
echo 1. Настройте токен бота в файле botf.py
echo 2. Добавьте ID администраторов в ADMIN_IDS
echo 3. Запустите систему командой: python run.py
echo.
echo 📋 После запуска будут доступны:
echo    - Админ-панель: http://localhost:5000
echo    - Mini App: http://localhost:8080
echo    - Публичные URL (если установлен cloudflared)
echo.
echo 🔐 Логин для админ-панели по умолчанию:
echo    Логин: admin
echo    Пароль: admin
echo.
pause
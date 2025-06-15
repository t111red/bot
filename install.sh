#!/bin/bash

echo "🐟 Установка системы 'Золотая рыбка' v2.0"
echo "=========================================="

# Проверка Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 не найден. Пожалуйста, установите Python 3.7 или выше."
    exit 1
fi

echo "✅ Python найден: $(python3 --version)"

# Установка зависимостей Python
echo "📦 Установка зависимостей Python..."
pip3 install -r requirements.txt

if [ $? -eq 0 ]; then
    echo "✅ Зависимости Python установлены успешно"
else
    echo "❌ Ошибка при установке зависимостей Python"
    exit 1
fi

# Проверка cloudflared
if command -v cloudflared &> /dev/null; then
    echo "✅ Cloudflared найден: $(cloudflared --version)"
else
    echo "⚠️ Cloudflared не найден. Рекомендуется установить для автоматического создания публичных URL."
    echo "   Инструкции по установке:"
    echo "   - macOS: brew install cloudflared"
    echo "   - Linux: https://github.com/cloudflare/cloudflared/releases"
    echo "   - Windows: winget install --id Cloudflare.cloudflared"
fi

echo ""
echo "🎉 Установка завершена!"
echo ""
echo "📝 Следующие шаги:"
echo "1. Настройте токен бота в файле botf.py"
echo "2. Добавьте ID администраторов в ADMIN_IDS"
echo "3. Запустите систему командой: python3 run.py"
echo ""
echo "📋 После запуска будут доступны:"
echo "   - Админ-панель: http://localhost:5000"
echo "   - Mini App: http://localhost:8080"
echo "   - Публичные URL (если установлен cloudflared)"
echo ""
echo "🔐 Логин для админ-панели по умолчанию:"
echo "   Логин: admin"
echo "   Пароль: admin"
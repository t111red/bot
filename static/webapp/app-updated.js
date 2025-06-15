document.addEventListener('DOMContentLoaded', function() {
    // Инициализация Telegram WebApp
    const tg = window.Telegram.WebApp;
    tg.expand(); // Раскрываем приложение на весь экран
    
    // Режим отладки отключен для продакшн
    const DEBUG = false; // Переключатель режима отладки
    
    console.log("DOM загружен, инициализация приложения...");
    
    // Сразу инициализируем функции с горячей загрузкой первого шага
    setTimeout(function() {
        console.log("Устанавливаем первый шаг формы...");
        initLogger();
        initNavigation(); // Инициализируем навигацию
        tryGetUserData();
        goToStep(1);
    }, 100);
    
    // Инициализация обработчиков навигации
    function initNavigation() {
        console.log("Инициализация навигации...");
        
        // Обработчики для кнопок навигации между шагами
        document.getElementById('nextToStep2').addEventListener('click', () => {
            if (validateStep1()) {
                goToStep(2);
                console.log("Переход к шагу 2 - выбор рыбы");
            }
        });
        
        document.getElementById('backToStep1').addEventListener('click', () => {
            goToStep(1);
            console.log("Возврат к шагу 1 - контактная информация");
        });
        
        document.getElementById('goToStep3').addEventListener('click', () => {
            if (validateStep2()) {
                goToStep(3);
                console.log("Переход к шагу 3 - промокод");
            }
        });
        
        document.getElementById('backToStep2').addEventListener('click', () => {
            goToStep(2);
            console.log("Возврат к шагу 2 - выбор рыбы");
        });
        
        document.getElementById('goToStep4').addEventListener('click', () => {
            goToStep(4);
            console.log("Переход к шагу 4 - время для звонка");
        });
        
        document.getElementById('backToStep3').addEventListener('click', () => {
            goToStep(3);
            console.log("Возврат к шагу 3 - промокод");
        });
        
        document.getElementById('placeOrder').addEventListener('click', () => {
            goToStep(5);
            console.log("Переход к шагу 5 - сводка заказа");
        });
        
        document.getElementById('backToStep4').addEventListener('click', () => {
            goToStep(4);
            console.log("Возврат к шагу 4 - время для звонка");
        });
        
        document.getElementById('submit-order').addEventListener('click', () => {
            submitOrder();
            console.log("Отправка заказа...");
        });
    }
    
    // Изменяем тему в соответствии с темой Telegram
    if (tg.colorScheme === 'dark') {
        document.documentElement.setAttribute('data-theme', 'dark');
        document.body.classList.add('tg-app');
    }

    // Переменные для системы логирования
    let logContainer;
    
    // Инициализируем систему логирования
    function initLogger() {
        logContainer = document.getElementById('log-container');
        if (!DEBUG && logContainer) {
            logContainer.style.display = 'none';
        } else if (logContainer) {
            logContainer.style.display = 'block';
        }
    }
    
    // Функция для логирования в консоль WebApp
    function log(message) {
        console.log(message);
        if (DEBUG && logContainer) {
            const logEntry = document.createElement('div');
            logEntry.className = 'log-entry';
            logEntry.textContent = `[${new Date().toLocaleTimeString()}] ${message}`;
            logContainer.appendChild(logEntry);
            logContainer.scrollTop = logContainer.scrollHeight;
        }
    }

    // Элементы формы
    const fullNameInput = document.getElementById('fullName');
    const phoneInput = document.getElementById('phone');
    const promoCodeInput = document.getElementById('promoCode');
    const callbackTimeSelect = document.getElementById('callbackTime');
    const progressBar = document.querySelector('.progress-bar');
    
    // Элементы для работы с корзиной
    const cartItems = document.getElementById('cart-items');
    let cart = [];
    let smallCount = 0;
    let mediumCount = 0;
    let largeCount = 0;
    const smallCountElement = document.getElementById('small-count');
    const mediumCountElement = document.getElementById('medium-count');
    const largeCountElement = document.getElementById('large-count');
    
    // Флаги для скидок
    let isWholesaleDiscount = false;
    let promoApplied = '';
    let hasThreeConfirmedOrders = false;
    
    // Константы для промокодов
    const PROMO_FISH = 'РЫБА2025';
    const PROMO_GOLD = 'ЗОЛОТО';
    
    // Попытка получить данные из Telegram WebApp initialData
    // Это позволит предзаполнить форму для повторных клиентов
    function tryGetUserData() {
        try {
            const initDataRaw = tg.initData;
            
            if (initDataRaw && tg.initDataUnsafe) {
                const userData = tg.initDataUnsafe.user;
                if (userData) {
                    log(`Получены данные пользователя: ${JSON.stringify(userData)}`);
                    
                    // Проверим, есть ли у пользователя имя в Telegram
                    if (userData.first_name || userData.last_name) {
                        let fullName = '';
                        if (userData.first_name) fullName += userData.first_name;
                        if (userData.last_name) fullName += ' ' + userData.last_name;
                        
                        // Заполняем поле с именем только если оно пустое
                        if (fullNameInput.value.trim() === '') {
                            fullNameInput.value = fullName.trim();
                            log(`Заполнено поле имени из данных Telegram: ${fullName.trim()}`);
                        }
                    }
                    
                    // Проверяем, является ли пользователь постоянным клиентом
                    hasThreeConfirmedOrders = userData.id && userData.id > 0; // Будет обновлено при обработке заказа на сервере
                    
                    // Можно добавить дополнительные параметры, если они будут переданы от бота
                    if (userData.language_code) {
                        log(`Язык пользователя: ${userData.language_code}`);
                    }
                }
            }
        } catch (e) {
            log(`Ошибка при получении данных пользователя: ${e.message}`);
        }
    }
    
    // Переключение между шагами
    function goToStep(step) {
        // Скрываем все секции
        document.querySelectorAll('.step-section').forEach(section => {
            section.style.display = 'none';
        });
        
        // Показываем соответствующую секцию
        document.getElementById(`step${step}`).style.display = 'block';
        
        // Обновляем прогресс-бар
        const progress = ((step - 1) / 5) * 100;
        progressBar.style.width = `${progress}%`;
        
        log(`Переход на шаг ${step}, прогресс: ${progress}%`);
        
        // Если переходим на шаг 4, обновляем сводку заказа
        if (step === 4) {
            updateSummary();
        }
        
        // Для шага с рабочим временем (шаг 5)
        if (step === 5) {
            const currentHour = new Date().getHours();
            const isWorkingTime = currentHour >= 9 && currentHour < 18;
            
            workingTimeMessage.textContent = isWorkingTime ? 
                'Сейчас рабочее время. Наш менеджер свяжется с вами в ближайшее время!' : 
                'Сейчас нерабочее время. Укажите удобное время для обратного звонка.';
            
            nonWorkingTimeForm.style.display = isWorkingTime ? 'none' : 'block';
            
            log(`Шаг выбора времени для обратной связи, рабочее время: ${isWorkingTime}`);
        }
    }

    // Обработчики для кнопок навигации
    document.getElementById('small-plus').addEventListener('click', () => {
        smallCount++;
        smallCountElement.textContent = smallCount;
        updateWholesaleDiscount();
        log(`Увеличено количество маленькой рыбы: ${smallCount}`);
    });
    
    document.getElementById('small-minus').addEventListener('click', () => {
        if (smallCount > 0) {
            smallCount--;
            smallCountElement.textContent = smallCount;
            updateWholesaleDiscount();
            log(`Уменьшено количество маленькой рыбы: ${smallCount}`);
        }
    });
    
    document.getElementById('medium-plus').addEventListener('click', () => {
        mediumCount++;
        mediumCountElement.textContent = mediumCount;
        updateWholesaleDiscount();
        log(`Увеличено количество средней рыбы: ${mediumCount}`);
    });
    
    document.getElementById('medium-minus').addEventListener('click', () => {
        if (mediumCount > 0) {
            mediumCount--;
            mediumCountElement.textContent = mediumCount;
            updateWholesaleDiscount();
            log(`Уменьшено количество средней рыбы: ${mediumCount}`);
        }
    });
    
    document.getElementById('large-plus').addEventListener('click', () => {
        largeCount++;
        largeCountElement.textContent = largeCount;
        updateWholesaleDiscount();
        log(`Увеличено количество крупной рыбы: ${largeCount}`);
    });
    
    document.getElementById('large-minus').addEventListener('click', () => {
        if (largeCount > 0) {
            largeCount--;
            largeCountElement.textContent = largeCount;
            updateWholesaleDiscount();
            log(`Уменьшено количество крупной рыбы: ${largeCount}`);
        }
    });
    
    // Функция для проверки оптовой скидки
    function updateWholesaleDiscount() {
        const totalFish = smallCount + mediumCount + largeCount;
        const wholesaleDiscountElement = document.getElementById('wholesale-discount');
        
        if (totalFish >= 4) {
            wholesaleDiscountElement.style.display = 'block';
            isWholesaleDiscount = true;
            log('Применена оптовая скидка (10%)');
        } else {
            wholesaleDiscountElement.style.display = 'none';
            isWholesaleDiscount = false;
            log('Оптовая скидка не применена');
        }
    }
    
    // Добавление товаров в корзину
    document.getElementById('add-to-cart').addEventListener('click', () => {
        let hasItems = false;
        
        if (smallCount > 0) {
            addToCart('Маленькая', smallCount);
            hasItems = true;
            smallCount = 0;
            smallCountElement.textContent = '0';
        }
        
        if (mediumCount > 0) {
            addToCart('Средняя', mediumCount);
            hasItems = true;
            mediumCount = 0;
            mediumCountElement.textContent = '0';
        }
        
        if (largeCount > 0) {
            addToCart('Крупная', largeCount);
            hasItems = true;
            largeCount = 0;
            largeCountElement.textContent = '0';
        }
        
        if (hasItems) {
            updateCartDisplay();
            document.getElementById('cart-error').style.display = 'none';
        } else {
            log('Ничего не добавлено в корзину');
        }
        
        updateWholesaleDiscount();
    });
    
    // Добавление товара в корзину
    function addToCart(size, quantity) {
        const existingItem = cart.find(item => item.size === size);
        if (existingItem) {
            existingItem.quantity += quantity;
            log(`Обновлено количество ${size} в корзине: ${existingItem.quantity}`);
        } else {
            cart.push({ size, quantity });
            log(`Добавлено в корзину: ${size}, количество: ${quantity}`);
        }
    }
    
    // Обновление отображения корзины
    function updateCartDisplay() {
        const cartItemsElement = document.getElementById('cart-items');
        
        if (cart.length === 0) {
            cartItemsElement.innerHTML = '<p>Корзина пуста</p>';
            return;
        }
        
        cartItemsElement.innerHTML = '';
        cart.forEach((item, index) => {
            const cartItem = document.createElement('div');
            cartItem.className = 'cart-item';
            
            const itemInfo = document.createElement('div');
            itemInfo.textContent = `${item.size}: ${item.quantity} шт.`;
            
            const removeButton = document.createElement('button');
            removeButton.className = 'btn btn-danger btn-small';
            removeButton.textContent = 'Удалить';
            removeButton.addEventListener('click', () => {
                cart.splice(index, 1);
                updateCartDisplay();
                updateWholesaleDiscount();
                log(`Удален товар из корзины: ${item.size}`);
            });
            
            cartItem.appendChild(itemInfo);
            cartItem.appendChild(removeButton);
            cartItemsElement.appendChild(cartItem);
        });
        
        // Проверяем общее количество для обновления скидки
        const totalFish = cart.reduce((total, item) => total + item.quantity, 0);
        isWholesaleDiscount = totalFish >= 4;
        document.getElementById('wholesale-discount').style.display = isWholesaleDiscount ? 'block' : 'none';
    }
    
    // Проверка промокода
    document.getElementById('check-promo').addEventListener('click', () => {
        const promoCode = document.getElementById('promoCode').value.trim();
        const promoValidElement = document.getElementById('promo-valid');
        const promoInvalidElement = document.getElementById('promo-invalid');
        
        promoValidElement.style.display = 'none';
        promoInvalidElement.style.display = 'none';
        
        // Сравнение без учета регистра
        if (promoCode.toUpperCase() === PROMO_FISH.toUpperCase()) {
            promoApplied = PROMO_FISH;
            promoValidElement.style.display = 'block';
            log('Применен промокод РЫБА2025');
            return;
        }
        
        // Сравнение без учета регистра
        if (promoCode.toUpperCase() === PROMO_GOLD.toUpperCase()) {
            // Проверка на наличие 3-х подтвержденных заказов
            if (hasThreeConfirmedOrders) {
                promoApplied = PROMO_GOLD;
                promoValidElement.style.display = 'block';
                log('Применен промокод ЗОЛОТО');
            } else {
                promoInvalidElement.style.display = 'block';
                promoInvalidElement.textContent = 'Промокод ЗОЛОТО доступен после 3-х подтвержденных заказов';
                log('Отказано в промокоде ЗОЛОТО - менее 3-х заказов');
            }
            return;
        }
        
        if (promoCode) {
            promoInvalidElement.style.display = 'block';
            log(`Неверный промокод: ${promoCode}`);
        }
    });
    
    // Валидация шага 1
    function validateStep1() {
        const fullName = document.getElementById('fullName').value.trim();
        const phone = document.getElementById('phone').value.trim();
        const fullNameError = document.getElementById('fullName-error');
        const phoneError = document.getElementById('phone-error');
        
        let isValid = true;
        
        if (!fullName) {
            fullNameError.style.display = 'block';
            isValid = false;
            log('Ошибка: не указано имя');
        } else {
            fullNameError.style.display = 'none';
        }
        
        if (!phone || !isValidPhone(phone)) {
            phoneError.style.display = 'block';
            isValid = false;
            log('Ошибка: не указан или неверный формат телефона');
        } else {
            phoneError.style.display = 'none';
        }
        
        return isValid;
    }
    
    // Валидация шага 2
    function validateStep2() {
        const cartError = document.getElementById('cart-error');
        
        if (cart.length === 0) {
            cartError.style.display = 'block';
            log('Ошибка: корзина пуста');
            return false;
        } else {
            cartError.style.display = 'none';
            return true;
        }
    }
    
    // Функция отправки заказа
    function submitOrder() {
        log('Начинаем отправку заказа...');
        
        // Деактивируем кнопку отправки, чтобы избежать двойной отправки
        const submitButton = document.getElementById('submit-order');
        submitButton.disabled = true;
        submitButton.innerHTML = 'Отправка...';
        
        // Проверяем, есть ли данные пользователя Telegram
        let tgUserId = null;
        let tgUsername = null;
        
        try {
            if (tg.initDataUnsafe && tg.initDataUnsafe.user) {
                tgUserId = tg.initDataUnsafe.user.id;
                tgUsername = tg.initDataUnsafe.user.username || null;
                log(`Получен ID пользователя Telegram: ${tgUserId}`);
            }
        } catch (e) {
            log(`Не удалось получить данные пользователя Telegram: ${e.message}`);
        }
        
        // Если мы не смогли получить идентификатор пользователя от Telegram, показываем предупреждение
        if (!tgUserId) {
            log('ВНИМАНИЕ: Не удалось получить ID пользователя Telegram, заказ может быть создан неправильно');
            
            // Здесь можно добавить вывод предупреждения пользователю, если нужно
            // Но в ботах Telegram это обычно невозможно - id всегда должен быть доступен
        }
        
        // Генерируем уникальный идентификатор сессии для предотвращения дублирования заказов
        const sessionId = `${tgUserId || ''}_${Date.now()}_${Math.random().toString(36).substring(2, 15)}`;
        log(`Сгенерирован уникальный ID сессии: ${sessionId}`);
        
        // Нормализуем данные товаров перед отправкой на сервер
        const normalizedCart = cart.map(item => ({
            size: item.size,
            name: item.name || item.size, // Используем размер в качестве имени, если имя не задано
            quantity: item.quantity,
            price: item.price || (
                item.size === 'Маленькая' ? 500 : 
                item.size === 'Средняя' ? 900 : 
                item.size === 'Крупная' ? 1500 : 800
            )
        }));
        
        log(`Нормализованная корзина для отправки: ${JSON.stringify(normalizedCart)}`);
        
        // Собираем данные заказа с нормализованными товарами
        const orderData = {
            name: document.getElementById('fullName').value.trim(),
            phone: document.getElementById('phone').value.trim(),
            callbackTime: document.getElementById('callbackTime').value,
            promoCode: document.getElementById('promoCode').value.trim() || '',
            items: normalizedCart,
            discounts: {
                isWholesale: isWholesaleDiscount,
                promoApplied: promoApplied,
                hasLoyaltyDiscount: hasThreeConfirmedOrders
            },
            tgUserId: tgUserId,
            tgUsername: tgUsername,
            sessionId: sessionId // Добавляем session_id для предотвращения дублирования
        };
        
        // Отправка данных на сервер
        log(`Отправляем заказ на сервер: ${JSON.stringify(orderData)}`);
        
        // Проверяем, что все обязательные данные присутствуют
        if (!orderData.name || !orderData.phone || !orderData.items || orderData.items.length === 0) {
            log(`ОШИБКА: Не все обязательные поля заполнены`);
            const errorModal = document.getElementById('error-modal');
            const errorMessage = document.getElementById('error-message');
            errorMessage.textContent = 'Пожалуйста, заполните все обязательные поля (имя, телефон, и выберите товары).';
            errorModal.style.display = 'block';
            return;
        }
        
        // Используем прямой URL для отправки заказа
        const endpointUrl = '/mini_app/process_order';
        log(`Отправляем запрос на: ${endpointUrl}`);
        
        fetch(endpointUrl, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Telegram-Data': tg.initData || '', // Для проверки на сервере
                'X-Requested-With': 'XMLHttpRequest' // Для защиты от CSRF
            },
            body: JSON.stringify(orderData),
            credentials: 'same-origin' // Добавляем передачу куки для сессии
        })
        .then(response => {
            log(`Получен ответ от сервера: ${response.status} ${response.statusText}`);
            if (!response.ok) {
                return response.json().then(errorData => {
                    log(`Ошибка в ответе сервера: ${JSON.stringify(errorData)}`);
                    throw new Error(errorData.error || `Ошибка HTTP: ${response.status}`);
                });
            }
            return response.json();
        })
        .then(data => {
            log(`Заказ успешно отправлен, ID: ${data.orderId}`);
            
            // Переходим к шагу благодарности
            goToStep(6);
            
            // Добавляем информацию о номере заказа в сообщение об успехе
            const orderNumberElement = document.getElementById('order-number');
            if (orderNumberElement) {
                orderNumberElement.textContent = `Номер вашего заказа: ${data.orderId}`;
            }
            
            // Отправляем данные в Telegram и закрываем WebApp через 3 секунды
            setTimeout(() => {
                try {
                    // Устанавливаем флаг для предотвращения дублирования заказа в боте
                    tg.sendData(JSON.stringify({
                        action: 'order_completed',
                        orderId: data.orderId,
                        skipDuplicate: true // Флаг для предотвращения создания дубликата
                    }));
                    
                    log('Данные успешно отправлены в Telegram');
                    
                    setTimeout(() => {
                        tg.close();
                    }, 1000);
                } catch (e) {
                    log(`Ошибка при отправке данных в Telegram: ${e.message}`);
                }
            }, 3000);
        })
        .catch(error => {
            log(`Ошибка при отправке заказа: ${error.message}`);
            
            // Показываем модальное окно с ошибкой вместо алерта
            const errorModal = document.getElementById('error-modal');
            const errorMessage = document.getElementById('error-message');
            errorMessage.textContent = error.message || 'Произошла ошибка при отправке заказа. Пожалуйста, попробуйте позже.';
            errorModal.style.display = 'block';
            
            // Добавляем обработчик закрытия модального окна
            document.getElementById('close-error').addEventListener('click', () => {
                errorModal.style.display = 'none';
                document.getElementById('submit-order').innerHTML = 'Отправить заказ';
                document.getElementById('submit-order').disabled = false;
            });
            
            // Крестик для закрытия окна
            document.querySelector('.close-button').addEventListener('click', () => {
                errorModal.style.display = 'none';
                document.getElementById('submit-order').innerHTML = 'Отправить заказ';
                document.getElementById('submit-order').disabled = false;
            });
        });
    }
    
    // Проверка формата телефона
    function isValidPhone(phone) {
        // Простая проверка: начинается с + и содержит от 10 до 15 цифр
        const phoneRegex = /^\+?\d{10,15}$/;
        return phoneRegex.test(phone.replace(/\s+/g, ''));
    }
    
    // Обновление сводки заказа
    function updateSummary() {
        document.getElementById('summary-name').textContent = document.getElementById('fullName').value;
        document.getElementById('summary-phone').textContent = document.getElementById('phone').value;
        document.getElementById('summary-time').textContent = document.getElementById('callbackTime').value + ':00';
        
        const promoCode = document.getElementById('promoCode').value.trim();
        document.getElementById('summary-promo').textContent = promoCode || 'Не указан';
        
        const summaryItemsElement = document.getElementById('summary-items');
        summaryItemsElement.innerHTML = '';
        
        let totalItems = 0;
        
        cart.forEach(item => {
            const itemElement = document.createElement('div');
            itemElement.className = 'cart-item';
            itemElement.innerHTML = `<div>${item.size}: ${item.quantity} шт.</div>`;
            summaryItemsElement.appendChild(itemElement);
            totalItems += item.quantity;
        });
        
        // Добавляем информацию о скидках
        if (isWholesaleDiscount || promoApplied) {
            const discountElement = document.createElement('div');
            discountElement.style.color = '#28a745';
            discountElement.style.marginTop = '10px';
            
            let discountText = 'Применены скидки: ';
            
            if (isWholesaleDiscount) {
                discountText += 'Оптовая (10%)';
            }
            
            if (promoApplied) {
                if (isWholesaleDiscount) discountText += ', ';
                discountText += `Промокод ${promoApplied}`;
            }
            
            discountElement.textContent = discountText;
            summaryItemsElement.appendChild(discountElement);
        }
        
        log('Обновлена сводка заказа');
    }
    
    // Отправка заказа
    document.getElementById('submit-order').addEventListener('click', () => {
        // Выполняем валидацию данных
        if (!validateStep1() || !validateStep2()) {
            log('Ошибка валидации при отправке заказа');
            return;
        }
        
        updateSummary();
        
        // Показываем индикатор загрузки
        document.getElementById('submit-order').innerHTML = 'Отправка...';
        document.getElementById('submit-order').disabled = true;
        
        // Вызываем функцию submitOrder для отправки заказа на сервер
        submitOrder();
    });

    // Обработчики кнопок переходов между шагами
    document.getElementById('nextToStep2').addEventListener('click', () => {
        if (validateStep1()) {
            goToStep(2);
        }
    });
    
    document.getElementById('backToStep1').addEventListener('click', () => {
        goToStep(1);
    });
    
    document.getElementById('nextToStep3').addEventListener('click', () => {
        if (validateStep2()) {
            goToStep(3);
        }
    });
    
    document.getElementById('backToStep2').addEventListener('click', () => {
        goToStep(2);
    });
    
    document.getElementById('nextToStep4').addEventListener('click', () => {
        goToStep(4);
    });
    
    document.getElementById('backToStep3').addEventListener('click', () => {
        goToStep(3);
    });
    
    document.getElementById('placeOrder').addEventListener('click', () => {
        goToStep(5);
    });
    
    document.getElementById('backToStep4').addEventListener('click', () => {
        goToStep(4);
    });
    
    // Инициализация приложения
    initLogger();
    log('WebApp инициализирована');
    tryGetUserData();
    
    // Начинаем с первого шага
    goToStep(1);
});
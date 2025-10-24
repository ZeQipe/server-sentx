document.addEventListener('DOMContentLoaded', function() {
    // Небольшая задержка для уверенности что DOM полностью загружен
    setTimeout(function() {
        // Проверяем, что мы на главной странице админки
        if (window.location.pathname === '/admin/' || window.location.pathname === '/admin') {
            console.log('На главной странице админки');
            
            // Пробуем разные селекторы для поиска заголовка
            let headerContainer = document.querySelector('#site-name') || 
                                  document.querySelector('#header') ||
                                  document.querySelector('.module h1') ||
                                  document.querySelector('h1');
            
            console.log('Найден header:', headerContainer);
            
            if (headerContainer) {
                // Создаем кнопку
                const button = document.createElement('a');
                button.href = '/admin/llm/message/';
                button.textContent = 'Messages Interface';
                button.style.cssText = `
                    background: #417690;
                    color: white;
                    padding: 8px 16px;
                    border-radius: 4px;
                    text-decoration: none;
                    margin-left: 20px;
                    font-size: 14px;
                    display: inline-block;
                    vertical-align: middle;
                `;
                
                // Пробуем добавить кнопку в разные места
                if (headerContainer.tagName === 'H1') {
                    headerContainer.appendChild(button);
                } else {
                    headerContainer.appendChild(button);
                }
                
                console.log('Кнопка добавлена');
            } else {
                console.log('Header не найден, добавляем кнопку в body');
                // Если не можем найти заголовок, добавляем кнопку в верхнюю часть страницы
                const button = document.createElement('div');
                button.innerHTML = '<a href="/admin/llm/message/" style="position: fixed; top: 10px; right: 10px; background: #417690; color: white; padding: 8px 16px; border-radius: 4px; text-decoration: none; font-size: 14px; z-index: 1000;">Messages Interface</a>';
                document.body.appendChild(button);
            }
        }
        
        // На кастомной странице добавляем кнопку "Home" 
               if (window.location.pathname.includes('/admin/llm/messages-interface/')) {
            // Ищем заголовок на кастомной странице
            const customHeader = document.querySelector('.header__title');
            if (customHeader) {
                // Создаем кнопку Home
                const homeButton = document.createElement('a');
                homeButton.href = '/admin/';
                homeButton.textContent = 'Home';
                homeButton.style.cssText = `
                    color: #f5dd5d;
                    text-decoration: none;
                    margin-right: 20px;
                    font-weight: 300;
                `;
                
                // Вставляем кнопку в начало заголовка
                customHeader.insertBefore(homeButton, customHeader.firstChild);
            }
        }
    }, 100);
});

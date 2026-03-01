import re

# Читаем base.html
with open('templates/base.html', 'r', encoding='utf-8') as f:
    content = f.read()

# Заменяем admin_panel на dashboard
new_content = content.replace("url_for('admin_panel')", "url_for('dashboard')")

# Сохраняем изменения
with open('templates/base.html', 'w', encoding='utf-8') as f:
    f.write(new_content)

print("✅ Ошибка исправлена! Теперь ссылка ведет на dashboard")
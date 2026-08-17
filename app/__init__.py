"""Инициализация приложения."""

from app.utils.inline_navigation import install_global_inline_back_button

# Подключаем UX-страховку до создания любых клавиатур в обработчиках.
install_global_inline_back_button()

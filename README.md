# ArizonaLauncher
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python Version](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

> Лаунчер который совмещает все достоинства всех лаунчеров для Аризоны

## 📋 Описание

Подробное описание того, что делает ваша программа и какие проблемы она решает. 

**Основные возможности:**
- Использует лаунчер Эира чтоб запускать игру
- Умеет редактировать настройки ArizonaPatches
- Имеет кастомные обои
- Имеет внутренний импорт\экспорт настроек патча
- Может открыть сразу путь к игре

## 📦 Установка

### Способ 1: Скачать готовый .exe (для Windows) ПОКА НЕТУ УСТАНОВКИ

1. Перейдите в раздел [Releases](https://github.com/worteng/ArizonaLauncher/releases)
2. Скачайте последнюю версию установки или уже сам лаунчер
3. Запустите его
4. Можете указать путь к игре.

### Способ 2: Из исходного кода
```bash
# Клонируйте репозиторий
git clone https://github.com/worteng/ArizonaLauncher.git
cd ArizonaLauncher

# Создайте виртуальное окружение
python -m venv venv
venv\Scripts\activate     # для Windows

# Установите зависимости
pip install -r requirements.txt

# Запустите программу от админа
python main.py
```

## 🔧 Требования

- **Операционная система:** Windows 10/11 c Microsoft Edge WebView2 Runtime
- **Python:** 3.10 или выше (если запускаете из исходников)
- **Оперативная память:** около 100 мб
- **Свободное место:** 200 МБ

## 🛠️ Технологии
- **Python 3.10+** — основной язык
- **pywebview** — графический интерфейс (WebView2/Edge)
- **requests** — загрузка серверов, новостей с GitHub
- **psutil** — поиск и завершение процесса лаунчера перед запуском
- **tkinter** — диалоги выбора файлов и папок (встроен в Python)

## 🐛 Сообщить о проблеме

Нашли баг? [Создайте issue](https://github.com/worteng/ArizonaLauncher/issues/new) или напишите в [ТГК](https://t.me/HalfikForEveryone)

При создании issue укажите:
- Версию программы
- Операционную систему
- Шаги для воспроизведения проблемы
- Ожидаемое и фактическое поведение

## 📜 Changelog - Полный список изменений будет в [updatenews.txt](updatenews.txt)

## 📄 Лицензия

Этот проект распространяется под лицензией MIT. Подробности в файле [LICENSE](LICENSE).

## 👨‍💻 Автор

**Halfik**
- Email: sergeybires@gmail.com
- Telegram: [@HalfikForEveryone](https://t.me/HalfikForEveryone) в директ

## 🙏 Благодарности

- [Black Jesus](https://www.youtube.com/@BlackJesus1337) — за вдохновение на создание
- Эиру за создание замечательного лаунчера с плагином
- [Dapo Dope](https://www.youtube.com/@DapoShow) — за идею создания функции импорта\экспорта настроек ArizonaPatches

---

**Сделано с уважением для всех пользователей. Даже для тех, кто читает README.**

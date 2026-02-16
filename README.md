# ArizonaLauncher
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python Version](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

> Лаунчер который совмещает все достоинства всех лаунчеров для Аризоны

## 📋 Описание

Подробное описание того, что делает ваша программа и какие проблемы она решает. 

**Основные возможности:**
- ✨ Использует лаунчер Эира чтоб запускать игру
- 🎯 Умеет редактировать настройки ArizonaPatches

## 📦 Установка

### Способ 1: Скачать готовый .exe (для Windows) ПОКА НЕТУ УСТАНОВКИ

1. Перейдите в раздел [Releases](https://github.com/worteng/ArizonaLauncher/releases)
2. Скачайте последнюю версию установки или уже сам лаунчер
3. Запустите его
4. Важно чтоб игра была в стандартном расположении а не в на другом диске. "C:\Users\Пользователь\AppData\Local\Programs\Arizona Games Launcher\bin\arizona"

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

- **Операционная система:** Windows 10/11
- **Python:** 3.10 или выше (если запускаете из исходников)
- **Оперативная память:** около 100 мб
- **Свободное место:** 200 МБ

## 🛠️ Технологии

- **Python** — основной язык
- **Webview** — графический интерфейс
- **Requests** — работа с API
- **psutil** — нахождение Лаунчера от AIR

## 🐛 Сообщить о проблеме

Нашли баг? [Создайте issue](https://github.com/worteng/ArizonaLauncher/issues/new)

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
- Telegram: [@HalfikForEveryone](https://t.me/HalfikForEveryone)

## 🙏 Благодарности

- [Black Jesus](https://www.youtube.com/@BlackJesus1337) — за вдохновение на создание
- Эиру за создание замечательного лаунчера с плагином
- [Dapo Dope](https://www.youtube.com/@DapoShow) — за идею создания функции импорта\экспорта настроек ArizonaPatches

---

**Слелано с уважением для всех кто будет пользоваться**

import os
import sys
import subprocess
import time
import json
import webview
import logging
from pathlib import Path
from threading import Thread
import psutil
import requests
import re

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('arizona_launcher.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class ArizonaLauncher:
    def __init__(self):
        # ~ автоматически заменится на домашнюю директорию пользователя
        self.launcher_path = os.path.expanduser(
            r"~\AppData\Local\Programs\Arizona Games Launcher\bin\arizona\ArizonaLauncher6_byAIR.exe"
        )
        
        self.patches_path = os.path.expanduser(
            r"~\AppData\Local\Programs\Arizona Games Launcher\bin\arizona\preloading_plugins\#ArizonaPatches.json"
        )
        
        self.config = self.load_config()
        
        logger.info(f"Инициализирован лаунчер. Путь: {self.launcher_path}")
    
    def load_config(self):
        """Загружает конфигурацию из файла"""
        config_path = Path('config.json')
        if config_path.exists():
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Ошибка загрузки конфига: {e}")
        return {}
    
    def save_config(self):
        """Сохраняет конфигурацию в файл"""
        try:
            with open('config.json', 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=2, ensure_ascii=False)
            logger.info("Конфигурация сохранена")
        except Exception as e:
            logger.error(f"Ошибка сохранения конфига: {e}")
    
    def is_launcher_available(self):
        """Проверяет, существует ли файл лаунчера"""
        if not os.path.exists(self.launcher_path):
            logger.error(f"Файл лаунчера не найден: {self.launcher_path}")
            return False
        return True
    
    def kill_all_launchers(self):
        """Убивает все запущенные процессы лаунчера"""
        try:
            for proc in psutil.process_iter(['pid', 'name']):
                try:
                    if 'arizonalauncher' in proc.info['name'].lower():
                        logger.info(f"Завершаем процесс: {proc.info['name']} (PID: {proc.info['pid']})")
                        proc.kill()
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    pass
            time.sleep(1)
        except Exception as e:
            logger.error(f"Ошибка при завершении процессов: {e}")
    
    def launch_game(self, nickname, server_data=None):
        """Запускает игру через командную строку"""
        try:
            logger.info(f"Запуск игры для {nickname}")
            
            # Проверяем лаунчер
            if not self.is_launcher_available():
                return {"success": False, "message": f"Лаунчер не найден: {self.launcher_path}"}
            
            # Валидация никнейма
            if not nickname or len(nickname.strip()) == 0:
                return {"success": False, "message": "Введите никнейм"}
            
            nickname = nickname.strip()
            if len(nickname) > 20:
                nickname = nickname[:20]
            
            # Параметры по умолчанию
            server_ip = "payson.arizona-rp.com"
            server_port = 7777
            
            # Если передан сервер
            if server_data:
                server_ip = server_data.get('ip', 'payson.arizona-rp.com')
                server_port = server_data.get('port', 7777)
            
            # Формируем команду
            cmd = [
                self.launcher_path,
                "-c",
                "-h", server_ip,
                "-p", str(server_port),
                "-mem", "4096",  # 4GB памяти
                "-n", nickname,
                "-arizona",
                "-x",
                "-window",
                "-cdn", "1,1,1"
            ]
            
            logger.info(f"Команда запуска: {' '.join(cmd)}")
            
            # Запускаем процесс
            try:
                # Сначала убиваем все старые процессы
                self.kill_all_launchers()
                time.sleep(1)
                
                # Запускаем новый процесс
                process = subprocess.Popen(
                    cmd,
                    cwd=os.path.dirname(self.launcher_path),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
                
                # Даем время на запуск
                time.sleep(2)
                
                # Проверяем, запустился ли процесс
                if process.poll() is None:
                    logger.info(f"Лаунчер запущен успешно (PID: {process.pid})")
                    
                    # Сохраняем последний никнейм и сервер
                    self.config['last_nickname'] = nickname
                    if server_data:
                        self.config['last_server'] = server_data.get('number')
                    self.save_config()
                    
                    return {
                        "success": True, 
                        "message": f"Игра запускается для {nickname} на сервере {server_ip}",
                        "pid": process.pid
                    }
                else:
                    # Пробуем получить ошибку
                    stdout, stderr = process.communicate()
                    error_msg = stderr.decode('utf-8', errors='ignore') if stderr else "Неизвестная ошибка"
                    logger.error(f"Лаунчер завершился с ошибкой: {error_msg}")
                    return {"success": False, "message": f"Ошибка запуска: {error_msg[:100]}"}
                    
            except Exception as e:
                logger.error(f"Исключение при запуске процесса: {e}")
                return {"success": False, "message": f"Ошибка запуска: {str(e)}"}
                
        except Exception as e:
            error_msg = f"Критическая ошибка: {str(e)}"
            logger.error(error_msg)
            return {"success": False, "message": error_msg}
    
    def read_patches(self):
        """Читает файл ArizonaPatches.json, удаляя комментарии"""
        try:
            if not os.path.exists(self.patches_path):
                logger.error(f"Файл ArizonaPatches.json не найден: {self.patches_path}")
                return {"success": False, "message": "Файл не найден"}
            
            with open(self.patches_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Удаляем однострочные комментарии //
            content_no_comments = re.sub(r'^\s*//.*$', '', content, flags=re.MULTILINE)
            # Удаляем пустые строки и лишние пробелы
            content_no_comments = '\n'.join(line for line in content_no_comments.split('\n') if line.strip())
            
            data = json.loads(content_no_comments)
            logger.info("ArizonaPatches.json успешно прочитан")
            return data
        except json.JSONDecodeError as e:
            logger.error(f"Ошибка парсинга JSON после удаления комментариев: {e}")
            return {"success": False, "message": f"Ошибка парсинга: {str(e)}"}
        except Exception as e:
            logger.error(f"Ошибка чтения ArizonaPatches.json: {e}")
            return {"success": False, "message": str(e)}
    
    def write_patches(self, data):
        """Записывает изменения в ArizonaPatches.json"""
        try:
            with open(self.patches_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
            logger.info("ArizonaPatches.json успешно обновлен")
            return {"success": True, "message": "Настройки сохранены"}
        except Exception as e:
            logger.error(f"Ошибка записи ArizonaPatches.json: {e}")
            return {"success": False, "message": str(e)}

class WebViewApp:
    def __init__(self):
        self.launcher = ArizonaLauncher()
        logger.info("WebViewApp инициализирован")
    
    def start_game(self, nickname, server_data=None):
        """Метод для вызова из JavaScript"""
        logger.info(f"Запрос на запуск игры: {nickname}, сервер: {server_data}")
        
        # Запускаем в отдельном потоке
        def run_in_thread():
            try:
                result = self.launcher.launch_game(nickname, server_data)
                logger.info(f"Результат запуска: {result}")
            except Exception as e:
                logger.error(f"Ошибка в потоке запуска: {e}")
        
        thread = Thread(target=run_in_thread)
        thread.daemon = True
        thread.start()
        
        return {"success": True, "message": "Запуск начат...", "status": "processing"}
    
    def get_config(self):
        """Возвращает текущую конфигурацию"""
        return {
            "launcher_path": self.launcher.launcher_path,
            "last_nickname": self.launcher.config.get('last_nickname', ''),
            "last_server": self.launcher.config.get('last_server', 15)
        }
    
    def update_nickname(self, nickname):
        """Обновляет никнейм в конфигурации"""
        self.launcher.config['last_nickname'] = nickname
        self.launcher.save_config()
        return {"success": True}
    
    def get_servers(self):
        """Загружает список серверов с API"""
        try:
            logger.info("=== НАЧАЛО ЗАГРУЗКИ СЕРВЕРОВ ===")
            url = "https://arizona-ping.react.group/desktop/ping/Arizona/ping.json"
            logger.info(f"URL API: {url}")
            
            logger.info("Отправка запроса...")
            response = requests.get(url, timeout=10)
            logger.info(f"Код ответа: {response.status_code}")
            
            if response.status_code != 200:
                logger.error(f"Неуспешный код ответа: {response.status_code}")
                logger.error(f"Текст ответа: {response.text[:200]}")
                return None
            
            logger.info("Парсинг JSON...")
            data = response.json()
            logger.info(f"Тип данных: {type(data)}")
            logger.info(f"Количество записей в JSON: {len(data)}")
            
            # API возвращает массив серверов в ключе 'query'
            if 'query' in data and isinstance(data['query'], list):
                logger.info(f"Формат API: массив в ключе 'query'")
                server_list = data['query']
            elif isinstance(data, list):
                logger.info(f"Формат API: прямой массив")
                server_list = data
            elif isinstance(data, dict):
                logger.info(f"Формат API: объект с ключами")
                server_list = list(data.values())
            else:
                logger.error(f"Неизвестный формат данных: {type(data)}")
                return None
            
            logger.info(f"Количество серверов в списке: {len(server_list)}")
            
            # Показываем первый сервер для примера
            if server_list:
                logger.info(f"Пример первого сервера: {server_list[0]}")
            
            # Преобразуем в нужный формат
            servers = []
            for idx, server in enumerate(server_list):
                try:
                    # Проверяем что это словарь
                    if not isinstance(server, dict):
                        logger.warning(f"Сервер {idx} не является словарем: {type(server)}")
                        continue
                    
                    server_id = server.get('number') or server.get('serverNumber') or server.get('id', idx + 1)
                    server_name = server.get('name', f'Server {server_id}')
                    server_online = server.get('online') or server.get('playersOnline', 0)
                    server_queue = server.get('queue') or server.get('queueLength', 0)
                    server_max = server.get('maxplayers') or server.get('maxPlayers') or server.get('maxonline', 1000)
                    server_ip = server.get('ip', f'server{server_id}.arizona-rp.com')
                    server_port = server.get('port', 7777)
                    
                    # Рекомендованные серверы
                    is_recommended = server.get('recomend', False) or server.get('recommended', False) or (server_online > 400 and server_queue == 0)
                    
                    servers.append({
                        'number': server_id,
                        'name': server_name,
                        'online': server_online,
                        'queue': server_queue,
                        'recommended': is_recommended,
                        'ip': server_ip,
                        'port': server_port,
                        'maxplayers': server_max
                    })
                except Exception as parse_error:
                    logger.error(f"Ошибка парсинга сервера {idx}: {parse_error}")
                    continue
            
            logger.info(f"✅ Успешно обработано серверов: {len(servers)}")
            
            if servers:
                # Показываем первые 3 для проверки
                for i, s in enumerate(servers[:3]):
                    logger.info(f"  Сервер {i+1}: {s['name']} - {s['online']} онлайн")
            
            logger.info("=== КОНЕЦ ЗАГРУЗКИ СЕРВЕРОВ ===")
            return servers
            
        except ImportError as e:
            logger.error(f"❌ Модуль requests не установлен: {e}")
            logger.error("Установите: pip install requests")
            return None
        except requests.exceptions.Timeout as e:
            logger.error(f"❌ Таймаут запроса: {e}")
            return None
        except requests.exceptions.ConnectionError as e:
            logger.error(f"❌ Ошибка подключения: {e}")
            logger.error("Проверьте интернет соединение")
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Ошибка HTTP запроса: {e}")
            return None
        except ValueError as e:
            logger.error(f"❌ Ошибка парсинга JSON: {e}")
            logger.error(f"Ответ сервера: {response.text[:500]}")
            return None
        except Exception as e:
            logger.error(f"❌ Неожиданная ошибка: {type(e).__name__}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None
    
    def read_patches(self):
        """Метод для чтения ArizonaPatches.json из JS"""
        return self.launcher.read_patches()
    
    def write_patches(self, data):
        """Метод для записи ArizonaPatches.json из JS"""
        return self.launcher.write_patches(data)

def main():
    logger.info("Запуск Arizona RP Launcher...")
    
    # Создаем экземпляр приложения
    app = WebViewApp()
    
    # Проверяем путь к лаунчеру
    if not app.launcher.is_launcher_available():
        logger.warning(f"Лаунчер не найден!")
    
    # Создаем окно webview
    try:
        window = webview.create_window(
            '🚀 Arizona RP Launcher',
            'index.html',
            js_api=app,
            width=1200,
            height=800,
            resizable=True,
            fullscreen=False,
            min_size=(800, 600)
        )
        
        logger.info("Окно создано, запуск интерфейса...")
        
        # Запускаем приложение
        webview.start(debug=False)
        
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        input("Нажмите Enter для выхода...")

if __name__ == '__main__':
    main()
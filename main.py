import os, sys, subprocess, time, json, webview, logging, psutil, requests, re
from pathlib import Path
from threading import Thread
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s',
                    handlers=[logging.FileHandler('arizona_launcher.log'), logging.StreamHandler()])
logger = logging.getLogger(__name__)

class ArizonaLauncher:
    def __init__(self):
        self.documents_path = str(Path.home() / "Documents" / "ArizonaLauncher")
        Path(self.documents_path).mkdir(parents=True, exist_ok=True)
        self.config_path = os.path.join(self.documents_path, "config.json")
        self.config = self.load_config()
        self.game_path = self.config.get('game_path', '')
        self.launcher_path = self.config.get('launcher_path', '')
        if not self.game_path or not self.launcher_path:
            self.auto_detect_game_paths()
        self.patches_path = os.path.join(os.path.dirname(self.game_path), "preloading_plugins", "#ArizonaPatches.json") if self.game_path else ""

    def load_config(self):
        defaults = {'last_nickname': '', 'last_server': 15, 'game_path': '', 'launcher_path': '',
                    'launch_params': {'memory': 4096, 'widescreen': False, 'texture_mode': False, 'color_depth_16': False,
                                      'allow_hdr': False, 'enable_grass': False, 'ldo': False, 'seasons': False,
                                      'graphics': False, 'auth_cef_enable': False, 'window_mode': True, 'cdn': '1,1,1'},
                    'launcher_settings': {'live_wallpaper': True, 'waves': True, 'particles': True, 'bg_image': None}}
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    cfg = json.load(f)
                    for k, v in defaults.items():
                        if k not in cfg: cfg[k] = v
                    if 'launch_params' in cfg:
                        for k, v in defaults['launch_params'].items():
                            if k not in cfg['launch_params']: cfg['launch_params'][k] = v
                    if 'launcher_settings' in cfg:
                        for k, v in defaults['launcher_settings'].items():
                            if k not in cfg['launcher_settings']: cfg['launcher_settings'][k] = v
                    return cfg
            except Exception as e: logger.error(f"Config load error: {e}")
        return defaults

    def save_config(self):
        try:
            with open(self.config_path, 'w', encoding='utf-8') as f: json.dump(self.config, f, indent=2, ensure_ascii=False)
        except Exception as e: logger.error(f"Config save error: {e}")

    def auto_detect_game_paths(self):
        searches = [Path.home() / "AppData" / "Local" / "Programs" / "Arizona Games Launcher",
                    Path("C:/Program Files/Arizona Games Launcher"), Path("C:/Program Files (x86)/Arizona Games Launcher"),
                    Path("D:/Games/Arizona"), Path("C:/Games/Arizona")] + [Path(f"{d}/") for d in ['C:', 'D:', 'E:', 'F:']]
        found_gta = found_launcher = None
        for base in searches:
            if not base.exists(): continue
            try:
                for gta in base.rglob("gta_sa.exe"):
                    if "temp" not in str(gta).lower() and "cache" not in str(gta).lower():
                        found_gta = gta
                        launch = gta.parent / "ArizonaLauncher6_byAIR.exe"
                        if launch.exists(): found_launcher = launch
                        break
                if found_gta and found_launcher: break
            except (PermissionError, OSError): continue
        if found_gta: self.game_path = self.config['game_path'] = str(found_gta)
        if found_launcher: self.launcher_path = self.config['launcher_path'] = str(found_launcher)
        if found_gta or found_launcher: self.save_config()
        return bool(found_gta and found_launcher)

    def set_game_paths(self, game, launcher):
        self.game_path, self.launcher_path = game, launcher
        self.config['game_path'], self.config['launcher_path'] = game, launcher
        if self.game_path:
            self.patches_path = os.path.join(os.path.dirname(self.game_path), "preloading_plugins", "#ArizonaPatches.json")
        self.save_config()

    def kill_all_launchers(self):
        for proc in psutil.process_iter(['pid', 'name']):
            try:
                if 'arizonalauncher' in proc.info['name'].lower(): proc.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess): pass
        time.sleep(1)

    def launch_game(self, nickname, server_data=None, launch_params=None):
        if not self.launcher_path or not os.path.exists(self.launcher_path):
            return {"success": False, "message": "Launcher not found"}
        if not nickname or len(nickname.strip()) == 0:
            return {"success": False, "message": "Enter nickname"}
        nickname = nickname.strip()[:20]
        srv_ip = server_data.get('ip', 'payson.arizona-rp.com') if server_data else 'payson.arizona-rp.com'
        srv_port = server_data.get('port', 7777) if server_data else 7777
        params = launch_params or self.config.get('launch_params', {})
        cmd = [self.launcher_path, "-c", "-h", srv_ip, "-p", str(srv_port), "-mem", str(params.get('memory', 4096)),
               "-n", nickname, "-arizona", "-x"]
        flags = {'widescreen': '-widescreen', 'texture_mode': '-t', 'color_depth_16': '-16bpp', 'allow_hdr': '-allow_hdr',
                 'enable_grass': '-enable_grass', 'ldo': '-ldo', 'seasons': '-seasons', 'graphics': '-graphics',
                 'auth_cef_enable': '-auth_cef_enable', 'window_mode': '-window'}
        for k, v in flags.items():
            if params.get(k, False): cmd.append(v)
        cmd.extend(["-cdn", params.get('cdn', '1,1,1')])
        try:
            self.kill_all_launchers()
            proc = subprocess.Popen(cmd, cwd=os.path.dirname(self.launcher_path), creationflags=subprocess.CREATE_NO_WINDOW)
            time.sleep(2)
            if proc.poll() is None:
                self.config['last_nickname'] = nickname
                if server_data: self.config['last_server'] = server_data.get('number')
                self.config['launch_params'] = params
                self.save_config()
                return {"success": True, "message": f"Launching for {nickname}", "pid": proc.pid}
            else:
                return {"success": False, "message": "Launcher crashed immediately"}
        except Exception as e: return {"success": False, "message": str(e)}

    def read_patches(self):
        logger.info(f"read_patches: patches_path='{self.patches_path}'")
        logger.info(f"read_patches: game_path='{self.game_path}'")

        if not self.patches_path:
            return {"success": False, "message": "patches_path пустой", "path": ""}

        if not os.path.exists(self.patches_path):
            return {"success": False, "message": f"Файл не найден: {self.patches_path}", "path": self.patches_path}

        try:
            with open(self.patches_path, 'r', encoding='utf-8') as f:
                raw = f.read()
            logger.info(f"read_patches: {len(raw)} байт, начало: {raw[:300]!r}")

            cleaned = re.sub(r'^\s*//.*$', '', raw, flags=re.MULTILINE)
            cleaned = '\n'.join(line for line in cleaned.split('\n') if line.strip())
            logger.info(f"read_patches: после очистки: {cleaned[:300]!r}")

            data = json.loads(cleaned)
            logger.info(f"read_patches: OK — {len(data)} ключей: {list(data.keys())}")
            return {"success": True, "data": data, "path": self.patches_path, "keys_count": len(data)}
        except Exception as e:
            logger.error(f"read_patches ОШИБКА: {e}")
            return {"success": False, "message": str(e), "path": self.patches_path}

    def write_patches(self, data):
        if not self.patches_path: return {"success": False, "message": "Path not set"}
        try:
            with open(self.patches_path, 'w', encoding='utf-8') as f: json.dump(data, f, indent=4, ensure_ascii=False)
            return {"success": True, "message": "Saved"}
        except Exception as e: return {"success": False, "message": str(e)}

class WebViewApp:
    def __init__(self): self.launcher = ArizonaLauncher()

    def start_game(self, nickname, server_data=None, launch_params=None):
        def run():
            try: self.launcher.launch_game(nickname, server_data, launch_params)
            except Exception as e: logger.error(f"Launch error: {e}")
        Thread(target=run, daemon=True).start()
        return {"success": True, "message": "Starting...", "status": "processing"}

    def get_config(self):
        return {"launcher_path": self.launcher.launcher_path, "game_path": self.launcher.game_path,
                "last_nickname": self.launcher.config.get('last_nickname', ''),
                "last_server": self.launcher.config.get('last_server', 15),
                "launch_params": self.launcher.config.get('launch_params', {}),
                "paths_configured": bool(self.launcher.launcher_path and self.launcher.game_path)}

    def get_saved_data(self):
        """Возвращает сохраненные данные (никнейм, сервер)"""
        return {
            "success": True,
            "nickname": self.launcher.config.get('last_nickname', ''),
            "server": self.launcher.config.get('last_server', 15)
        }

    def get_launcher_settings(self):
        return {"success": True, "data": self.launcher.config.get('launcher_settings', {})}

    def save_launcher_settings(self, settings):
        self.launcher.config['launcher_settings'] = settings
        self.launcher.save_config()
        return {"success": True}

    def set_game_paths(self, game, launcher):
        self.launcher.set_game_paths(game, launcher)
        return {"success": True, "message": "Paths set"}

    def auto_detect_paths(self):
        success = self.launcher.auto_detect_game_paths()
        return {"success": success, "message": "Found" if success else "Not found",
                "game_path": self.launcher.game_path, "launcher_path": self.launcher.launcher_path}

    def select_game_path(self):
        """Открыть диалог выбора папки с игрой"""
        try:
            import tkinter as tk
            from tkinter import filedialog

            root = tk.Tk()
            root.withdraw()
            root.attributes('-topmost', True)

            folder_path = filedialog.askdirectory(
                title="Выберите папку с игрой (где находится gta_sa.exe)"
            )
            root.destroy()

            if not folder_path:
                return {"success": False, "message": "Папка не выбрана"}

            game_exe = os.path.join(folder_path, "gta_sa.exe")
            launcher_exe = os.path.join(folder_path, "ArizonaLauncher6_byAIR.exe")

            if not os.path.exists(game_exe):
                return {"success": False, "message": "gta_sa.exe не найден в выбранной папке"}

            if not os.path.exists(launcher_exe):
                return {"success": False, "message": "ArizonaLauncher6_byAIR.exe не найден в выбранной папке"}

            self.launcher.set_game_paths(game_exe, launcher_exe)
            return {"success": True, "message": f"Путь установлен: {folder_path}"}
        except Exception as e:
            logger.error(f"Error selecting game path: {e}")
            return {"success": False, "message": str(e)}

    def select_bg_image(self):
        """Выбрать картинку для фона лаунчера, вернуть base64 data URL"""
        try:
            import tkinter as tk
            from tkinter import filedialog
            import base64, mimetypes
            root = tk.Tk()
            root.withdraw()
            root.attributes('-topmost', True)
            file_path = filedialog.askopenfilename(
                title="Выбрать картинку для фона",
                filetypes=[
                    ("Изображения", "*.png *.jpg *.jpeg *.webp *.bmp"),
                    ("Все файлы", "*.*")
                ]
            )
            root.destroy()
            if not file_path:
                return {"success": False, "message": "Отменено"}
            mime = mimetypes.guess_type(file_path)[0] or "image/jpeg"
            with open(file_path, 'rb') as f:
                data = base64.b64encode(f.read()).decode('utf-8')
            data_url = f"data:{mime};base64,{data}"
            return {"success": True, "data_url": data_url}
        except Exception as e:
            logger.error(f"select_bg_image error: {e}")
            return {"success": False, "message": str(e)}

    def export_patches(self, data):
        """Сохранить настройки патчей в файл через диалог"""
        try:
            import tkinter as tk
            from tkinter import filedialog
            root = tk.Tk()
            root.withdraw()
            root.attributes('-topmost', True)
            file_path = filedialog.asksaveasfilename(
                title="Сохранить настройки патчей",
                defaultextension=".json",
                initialfile="ArizonaPatches_settings.json",
                filetypes=[("JSON файл", "*.json"), ("Все файлы", "*.*")]
            )
            root.destroy()
            if not file_path:
                return {"success": False, "message": "Отменено"}
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
            return {"success": True, "message": f"Сохранено: {file_path}"}
        except Exception as e:
            logger.error(f"export_patches error: {e}")
            return {"success": False, "message": str(e)}

    def import_patches(self):
        """Загрузить настройки патчей из файла через диалог"""
        try:
            import tkinter as tk
            from tkinter import filedialog
            root = tk.Tk()
            root.withdraw()
            root.attributes('-topmost', True)
            file_path = filedialog.askopenfilename(
                title="Открыть файл настроек патчей",
                filetypes=[("JSON файл", "*.json"), ("Все файлы", "*.*")]
            )
            root.destroy()
            if not file_path:
                return {"success": False, "message": "Отменено"}
            with open(file_path, 'r', encoding='utf-8') as f:
                raw = f.read()
            cleaned = re.sub(r'^\s*//.*$', '', raw, flags=re.MULTILINE)
            cleaned = '\n'.join(line for line in cleaned.split('\n') if line.strip())
            data = json.loads(cleaned)
            bool_count = sum(1 for v in data.values() if isinstance(v, bool))
            if bool_count == 0:
                return {"success": False, "message": "Файл не содержит настроек патчей"}
            return {"success": True, "data": data, "keys_count": bool_count}
        except Exception as e:
            logger.error(f"import_patches error: {e}")
            return {"success": False, "message": str(e)}

    def open_game_folder(self):
        """Открыть папку с игрой в проводнике"""
        try:
            if not self.launcher.game_path or not os.path.exists(self.launcher.game_path):
                return {"success": False, "message": "Путь к игре не установлен"}
            
            game_dir = os.path.dirname(self.launcher.game_path)
            if sys.platform == 'win32':
                os.startfile(game_dir)
            elif sys.platform == 'darwin':  # macOS
                subprocess.Popen(['open', game_dir])
            else:  # linux
                subprocess.Popen(['xdg-open', game_dir])
            
            return {"success": True, "message": "Папка открыта"}
        except Exception as e:
            logger.error(f"Error opening folder: {e}")
            return {"success": False, "message": str(e)}

    def update_nickname(self, nickname):
        self.launcher.config['last_nickname'] = nickname
        self.launcher.save_config()
        return {"success": True}

    def update_launch_params(self, params):
        self.launcher.config['launch_params'] = params
        self.launcher.save_config()
        return {"success": True}

    def read_launch_params(self):
        """Возвращает параметры запуска"""
        return self.launcher.config.get('launch_params', {})

    def get_servers(self):
        try:
            resp = requests.get("https://arizona-ping.react.group/desktop/ping/Arizona/ping.json", timeout=10)
            if resp.status_code != 200: return None
            data = resp.json()
            server_list = data.get('query', data) if isinstance(data, dict) else data
            if not isinstance(server_list, list): return None
            servers = []
            for s in server_list:
                if not isinstance(s, dict): continue
                servers.append({
                    'number': s.get('number') or s.get('serverNumber') or s.get('id', 1),
                    'name': s.get('name', 'Server'),
                    'online': s.get('online') or s.get('playersOnline', 0),
                    'queue': s.get('queue') or s.get('queueLength', 0),
                    'recommended': s.get('recomend') or s.get('recommended') or False,
                    'ip': s.get('ip', f"server{s.get('number', 1)}.arizona-rp.com"),
                    'port': s.get('port', 7777),
                    'maxplayers': s.get('maxplayers') or s.get('maxPlayers') or 1000
                })
            return servers
        except Exception as e: logger.error(f"Server fetch error: {e}"); return None

    def get_launcher_news(self):
        print("Функция get_launcher_news вызвана")
        logger.info("Функция get_launcher_news вызвана")

        """Загрузка новостей лаунчера с GitHub (устойчивая версия)"""
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

        urls = [
            "https://raw.githubusercontent.com/worteng/ArizonaLauncher/main/updatenews.txt",
            "https://raw.githubusercontent.com/worteng/ArizonaLauncher/refs/heads/main/updatenews.txt",
            "https://github.com/worteng/ArizonaLauncher/raw/main/updatenews.txt"
        ]

        for url in urls:
            try:
                logger.info(f"Пробуем загрузить новости: {url}")
                
                response = requests.get(
                    url,
                    timeout=20,
                    headers={
                        "Cache-Control": "no-cache",
                        "Pragma": "no-cache",
                        "User-Agent": "Mozilla/5.0"
                    },
                    verify=False  # отключаем SSL проверку (частая проблема)
                )

                logger.info(f"Статус ответа: {response.status_code}")

                if response.status_code == 200 and response.text.strip():
                    return {
                        "success": True,
                        "text": response.text
                    }

            except Exception as e:
                logger.error(f"Ошибка при загрузке с {url}: {e}")

        return {
            "success": False,
            "message": "Не удалось загрузить новости (проверьте интернет или блокировку GitHub)"
        }


    def read_patches(self): return self.launcher.read_patches()
    def write_patches(self, data): return self.launcher.write_patches(data)
    

def main():
    app = WebViewApp()
    try:
        window = webview.create_window('Arizona RP Launcher', 'index.html', js_api=app, width=1200, height=800,
                                       resizable=True, fullscreen=False, min_size=(800, 600))
        webview.start(debug=False)
    except Exception as e:
        logger.error(f"Error: {e}")
        input("Press Enter to exit...")

if __name__ == '__main__':
    main()

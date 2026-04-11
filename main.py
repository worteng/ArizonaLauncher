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
                                      'graphics': False, 'auth_cef_enable': False, 'window_mode': True, 'cdn': '1,1,1',
                                      # v7 параметры
                                      'enable_new_grass': False, 'old_window': False, 'use_d3dx9_43': False,
                                      'show_dialog_ids': False, 'offcef': False, 'modern_scale': False},
                    'launcher_settings': {'bg_image': None}}
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
        """Быстрый поиск по известным путям установки Arizona Games Launcher."""
        GAME_SUBPATH = Path("bin") / "arizona"

        # Точные известные пути (без rglob — мгновенно)
        base_candidates = [
            Path.home() / "AppData" / "Local" / "Programs" / "Arizona Games Launcher",
            Path("C:/Program Files/Arizona Games Launcher"),
            Path("C:/Program Files (x86)/Arizona Games Launcher"),
        ]

        found_gta = found_launcher = None

        for base in base_candidates:
            game_dir = base / GAME_SUBPATH
            gta = game_dir / "gta_sa.exe"
            if gta.exists():
                found_gta = gta
                launch_v7 = game_dir / "ArizonaLauncher7.0_byAIR.exe"
                launch_v6 = game_dir / "ArizonaLauncher6_byAIR.exe"
                if launch_v7.exists():
                    found_launcher = launch_v7
                elif launch_v6.exists():
                    found_launcher = launch_v6
                break

        if found_gta: self.game_path = self.config['game_path'] = str(found_gta)
        if found_launcher: self.launcher_path = self.config['launcher_path'] = str(found_launcher)
        if found_gta or found_launcher: self.save_config()
        return bool(found_gta)  # достаточно найти gta_sa.exe

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

    def get_launcher_version(self):
        """Возвращает 'v7' или 'v6' в зависимости от установленного лаунчера.
        Логика:
        1. Если есть папка preloading_plugins с файлами (dll и конфиг)
        2. Проверяем какой лаунчер установлен в корневой папке игры
        3. Если найден v7 -> возвращаем 'v7', если v6 -> 'v6'
        4. Если лаунчера нет или папки preloading нет -> 'v6' (по умолчанию)
        """
        logger.info("[get_launcher_version] Определение версии лаунчера")
        
        if not self.game_path:
            logger.info("[get_launcher_version] game_path не установлен, возвращаем v6 по умолчанию")
            return "v6"
        
        game_dir = os.path.dirname(self.game_path)
        plugins_dir = os.path.join(game_dir, "preloading_plugins")
        
        logger.info(f"[get_launcher_version] Проверка папки: {plugins_dir}")
        
        # Проверяем наличие папки preloading_plugins с файлами
        if os.path.isdir(plugins_dir) and os.listdir(plugins_dir):
            logger.info(f"[get_launcher_version] Папка preloading_plugins найдена, файлов: {len(os.listdir(plugins_dir))}")
            # Проверяем какой лаунчер установлен
            launcher_v7 = os.path.join(game_dir, "ArizonaLauncher7.0_byAIR.exe")
            launcher_v6 = os.path.join(game_dir, "ArizonaLauncher6_byAIR.exe")
            
            if os.path.exists(launcher_v7):
                logger.info(f"[get_launcher_version] Найден лаунчер v7: {launcher_v7}")
                return "v7"
            elif os.path.exists(launcher_v6):
                logger.info(f"[get_launcher_version] Найден лаунчер v6: {launcher_v6}")
                return "v6"
            else:
                logger.info("[get_launcher_version] Лаунчер не найден, возвращаем v6 по умолчанию")
        else:
            logger.info("[get_launcher_version] Папка preloading_plugins не найдена или пуста, возвращаем v6 по умолчанию")
        
        return "v6"

    def launch_game(self, nickname, server_data=None, launch_params=None):
        if not self.launcher_path or not os.path.exists(self.launcher_path):
            return {"success": False, "message": "Launcher not found"}
        if not nickname or len(nickname.strip()) == 0:
            return {"success": False, "message": "Enter nickname"}
        nickname = nickname.strip()[:20]
        srv_ip = server_data.get('ip', 'payson.arizona-rp.com') if server_data else 'payson.arizona-rp.com'
        srv_port = server_data.get('port', 7777) if server_data else 7777
        params = launch_params or self.config.get('launch_params', {})
        is_v7 = self.get_launcher_version() == "v7"

        cmd = [self.launcher_path, "-c", "-h", srv_ip, "-p", str(srv_port), "-mem", str(params.get('memory', 4096)),
               "-n", nickname, "-arizona", "-x"]

        # Общие флаги для v6 и v7
        common_flags = {
            'widescreen': '-widescreen', 'texture_mode': '-t', 'color_depth_16': '-16bpp',
            'allow_hdr': '-allow_hdr', 'enable_grass': '-enable_grass', 'ldo': '-ldo',
            'seasons': '-seasons', 'graphics': '-graphics', 'auth_cef_enable': '-auth_cef_enable',
        }
        for k, v in common_flags.items():
            if params.get(k, False): cmd.append(v)

        # Оконный режим: -window и -old_window взаимоисключающие
        # old_window доступен только в v7
        if is_v7 and params.get('old_window', False):
            cmd.append('-old_window')
        elif params.get('window_mode', False):
            cmd.append('-window')

        # Флаги только для v7
        if is_v7:
            v7_flags = {
                'enable_new_grass': '-enable_new_grass',
                'use_d3dx9_43':     '-use_d3dx9_43',
                'show_dialog_ids':  '-show_dialog_ids',
                'offcef':           '-offcef',
                'modern_scale':     '-modern_scale',
            }
            for k, v in v7_flags.items():
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
            # Создаём бэкап перед записью (если файл уже существует)
            if os.path.exists(self.patches_path):
                self._create_patches_backup()
            with open(self.patches_path, 'w', encoding='utf-8') as f: json.dump(data, f, indent=4, ensure_ascii=False)
            return {"success": True, "message": "Saved"}
        except Exception as e: return {"success": False, "message": str(e)}

    def _create_patches_backup(self, label: str = ""):
        """Сохраняет текущий #ArizonaPatches.json в папку бэкапов. Максимум 15 штук."""
        MAX_BACKUPS = 15
        try:
            backup_dir = Path(self.documents_path) / "backups"
            backup_dir.mkdir(parents=True, exist_ok=True)

            from datetime import datetime
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            suffix = f"_{label}" if label else ""
            backup_name = f"patches_{ts}{suffix}.json"
            backup_path = backup_dir / backup_name

            import shutil
            shutil.copy2(self.patches_path, backup_path)
            logger.info(f"_create_patches_backup: {backup_path}")

            # Удаляем старые если больше MAX_BACKUPS
            all_backups = sorted(backup_dir.glob("patches_*.json"), key=lambda p: p.stat().st_mtime)
            while len(all_backups) > MAX_BACKUPS:
                all_backups[0].unlink(missing_ok=True)
                all_backups.pop(0)

            return str(backup_path)
        except Exception as e:
            logger.warning(f"_create_patches_backup error: {e}")
            return None

    def list_patches_backups(self):
        """Возвращает список бэкапов (новые первыми)."""
        try:
            backup_dir = Path(self.documents_path) / "backups"
            if not backup_dir.exists():
                return []
            files = sorted(backup_dir.glob("patches_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
            result = []
            from datetime import datetime
            for f in files:
                try:
                    mtime = datetime.fromtimestamp(f.stat().st_mtime)
                    result.append({
                        "filename": f.name,
                        "path": str(f),
                        "date": mtime.strftime("%d.%m.%Y %H:%M:%S"),
                        "size": f.stat().st_size,
                    })
                except Exception:
                    continue
            return result
        except Exception as e:
            logger.warning(f"list_patches_backups error: {e}")
            return []

    def restore_patches_backup(self, filename: str):
        """Восстанавливает патчи из бэкапа."""
        try:
            backup_dir = Path(self.documents_path) / "backups"
            backup_path = backup_dir / filename
            if not backup_path.exists():
                return {"success": False, "message": f"Бэкап не найден: {filename}"}
            with open(backup_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            # Создаём бэкап текущего перед восстановлением
            if self.patches_path and os.path.exists(self.patches_path):
                self._create_patches_backup(label="before_restore")
            result = self.write_patches(data)
            if result["success"]:
                logger.info(f"restore_patches_backup: восстановлен {filename}")
                return {"success": True, "data": data, "message": f"Восстановлен: {filename}"}
            return result
        except Exception as e:
            logger.error(f"restore_patches_backup error: {e}")
            return {"success": False, "message": str(e)}

    def delete_patches_backup(self, filename: str):
        """Удаляет конкретный бэкап."""
        try:
            backup_dir = Path(self.documents_path) / "backups"
            backup_path = backup_dir / filename
            if not backup_path.exists():
                return {"success": False, "message": "Файл не найден"}
            backup_path.unlink()
            return {"success": True}
        except Exception as e:
            return {"success": False, "message": str(e)}


class WebViewApp:
    def __init__(self): self.launcher = ArizonaLauncher()
    
    def is_gta_running(self):
        running = any('gta_sa' in p.info['name'].lower()
                    for p in psutil.process_iter(['name'])
                    if p.info['name'])
        was = getattr(self, '_gta_was_running', False)
        self._gta_was_running = running
        return {"running": running, "was_running": was}

    def restore_window(self):
        """Разворачивает окно лаунчера. Останавливает трей если активен."""
        try:
            # Остановить трей если активен
            if getattr(self, '_tray_icon', None):
                try: self._tray_icon.stop()
                except Exception: pass
                self._tray_icon = None

            wins = webview.windows
            if wins:
                try: wins[0].show()
                except Exception: pass
                try: wins[0].restore()
                except Exception: pass

            # Форсируем вывод на передний план через win32gui
            try:
                import win32gui, win32con
                def _bring_to_front(hwnd, _):
                    title = win32gui.GetWindowText(hwnd)
                    if 'Arizona RP Launcher' in title:
                        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                        win32gui.SetForegroundWindow(hwnd)
                        win32gui.BringWindowToTop(hwnd)
                win32gui.EnumWindows(_bring_to_front, None)
            except ImportError:
                pass
            except Exception as e:
                logger.warning(f"restore_window win32 error: {e}")

            return {"success": True}
        except Exception as e:
            logger.error(f"restore_window error: {e}")
            return {"success": False, "message": str(e)}

    def minimize_to_tray(self):
        """Сворачивает в системный трей. Если pystray/Pillow не установлены — обычный minimize."""
        try:
            import pystray
            from PIL import Image, ImageDraw
        except ImportError:
            logger.info("pystray/Pillow не установлены, используем обычный minimize")
            return self.minimize_window()

        wins = webview.windows
        if not wins:
            return {"success": False, "message": "No window"}

        # Иконка 64x64: синий круг с буквой A
        img = Image.new('RGBA', (64, 64), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.ellipse([2, 2, 62, 62], fill=(0, 120, 212, 255))
        try:
            from PIL import ImageFont
            font = ImageFont.truetype("arial.ttf", 30)
            draw.text((17, 12), "A", fill=(255, 255, 255, 255), font=font)
        except Exception:
            draw.rectangle([20, 42, 44, 46], fill=(255, 255, 255, 255))  # fallback: горизонтальная черта
            draw.polygon([(32, 12), (20, 44), (44, 44)], outline=(255, 255, 255, 255))

        _self = self

        def _on_open(icon, item):
            icon.stop()
            _self._tray_icon = None
            _self.restore_window()

        def _on_quit(icon, item):
            icon.stop()
            _self._tray_icon = None
            try:
                wins = webview.windows
                if wins: wins[0].destroy()
            except Exception: pass

        menu = pystray.Menu(
            pystray.MenuItem("Открыть лаунчер", _on_open, default=True),
            pystray.MenuItem("Выход", _on_quit),
        )
        icon = pystray.Icon("ArzLauncher", img, "Arizona RP Launcher", menu)
        self._tray_icon = icon

        # Скрываем окно
        try:
            wins[0].hide()
        except Exception:
            wins[0].minimize()

        import threading
        threading.Thread(target=icon.run, daemon=True).start()
        logger.info("minimize_to_tray: трей запущен")
        return {"success": True}

    def check_tray_support(self):
        """Проверяет наличие pystray и Pillow."""
        try:
            import pystray
            from PIL import Image
            return {"success": True, "available": True}
        except ImportError:
            return {"success": True, "available": False}
    def get_debug_info(self):
        """Возвращает диагностическую информацию для Debug-вкладки."""
        try:
            profiles = self.launcher.config.get('profiles', [])
            active_id = self.launcher.config.get('active_profile_id', None)
            active_name = next((p.get('name') for p in profiles if p.get('id') == active_id), None)
            return {
                "success": True,
                "data": {
                    "config_path":         self.launcher.config_path,
                    "docs_path":           self.launcher.documents_path,
                    "game_path":           self.launcher.game_path or "",
                    "launcher_path":       self.launcher.launcher_path or "",
                    "patches_path":        self.launcher.patches_path or "",
                    "profiles_count":      len(profiles),
                    "active_profile_name": active_name or "нет",
                }
            }
        except Exception as e:
            return {"success": False, "message": str(e)}

    def open_data_folder(self):
        """Открывает папку данных лаунчера в проводнике."""
        try:
            path = self.launcher.documents_path
            os.makedirs(path, exist_ok=True)
            if sys.platform == 'win32':
                os.startfile(path)
            elif sys.platform == 'darwin':
                subprocess.Popen(['open', path])
            else:
                subprocess.Popen(['xdg-open', path])
            return {"success": True}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def open_log_file(self):
        """Открывает файл лога в Блокноте."""
        try:
            log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "arizona_launcher.log")
            if not os.path.exists(log_path):
                return {"success": False, "message": "Файл лога не найден"}
            if sys.platform == 'win32':
                subprocess.Popen(["notepad", log_path])
            elif sys.platform == 'darwin':
                subprocess.Popen(["open", log_path])
            else:
                subprocess.Popen(["xdg-open", log_path])
            return {"success": True}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def get_profiles(self):
        profiles = self.launcher.config.get('profiles', [])
        active_id = self.launcher.config.get('active_profile_id', None)
        return {"success": True, "profiles": profiles, "active_id": active_id}

    def save_profiles(self, profiles, active_id):
        self.launcher.config['profiles'] = profiles
        self.launcher.config['active_profile_id'] = active_id
        self.launcher.save_config()
        return {"success": True}
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
                "paths_configured": bool(self.launcher.launcher_path and self.launcher.game_path),
                "launcher_version": self.launcher.get_launcher_version()}

    def get_launcher_version(self):
        """Возвращает версию установленного лаунчера для JS."""
        return {"success": True, "version": self.launcher.get_launcher_version()}

    def get_saved_data(self):
        """Возвращает сохраненные данные (никнейм, сервер)"""
        return {
            "success": True,
            "nickname": self.launcher.config.get('last_nickname', ''),
            "server": self.launcher.config.get('last_server', 15),
            "game_path": self.launcher.game_path or '',
            "paths_configured": bool(self.launcher.launcher_path and self.launcher.game_path)
        }
    def get_read_news_ids(self):
        """Возвращает список прочитанных ID новостей"""
        ids = self.launcher.config.get('read_news_ids', [])
        return {"success": True, "ids": ids}

    def save_read_news_ids(self, ids):
        """Сохраняет список прочитанных ID новостей"""
        self.launcher.config['read_news_ids'] = ids
        self.launcher.save_config()
        return {"success": True}
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

    def _qt_app(self):
        """Возвращает существующий QApplication или создаёт новый"""
        from PyQt5.QtWidgets import QApplication
        return QApplication.instance() or QApplication([])

    def select_bg_image(self):
        """Выбрать картинку для фона лаунчера, вернуть base64 data URL"""
        import base64, mimetypes, queue
        from threading import Thread
        result_queue = queue.Queue()

        def _pick():
            try:
                from PyQt5.QtWidgets import QFileDialog
                app = self._qt_app()
                file_path, _ = QFileDialog.getOpenFileName(
                    None,
                    "Выбрать картинку для фона",
                    "",
                    "Изображения (*.png *.jpg *.jpeg *.webp *.bmp);;Все файлы (*)"
                )
                if not file_path:
                    result_queue.put({"success": False, "message": "Отменено"})
                    return
                mime = mimetypes.guess_type(file_path)[0] or "image/jpeg"
                with open(file_path, 'rb') as f:
                    data = base64.b64encode(f.read()).decode('utf-8')
                result_queue.put({"success": True, "data_url": f"data:{mime};base64,{data}"})
            except Exception as e:
                logger.error(f"select_bg_image error: {e}")
                result_queue.put({"success": False, "message": str(e)})

        t = Thread(target=_pick, daemon=True)
        t.start()
        t.join(timeout=60)
        return result_queue.get() if not result_queue.empty() else {"success": False, "message": "Таймаут"}

    def _check_game_folder(self, folder_path):
        """Проверяет папку игры и возвращает статус.
        Варианты:
          ok          — всё есть (gta_sa + launcher + plugins с файлами)
          needs_install — нужна установка лаунчера/патчер архива
          no_game     — gta_sa.exe не найден
        """
        game_exe    = os.path.join(folder_path, "gta_sa.exe")
        launcher_v6 = os.path.join(folder_path, "ArizonaLauncher6_byAIR.exe")
        launcher_v7 = os.path.join(folder_path, "ArizonaLauncher7.0_byAIR.exe")
        plugins_dir = os.path.join(folder_path, "preloading_plugins")

        if not os.path.exists(game_exe):
            return {"status": "no_game", "folder": folder_path}

        # Лаунчер найден если установлена любая из версий (v6 или v7)
        launcher_exe = ""
        if os.path.exists(launcher_v7):
            launcher_exe = launcher_v7
        elif os.path.exists(launcher_v6):
            launcher_exe = launcher_v6
        has_launcher = bool(launcher_exe)
        has_plugins  = os.path.isdir(plugins_dir) and bool(os.listdir(plugins_dir))

        if has_launcher and has_plugins:
            return {"status": "ok", "folder": folder_path,
                    "game_exe": game_exe, "launcher_exe": launcher_exe}

        # Чего не хватает
        missing = []
        if not has_launcher: missing.append("launcher")
        if not has_plugins:  missing.append("preloading_plugins")

        return {"status": "needs_install", "folder": folder_path,
                "missing": missing,
                "game_exe": game_exe,
                "launcher_exe": launcher_exe}

    def get_install_action(self, folder_path):
        """Определяет какое действие нужно выполнить для установки.
        Возвращает:
        - action: 'none' | 'choose_version' | 'install_preloading_only' | 'install_launcher_only'
        - has_launcher: bool
        - has_preloading: bool
        - launcher_version: 'v6' | 'v7' | None
        """
        logger.info(f"[get_install_action] Начало проверки папки: {folder_path}")
        
        game_exe    = os.path.join(folder_path, "gta_sa.exe")
        launcher_v6 = os.path.join(folder_path, "ArizonaLauncher6_byAIR.exe")
        launcher_v7 = os.path.join(folder_path, "ArizonaLauncher7.0_byAIR.exe")
        plugins_dir = os.path.join(folder_path, "preloading_plugins")

        if not os.path.exists(game_exe):
            logger.error(f"[get_install_action] gta_sa.exe не найден в {folder_path}")
            return {"action": "error", "message": "gta_sa.exe не найден"}

        has_v6 = os.path.exists(launcher_v6)
        has_v7 = os.path.exists(launcher_v7)
        has_launcher = has_v6 or has_v7
        has_preloading = os.path.isdir(plugins_dir) and bool(os.listdir(plugins_dir))
        launcher_version = 'v7' if has_v7 else ('v6' if has_v6 else None)

        logger.info(f"[get_install_action] Статус проверки:")
        logger.info(f"  - has_v6: {has_v6}")
        logger.info(f"  - has_v7: {has_v7}")
        logger.info(f"  - has_preloading: {has_preloading}")
        logger.info(f"  - launcher_version: {launcher_version}")

        # Логика определения действия:
        # 1. Есть preloading + v7 -> ничего не делать
        if has_preloading and has_v7:
            logger.info("[get_install_action] Результат: Лаунчер v7 уже установлен (action: none)")
            return {
                "action": "none",
                "message": "Лаунчер v7 уже установлен",
                "has_launcher": True,
                "has_preloading": True,
                "launcher_version": "v7"
            }

        # 2. Есть preloading + v6 -> ничего не делать
        if has_preloading and has_v6:
            logger.info("[get_install_action] Результат: Лаунчер v6 уже установлен (action: none)")
            return {
                "action": "none",
                "message": "Лаунчер v6 уже установлен",
                "has_launcher": True,
                "has_preloading": True,
                "launcher_version": "v6"
            }

        # 3. Нет preloading + есть лаунчер (v6 или v7) -> установить только preloading
        if not has_preloading and has_launcher:
            logger.info(f"[get_install_action] Результат: Требуется установка preloading_plugins (action: install_preloading_only, launcher: {launcher_version})")
            return {
                "action": "install_preloading_only",
                "message": "Требуется установка папки preloading_plugins",
                "has_launcher": True,
                "has_preloading": False,
                "launcher_version": launcher_version
            }

        # 4. Есть preloading + нет лаунчера -> предложить выбор версии (установить только лаунчер)
        if has_preloading and not has_launcher:
            logger.info("[get_install_action] Результат: Требуется установка лаунчера (action: install_launcher_only)")
            return {
                "action": "install_launcher_only",
                "message": "Выберите версию лаунчера для установки",
                "has_launcher": False,
                "has_preloading": True,
                "launcher_version": None
            }

        # 5. Нет ничего -> предложить выбор версии (полная установка)
        logger.info("[get_install_action] Результат: Требуется полная установка (action: choose_version)")
        return {
            "action": "choose_version",
            "message": "Выберите версию лаунчера для установки",
            "has_launcher": False,
            "has_preloading": False,
            "launcher_version": None
        }

    def select_game_path(self):
        """Открыть диалог выбора папки с игрой"""
        logger.info("[select_game_path] Открытие диалога выбора папки")
        try:
            from PyQt5.QtWidgets import QFileDialog
            app = self._qt_app()
            folder_path = QFileDialog.getExistingDirectory(
                None,
                "Выберите папку с игрой (где находится gta_sa.exe)",
                "",
                QFileDialog.ShowDirsOnly | QFileDialog.DontResolveSymlinks
            )
            if not folder_path:
                logger.info("[select_game_path] Пользователь отменил выбор папки")
                return {"success": False, "message": "Папка не выбрана"}

            logger.info(f"[select_game_path] Выбрана папка: {folder_path}")
            check = self._check_game_folder(folder_path)

            if check["status"] == "no_game":
                logger.error(f"[select_game_path] gta_sa.exe не найден в {folder_path}")
                return {"success": False, "message": "gta_sa.exe не найден в выбранной папке"}

            # Сохраняем путь к игре независимо от наличия лаунчера
            logger.info(f"[select_game_path] Сохранение путей: game_exe={check['game_exe']}, launcher_exe={check.get('launcher_exe', 'нет')}")
            self.launcher.set_game_paths(check["game_exe"], check.get("launcher_exe", ""))
            
            # Получаем информацию о необходимых действиях
            logger.info("[select_game_path] Вызов get_install_action для определения необходимых действий")
            install_info = self.get_install_action(folder_path)
            
            logger.info(f"[select_game_path] Успешно завершено. Action: {install_info.get('action')}")
            return {
                "success": True, 
                "message": f"Путь установлен: {folder_path}",
                "folder": folder_path,
                "install_info": install_info
            }
        except Exception as e:
            logger.error(f"[select_game_path] Ошибка: {e}", exc_info=True)
            return {"success": False, "message": str(e)}

    def get_install_action_api(self, folder_path):
        """API метод для получения информации о необходимых действиях установки"""
        logger.info(f"[get_install_action_api] Вызов для папки: {folder_path}")
        try:
            install_info = self.get_install_action(folder_path)
            logger.info(f"[get_install_action_api] Результат: {install_info.get('action')}")
            return {
                "success": True,
                "install_info": install_info
            }
        except Exception as e:
            logger.error(f"[get_install_action_api] Ошибка: {e}", exc_info=True)
            return {"success": False, "message": str(e)}

    def download_and_install_launcher(self, folder_path, version='v6', install_type='choose_version'):
        """Скачивает архив лаунчера с GitHub и устанавливает в папку игры.
           version: 'v6' — ArizonaLauncher6_byAIR, 'v7' — ArizonaLauncher7_byAIR
           install_type: 'choose_version' — полная установка
                        'install_preloading_only' — только папка preloading_plugins
                        'install_launcher_only' — только лаунчер
           Отправляет прогресс через JS-событие."""
        logger.info(f"[download_and_install_launcher] ========== НАЧАЛО УСТАНОВКИ ==========")
        logger.info(f"[download_and_install_launcher] Параметры:")
        logger.info(f"  - folder_path: {folder_path}")
        logger.info(f"  - version: {version}")
        logger.info(f"  - install_type: {install_type}")
        
        VERSIONS = {
            "v6": {
                "url": "https://raw.githubusercontent.com/worteng/ArizonaLauncher/refs/heads/main/others/arizonapatcher.zip",
                "exe_names": ["arizonalauncher6_byair.exe"],
            },
            "v7": {
                "url": "https://raw.githubusercontent.com/worteng/ArizonaLauncher/refs/heads/main/others/arizonapatchesV2.zip",
                "exe_names": ["arizonalauncher7.0_byair.exe"],
            },
        }
        ver = VERSIONS.get(version, VERSIONS["v6"])
        GITHUB_RELEASE_URL = ver["url"]
        TARGET_EXE_NAMES   = ver["exe_names"]
        logger.info(f"[download_and_install_launcher] URL для скачивания: {GITHUB_RELEASE_URL}")
        logger.info(f"[download_and_install_launcher] Целевые exe файлы: {TARGET_EXE_NAMES}")
        import zipfile, tempfile, shutil

        def _send(stage, progress=0, message=""):
            try:
                import webview as wv
                wins = wv.windows
                if wins:
                    js = f"window._onLauncherInstallProgress && window._onLauncherInstallProgress({json.dumps({'stage': stage, 'progress': progress, 'message': message})})"
                    wins[0].evaluate_js(js)
            except Exception as ex:
                logger.warning(f"_send progress error: {ex}")

        try:
            logger.info("[download_and_install_launcher] Этап 1: Скачивание архива")
            _send("download", 0, "Подключение к GitHub...")

            # 1. Качаем архив с прогрессом
            resp = requests.get(GITHUB_RELEASE_URL, stream=True, timeout=60, verify=False,
                                headers={"User-Agent": "Mozilla/5.0"})
            if resp.status_code != 200:
                logger.error(f"[download_and_install_launcher] Ошибка HTTP: {resp.status_code}")
                _send("error", 0, f"Ошибка загрузки: HTTP {resp.status_code}")
                return {"success": False, "message": f"HTTP {resp.status_code}"}

            total = int(resp.headers.get("content-length", 0))
            downloaded = 0
            logger.info(f"[download_and_install_launcher] Размер архива: {total / 1024 / 1024:.2f} МБ")

            tmp_zip = os.path.join(tempfile.gettempdir(), "arizona_launcher_install.zip")
            logger.info(f"[download_and_install_launcher] Временный файл: {tmp_zip}")
            
            with open(tmp_zip, "wb") as f:
                for chunk in resp.iter_content(chunk_size=65536):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        pct = int(downloaded / total * 80) if total else 10
                        mb = downloaded / 1024 / 1024
                        _send("download", pct, f"Скачано {mb:.1f} МБ...")

            logger.info(f"[download_and_install_launcher] Скачивание завершено: {downloaded / 1024 / 1024:.2f} МБ")
            logger.info("[download_and_install_launcher] Этап 2: Распаковка архива")
            _send("extract", 82, "Распаковка архива...")

            # 2. Распаковываем архив в зависимости от типа установки
            extracted_count = 0
            skipped_count = 0
            with zipfile.ZipFile(tmp_zip, 'r') as zf:
                logger.info(f"[download_and_install_launcher] Файлов в архиве: {len(zf.infolist())}")
                for member in zf.infolist():
                    filename = os.path.basename(member.filename)
                    if not filename:  # это папка внутри архива
                        continue
                    
                    # Проверяем что это файл из preloading_plugins
                    is_preloading = "preloading_plugins" in member.filename.replace("\\", "/")
                    is_exe = filename.lower().endswith(".exe")
                    
                    # Логика установки в зависимости от типа:
                    should_extract = False
                    
                    if install_type == 'install_preloading_only':
                        # Устанавливаем только preloading_plugins
                        should_extract = is_preloading
                    elif install_type == 'install_launcher_only':
                        # Устанавливаем только лаунчер (exe файлы)
                        should_extract = is_exe
                    else:
                        # Полная установка (всё)
                        should_extract = True
                    
                    if not should_extract:
                        skipped_count += 1
                        continue
                    
                    # preloading_plugins — сохраняем структуру
                    if is_preloading:
                        rel = member.filename.replace("\\", "/")
                        idx = rel.find("preloading_plugins")
                        dest_rel = rel[idx:]  # "preloading_plugins/file.ext"
                        dest_path = os.path.join(folder_path, dest_rel)
                        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                        with zf.open(member) as src, open(dest_path, "wb") as dst:
                            shutil.copyfileobj(src, dst)
                        logger.info(f"[download_and_install_launcher] Извлечён (preloading): {dest_rel}")
                        extracted_count += 1
                    else:
                        dest_path = os.path.join(folder_path, filename)
                        with zf.open(member) as src, open(dest_path, "wb") as dst:
                            shutil.copyfileobj(src, dst)
                        logger.info(f"[download_and_install_launcher] Извлечён: {filename}")
                        extracted_count += 1

                        # Как только записали .exe — сразу в исключения Defender'а
                        if is_exe and filename.lower() in TARGET_EXE_NAMES:
                            launcher_dest = dest_path
                            self._add_defender_exclusion(launcher_dest)
                            logger.info(f"[download_and_install_launcher] Defender exclusion добавлен: {launcher_dest}")

            logger.info(f"[download_and_install_launcher] Распаковка завершена:")
            logger.info(f"  - Извлечено файлов: {extracted_count}")
            logger.info(f"  - Пропущено файлов: {skipped_count}")
            logger.info("[download_and_install_launcher] Этап 3: Финализация установки")
            _send("install", 90, "Установка файлов...")

            # 3. Проверяем что .exe нашёлся
            logger.info("[download_and_install_launcher] Проверка наличия exe файла")
            launcher_dest_check = None
            for exe_name in TARGET_EXE_NAMES:
                candidate = os.path.join(folder_path, os.path.basename(exe_name))
                # ищем без учёта регистра
                for f in os.listdir(folder_path):
                    if f.lower() == exe_name:
                        launcher_dest_check = os.path.join(folder_path, f)
                        logger.info(f"[download_and_install_launcher] Найден exe: {f}")
                        break
                if launcher_dest_check:
                    break

            if not launcher_dest_check:
                logger.warning("[download_and_install_launcher] Целевой exe не найден, ищем любой exe")
                # Fallback: любой новый .exe в папке
                for f in os.listdir(folder_path):
                    if f.lower().endswith(".exe") and f.lower() != "gta_sa.exe":
                        launcher_dest_check = os.path.join(folder_path, f)
                        logger.info(f"[download_and_install_launcher] Найден альтернативный exe: {f}")
                        break

            if not launcher_dest_check:
                logger.error("[download_and_install_launcher] Исполняемый файл лаунчера не найден после распаковки")
                _send("error", 0, "Исполняемый файл лаунчера не найден после распаковки")
                return {"success": False, "message": "Исполняемый файл не найден"}

            launcher_dest = launcher_dest_check
            logger.info(f"[download_and_install_launcher] Финальный путь к лаунчеру: {launcher_dest}")

            # 4. Убеждаемся что preloading_plugins существует
            plugins_dir = os.path.join(folder_path, "preloading_plugins")
            if not os.path.isdir(plugins_dir):
                logger.info(f"[download_and_install_launcher] Создание папки preloading_plugins: {plugins_dir}")
                os.makedirs(plugins_dir, exist_ok=True)
            else:
                logger.info(f"[download_and_install_launcher] Папка preloading_plugins уже существует")

            _send("install", 97, "Финализация...")

            # 5. Устанавливаем пути
            game_exe = os.path.join(folder_path, "gta_sa.exe")
            logger.info(f"[download_and_install_launcher] Сохранение путей: game_exe={game_exe}, launcher={launcher_dest}")
            self.launcher.set_game_paths(game_exe, launcher_dest)

            # Чистка только zip-архива (tmp_dir больше не используется)
            try:
                os.remove(tmp_zip)
                logger.info(f"[download_and_install_launcher] Временный архив удалён: {tmp_zip}")
            except Exception as e:
                logger.warning(f"[download_and_install_launcher] Не удалось удалить временный архив: {e}")

            _send("done", 100, "Установка завершена!")
            logger.info(f"[download_and_install_launcher] ========== УСТАНОВКА ЗАВЕРШЕНА УСПЕШНО ==========")
            logger.info(f"[download_and_install_launcher] Установлено в: {folder_path}")
            return {"success": True, "message": "Лаунчер успешно установлен"}

        except requests.exceptions.ConnectionError as e:
            logger.error(f"[download_and_install_launcher] Ошибка подключения: {e}")
            _send("error", 0, "Нет подключения к интернету")
            return {"success": False, "message": "Нет подключения к интернету"}
        except requests.exceptions.Timeout as e:
            logger.error(f"[download_and_install_launcher] Тайм-аут: {e}")
            _send("error", 0, "Тайм-аут соединения")
            return {"success": False, "message": "Тайм-аут соединения"}
        except Exception as e:
            logger.error(f"[download_and_install_launcher] ========== ОШИБКА УСТАНОВКИ ==========")
            logger.error(f"[download_and_install_launcher] {e}", exc_info=True)
            _send("error", 0, str(e))
            return {"success": False, "message": str(e)}

    def start_launcher_install(self, folder_path, version='v6', install_type='choose_version'):
        """Запускает скачивание и установку лаунчера в фоновом потоке
        install_type: 'choose_version', 'install_preloading_only', 'install_launcher_only'
        """
        logger.info(f"[start_launcher_install] Запуск установки:")
        logger.info(f"  - folder_path: {folder_path}")
        logger.info(f"  - version: {version}")
        logger.info(f"  - install_type: {install_type}")
        
        def run():
            self.download_and_install_launcher(folder_path, version, install_type)
        Thread(target=run, daemon=True).start()
        logger.info("[start_launcher_install] Фоновый поток установки запущен")
        return {"success": True, "message": "Загрузка начата"}


    def export_patches(self, data):
        """Сохранить настройки патчей в файл через диалог"""
        try:
            from PyQt5.QtWidgets import QFileDialog
            app = self._qt_app()
            file_path, _ = QFileDialog.getSaveFileName(
                None,
                "Сохранить настройки патчей",
                "ArizonaPatches_settings.json",
                "JSON файл (*.json);;Все файлы (*)"
            )
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
            from PyQt5.QtWidgets import QFileDialog
            app = self._qt_app()
            file_path, _ = QFileDialog.getOpenFileName(
                None,
                "Открыть файл настроек патчей",
                "",
                "JSON файл (*.json);;Все файлы (*)"
            )
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
            # Создаём бэкап текущего конфига перед применением импорта
            if self.launcher.patches_path and os.path.exists(self.launcher.patches_path):
                self.launcher._create_patches_backup(label="before_import")
            return {"success": True, "data": data, "keys_count": bool_count}
        except Exception as e:
            logger.error(f"import_patches error: {e}")
            return {"success": False, "message": str(e)}

    def get_wallpapers(self):
        """Сканирует папку wallpapers/ рядом с main.py и возвращает список файлов"""
        import base64, mimetypes
        try:
            base_dir = Path(__file__).parent / "wallpapers"
            if not base_dir.exists():
                base_dir.mkdir(parents=True, exist_ok=True)
                return {"success": True, "wallpapers": []}

            supported = {'.jpg', '.jpeg', '.png', '.webp', '.bmp'}
            result = []
            for f in sorted(base_dir.iterdir()):
                if f.is_file() and f.suffix.lower() in supported:
                    try:
                        mime = mimetypes.guess_type(f.name)[0] or 'image/jpeg'
                        data = base64.b64encode(f.read_bytes()).decode('utf-8')
                        result.append({
                            "name": f.stem,
                            "filename": f.name,
                            "data_url": f"data:{mime};base64,{data}"
                        })
                    except Exception as e:
                        logger.warning(f"get_wallpapers skip {f.name}: {e}")
            return {"success": True, "wallpapers": result}
        except Exception as e:
            logger.error(f"get_wallpapers error: {e}")
            return {"success": False, "message": str(e), "wallpapers": []}

    def _add_defender_exclusion(self, file_path: str):
        """Добавляет файл и его папку в исключения Windows Defender через PowerShell."""
        try:
            folder_path = os.path.dirname(file_path)
            # Добавляем и файл и всю папку игры
            ps_cmd = (
                f"Add-MpPreference -ExclusionPath '{folder_path}'; "
                f"Add-MpPreference -ExclusionProcess '{file_path}'"
            )
            result = subprocess.run(
                ["powershell", "-NonInteractive", "-WindowStyle", "Hidden",
                 "-Command", ps_cmd],
                capture_output=True, timeout=15
            )
            if result.returncode == 0:
                logger.info(f"_add_defender_exclusion: OK — {file_path}")
            else:
                # Если нет прав — пробуем через elevation (запрос UAC)
                logger.warning(f"_add_defender_exclusion: нет прав, пробуем с elevation")
                subprocess.run(
                    ["powershell", "-NonInteractive", "-WindowStyle", "Hidden",
                     "-Command",
                     f"Start-Process powershell -Verb RunAs -ArgumentList "
                     f"'-NonInteractive -WindowStyle Hidden -Command \"{ps_cmd}\"'"],
                    capture_output=True, timeout=15
                )
        except Exception as e:
            logger.warning(f"_add_defender_exclusion error: {e}")

    def minimize_window(self):
        """Сворачивает окно лаунчера в панель задач"""
        try:
            import webview as wv
            wins = wv.windows
            if wins:
                wins[0].minimize()
            return {"success": True}
        except Exception as e:
            logger.error(f"minimize_window error: {e}")
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
    def list_patches_backups(self): return self.launcher.list_patches_backups()
    def restore_patches_backup(self, filename): return self.launcher.restore_patches_backup(filename)
    def delete_patches_backup(self, filename): return self.launcher.delete_patches_backup(filename)

    def fetch_patch_presets(self):
        """Загружает configs.txt с GitHub и парсит список пресетов"""
        CONFIGS_URL = "https://raw.githubusercontent.com/worteng/ArizonaLauncher/main/configs.txt"
        try:
            logger.info(f"fetch_patch_presets: запрос {CONFIGS_URL}")
            resp = requests.get(CONFIGS_URL, timeout=10, headers={"Cache-Control": "no-cache"}, verify=False)
            logger.info(f"fetch_patch_presets: статус {resp.status_code}, размер {len(resp.text)} байт")
            if resp.status_code == 404:
                return {"success": False, "message": "Файл configs.txt не найден на GitHub (404). Создай его в репозитории."}
            if resp.status_code != 200:
                return {"success": False, "message": f"GitHub вернул HTTP {resp.status_code}"}
            presets = self._parse_catalog_txt(resp.text)
            logger.info(f"fetch_patch_presets: распарсено {len(presets)} конфигов")
            if len(presets) == 0:
                return {"success": False, "message": "configs.txt найден, но не содержит блоков [config]"}
            return {"success": True, "data": presets}
        except requests.exceptions.ConnectionError:
            return {"success": False, "message": "Нет подключения к интернету"}
        except requests.exceptions.Timeout:
            return {"success": False, "message": "Превышено время ожидания (GitHub не отвечает)"}
        except Exception as e:
            logger.error(f"fetch_patch_presets error: {e}")
            return {"success": False, "message": str(e)}

    def _parse_catalog_txt(self, text):
        """Парсит configs.txt / moonloader.txt — любые блоки [секция]"""
        presets = []
        current = None
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            # Любой заголовок блока вида [что-угодно]
            if line.startswith("[") and line.endswith("]"):
                if current is not None:
                    presets.append(current)
                current = {}
                continue
            if current is not None and "=" in line:
                key, _, val = line.partition("=")
                current[key.strip()] = val.strip()
        if current is not None:
            presets.append(current)
        return presets

    # Оставляем старое имя как алиас — на случай если где-то ещё используется
    def _parse_configs_txt(self, text):
        return self._parse_catalog_txt(text)

    def install_patch_preset(self, url):
        """Скачивает JSON-конфиг по ссылке и записывает в #ArizonaPatches.json"""
        if not self.launcher.patches_path:
            return {"success": False, "message": "Путь к патчам не установлен. Сначала укажи путь к игре."}
        try:
            resp = requests.get(url, timeout=15, verify=False)
            if resp.status_code != 200:
                return {"success": False, "message": f"Ошибка загрузки: HTTP {resp.status_code}", "stage": "downloading"}

            raw = resp.text
            cleaned = re.sub(r"^\s*//.*$", "", raw, flags=re.MULTILINE)
            cleaned = "\n".join(l for l in cleaned.split("\n") if l.strip())
            data = json.loads(cleaned)

            bool_count = sum(1 for v in data.values() if isinstance(v, bool))
            if bool_count == 0:
                return {"success": False, "message": "Файл не содержит настроек патчей", "stage": "installing"}

            result = self.launcher.write_patches(data)
            if not result["success"]:
                return {"success": False, "message": result["message"], "stage": "installing"}

            return {"success": True, "message": f"Установлено {bool_count} настроек", "keys_count": bool_count}
        except json.JSONDecodeError as e:
            return {"success": False, "message": f"Неверный формат JSON: {e}", "stage": "installing"}
        except Exception as e:
            logger.error(f"install_patch_preset error: {e}")
            return {"success": False, "message": str(e), "stage": "downloading"}

    # ---- MOONLOADER ----

    def _get_moonloader_dir(self):
        """Путь к папке moonloader/ рядом с gta_sa.exe"""
        if not self.launcher.game_path:
            return None
        ml_dir = os.path.join(os.path.dirname(self.launcher.game_path), "moonloader")
        return ml_dir if os.path.isdir(ml_dir) else None

    def get_moonloader_scripts(self):
        """Возвращает список скриптов в moonloader/ (без подпапок)"""
        ml_dir = self._get_moonloader_dir()
        if not ml_dir:
            return {"success": False, "message": "Папка moonloader не найдена"}
        try:
            scripts = []
            for entry in os.scandir(ml_dir):
                if not entry.is_file():
                    continue
                name = entry.name
                # Считаем файл активным если он НЕ заканчивается на .disabled
                if name.endswith(".disabled"):
                    real_name = name[:-len(".disabled")]
                    enabled = False
                else:
                    real_name = name
                    enabled = True
                # Берём только скриптовые расширения (и их .disabled варианты)
                base, ext = os.path.splitext(real_name)
                if ext.lower() not in (".lua", ".cs", ".asi", ".luac"):
                    continue
                scripts.append({
                    "name": real_name,
                    "ext": ext.lower().lstrip("."),
                    "enabled": enabled,
                    "full_path": entry.path
                })
            scripts.sort(key=lambda s: s["name"].lower())
            return {"success": True, "scripts": scripts, "dir": ml_dir}
        except Exception as e:
            logger.error(f"get_moonloader_scripts error: {e}")
            return {"success": False, "message": str(e)}

    def toggle_moonloader_script(self, script_name, enable):
        """Включает или выключает скрипт добавлением/удалением .disabled"""
        ml_dir = self._get_moonloader_dir()
        if not ml_dir:
            return {"success": False, "message": "Папка moonloader не найдена"}
        try:
            enabled_path  = os.path.join(ml_dir, script_name)
            disabled_path = os.path.join(ml_dir, script_name + ".disabled")

            if enable:
                # Включить: убрать .disabled
                if os.path.exists(disabled_path):
                    os.rename(disabled_path, enabled_path)
                elif not os.path.exists(enabled_path):
                    return {"success": False, "message": f"Файл не найден: {script_name}"}
            else:
                # Выключить: добавить .disabled
                if os.path.exists(enabled_path):
                    os.rename(enabled_path, disabled_path)
                elif not os.path.exists(disabled_path):
                    return {"success": False, "message": f"Файл не найден: {script_name}"}

            return {"success": True}
        except Exception as e:
            logger.error(f"toggle_moonloader_script error: {e}")
            return {"success": False, "message": str(e)}

    def open_moonloader_folder(self):
        """Открыть папку moonloader в проводнике"""
        ml_dir = self._get_moonloader_dir()
        if not ml_dir:
            return {"success": False, "message": "Папка moonloader не найдена"}
        try:
            if sys.platform == 'win32':
                os.startfile(ml_dir)
            elif sys.platform == 'darwin':
                subprocess.Popen(['open', ml_dir])
            else:
                subprocess.Popen(['xdg-open', ml_dir])
            return {"success": True}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def fetch_moonloader_catalog(self):
        """Загружает lua.txt из ArzLaunchRepo и парсит список скриптов"""
        MOONLOADER_URL = "https://raw.githubusercontent.com/worteng/ArzLaunchRepo/main/Lua/lua.txt"
        FALLBACK_URL   = "https://raw.githubusercontent.com/worteng/ArizonaLauncher/main/moonloader.txt"
        for url in (MOONLOADER_URL, FALLBACK_URL):
            try:
                logger.info(f"fetch_moonloader_catalog: запрос {url}")
                resp = requests.get(url, timeout=10, headers={"Cache-Control": "no-cache"}, verify=False)
                logger.info(f"fetch_moonloader_catalog: статус {resp.status_code}")
                if resp.status_code != 200:
                    continue
                scripts = self._parse_catalog_txt(resp.text)
                if scripts:
                    logger.info(f"fetch_moonloader_catalog: {len(scripts)} скриптов из {url}")
                    return {"success": True, "data": scripts}
            except Exception as e:
                logger.warning(f"fetch_moonloader_catalog {url}: {e}")
        return {"success": False, "message": "Нет соединения с GitHub или каталог пуст"}


    def fetch_community_themes(self):
        """Загружает themes.txt из ArzLaunchRepo."""
        THEMES_URL = "https://raw.githubusercontent.com/worteng/ArzLaunchRepo/main/Themes/themes.txt"
        try:
            resp = requests.get(THEMES_URL, timeout=10, headers={"Cache-Control": "no-cache"}, verify=False)
            if resp.status_code == 404:
                return {"success": False, "message": "themes.txt ещё не создан в репозитории"}
            if resp.status_code != 200:
                return {"success": False, "message": f"HTTP {resp.status_code}"}
            themes = self._parse_catalog_txt(resp.text)
            logger.info(f"fetch_community_themes: {len(themes)} тем")
            return {"success": True, "data": themes}
        except Exception as e:
            logger.error(f"fetch_community_themes error: {e}")
            return {"success": False, "message": str(e)}

    def download_community_theme(self, json_url):
        """Скачивает JSON темы и, если есть wallpaper_url, скачивает обои и возвращает base64."""
        import base64, mimetypes
        try:
            resp = requests.get(json_url, timeout=15, verify=False)
            if resp.status_code != 200:
                return {"success": False, "message": f"Ошибка загрузки темы: HTTP {resp.status_code}"}
            theme = resp.json()

            # Скачиваем обои если есть ссылка
            wallpaper_data = theme.get("wallpaper")  # может быть уже base64
            if not wallpaper_data and theme.get("wallpaper_url"):
                try:
                    wp_resp = requests.get(theme["wallpaper_url"], timeout=20, verify=False)
                    if wp_resp.status_code == 200:
                        content_type = wp_resp.headers.get("Content-Type", "image/jpeg").split(";")[0]
                        b64 = base64.b64encode(wp_resp.content).decode("utf-8")
                        wallpaper_data = f"data:{content_type};base64,{b64}"
                except Exception as e:
                    logger.warning(f"download_community_theme wallpaper error: {e}")

            theme["wallpaper_data"] = wallpaper_data
            return {"success": True, "theme": theme}
        except Exception as e:
            logger.error(f"download_community_theme error: {e}")
            return {"success": False, "message": str(e)}

    def open_telegram_share(self):
        """Открывает Telegram-бота для отправки скрипта/темы в комьюнити."""
        BOT_USERNAME = "ARZLaunchBot"
        url = f"https://t.me/{BOT_USERNAME}"
        try:
            if sys.platform == "win32":
                os.startfile(url)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", url])
            else:
                subprocess.Popen(["xdg-open", url])
            return {"success": True}
        except Exception as e:
            return {"success": False, "message": str(e), "url": url}

    def install_moonloader_script(self, url, filename):
        """Скачивает скрипт и кладёт в moonloader/"""
        ml_dir = self._get_moonloader_dir()
        if not ml_dir:
            return {"success": False, "message": "Папка moonloader не найдена. Сначала укажи путь к игре."}
        try:
            resp = requests.get(url, timeout=30, verify=False)
            if resp.status_code != 200:
                return {"success": False, "message": f"Ошибка загрузки: HTTP {resp.status_code}"}
            dest = os.path.join(ml_dir, filename)
            with open(dest, 'wb') as f:
                f.write(resp.content)
            return {"success": True, "message": f"Установлен: {filename}"}
        except Exception as e:
            logger.error(f"install_moonloader_script error: {e}")
            return {"success": False, "message": str(e)}

    # ---- ДРУГОЕ (others.txt) ----

    DEST_MAP = {
        "root":       lambda self: os.path.dirname(self.launcher.game_path) if self.launcher.game_path else None,
        "cleo":       lambda self: os.path.join(os.path.dirname(self.launcher.game_path), "CLEO") if self.launcher.game_path else None,
        "moonloader": lambda self: self._get_moonloader_dir(),
        "plugins":    lambda self: os.path.join(os.path.dirname(self.launcher.game_path), "plugins") if self.launcher.game_path else None,
        "asi":        lambda self: os.path.dirname(self.launcher.game_path) if self.launcher.game_path else None,
    }

    def _resolve_dest(self, destination):
        """Возвращает абсолютный путь к папке назначения"""
        fn = self.DEST_MAP.get(destination.lower())
        if not fn:
            return None, f"Неизвестное назначение: {destination}"
        path = fn(self)
        if not path:
            return None, "Путь к игре не установлен — укажи его в настройках"
        if not os.path.isdir(path):
            try:
                os.makedirs(path, exist_ok=True)
            except Exception as e:
                return None, f"Не удалось создать папку {path}: {e}"
        return path, None

    def fetch_others_catalog(self):
        """Загружает others.txt с GitHub"""
        OTHERS_URL = "https://raw.githubusercontent.com/worteng/ArizonaLauncher/main/others.txt"
        try:
            resp = requests.get(OTHERS_URL, timeout=10,
                                headers={"Cache-Control": "no-cache"}, verify=False)
            if resp.status_code == 404:
                return {"success": False, "message": "Файл others.txt не найден на GitHub (404)"}
            if resp.status_code != 200:
                return {"success": False, "message": f"GitHub вернул HTTP {resp.status_code}"}
            items = self._parse_catalog_txt(resp.text)
            logger.info(f"fetch_others_catalog: {len(items)} файлов")
            return {"success": True, "data": items}
        except requests.exceptions.ConnectionError:
            return {"success": False, "message": "Нет подключения к интернету"}
        except requests.exceptions.Timeout:
            return {"success": False, "message": "Тайм-аут (GitHub не отвечает)"}
        except Exception as e:
            logger.error(f"fetch_others_catalog error: {e}")
            return {"success": False, "message": str(e)}

    def install_other_file(self, url, filename, destination):
        """Скачивает файл и кладёт его в нужную папку"""
        dest_dir, err = self._resolve_dest(destination)
        if err:
            return {"success": False, "message": err}
        try:
            resp = requests.get(url, timeout=30, verify=False)
            if resp.status_code != 200:
                return {"success": False, "message": f"Ошибка загрузки: HTTP {resp.status_code}"}
            out_path = os.path.join(dest_dir, filename)
            with open(out_path, 'wb') as f:
                f.write(resp.content)
            logger.info(f"install_other_file: {out_path}")
            return {"success": True, "message": f"Установлен в {dest_dir}", "path": out_path}
        except Exception as e:
            logger.error(f"install_other_file error: {e}")
            return {"success": False, "message": str(e)}

    def remove_other_file(self, filename, destination):
        """Удаляет файл из папки назначения"""
        dest_dir, err = self._resolve_dest(destination)
        if err:
            return {"success": False, "message": err}
        try:
            file_path = os.path.join(dest_dir, filename)
            if not os.path.exists(file_path):
                return {"success": False, "message": f"Файл не найден: {file_path}"}
            os.remove(file_path)
            logger.info(f"remove_other_file: {file_path}")
            return {"success": True, "message": f"Удалён: {filename}"}
        except Exception as e:
            logger.error(f"remove_other_file error: {e}")
            return {"success": False, "message": str(e)}

    def delete_moonloader_script(self, filename):
        """Удаляет скрипт из папки moonloader (поддерживает .disabled версию)"""
        ml_dir = self._get_moonloader_dir()
        if not ml_dir:
            return {"success": False, "message": "Папка moonloader не найдена"}
        try:
            # Пробуем найти файл в обоих вариантах
            candidates = [
                os.path.join(ml_dir, filename),
                os.path.join(ml_dir, filename + '.disabled'),
            ]
            deleted = []
            for path in candidates:
                if os.path.exists(path):
                    os.remove(path)
                    deleted.append(os.path.basename(path))
            if deleted:
                logger.info(f"delete_moonloader_script: удалён {deleted}")
                return {"success": True, "message": f"Удалён: {', '.join(deleted)}"}
            return {"success": False, "message": f"Файл не найден: {filename}"}
        except Exception as e:
            logger.error(f"delete_moonloader_script error: {e}")
            return {"success": False, "message": str(e)}

    def install_patches_file(self, filename, content_b64):
        """Принимает .json файл (base64) и кладёт его как #ArizonaPatches.json в preloading_plugins"""
        import base64 as _b64
        try:
            if not self.launcher.game_path:
                return {"success": False, "message": "Путь к игре не установлен"}
            plugins_dir = os.path.join(os.path.dirname(self.launcher.game_path), "preloading_plugins")
            os.makedirs(plugins_dir, exist_ok=True)
            dest = os.path.join(plugins_dir, "#ArizonaPatches.json")
            # Бэкап старого файла перед заменой
            if os.path.exists(dest):
                self.launcher._create_patches_backup(label="before_drop")
            content = _b64.b64decode(content_b64)
            with open(dest, 'wb') as f:
                f.write(content)
            logger.info(f"install_patches_file: установлен {dest}")
            return {"success": True, "message": f"Патчи обновлены из {filename}"}
        except Exception as e:
            logger.error(f"install_patches_file error: {e}")
            return {"success": False, "message": str(e)}

    def install_lua_file(self, filename, content_b64):
        """Копирует .lua файл (переданный как base64) в папку moonloader"""
        import base64 as _b64
        ml_dir = self._get_moonloader_dir()
        if not ml_dir:
            return {"success": False, "message": "Папка moonloader не найдена. Сначала укажи путь к игре."}
        try:
            content = _b64.b64decode(content_b64)
            dest = os.path.join(ml_dir, filename)
            with open(dest, 'wb') as f:
                f.write(content)
            logger.info(f"install_lua_file: {dest}")
            return {"success": True, "message": f"Скрипт '{filename}' установлен в moonloader"}
        except Exception as e:
            logger.error(f"install_lua_file error: {e}")
            return {"success": False, "message": str(e)}

    def check_other_installed(self, filename, destination):
        """Проверяет установлен ли файл"""
        dest_dir, err = self._resolve_dest(destination)
        if err:
            return {"installed": False}
        file_path = os.path.join(dest_dir, filename)
        return {"installed": os.path.exists(file_path), "path": file_path}


def _check_vcredist() -> bool:
    """Проверяет наличие Visual C++ Redistributable 2015–2022 (x64)."""
    try:
        import winreg
        keys = [
            # VC++ 2015–2022 x64
            r"SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\X64",
            r"SOFTWARE\WOW6432Node\Microsoft\VisualStudio\14.0\VC\Runtimes\X64",
            # VC++ 2022 (v17)
            r"SOFTWARE\Microsoft\VisualStudio\17.0\VC\Runtimes\X64",
        ]
        for key_path in keys:
            try:
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path) as k:
                    installed, _ = winreg.QueryValueEx(k, "Installed")
                    if installed == 1:
                        return True
            except OSError:
                continue
        return False
    except Exception:
        return True  # если не Windows или ошибка — не блокируем


def _check_webview2() -> bool:
    """Проверяет наличие Microsoft Edge WebView2 Runtime."""
    try:
        import winreg
        guids = [
            "{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}",  # WebView2 Runtime
            "{2CD8A007-E189-409D-A2C8-9AF4EF3C72AA}",  # Edge (Chromium)
        ]
        roots = [winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER]
        sub_paths = [
            r"SOFTWARE\Microsoft\EdgeUpdate\Clients\{}",
            r"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{}",
        ]
        for root in roots:
            for sub in sub_paths:
                for guid in guids:
                    try:
                        with winreg.OpenKey(root, sub.format(guid)):
                            return True
                    except OSError:
                        continue
        return False
    except Exception:
        return True  # не блокируем при ошибке


def _show_dependency_dialog(missing: list):
    """Показывает нативное PyQt5-окно со ссылками на скачивание зависимостей.
    Возвращает True если пользователь нажал 'Продолжить', False если 'Выход'."""
    from PyQt5.QtWidgets import (QApplication, QDialog, QVBoxLayout, QHBoxLayout,
                                  QLabel, QPushButton, QFrame)
    from PyQt5.QtCore import Qt, QUrl
    from PyQt5.QtGui import QDesktopServices, QFont, QColor, QPalette

    app = QApplication.instance() or QApplication(sys.argv)

    dlg = QDialog()
    dlg.setWindowTitle("Arizona RP Launcher — Требуются компоненты")
    dlg.setFixedSize(520, 0)  # высота авто
    dlg.setStyleSheet("""
        QDialog {
            background: #0d0f18;
        }
        QLabel {
            color: #ffffff;
            font-family: 'Segoe UI', sans-serif;
        }
        QPushButton {
            font-family: 'Segoe UI', sans-serif;
            font-size: 13px;
            padding: 9px 20px;
            border-radius: 8px;
            border: none;
            cursor: pointer;
        }
        QPushButton#dlBtn {
            background: rgba(0,120,212,0.85);
            color: white;
        }
        QPushButton#dlBtn:hover {
            background: rgba(0,140,240,0.95);
        }
        QPushButton#continueBtn {
            background: rgba(255,255,255,0.08);
            color: rgba(255,255,255,0.7);
            border: 1px solid rgba(255,255,255,0.12);
        }
        QPushButton#continueBtn:hover {
            background: rgba(255,255,255,0.14);
            color: white;
        }
        QPushButton#exitBtn {
            background: rgba(200,50,50,0.3);
            color: rgba(255,150,150,0.9);
            border: 1px solid rgba(200,50,50,0.4);
        }
        QPushButton#exitBtn:hover {
            background: rgba(220,60,60,0.5);
        }
        QFrame#card {
            background: rgba(255,255,255,0.04);
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: 12px;
        }
    """)

    layout = QVBoxLayout(dlg)
    layout.setContentsMargins(24, 22, 24, 22)
    layout.setSpacing(14)

    # Заголовок
    title = QLabel("⚠️  Требуются дополнительные компоненты")
    title.setStyleSheet("font-size: 16px; font-weight: bold; color: rgba(255,220,80,0.95);")
    title.setWordWrap(True)
    layout.addWidget(title)

    subtitle = QLabel("Для работы лаунчера необходимо установить следующие компоненты:")
    subtitle.setStyleSheet("font-size: 12px; color: rgba(255,255,255,0.55); margin-bottom: 4px;")
    subtitle.setWordWrap(True)
    layout.addWidget(subtitle)

    DEPS = {
        "vcredist": {
            "name": "Visual C++ Redistributable 2015–2022",
            "desc": "Библиотеки времени выполнения Microsoft C++",
            "url": "https://aka.ms/vs/17/release/vc_redist.x64.exe",
            "icon": "🔧"
        },
        "webview2": {
            "name": "Microsoft Edge WebView2 Runtime",
            "desc": "Движок для отображения интерфейса лаунчера",
            "url": "https://go.microsoft.com/fwlink/p/?LinkId=2124703",
            "icon": "🌐"
        }
    }

    result = {"action": "exit"}

    for key in missing:
        dep = DEPS.get(key)
        if not dep:
            continue

        card = QFrame()
        card.setObjectName("card")
        card_layout = QHBoxLayout(card)
        card_layout.setContentsMargins(16, 14, 16, 14)
        card_layout.setSpacing(14)

        icon_lbl = QLabel(dep["icon"])
        icon_lbl.setStyleSheet("font-size: 26px;")
        icon_lbl.setFixedWidth(36)
        card_layout.addWidget(icon_lbl)

        info_layout = QVBoxLayout()
        info_layout.setSpacing(3)
        name_lbl = QLabel(dep["name"])
        name_lbl.setStyleSheet("font-size: 13px; font-weight: bold; color: rgba(255,255,255,0.92);")
        desc_lbl = QLabel(dep["desc"])
        desc_lbl.setStyleSheet("font-size: 11px; color: rgba(255,255,255,0.4);")
        info_layout.addWidget(name_lbl)
        info_layout.addWidget(desc_lbl)
        card_layout.addLayout(info_layout, 1)

        url = dep["url"]
        dl_btn = QPushButton("⬇ Скачать")
        dl_btn.setObjectName("dlBtn")
        dl_btn.setFixedHeight(36)
        dl_btn.clicked.connect(lambda checked, u=url: QDesktopServices.openUrl(QUrl(u)))
        card_layout.addWidget(dl_btn)

        layout.addWidget(card)

    # Разделитель
    sep = QFrame()
    sep.setFrameShape(QFrame.HLine)
    sep.setStyleSheet("border: none; border-top: 1px solid rgba(255,255,255,0.06); margin: 4px 0;")
    layout.addWidget(sep)

    note = QLabel("После установки компонентов перезапустите лаунчер.\n"
                  "Или нажмите «Продолжить», чтобы запустить без гарантий.")
    note.setStyleSheet("font-size: 11px; color: rgba(255,255,255,0.35); line-height: 1.5;")
    note.setWordWrap(True)
    layout.addWidget(note)

    # Кнопки
    btn_row = QHBoxLayout()
    btn_row.setSpacing(8)

    exit_btn = QPushButton("Выход")
    exit_btn.setObjectName("exitBtn")
    exit_btn.setFixedHeight(40)
    exit_btn.clicked.connect(lambda: (result.update({"action": "exit"}), dlg.accept()))

    cont_btn = QPushButton("Продолжить без установки →")
    cont_btn.setObjectName("continueBtn")
    cont_btn.setFixedHeight(40)
    cont_btn.clicked.connect(lambda: (result.update({"action": "continue"}), dlg.accept()))

    btn_row.addWidget(exit_btn)
    btn_row.addWidget(cont_btn, 1)
    layout.addLayout(btn_row)

    dlg.adjustSize()
    dlg.exec_()

    return result["action"] == "continue"


def main():
    os.environ.setdefault("PYWEBVIEW_GUI", "pyqt5")

    # ── Проверка первого запуска ──────────────────────────
    config_path = Path.home() / "Documents" / "ArizonaLauncher" / "config.json"
    is_first_run = not config_path.exists()
    force_deps   = "--show-deps" in sys.argv

    if is_first_run or force_deps:
        missing = []
        if force_deps:
            # Режим просмотра — показываем оба пункта независимо от реальных проверок
            missing = ["vcredist", "webview2"]
        else:
            if not _check_vcredist():
                missing.append("vcredist")
            if not _check_webview2():
                missing.append("webview2")

        if missing:
            logger.info(f"{'[force]' if force_deps else 'Первый запуск'}, отсутствуют: {missing}")
            should_continue = _show_dependency_dialog(missing)
            if not should_continue:
                sys.exit(0)

    # ── Запуск основного окна ─────────────────────────────
    app = WebViewApp()

    # При первом запуске — пробуем найти игру автоматически
    auto_found = False
    if is_first_run and not force_deps:
        auto_found = app.launcher.auto_detect_game_paths()
        if auto_found:
            logger.info(f"Авто-обнаружение: {app.launcher.game_path}")
        else:
            logger.info("Авто-обнаружение: игра не найдена, пользователь укажет вручную")

    def _on_loaded():
        """После загрузки страницы открываем панель первого запуска."""
        import time as _t, json as _json
        _t.sleep(0.8)
        try:
            wins = webview.windows
            if not wins:
                return
            w = wins[0]

            data = {
                "auto_found": auto_found,
                "game_path": str(app.launcher.game_path or "").replace("\\", "\\\\"),
                "check_status": "not_found",
                "folder": "",
                "missing": []
            }

            if auto_found and app.launcher.game_path:
                game_dir = str(Path(app.launcher.game_path).parent)
                check = app._check_game_folder(game_dir)
                data["check_status"] = check["status"]
                data["folder"]       = check.get("folder", game_dir).replace("\\", "\\\\")
                data["missing"]      = check.get("missing", [])

            payload = _json.dumps(data)
            w.evaluate_js(f"window._flStart && window._flStart({payload})")
        except Exception as ex:
            logger.warning(f"_on_loaded error: {ex}")

    try:
        window = webview.create_window('Arizona RP Launcher', 'index.html', js_api=app, width=1285, height=732,
                                       resizable=True, fullscreen=False, min_size=(1032, 583))
        if is_first_run:
            window.events.loaded += _on_loaded
        webview.start(debug=False)
    except Exception as e:
        logger.error(f"Error: {e}")
        if sys.stdin and sys.stdin.isatty():
            input("Press Enter to exit...")

if __name__ == '__main__':
    main()
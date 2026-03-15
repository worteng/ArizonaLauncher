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
                launch = game_dir / "ArizonaLauncher6_byAIR.exe"
                if launch.exists():
                    found_launcher = launch
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
        try:
            wins = webview.windows
            if wins:
                wins[0].restore()
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
                "paths_configured": bool(self.launcher.launcher_path and self.launcher.game_path)}

    def get_saved_data(self):
        """Возвращает сохраненные данные (никнейм, сервер)"""
        return {
            "success": True,
            "nickname": self.launcher.config.get('last_nickname', ''),
            "server": self.launcher.config.get('last_server', 15)
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
        game_exe     = os.path.join(folder_path, "gta_sa.exe")
        launcher_exe = os.path.join(folder_path, "ArizonaLauncher6_byAIR.exe")
        plugins_dir  = os.path.join(folder_path, "preloading_plugins")

        if not os.path.exists(game_exe):
            return {"status": "no_game", "folder": folder_path}

        has_launcher = os.path.exists(launcher_exe)
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
                "launcher_exe": launcher_exe if has_launcher else ""}

    def select_game_path(self):
        """Открыть диалог выбора папки с игрой"""
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
                return {"success": False, "message": "Папка не выбрана"}

            check = self._check_game_folder(folder_path)

            if check["status"] == "no_game":
                return {"success": False, "message": "gta_sa.exe не найден в выбранной папке"}

            if check["status"] == "needs_install":
                # Сохраняем game_path уже сейчас, launcher установим позже
                self.launcher.set_game_paths(check["game_exe"], check.get("launcher_exe", ""))
                return {
                    "success": False,
                    "needs_install": True,
                    "folder": folder_path,
                    "missing": check["missing"],
                    "message": "Требуется установка компонентов"
                }

            # Всё хорошо
            self.launcher.set_game_paths(check["game_exe"], check["launcher_exe"])
            return {"success": True, "message": f"Путь установлен: {folder_path}"}
        except Exception as e:
            logger.error(f"Error selecting game path: {e}")
            return {"success": False, "message": str(e)}

    def download_and_install_launcher(self, folder_path):
        """Скачивает архив лаунчера с GitHub и устанавливает в папку игры.
           Отправляет прогресс через JS-событие."""
        GITHUB_RELEASE_URL = "https://raw.githubusercontent.com/worteng/ArizonaLauncher/refs/heads/main/others/arizonapatcher.zip"
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
            _send("download", 0, "Подключение к GitHub...")

            # 1. Качаем архив с прогрессом
            resp = requests.get(GITHUB_RELEASE_URL, stream=True, timeout=60, verify=False,
                                headers={"User-Agent": "Mozilla/5.0"})
            if resp.status_code != 200:
                _send("error", 0, f"Ошибка загрузки: HTTP {resp.status_code}")
                return {"success": False, "message": f"HTTP {resp.status_code}"}

            total = int(resp.headers.get("content-length", 0))
            downloaded = 0

            tmp_zip = os.path.join(tempfile.gettempdir(), "arizona_launcher_install.zip")
            with open(tmp_zip, "wb") as f:
                for chunk in resp.iter_content(chunk_size=65536):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        pct = int(downloaded / total * 80) if total else 10
                        mb = downloaded / 1024 / 1024
                        _send("download", pct, f"Скачано {mb:.1f} МБ...")

            _send("extract", 82, "Распаковка архива...")

            # 2. Распаковываем
            tmp_dir = os.path.join(tempfile.gettempdir(), "arizona_launcher_extract")
            if os.path.exists(tmp_dir):
                shutil.rmtree(tmp_dir, ignore_errors=True)
            os.makedirs(tmp_dir, exist_ok=True)

            with zipfile.ZipFile(tmp_zip, 'r') as zf:
                zf.extractall(tmp_dir)

            _send("install", 90, "Установка файлов...")

            # 3. Ищем ArizonaLauncher6_byAIR.exe рекурсивно в распакованном
            launcher_src = None
            for root, dirs, files in os.walk(tmp_dir):
                for fname in files:
                    if fname.lower() == "arizonalauncher6_byair.exe":
                        launcher_src = os.path.join(root, fname)
                        break
                if launcher_src:
                    break

            if not launcher_src:
                # Если не нашли точное имя — берём любой .exe
                for root, dirs, files in os.walk(tmp_dir):
                    for fname in files:
                        if fname.lower().endswith(".exe"):
                            launcher_src = os.path.join(root, fname)
                            break
                    if launcher_src:
                        break

            if not launcher_src:
                _send("error", 0, "ArizonaLauncher6_byAIR.exe не найден в архиве")
                return {"success": False, "message": "Исполняемый файл не найден в архиве"}

            launcher_dest = os.path.join(folder_path, "ArizonaLauncher6_byAIR.exe")
            shutil.copy2(launcher_src, launcher_dest)

            # 4. Копируем все файлы рядом с .exe (DLL и т.п.)
            src_dir = os.path.dirname(launcher_src)
            for fname in os.listdir(src_dir):
                src_file = os.path.join(src_dir, fname)
                if os.path.isfile(src_file) and src_file != launcher_src:
                    shutil.copy2(src_file, os.path.join(folder_path, fname))

            # 5. Копируем preloading_plugins из архива (если есть), иначе создаём пустую
            plugins_dir = os.path.join(folder_path, "preloading_plugins")
            plugins_src = None
            for root, dirs, files in os.walk(tmp_dir):
                if os.path.basename(root).lower() == "preloading_plugins":
                    plugins_src = root
                    break

            if plugins_src:
                _send("install", 94, "Копирование preloading_plugins...")
                if os.path.exists(plugins_dir):
                    # Копируем файлы поверх, не удаляя существующие
                    for fname in os.listdir(plugins_src):
                        src_file = os.path.join(plugins_src, fname)
                        if os.path.isfile(src_file):
                            shutil.copy2(src_file, os.path.join(plugins_dir, fname))
                else:
                    shutil.copytree(plugins_src, plugins_dir)
                logger.info(f"preloading_plugins скопирован из архива в {plugins_dir}")
            else:
                os.makedirs(plugins_dir, exist_ok=True)

            _send("install", 97, "Финализация...")

            # 6. Устанавливаем пути
            game_exe = os.path.join(folder_path, "gta_sa.exe")
            self.launcher.set_game_paths(game_exe, launcher_dest)

            # 7. Добавляем в исключения Windows Defender
            _send("install", 98, "Добавление в исключения антивируса...")
            self._add_defender_exclusion(launcher_dest)

            # Чистка
            try:
                os.remove(tmp_zip)
                shutil.rmtree(tmp_dir, ignore_errors=True)
            except Exception:
                pass

            _send("done", 100, "Установка завершена!")
            logger.info(f"download_and_install_launcher: установлен в {folder_path}")
            return {"success": True, "message": "Лаунчер успешно установлен"}

        except requests.exceptions.ConnectionError:
            _send("error", 0, "Нет подключения к интернету")
            return {"success": False, "message": "Нет подключения к интернету"}
        except requests.exceptions.Timeout:
            _send("error", 0, "Тайм-аут соединения")
            return {"success": False, "message": "Тайм-аут соединения"}
        except Exception as e:
            logger.error(f"download_and_install_launcher error: {e}")
            _send("error", 0, str(e))
            return {"success": False, "message": str(e)}

    def start_launcher_install(self, folder_path):
        """Запускает скачивание и установку лаунчера в фоновом потоке"""
        def run():
            self.download_and_install_launcher(folder_path)
        Thread(target=run, daemon=True).start()
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
        """Загружает moonloader.txt с GitHub и парсит список скриптов"""
        MOONLOADER_URL = "https://raw.githubusercontent.com/worteng/ArizonaLauncher/main/moonloader.txt"
        try:
            logger.info(f"fetch_moonloader_catalog: запрос {MOONLOADER_URL}")
            resp = requests.get(MOONLOADER_URL, timeout=10, headers={"Cache-Control": "no-cache"}, verify=False)
            logger.info(f"fetch_moonloader_catalog: статус {resp.status_code}, размер {len(resp.text)} байт")
            if resp.status_code == 404:
                return {"success": False, "message": "Файл moonloader.txt не найден на GitHub (404). Создай его в репозитории."}
            if resp.status_code != 200:
                return {"success": False, "message": f"GitHub вернул HTTP {resp.status_code}"}
            scripts = self._parse_catalog_txt(resp.text)
            logger.info(f"fetch_moonloader_catalog: распарсено {len(scripts)} скриптов")
            if len(scripts) == 0:
                return {"success": False, "message": "moonloader.txt найден, но не содержит блоков [script]"}
            return {"success": True, "data": scripts}
        except requests.exceptions.ConnectionError:
            return {"success": False, "message": "Нет подключения к интернету"}
        except requests.exceptions.Timeout:
            return {"success": False, "message": "Превышено время ожидания (GitHub не отвечает)"}
        except Exception as e:
            logger.error(f"fetch_moonloader_catalog error: {e}")
            return {"success": False, "message": str(e)}


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
        """После загрузки страницы проверяем состояние игры."""
        import time as _t, json as _json
        _t.sleep(0.8)
        try:
            wins = webview.windows
            if not wins:
                return
            w = wins[0]

            if not auto_found:
                w.evaluate_js(
                    "showNotification('📂 Игра не найдена — укажите путь в меню папок', 'error')"
                )
                return

            game_dir = str(Path(app.launcher.game_path).parent)
            check = app._check_game_folder(game_dir)

            if check["status"] == "ok":
                safe_dir = game_dir.replace("\\", "\\\\")
                w.evaluate_js(
                    f"showNotification('✅ Игра найдена: {safe_dir}', 'success')"
                )
            elif check["status"] == "needs_install":
                payload = _json.dumps({
                    "folder": check["folder"].replace("\\", "\\\\"),
                    "missing": check["missing"]
                })
                w.evaluate_js(
                    f"window._autoInstallPrompt && window._autoInstallPrompt({payload})"
                )
        except Exception as ex:
            logger.warning(f"_on_loaded notify error: {ex}")

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
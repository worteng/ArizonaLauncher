import os, sys, subprocess, time, json, webview, logging, psutil, requests, re, base64
from pathlib import Path
from threading import Thread
import threading
import urllib3

# ── DEBUG ──────────────────────────────────────────────────────────
# Если True — запускается HTTP debug-сервер на 127.0.0.1:8765
# и CDP-отладка на порту 9222. Перед релизом поставить False.
DEBUG = True

# Включаем CDP-отладку (Chrome DevTools Protocol) на порту 9222 в debug-режиме.
if DEBUG:
    webview.settings['REMOTE_DEBUGGING_PORT'] = 9222

# PyQt5 — единый импорт для всех Qt-диалогов (избегаем дублирования внутри методов)
try:
    from PyQt5.QtWidgets import (
        QApplication, QFileDialog, QDialog, QLabel, QPushButton,
        QFrame, QHBoxLayout, QVBoxLayout
    )
    _HAS_QT = True
except ImportError:
    _HAS_QT = False

# Версия лаунчера
LAUNCHER_VERSION = "v1.8.2"

# Лимиты для безопасной распаковки архивов
_MAX_ZIP_FILES    = 5000    # макс. количество файлов в архиве
_MAX_ZIP_FILE_MB  = 200     # макс. размер одного файла (МБ)
_MAX_ZIP_TOTAL_MB = 2000    # макс. общий размер распакованных данных (МБ)


def _get_app_dir():
    """Возвращает директорию, где лежат ресурсы приложения (index.html, assets).

    • В обычном запуске (python main.py) — директория скрипта.
    • В PyInstaller --onefile — sys._MEIPASS (временная распаковка).
    • В PyInstaller --onedir — директория .exe (рядом с ресурсами из --add-data).
    """
    meipass = getattr(sys, '_MEIPASS', None)
    if meipass:
        return meipass
    return os.path.dirname(os.path.abspath(sys.executable if getattr(sys, 'frozen', False) else __file__))


def _get_icon_cache_dir():
    """Возвращает директорию для кэша иконок серверов."""
    cache_dir = Path(os.getenv('LOCALAPPDATA') or Path.home()) / 'ArizonaLauncher' / 'icons'
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def _safe_extract(zf, dest_dir):
    """Безопасная распаковка zip: защита от zip-slip и переполнения диска.

    Проверяет:
      • Путь каждого файла не выходит за пределы dest_dir (защита от zip-slip)
      • Общее число файлов не превышает _MAX_ZIP_FILES
      • Размер каждого файла ≤ _MAX_ZIP_FILE_MB
      • Суммарный размер ≤ _MAX_ZIP_TOTAL_MB

    Raises:
        ValueError: при обнаружении zip-slip или превышении лимитов
    """
    dest_real = os.path.realpath(dest_dir)
    total_bytes = 0
    names = zf.namelist()
    if len(names) > _MAX_ZIP_FILES:
        raise ValueError(f"Слишком много файлов в архиве: {len(names)} > {_MAX_ZIP_FILES}")

    for member in zf.infolist():
        # Пропускаем записи директорий (no filename)
        member_name = member.filename
        if not member_name or member_name.endswith('/'):
            continue

        # Проверка zip-slip: разрешаем только абсолютные пути внутри dest_dir
        member_path = os.path.realpath(os.path.join(dest_real, member_name))
        if not (member_path == dest_real or member_path.startswith(dest_real + os.sep)):
            raise ValueError(f"Zip-slip обнаружен: {member_name}")

        # Проверка размера файла
        size_mb = member.file_size / 1024 / 1024
        if size_mb > _MAX_ZIP_FILE_MB:
            raise ValueError(f"Файл {member_name} слишком большой: {size_mb:.1f} МБ > {_MAX_ZIP_FILE_MB} МБ")

        total_bytes += member.file_size
        if total_bytes / 1024 / 1024 > _MAX_ZIP_TOTAL_MB:
            raise ValueError(f"Суммарный размер архива превышает {_MAX_ZIP_TOTAL_MB} МБ")

    # Все проверки пройдены — безопасно распаковываем
    zf.extractall(dest_real)


def _safe_basename(name: str) -> str:
    """Очищает имя файла: оставляет только basename, затем проверяет whitelist.
    Возвращает безопасное имя или вызывает ValueError."""
    if not name or not name.strip():
        raise ValueError("Пустое имя файла")
    cleaned = os.path.basename(name)
    if not cleaned or cleaned in ('.', '..'):
        raise ValueError(f"Недопустимое имя файла: {name}")
    if not re.fullmatch(r'^[A-Za-z0-9._\- ()]+$', cleaned):
        raise ValueError(f"Недопустимые символы в имени файла: {cleaned}")
    return cleaned

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s',
                    handlers=[logging.FileHandler(os.path.join(_get_app_dir(), 'arizona_launcher.log')), logging.StreamHandler()])
logger = logging.getLogger(__name__)

class ArizonaLauncher:
    def __init__(self):
        self.documents_path = str(Path.home() / "Documents" / "ArizonaLauncher")
        Path(self.documents_path).mkdir(parents=True, exist_ok=True)
        self.config_path = os.path.join(self.documents_path, "config.json")
        # Блокировка для безопасного доступа к config из разных потоков
        # (autocheck daemon, resize Timer, JS-API worker).
        self._cfg_lock = threading.RLock()
        self.config = self.load_config()
        self.game_path = self.config.get('game_path', '')
        self.launcher_path = self.config.get('launcher_path', '')
        if not self.game_path or not self.launcher_path:
            self.auto_detect_game_paths()
        self.patches_path = os.path.join(os.path.dirname(self.game_path), "preloading_plugins", "#ArizonaPatches.json") if self.game_path else ""

    def load_config(self):
        defaults = {'last_nickname': '', 'last_server': 15, 'game_path': '', 'launcher_path': '',
                    'last_launcher_version': None,
                    'patches_version': None,
                    'patches_last_check': 0,
                    'launch_params': {'memory': 4096, 'widescreen': False, 'texture_mode': False, 'color_depth_16': False,
                                      'allow_hdr': False, 'enable_grass': False, 'ldo': False,
                                      'auth_cef_enable': False, 'window_mode': True, 'cdn': '1,1,1',
                                      'autologin': True,
                                      # v7/v8 параметры
                                      'enable_new_grass': False, 'old_window': False, 'use_d3dx9_43': False,
                                      'show_dialog_ids': False, 'offcef': False, 'modern_scale': False,
                                      'trees_new': False},
                    'launcher_settings': {'bg_image': None}}
        with self._cfg_lock:
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
        # Атомарная запись: пишем во временный файл и переименовываем.
        # Блокировка исключает чередующуюся запись из разных потоков.
        with self._cfg_lock:
            tmp_path = self.config_path + '.tmp'
            try:
                with open(tmp_path, 'w', encoding='utf-8') as f:
                    json.dump(self.config, f, indent=2, ensure_ascii=False)
                os.replace(tmp_path, self.config_path)
            except Exception as e:
                logger.error(f"Config save error: {e}")
                # Чистим temp-файл при ошибке
                try:
                    if os.path.exists(tmp_path):
                        os.remove(tmp_path)
                except Exception:
                    pass

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
                launch_v8 = game_dir / "ArizonaLauncher8.0_byAIR.exe"
                launch_v7 = game_dir / "ArizonaLauncher7.0_byAIR.exe"
                launch_v6 = game_dir / "ArizonaLauncher6_byAIR.exe"
                if launch_v8.exists():
                    found_launcher = launch_v8
                elif launch_v7.exists():
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
        # Фиксируем фактически установленную версию лаунчера AIR
        detected = self.get_launcher_version()
        self.config['last_launcher_version'] = detected
        self.save_config()

    def kill_all_launchers(self):
        # Точные имена exe-файлов лаунчера — не substring match, чтобы не убить
        # себя (PyInstaller exe тоже содержит "arizonalauncher") или античит.
        LAUNCHER_EXES = {'arizonalauncher6_byair.exe', 'arizonalauncher7.0_byair.exe', 'arizonalauncher8.0_byair.exe'}
        my_pid = os.getpid()
        killed, denied = 0, 0
        for proc in psutil.process_iter(['pid', 'name']):
            try:
                if proc.pid == my_pid:
                    continue
                name = (proc.info.get('name') or '').lower()
                if name in LAUNCHER_EXES:
                    proc.kill()
                    killed += 1
            except (psutil.NoSuchProcess, psutil.ZombieProcess):
                continue
            except psutil.AccessDenied:
                denied += 1
                logger.warning(f"kill_all_launchers: AccessDenied pid={proc.pid} name={proc.info.get('name')}")
        if denied:
            logger.warning(f"kill_all_launchers: {denied} процессов не удалось убить (нет прав)")
        logger.info(f"kill_all_launchers: killed={killed}, denied={denied}")
        time.sleep(1)

    def get_launcher_version(self):
        """Возвращает 'v8'/'v7'/'v6' в зависимости от установленного лаунчера.
        Логика:
        1. Если есть папка preloading_plugins с файлами (dll и конфиг)
        2. Проверяем какой лаунчер установлен в корневой папке игры
        3. Приоритет: v8 > v7 > v6
        4. Если лаунчера нет или папки preloading нет -> 'v8' (по умолчанию)
        """
        logger.info("[get_launcher_version] Определение версии лаунчера")
        
        if not self.game_path:
            logger.info("[get_launcher_version] game_path не установлен, возвращаем v8 по умолчанию")
            return "v8"
        
        game_dir = os.path.dirname(self.game_path)
        plugins_dir = os.path.join(game_dir, "preloading_plugins")
        
        logger.info(f"[get_launcher_version] Проверка папки: {plugins_dir}")
        
        # Проверяем наличие папки preloading_plugins с файлами
        if os.path.isdir(plugins_dir) and os.listdir(plugins_dir):
            logger.info(f"[get_launcher_version] Папка preloading_plugins найдена, файлов: {len(os.listdir(plugins_dir))}")
            # Проверяем какой лаунчер установлен (приоритет v8 > v7 > v6)
            launcher_v8 = os.path.join(game_dir, "ArizonaLauncher8.0_byAIR.exe")
            launcher_v7 = os.path.join(game_dir, "ArizonaLauncher7.0_byAIR.exe")
            launcher_v6 = os.path.join(game_dir, "ArizonaLauncher6_byAIR.exe")
            
            if os.path.exists(launcher_v8):
                logger.info(f"[get_launcher_version] Найден лаунчер v8: {launcher_v8}")
                return "v8"
            elif os.path.exists(launcher_v7):
                logger.info(f"[get_launcher_version] Найден лаунчер v7: {launcher_v7}")
                return "v7"
            elif os.path.exists(launcher_v6):
                logger.info(f"[get_launcher_version] Найден лаунчер v6: {launcher_v6}")
                return "v6"
            else:
                logger.info("[get_launcher_version] Лаунчер не найден, возвращаем v8 по умолчанию")
        else:
            logger.info("[get_launcher_version] Папка preloading_plugins не найдена или пуста, возвращаем v8 по умолчанию")
        
        return "v8"

    def launch_game(self, nickname, server_data=None, launch_params=None):
        if not self.launcher_path or not os.path.exists(self.launcher_path):
            return {"success": False, "message": "Launcher not found", "code": "LAUNCHER_MISSING"}
        if not self.game_path or not os.path.exists(self.game_path):
            return {"success": False, "message": "Game path is missing or invalid — set it in Settings",
                    "code": "GAME_MISSING"}
        if nickname is None or not isinstance(nickname, str) or not nickname.strip():
            return {"success": False, "message": "Enter nickname", "code": "NICKNAME_EMPTY"}
        # Санитайзер: убираем control-символы (включая \n, \r, \0) и обрезаем
        nickname = re.sub(r'[\x00-\x1f\x7f]', '', nickname.strip())[:20]
        if not nickname:
            return {"success": False, "message": "Nickname contains only invalid characters",
                    "code": "NICKNAME_INVALID"}
        srv_ip = server_data.get('ip', 'payson.arizona-rp.com') if server_data else 'payson.arizona-rp.com'
        srv_port = server_data.get('port', 7777) if server_data else 7777
        params = launch_params or self.config.get('launch_params', {})
        # v8 — наследник v7, поддерживает те же доп. флаги (если v8 их не сломал)
        launcher_ver = self.get_launcher_version()
        is_v7plus = launcher_ver in ("v7", "v8")

        # Валидация CDN: должен быть формат "n,n,n" (3 слота, цифры)
        cdn_value = str(params.get('cdn', '1,1,1'))
        if not re.fullmatch(r'\d+,\d+,\d+', cdn_value):
            logger.warning(f"launch_game: некорректный CDN '{cdn_value}', использую '1,1,1'")
            cdn_value = '1,1,1'

        cmd = [self.launcher_path, "-c", "-h", srv_ip, "-p", str(srv_port), "-mem", str(params.get('memory', 4096)),
               "-n", nickname, "-arizona"]

        # Общие флаги для всех версий (v6/v7/v8)
        common_flags = {
            'widescreen': '-widescreen', 'texture_mode': '-t', 'color_depth_16': '-16bpp',
            'allow_hdr': '-allow_hdr', 'enable_grass': '-enable_grass', 'ldo': '-ldo',
            'auth_cef_enable': '-auth_cef_enable',
            'autologin': '-x',
        }
        for k, v in common_flags.items():
            if params.get(k, False): cmd.append(v)

        # Оконный режим: -window и -old_window взаимоисключающие
        # old_window доступен в v7 и v8
        if is_v7plus and params.get('old_window', False):
            cmd.append('-old_window')
        elif params.get('window_mode', False):
            cmd.append('-window')

        # Доп. флаги v7+ (v8 наследует v7; добавлен новый v8-флаг trees_new)
        if is_v7plus:
            v7plus_flags = {
                'enable_new_grass': '-enable_new_grass',
                'use_d3dx9_43':     '-use_d3dx9_43',
                'show_dialog_ids':  '-show_dialog_ids',
                'offcef':           '-offcef',
                'modern_scale':     '-modern_scale',
                'trees_new':        '-trees_new',
            }
            for k, v in v7plus_flags.items():
                if params.get(k, False): cmd.append(v)

        cmd.extend(["-cdn", cdn_value])
        try:
            self.kill_all_launchers()
            proc = subprocess.Popen(cmd, cwd=os.path.dirname(self.launcher_path), creationflags=subprocess.CREATE_NO_WINDOW)
            # Poll до 2 секунд, чтобы убедиться, что процесс жив и не крашнулся.
            # ВАЖНО: stub-лаунчеры (Air v6/v7/v8) могут завершиться с кодом 0
            # сразу после spawning дочернего процесса игры — это НЕ краш.
            deadline = time.time() + 2.0
            exit_code = None
            while time.time() < deadline:
                rc = proc.poll()
                if rc is not None:
                    exit_code = rc
                    break
                time.sleep(0.1)
            rc_now = proc.poll()

            # Успех: процесс либо ещё жив, либо завершился с кодом 0 (stub).
            if (rc_now is None) or rc_now == 0:
                self.config['last_nickname'] = nickname
                if server_data: self.config['last_server'] = server_data.get('number')
                self.config['launch_params'] = params
                self.save_config()
                # Detach: пусть ОС перехватит handle, не держим зомби
                return {"success": True, "message": f"Launching for {nickname}", "pid": proc.pid}
            else:
                return {"success": False, "message": f"Launcher crashed (exit code {rc_now})",
                        "code": "LAUNCHER_CRASHED"}
        except Exception as e:
            logger.error(f"launch_game: {e}")
            return {"success": False, "message": str(e), "code": "EXCEPTION"}

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

            cleaned = re.sub(r'^\s*//.*', '', raw, flags=re.MULTILINE)
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
            # Защита от path traversal: имя файла не должно содержать разделителей/относительных путей.
            if not filename or '/' in filename or '\\' in filename or filename in ('.', '..'):
                return {"success": False, "message": "Недопустимое имя файла"}
            backup_dir = Path(self.documents_path) / "backups"
            backup_path = backup_dir / filename
            # Двойная проверка: реальный путь не должен выйти за пределы backup_dir.
            if os.path.realpath(backup_path) != os.path.realpath(os.path.join(str(backup_dir), filename)) \
                    or os.path.commonpath([os.path.realpath(str(backup_path)), os.path.realpath(str(backup_dir))]) != os.path.realpath(str(backup_dir)):
                return {"success": False, "message": "Недопустимое имя файла"}
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
            # Защита от path traversal
            if not filename or '/' in filename or '\\' in filename or filename in ('.', '..'):
                return {"success": False, "message": "Недопустимое имя файла"}
            backup_dir = Path(self.documents_path) / "backups"
            backup_path = backup_dir / filename
            if os.path.realpath(str(backup_path)) != os.path.realpath(os.path.join(str(backup_dir), filename)):
                return {"success": False, "message": "Недопустимое имя файла"}
            if not backup_path.exists():
                return {"success": False, "message": "Файл не найден"}
            backup_path.unlink()
            return {"success": True}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def preview_patches_backup(self, filename: str):
        """Возвращает содержимое бэкапа для предпросмотра."""
        try:
            backup_dir = Path(self.documents_path) / "backups"
            backup_path = backup_dir / filename
            if not backup_path.exists():
                return {"success": False, "message": "Файл не найден"}
            if backup_path.name != filename or '/' in filename or '\\' in filename:
                return {"success": False, "message": "Недопустимое имя файла"}
            with open(backup_path, 'r', encoding='utf-8') as f:
                raw = f.read()
            cleaned = re.sub(r'^\s*//.*', '', raw, flags=re.MULTILINE)
            cleaned = '\n'.join(line for line in cleaned.split('\n') if line.strip())
            data = json.loads(cleaned)
            # Бэкап может быть плоским (ключи патчей на верхнем уровне)
            # или вложенным ({"patches": {...}, "launch_params": {...}})
            if 'patches' in data and isinstance(data['patches'], dict):
                patches = data['patches']
                launch_params = data.get('launch_params', {})
            else:
                patches = {k: v for k, v in data.items() if isinstance(v, bool)}
                launch_params = {k: v for k, v in data.items() if not isinstance(v, bool)}
            enabled = [k for k, v in patches.items() if v]
            disabled = [k for k, v in patches.items() if not v]
            return {
                "success": True,
                "filename": filename,
                "type": "before_import" if "before_import" in filename
                        else "before_restore" if "before_restore" in filename
                        else "save",
                "size": backup_path.stat().st_size,
                "patches_total": len(patches),
                "patches_enabled": enabled,
                "patches_disabled": disabled,
                "launch_params": launch_params,
                "saved_at": data.get('saved_at', '') if isinstance(data, dict) else '',
            }
        except json.JSONDecodeError:
            return {"success": False, "message": "Файл повреждён (не JSON)"}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def _get_dll_version(self, dll_path):
        """Возвращает версию DLL как строку '1.0.0.0' или None при ошибке."""
        try:
            import win32api
            info = win32api.GetFileVersionInfo(dll_path, '\\')
            ms = info['FileVersionMS']
            ls = info['FileVersionLS']
            return f"{ms >> 16}.{ms & 0xFFFF}.{ls >> 16}.{ls & 0xFFFF}"
        except Exception as e:
            logger.warning(f"Failed to get DLL version for {dll_path}: {e}")
            return None

    # ===== ArizonaPatches Management =====

    def check_patches_files(self):
        """Проверяет наличие #ArizonaPatches.json и #ArizonaPatches.dll в preloading_plugins/."""
        if not self.game_path:
            return {"json_exists": False, "dll_exists": False, "dll_version": None, "message": "game_path не установлен", "both_exist": False}
        
        plugins_dir = os.path.join(os.path.dirname(self.game_path), "preloading_plugins")
        json_path = os.path.join(plugins_dir, "#ArizonaPatches.json")
        dll_path = os.path.join(plugins_dir, "#ArizonaPatches.dll")
        
        if not os.path.isdir(plugins_dir):
            return {"json_exists": False, "dll_exists": False, "dll_version": None, "message": "preloading_plugins не найдена", "both_exist": False}

        json_exists = os.path.exists(json_path)
        dll_exists = os.path.exists(dll_path)
        dll_version = None
        dll_path_checked = None
        
        # Ищем DLL: основной файл или любой бэкап (.1, .1.1, .1.2, etc.)
        dll_candidates = []
        if os.path.exists(dll_path):
            dll_candidates.append(dll_path)
        # Ищем бэкапы: .1, .1.1, .1.2, etc.
        try:
            for fname in os.listdir(plugins_dir):
                if fname.startswith("#ArizonaPatches.dll") and fname != "#ArizonaPatches.dll":
                    dll_candidates.append(os.path.join(plugins_dir, fname))
        except OSError:
            pass
        
        dll_exists = False
        dll_version = None
        dll_path_checked = None
        
        for cand in dll_candidates:
            ver = self._get_dll_version(cand)
            if ver:
                dll_exists = True
                dll_version = ver
                dll_path_checked = cand
                break
        
        return {
            "json_exists": os.path.exists(json_path),
            "dll_exists": dll_exists,
            "dll_version": dll_version,
            "json_path": json_path if os.path.exists(json_path) else None,
            "dll_path": dll_path_checked,
            "plugins_dir": os.path.dirname(dll_path),
            "both_exist": os.path.exists(json_path) and dll_exists
        }

    def _disable_old_dll(self, dll_path):
        """Переименовывает старый DLL в .dll1 чтобы игра его не грузила."""
        try:
            # Не переименовываем если уже переименован (заканчивается на .1, .1.1, .1.2 и т.д.)
            import re
            if re.search(r'\.1(\.\d+)?$', dll_path):
                return dll_path
            if os.path.exists(dll_path):
                backup_path = dll_path + ".1"
                if os.path.exists(backup_path):
                    os.remove(backup_path)
                os.rename(dll_path, backup_path)
                logger.info(f"Old DLL renamed to .1: {backup_path}")
                return backup_path
        except Exception as e:
            logger.warning(f"Failed to rename old DLL: {e}")
        return None

    def _remove_disabled_dll(self, dll_path):
        """Удаляет переименованный .dll1 при установке v2."""
        try:
            backup_path = dll_path + ".1"
            if os.path.exists(backup_path):
                os.remove(backup_path)
                logger.info(f"Removed old disabled DLL: {backup_path}")
                return True
        except Exception as e:
            logger.warning(f"Failed to remove old DLL: {e}")
        return False

    def get_installed_patches_version(self):
        """Возвращает установленную версию патчей из конфига (v1/v2/None)."""
        return self.config.get('patches_version')

    def check_patches_status(self):
        """
        Главный метод проверки статуса патчей.
        Возвращает: {status, version, message, can_update, download_url, message_detail}
        status: 'missing' | 'outdated_v1' | 'current'
        """
        try:
            files = self.check_patches_files()
        except Exception as e:
            logger.warning(f"check_patches_status: check_patches_files failed: {e}")
            return {
                "status": "missing",
                "version": None,
                "message": "Патчи недоступны",
                "message_detail": str(e),
                "can_update": True,
                "download_url": self._get_patches_download_url("v2"),
                "installed_version": None
            }
        installed_version = self.get_installed_patches_version()
        
        # 1. Missing: нет json ИЛИ нет dll
        if not files['both_exist']:
            missing = []
            if not os.path.exists(os.path.join(os.path.dirname(self.game_path), "preloading_plugins", "#ArizonaPatches.json")):
                missing.append("#ArizonaPatches.json")
            if not os.path.exists(os.path.join(os.path.dirname(self.game_path), "preloading_plugins", "#ArizonaPatches.dll")):
                missing.append("#ArizonaPatches.dll")
            
            return {
                "status": "missing",
                "version": None,
                "message": f"Патчи недоступны: отсутствуют файлы: {', '.join(missing)}",
                "message_detail": "Файлы патчей не найдены в папке preloading_plugins. Необходимо скачать патчи.",
                "can_update": True,
                "download_url": self._get_patches_download_url("v2"),
                "installed_version": None
            }
        
        # 2. Проверяем версию DLL — если 1.0.0.0, блокируем настройки
        dll_version = files.get('dll_version')
        if dll_version == "1.0.0.0":
            # Отключаем старый DLL переименованием
            dll_path = files.get('dll_path')
            if dll_path:
                self._disable_old_dll(dll_path)
            return {
                "status": "outdated_dll_v1",
                "version": "1.0.0.0",
                "message": "Патчи недоступны: устаревший ArizonaPatches.dll (1.0.0.0)",
                "message_detail": "Установлен старый ArizonaPatches.dll (1.0.0.0), он вызывает краши игры. Ждите выхода v2 от EIR — тогда кнопка «Скачать» станет активной.",
                "can_update": False,
                "download_url": None,
                "installed_version": "1.0.0.0"
            }
        
        # 3. Файлы есть, проверяем версию в конфиге
        installed_version = self.config.get('patches_version')
        
        # 4. Если версия не задана, но файлы на месте и DLL не 1.0.0.0 — считаем current
        if installed_version is None:
            if dll_version and dll_version != "1.0.0.0":
                return {
                    "status": "current",
                    "version": "v2",
                    "message": "Патчи актуальны",
                    "message_detail": "Патчи установлены и работают корректно.",
                    "can_update": False,
                    "download_url": None,
                    "installed_version": "v2"
                }
            return {
                "status": "missing",
                "version": None,
                "message": "Патчи не установлены",
                "message_detail": "Патчи не были установлены через лаунчер. Необходимо скачать и установить патчи.",
                "can_update": True,
                "download_url": self._get_patches_download_url("v2"),
                "installed_version": None
            }
        
        # 5. outdated_v1: версия v1
        if installed_version == "v1":
            return {
                "status": "outdated_v1",
                "version": "v1",
                "message": "Патчи v1 не работают после глобальной обновы игры",
                "message_detail": "У вас установлены патчи v1 — они не работают после глобальной обновы игры (февраль 2026). EIR выпустил исправленную версию v2.",
                "can_update": True,
                "download_url": self._get_patches_download_url("v2"),
                "installed_version": "v1"
            }
        
        # 3. current: версия v2 или новее
        return {
            "status": "current",
            "version": installed_version or "v2",
            "message": "Патчи актуальны",
            "message_detail": "Патчи v2 установлены и работают корректно.",
            "can_update": False,
            "download_url": None,
            "installed_version": installed_version
        }

    def _get_patches_download_url(self, version):
        """Возвращает URL для скачивания патчей заданной версии."""
        # Структура: patches/arizonapatches_v{version}.zip
        return f"https://raw.githubusercontent.com/worteng/ArizonaLauncher/main/patches/arizonapatches_{version}.zip"

    def check_patches_available(self, version="v2"):
        """Проверяет доступен ли архив патчей на GitHub (HEAD-запрос)."""
        url = self._get_patches_download_url(version)
        try:
            resp = requests.head(url, timeout=10, allow_redirects=True, headers={"User-Agent": "Mozilla/5.0"})
            if resp.status_code == 200:
                return {"success": True, "available": True, "url": url, "version": version}
            else:
                return {"success": True, "available": False, "message": f"Патчи {version} пока недоступны. Следите за обновлениями!"}
        except Exception as e:
            logger.warning(f"check_patches_available error: {e}")
            return {"success": True, "available": False, "message": "Не удалось проверить доступность. Проверьте подключение к интернету."}

    def get_patches_latest_version(self):
        """
        Проверяет последнюю доступную версию патчей на GitHub.
        Читает patches/version.txt с GitHub.
        Возвращает: {"success": True, "version": "v2", "url": "..."} или {"success": False, "message": "..."}
        """
        url = "https://raw.githubusercontent.com/worteng/ArizonaLauncher/main/patches/version.txt"
        try:
            resp = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
            try:
                version = resp.content.decode('utf-8').strip()
            except UnicodeDecodeError:
                version = resp.content.decode('windows-1251', errors='replace').strip()
            if resp.status_code == 200:
                if version and version.startswith('v'):
                    return {
                        "success": True,
                        "version": version,
                        "download_url": self._get_patches_download_url(version)
                    }
            return {"success": False, "message": f"HTTP {resp.status_code}"}
        except Exception as e:
            logger.warning(f"get_patches_latest_version error: {e}")
            return {"success": False, "message": str(e)}

    def check_patches_update_status(self):
        """
        Проверяет статус обновления патчей через удалённый манифест updates/patches.json на GitHub.
        Это единый источник правды для показа оранжевого язычка «Обновить» при установленном v8.
        Возвращает: {"success": True, "released": bool, "latest_version": str, "notes": str}
        или {"success": False, "message": "..."} (в этом случае язычок не показывается — безопасное поведение).
        """
        import json as _json
        url = "https://raw.githubusercontent.com/worteng/ArizonaLauncher/main/updates/patches.json"
        try:
            resp = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
            if resp.status_code != 200:
                logger.warning(f"[check_patches_update_status] HTTP {resp.status_code}")
                return {"success": False, "message": f"HTTP {resp.status_code}"}
            try:
                data = _json.loads(resp.content.decode('utf-8').strip())
            except (ValueError, UnicodeDecodeError) as e:
                logger.warning(f"[check_patches_update_status] parse error: {e}")
                return {"success": False, "message": "Некорректный манифест"}
            logger.info(f"[check_patches_update_status] released={data.get('released')}, version={data.get('latest_version')}")
            return {
                "success": True,
                "released": bool(data.get("released", False)),
                "latest_version": str(data.get("latest_version", "")),
                "notes": str(data.get("notes", "")),
            }
        except Exception as e:
            logger.warning(f"[check_patches_update_status] error: {e}")
            return {"success": False, "message": str(e)}

    def download_and_install_patches(self, version="v2", progress_callback=None):
        """
        Скачивает архив патчей с GitHub и устанавливает в preloading_plugins/.
        version: "v2" (или другая доступная версия)
        progress_callback: функция(stage, progress, message) для прогресса
        """
        if not self.game_path:
            return {"success": False, "message": "game_path не установлен"}
        
        plugins_dir = os.path.join(os.path.dirname(self.game_path), "preloading_plugins")
        os.makedirs(plugins_dir, exist_ok=True)
        
        download_url = self._get_patches_download_url(version)
        
        def _send(stage, progress=0, message=""):
            if progress_callback:
                try:
                    progress_callback({"stage": stage, "progress": progress, "message": message})
                except Exception as e:
                    logger.warning(f"progress_callback error: {e}")

        _send("download", 0, "Подключение к GitHub...")
        
        try:
            # 1. Скачивание (используем вычисленный URL для запрошенной версии)
            if not download_url:
                _send("error", 0, "Не удалось определить URL загрузки для версии")
                return {"success": False, "message": f"Нет URL для версии {version}"}
            resp = requests.get(
                download_url,
                stream=True, timeout=60,
                headers={"User-Agent": "Mozilla/5.0"}
            )
            if resp.status_code != 200:
                _send("error", 0, f"Ошибка загрузки: HTTP {resp.status_code}")
                return {"success": False, "message": f"HTTP {resp.status_code}"}
            
            total = int(resp.headers.get("content-length", 0))
            downloaded = 0
            import tempfile
            # Уникальное имя файла, чтобы исключить symlink/TOCTOU атаки
            tmp_fd, tmp_zip = tempfile.mkstemp(suffix='.zip', prefix='arizonapatches_install_')
            os.close(tmp_fd)

            with open(tmp_zip, "wb") as f:
                for chunk in resp.iter_content(chunk_size=65536):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        pct = int(downloaded / total * 80) if total else 10
                        mb = downloaded / 1024 / 1024
                        _send("download", pct, f"Скачано {mb:.1f} МБ...")
            
            _send("extract", 82, "Распаковка архива...")
            
            # 2. Распаковка (без пароля)
            import zipfile, shutil
            plugins_real = os.path.realpath(os.path.join(os.path.dirname(self.game_path), "preloading_plugins"))
            
            with zipfile.ZipFile(tmp_zip, 'r') as zf:
                # Безопасность: проверка zip-slip и лимитов
                names = zf.namelist()
                if len(names) > 500:
                    raise ValueError(f"Слишком много файлов в архиве: {len(names)}")
                
                for member in zf.infolist():
                    # Защита от zip-slip
                    if ".." in member.filename.replace("\\", "/"):
                        raise ValueError(f"Недопустимый путь в архиве: {member.filename}")
                    
                    # Извлекаем только нужные файлы в корень preloading_plugins
                    filename = os.path.basename(member.filename)
                    if not filename:
                        continue
                    
                    if filename not in ("#ArizonaPatches.json", "#ArizonaPatches.dll"):
                        continue
                    
                    dest_path = os.path.join(plugins_real, filename)
                    if not (dest_path == plugins_real or dest_path.startswith(plugins_real + os.sep)):
                        raise ValueError(f"Zip-slip обнаружен: {member.filename}")
                    
                    with zf.open(member) as src, open(dest_path, "wb") as dst:
                        shutil.copyfileobj(src, dst)
                    logger.info(f"[download_and_install_patches] Извлечён: {filename}")
            
            # Удаляем временный архив
            try:
                os.remove(tmp_zip)
            except Exception:
                pass
            
            # Удаляем старый отключенный DLL (.1) если есть
            dll_path = os.path.join(plugins_real, "#ArizonaPatches.dll")
            self._remove_disabled_dll(dll_path)
            
            # Обновляем версию в конфиге
            self.config['patches_version'] = version
            self.config['patches_last_check'] = int(time.time())
            self.save_config()

            _send("done", 100, "Патчи успешно установлены!")
            logger.info(f"[download_and_install_patches] Патчи {version} установлены в {plugins_real}")

            return {"success": True, "message": "Патчи успешно установлены", "version": version}
            
        except requests.exceptions.ConnectionError as e:
            _send("error", 0, "Нет подключения к интернету")
            return {"success": False, "message": "Нет подключения к интернету"}
        except requests.exceptions.Timeout as e:
            _send("error", 0, "Тайм-аут соединения")
            return {"success": False, "message": "Тайм-аут соединения"}
        except Exception as e:
            logger.error(f"[download_and_install_patches] Ошибка: {e}", exc_info=True)
            _send("error", 0, str(e))
            return {"success": False, "message": str(e)}


class WebViewApp:
    def __init__(self):
        self.launcher = ArizonaLauncher()
        # Автопроверка обновлений патчей каждые 3 часа
        self._start_patches_autocheck()
    
    def _start_patches_autocheck(self):
        """Запускает фоновую проверку обновлений патчей каждые 3 часа."""
        def _check():
            try:
                with self.launcher._cfg_lock:
                    last_check = self.launcher.config.get('patches_last_check', 0)
                if time.time() - last_check > 10800:  # 3 часа = 10800 сек
                    logger.info("[autocheck] Проверка обновлений патчей...")
                    result = self.launcher.get_patches_latest_version()
                    if result.get("success"):
                        latest = result.get("version")
                        with self.launcher._cfg_lock:
                            installed = self.launcher.config.get('patches_version')
                        if latest and latest != installed:
                            # Есть новая версия
                            with self.launcher._cfg_lock:
                                self.launcher.config['patches_update_available'] = latest
                            logger.info(f"[autocheck] Доступна новая версия патчей: {latest} (установлено: {installed})")
                            # Отправляем событие в JS если окно уже есть
                            try:
                                w = getattr(self, '_window', None)
                                if w:
                                    js = f"window._onPatchesUpdateAvailable && window._onPatchesUpdateAvailable({json.dumps({'version': latest})})"
                                    w.evaluate_js(js)
                            except Exception:
                                pass
                    # Обновляем время проверки
                    with self.launcher._cfg_lock:
                        self.launcher.config['patches_last_check'] = int(time.time())
                        self.launcher.save_config()
            except Exception as e:
                logger.warning(f"autocheck patches error: {e}")
        
        import threading
        threading.Thread(target=_check, daemon=True).start()
    
    def is_gta_running(self):
        try:
            running = any('gta_sa' in (p.info.get('name') or '').lower()
                          for p in psutil.process_iter(['name']))
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess, OSError) as e:
            logger.warning(f"is_gta_running: {e}")
            running = getattr(self, '_gta_cached_running', False)
        was = getattr(self, '_gta_was_running', False)
        self._gta_was_running = running
        self._gta_cached_running = running
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
            import platform
            profiles = self.launcher.config.get('profiles', [])
            active_id = self.launcher.config.get('active_profile_id', None)
            active_name = next((p.get('name') for p in profiles if p.get('id') == active_id), None)
            
            # Версия лаунчера
            launcher_version = self.launcher.get_launcher_version()
            
            # Количество бэкапов
            backups = self.launcher.list_patches_backups()
            backups_count = len(backups) if backups else 0
            
            # Moonloader статус
            ml_dir = self._get_moonloader_dir()
            ml_status = "найдена" if ml_dir else "не найдена"
            ml_scripts_count = 0
            if ml_dir and os.path.isdir(ml_dir):
                try:
                    ml_scripts_count = len([f for f in os.listdir(ml_dir) if f.endswith(('.lua', '.luac', '.cs', '.asi'))])
                except:
                    pass
            
            # Параметры запуска
            launch_params = self.launcher.config.get('launch_params', {})
            params_enabled = [k for k, v in launch_params.items() if v is True]
            
            return {
                "success": True,
                "data": {
                    # Пути
                    "config_path":         self.launcher.config_path,
                    "docs_path":           self.launcher.documents_path,
                    "game_path":           self.launcher.game_path or "",
                    "launcher_path":       self.launcher.launcher_path or "",
                    "patches_path":        self.launcher.patches_path or "",
                    
                    # Профили
                    "profiles_count":      len(profiles),
                    "active_profile_name": active_name or "нет",
                    
                    # Лаунчер
                    "app_version":         LAUNCHER_VERSION,
                    "launcher_version":    launcher_version,
                    "last_nickname":       self.launcher.config.get('last_nickname', ''),
                    "last_server":         self.launcher.config.get('last_server', 15),
                    
                    # Параметры запуска
                    "launch_params_count": len(params_enabled),
                    "launch_params_list":  ', '.join(params_enabled) if params_enabled else 'нет',
                    "memory":              launch_params.get('memory', 4096),
                    
                    # Бэкапы
                    "backups_count":       backups_count,
                    
                    # Moonloader
                    "moonloader_status":   ml_status,
                    "moonloader_scripts":  ml_scripts_count,
                    
                    # Система
                    "python_version":      platform.python_version(),
                    "os_name":             platform.system(),
                    "os_version":          platform.release(),
                    "architecture":        platform.machine(),
                }
            }
        except Exception as e:
            logger.error(f"get_debug_info error: {e}")
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
            log_path = os.path.join(_get_app_dir(), "arizona_launcher.log")
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
        def run(container):
            try:
                container['result'] = self.launcher.launch_game(nickname, server_data, launch_params)
            except Exception as e:
                logger.error(f"start_game thread error: {e}")
                container['result'] = {"success": False, "message": str(e), "code": "EXCEPTION"}
            container['done'] = True
        container = {'done': False, 'result': None}
        Thread(target=run, args=(container,), daemon=True).start()
        # Ждём завершения (launch_game делает kill + 2s poll, в среднем ~3-5s)
        deadline = time.time() + 10.0
        while time.time() < deadline and not container['done']:
            time.sleep(0.05)
        if not container['done']:
            return {"success": False, "message": "Launch timeout", "code": "TIMEOUT",
                    "status": "processing"}
        return container['result']

    def get_config(self):
        lp = self.launcher.launcher_path
        gp = self.launcher.game_path
        paths_ok = bool(lp and gp and os.path.exists(lp) and os.path.exists(gp))
        return {"launcher_path": lp, "game_path": gp,
                "last_nickname": self.launcher.config.get('last_nickname', ''),
                "last_server": self.launcher.config.get('last_server', 15),
                "launch_params": self.launcher.config.get('launch_params', {}),
                "paths_configured": paths_ok,
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
    def get_init_data(self):
        """Быстрый вызов: только saved_data (ник, сервер, пути).
        Update check — отдельно (не блокирует загрузку)."""
        try:
            saved = {
                "success": True,
                "nickname": self.launcher.config.get('last_nickname', ''),
                "server": self.launcher.config.get('last_server', 15),
                "game_path": self.launcher.game_path or '',
                "paths_configured": bool(self.launcher.launcher_path and self.launcher.game_path)
            }
            return {"success": True, "saved": saved}
        except Exception as e:
            logger.error(f"[get_init_data] error: {e}")
            return {"success": False, "saved": {"success": True, "nickname": "", "server": 15, "game_path": "", "paths_configured": False}}

    def check_launcher_update(self):
        """Проверка обновления лаунчера (отдельно от init, не блокирует загрузку)."""
        try:
            game_path = self.launcher.game_path or ''
            paths_configured = bool(self.launcher.launcher_path and game_path)
            if not paths_configured or not game_path:
                return {"success": True, "needs_update": False, "message": "Путь к игре не настроен", "folder": None}
            sep = '\\' if '\\' in game_path else '/'
            folder_path = game_path[:game_path.rfind(sep)]
            install_info = self.get_install_action(folder_path)
            action = install_info.get('action', 'none')
            if action == 'none':
                return {"success": True, "needs_update": False, "message": "Лаунчер v8 уже установлен", "folder": folder_path}
            messages = {
                'choose_version': 'Требуется установка лаунчера v8',
                'install_launcher_only': 'Требуется установка лаунчера v8',
                'install_preloading_only': 'Требуется установка патчей',
                'upgrade_to_v8': f'Доступно обновление v{install_info.get("launcher_version", "?")} → v8',
            }
            return {"success": True, "needs_update": True, "message": messages.get(action, "Доступно обновление"), "folder": folder_path, "action": action}
        except Exception as e:
            logger.error(f"[check_launcher_update] error: {e}")
            return {"success": False, "needs_update": False}

    def get_servers_and_news(self):
        """Один вызов для загрузки серверов и новостей параллельно (threading).
        Экономит 1 мост pywebview (вместо 2 отдельных вызовов)."""
        from concurrent.futures import ThreadPoolExecutor
        servers_result = [None]
        news_result = [None]

        def fetch_servers():
            try:
                servers_result[0] = self.get_servers()
            except Exception as e:
                logger.error(f"[get_servers_and_news] servers error: {e}")
                servers_result[0] = []

        def fetch_news():
            try:
                news_result[0] = self.get_launcher_news()
            except Exception as e:
                logger.error(f"[get_servers_and_news] news error: {e}")
                news_result[0] = {"success": False, "message": str(e)}

        with ThreadPoolExecutor(max_workers=2) as pool:
            pool.submit(fetch_servers)
            pool.submit(fetch_news)

        return {"success": True, "servers": servers_result[0] or [], "news": news_result[0] or {"success": False}}

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

    def set_window_title(self, title):
        """Устанавливает заголовок окна лаунчера"""
        try:
            import webview as wv
            wins = wv.windows
            if wins:
                wins[0].title = title
            self.launcher.config['launcher_settings']['window_title'] = title
            self.launcher.save_config()
            return {"success": True}
        except Exception as e:
            logger.error(f"set_window_title error: {e}")
            return {"success": False, "message": str(e)}

    def get_window_title(self):
        """Возвращает текущий заголовок окна"""
        title = self.launcher.config.get('launcher_settings', {}).get('window_title', 'Arizona RP Launcher')
        return {"success": True, "title": title}

    def set_game_paths(self, game, launcher):
        self.launcher.set_game_paths(game, launcher)
        return {"success": True, "message": "Paths set"}

    def auto_detect_paths(self):
        success = self.launcher.auto_detect_game_paths()
        return {"success": success, "message": "Found" if success else "Not found",
                "game_path": self.launcher.game_path, "launcher_path": self.launcher.launcher_path}

    def _qt_app(self):
        """Возвращает существующий QApplication или создаёт новый"""
        return QApplication.instance() or QApplication([])

    def select_bg_image(self):
        """Выбрать картинку для фона лаунчера, вернуть base64 data URL"""
        import base64, mimetypes, queue
        from threading import Thread
        result_queue = queue.Queue()

        def _pick():
            try:
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
        launcher_v8 = os.path.join(folder_path, "ArizonaLauncher8.0_byAIR.exe")
        plugins_dir = os.path.join(folder_path, "preloading_plugins")

        if not os.path.exists(game_exe):
            return {"status": "no_game", "folder": folder_path}

        # Лаунчер найден если установлена любая из версий (приоритет v8 > v7 > v6)
        launcher_exe = ""
        if os.path.exists(launcher_v8):
            launcher_exe = launcher_v8
        elif os.path.exists(launcher_v7):
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
        launcher_v8 = os.path.join(folder_path, "ArizonaLauncher8.0_byAIR.exe")
        plugins_dir = os.path.join(folder_path, "preloading_plugins")

        if not os.path.exists(game_exe):
            logger.error(f"[get_install_action] gta_sa.exe не найден в {folder_path}")
            return {"action": "error", "message": "gta_sa.exe не найден"}

        has_v6 = os.path.exists(launcher_v6)
        has_v7 = os.path.exists(launcher_v7)
        has_v8 = os.path.exists(launcher_v8)
        has_launcher = has_v6 or has_v7 or has_v8
        has_preloading = os.path.isdir(plugins_dir) and bool(os.listdir(plugins_dir))
        if has_v8:
            launcher_version = 'v8'
        elif has_v7:
            launcher_version = 'v7'
        elif has_v6:
            launcher_version = 'v6'
        else:
            launcher_version = None

        logger.info(f"[get_install_action] Статус проверки:")
        logger.info(f"  - has_v6: {has_v6}")
        logger.info(f"  - has_v7: {has_v7}")
        logger.info(f"  - has_v8: {has_v8}")
        logger.info(f"  - has_preloading: {has_preloading}")
        logger.info(f"  - launcher_version: {launcher_version}")

        # Логика определения действия:
        # 1. Есть preloading + v8 -> ничего не делать
        if has_preloading and has_v8:
            logger.info("[get_install_action] Результат: Лаунчер v8 уже установлен (action: none)")
            return {
                "action": "none",
                "message": "Лаунчер v8 уже установлен",
                "has_launcher": True,
                "has_preloading": True,
                "launcher_version": "v8"
            }

        # 2. Есть preloading + v7 -> предложить апгрейд до v8
        if has_preloading and has_v7 and not has_v8:
            logger.info("[get_install_action] Результат: Доступно обновление v7 -> v8 (action: upgrade_to_v8)")
            return {
                "action": "upgrade_to_v8",
                "message": "Доступно обновление до v8",
                "has_launcher": True,
                "has_preloading": True,
                "launcher_version": "v7"
            }

        # 3. Есть preloading + v6 -> предложить апгрейд до v8
        if has_preloading and has_v6 and not has_v8 and not has_v7:
            logger.info("[get_install_action] Результат: Доступно обновление v6 -> v8 (action: upgrade_to_v8)")
            return {
                "action": "upgrade_to_v8",
                "message": "Доступно обновление до v8",
                "has_launcher": True,
                "has_preloading": True,
                "launcher_version": "v6"
            }

        # 4. Нет preloading + есть лаунчер (v6/v7/v8) -> установить только preloading
        # НО: для v8 установка preloading управляется удалённым флагом released в updates/patches.json
        # (патчер сознательно убран из архива, т.к. сломан до выхода 2.0.0.0).
        # Поэтому пустая/отсутствующая preloading_plugins при установленном v8 НЕ считается поводом
        # для бесконечного показа язычка «Обновить».
        if not has_preloading and has_launcher:
            if has_v8:
                logger.info("[get_install_action] Результат: v8 установлен, preloading отсутствует — проверяется удалённым флагом released (action: none)")
                return {
                    "action": "none",
                    "message": "Лаунчер v8 уже установлен",
                    "has_launcher": True,
                    "has_preloading": False,
                    "launcher_version": "v8"
                }
            logger.info(f"[get_install_action] Результат: Требуется установка preloading_plugins (action: install_preloading_only, launcher: {launcher_version})")
            return {
                "action": "install_preloading_only",
                "message": "Требуется установка папки preloading_plugins",
                "has_launcher": True,
                "has_preloading": False,
                "launcher_version": launcher_version
            }

        # 5. Есть preloading + нет лаунчера -> предложить выбор версии (установить только лаунчер)
        if has_preloading and not has_launcher:
            logger.info("[get_install_action] Результат: Требуется установка лаунчера (action: install_launcher_only)")
            return {
                "action": "install_launcher_only",
                "message": "Выберите версию лаунчера для установки",
                "has_launcher": False,
                "has_preloading": True,
                "launcher_version": None
            }

        # 6. Нет ничего -> предложить выбор версии (полная установка)
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

    def check_update_api(self, game_path=None):
        """Проверяет доступность обновления лаунчера v8 + патчей.
        Возвращает: {needs_update: bool, message: str, folder: str|None}"""
        try:
            if not game_path:
                saved = self.get_saved_data()
                if not saved.get('success') or not saved.get('game_path'):
                    return {"success": True, "needs_update": False, "message": "Путь к игре не настроен", "folder": None}
                game_path = saved['game_path']

            sep = '\\' if '\\' in game_path else '/'
            folder_path = game_path[:game_path.rfind(sep)]

            install_info = self.get_install_action(folder_path)
            action = install_info.get('action', 'none')

            if action == 'none':
                # v8 уже установлен локально. Но показ язычка управляется удалённым флагом
                # released в updates/patches.json — это нужно для авторелиза нового патчера (2.0.0.0).
                if install_info.get('launcher_version') == 'v8':
                    status = self.check_patches_update_status()
                    if status.get('success') and status.get('released'):
                        ver = status.get('latest_version') or ''
                        msg = f"Доступно обновление патчей" + (f" до v{ver}" if ver else "")
                        logger.info(f"[check_update_api] {msg} (удалённый флаг released=true)")
                        return {"success": True, "needs_update": True, "message": msg,
                                "folder": folder_path, "action": "update_patches"}
                return {"success": True, "needs_update": False, "message": "Лаунчер v8 уже установлен", "folder": folder_path}

            messages = {
                'choose_version': 'Требуется установка лаунчера v8',
                'install_launcher_only': 'Требуется установка лаунчера v8',
                'install_preloading_only': 'Требуется установка патчей',
                'upgrade_to_v8': f'Доступно обновление v{install_info.get("launcher_version", "?")} → v8',
            }
            return {
                "success": True,
                "needs_update": True,
                "message": messages.get(action, "Доступно обновление"),
                "folder": folder_path,
                "action": action,
            }
        except Exception as e:
            logger.error(f"[check_update_api] Ошибка: {e}", exc_info=True)
            return {"success": False, "message": str(e), "needs_update": False}

    def download_update_api(self):
        """Скачивает обновление (v8 + патчи) в фоне.
        Определяет install_type автоматически, отправляет прогресс через JS."""
        try:
            saved = self.get_saved_data()
            if not saved.get('success') or not saved.get('game_path'):
                return {"success": False, "message": "Путь к игре не настроен"}

            game_path = saved['game_path']
            sep = '\\' if '\\' in game_path else '/'
            folder_path = game_path[:game_path.rfind(sep)]

            install_info = self.get_install_action(folder_path)
            action = install_info.get('action', 'none')

            # Если локально всё на месте (action: none) — проверяем удалённый флаг released.
            # Это случай авторелиза нового патчера (2.0.0.0): конфиг updates/patches.json
            # переключается в released: true, и пользователи получают обновление автоматически.
            if action == 'none':
                status = self.check_patches_update_status()
                if not (status.get('success') and status.get('released')):
                    return {"success": False, "message": "Обновление не требуется"}
                # Удалённый флаг сработал — скачиваем только preloading_plugins (патчер)
                logger.info("[download_update_api] Удалённый флаг released=true — скачиваем патчи")
                install_type = 'install_preloading_only'
            elif action == 'install_preloading_only':
                install_type = 'install_preloading_only'
            else:
                install_type = 'choose_version'

            def run():
                self.download_and_install_launcher(folder_path, 'v8', install_type)

            Thread(target=run, daemon=True).start()
            logger.info("[download_update_api] Фоновое скачивание обновления запущено")
            return {"success": True, "message": "Скачивание начато"}
        except Exception as e:
            logger.error(f"[download_update_api] Ошибка: {e}", exc_info=True)
            return {"success": False, "message": str(e)}

    def download_and_install_launcher(self, folder_path, version='v8', install_type='choose_version'):
        """Скачивает архив лаунчера v8 с GitHub и устанавливает в папку игры.
           version: 'v8' — ArizonaLauncher8.0_byAIR
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
            "v8": {
                "url": "https://raw.githubusercontent.com/worteng/ArizonaLauncher/refs/heads/main/others/ArizonaLauncher8.0_byAIR.zip",
                "exe_names": ["arizonalauncher8.0_byair.exe"],
                "password": b"1111",
            },
        }
        ver = VERSIONS.get(version, VERSIONS["v8"])
        GITHUB_RELEASE_URL = ver["url"]
        TARGET_EXE_NAMES   = ver["exe_names"]
        ZIP_PASSWORD       = ver["password"]
        logger.info(f"[download_and_install_launcher] URL для скачивания: {GITHUB_RELEASE_URL}")
        logger.info(f"[download_and_install_launcher] Целевые exe файлы: {TARGET_EXE_NAMES}")
        logger.info(f"[download_and_install_launcher] Архив зашифрован: {ZIP_PASSWORD is not None}")
        import zipfile, tempfile, shutil

        def _send(stage, progress=0, message=""):
            try:
                w = getattr(self, '_window', None)
                if w:
                    js = f"window._onLauncherInstallProgress && window._onLauncherInstallProgress({json.dumps({'stage': stage, 'progress': progress, 'message': message})})"
                    w.evaluate_js(js)
            except Exception as ex:
                logger.warning(f"_send progress error: {ex}")

        if ZIP_PASSWORD is not None:
            try:
                import pyzipper
            except ImportError:
                logger.error("[download_and_install_launcher] pyzipper не установлен, требуется для v8")
                _send("error", 0, "pyzipper не установлен (pip install pyzipper)")
                return {"success": False, "message": "pyzipper required for encrypted archives"}

        try:
            # 0. При установке новой версии — удалить старые exe лаунчеров
            # (чтобы не было конфликта файлов и не оставался мусор)
            if install_type in ('install_launcher_only', 'choose_version'):
                folder_real = os.path.realpath(folder_path)
                # Убиваем процессы старых лаунчеров, чтобы Windows не блокировала удаление .exe
                self.launcher.kill_all_launchers()
                # Собираем имена ВСЕХ возможных exe лаунчеров
                ALL_LAUNCHER_EXES = {
                    'arizonalauncher6_byair.exe', 'arizonalauncher7.0_byair.exe', 'arizonalauncher8.0_byair.exe',
                }
                # Удаляем все, КРОМЕ того что ставим
                for old_exe in (ALL_LAUNCHER_EXES - set(TARGET_EXE_NAMES)):
                    old_path = os.path.join(folder_real, old_exe)
                    if os.path.exists(old_path):
                        try:
                            os.remove(old_path)
                            logger.info(f"[download_and_install_launcher] Удалён старый лаунчер: {old_exe}")
                        except Exception as e:
                            logger.warning(f"[download_and_install_launcher] Не удалось удалить {old_exe}: {e}")

            logger.info("[download_and_install_launcher] Этап 1: Скачивание архива")
            _send("download", 0, "Подключение к GitHub...")

            # 1. Качаем архив с прогрессом
            resp = requests.get(GITHUB_RELEASE_URL, stream=True, timeout=60,
                                headers={"User-Agent": "Mozilla/5.0"})
            if resp.status_code != 200:
                logger.error(f"[download_and_install_launcher] Ошибка HTTP: {resp.status_code}")
                _send("error", 0, f"Ошибка загрузки: HTTP {resp.status_code}")
                return {"success": False, "message": f"HTTP {resp.status_code}"}

            total = int(resp.headers.get("content-length", 0))
            downloaded = 0
            logger.info(f"[download_and_install_launcher] Размер архива: {total / 1024 / 1024:.2f} МБ")

            tmp_fd, tmp_zip = tempfile.mkstemp(suffix='.zip', prefix='arizona_launcher_install_')
            os.close(tmp_fd)
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
            if ZIP_PASSWORD is not None:
                zf_ctx = pyzipper.AESZipFile(tmp_zip, 'r')
                zf_ctx.setpassword(ZIP_PASSWORD)
            else:
                zf_ctx = zipfile.ZipFile(tmp_zip, 'r')
            with zf_ctx as zf:
                logger.info(f"[download_and_install_launcher] Файлов в архиве: {len(zf.infolist())}")
                if len(zf.infolist()) > _MAX_ZIP_FILES:
                    raise ValueError(f"Слишком много файлов в архиве: {len(zf.infolist())} > {_MAX_ZIP_FILES}")
                folder_real = os.path.realpath(folder_path)
                for member in zf.infolist():
                    filename = os.path.basename(member.filename)
                    if not filename:  # это папка внутри архива
                        continue

                    # Защита от zip-slip: итоговый путь должен оставаться внутри folder_path
                    if ".." in member.filename.replace("\\", "/"):
                        raise ValueError(f"Недопустимый путь в архиве: {member.filename}")

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
                        dest_path = os.path.realpath(os.path.join(folder_path, dest_rel))
                        if not (dest_path == folder_real or dest_path.startswith(folder_real + os.sep)):
                            raise ValueError(f"Zip-slip обнаружен: {member.filename}")
                        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                        with zf.open(member) as src, open(dest_path, "wb") as dst:
                            shutil.copyfileobj(src, dst)
                        logger.info(f"[download_and_install_launcher] Извлечён (preloading): {dest_rel}")
                        extracted_count += 1
                    else:
                        dest_path = os.path.realpath(os.path.join(folder_path, filename))
                        if not (dest_path == folder_real or dest_path.startswith(folder_real + os.sep)):
                            raise ValueError(f"Zip-slip обнаружен: {member.filename}")
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

    def start_launcher_install(self, folder_path, version='v8', install_type='choose_version'):
        """Запускает скачивание и установку лаунчера в фоновом потоке
        install_type: 'choose_version', 'install_preloading_only', 'install_launcher_only', 'upgrade_to_v8'
        """
        valid_types = ('choose_version', 'install_preloading_only', 'install_launcher_only', 'upgrade_to_v8')
        if install_type not in valid_types:
            logger.warning(f"[start_launcher_install] Отклонено: недопустимый install_type='{install_type}'")
            return {"success": False, "message": f"Установка не требуется (action: {install_type})"}

        # upgrade_to_v8 — ставим только лаунчер (preloading_plugins уже есть)
        if install_type == 'upgrade_to_v8':
            install_type = 'install_launcher_only'

        # Дополнительная проверка: если лаунчер нужной версии уже стоит — не качаем
        if folder_path and os.path.isdir(folder_path):
            check = self.get_install_action(folder_path)
            if check.get('action') == 'none':
                logger.info(f"[start_launcher_install] Лаунчер уже установлен в {folder_path}, пропускаем")
                return {"success": False, "message": check.get('message', 'Лаунчер уже установлен')}

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
            cleaned = re.sub(r'^\s*//.*', '', raw, flags=re.MULTILINE)
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
        """Сканирует папку wallpapers/ и возвращает список файлов (только имена, без base64)."""
        try:
            base_dir = Path(_get_app_dir()) / "wallpapers"
            if not base_dir.exists():
                base_dir.mkdir(parents=True, exist_ok=True)
                return {"success": True, "wallpapers": []}

            supported = {'.jpg', '.jpeg', '.png', '.webp', '.bmp'}
            result = []
            for f in sorted(base_dir.iterdir()):
                if f.is_file() and f.suffix.lower() in supported:
                    result.append({
                        "name": f.stem,
                        "filename": f.name,
                    })
            return {"success": True, "wallpapers": result}
        except Exception as e:
            logger.error(f"get_wallpapers error: {e}")
            return {"success": False, "message": str(e), "wallpapers": []}

    def get_wallpaper_thumb(self, filename):
        """Возвращает LOW-QUALITY base64 data_url для превью в настройках (ресайз 800px)."""
        import base64, mimetypes
        try:
            base_dir = Path(_get_app_dir()) / "wallpapers"
            f = base_dir / filename
            if not f.exists() or not f.is_file():
                return {"success": False, "message": "File not found"}
            try:
                from PIL import Image
                img = Image.open(f)
                img.thumbnail((500, 500), Image.Resampling.LANCZOS)
                from io import BytesIO
                buf = BytesIO()
                img.save(buf, format='WEBP', quality=80)
                data = base64.b64encode(buf.getvalue()).decode('utf-8')
                return {"success": True, "data_url": f"data:image/webp;base64,{data}"}
            except ImportError:
                # Fallback: original file if PIL not available
                mime = mimetypes.guess_type(f.name)[0] or 'image/jpeg'
                data = base64.b64encode(f.read_bytes()).decode('utf-8')
                return {"success": True, "data_url": f"data:{mime};base64,{data}"}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def get_wallpaper_full(self, filename):
        """Возвращает FULL-QUALITY base64 data_url для фона."""
        import base64, mimetypes
        try:
            base_dir = Path(_get_app_dir()) / "wallpapers"
            f = base_dir / filename
            if not f.exists() or not f.is_file():
                return {"success": False, "message": "File not found"}
            mime = mimetypes.guess_type(f.name)[0] or 'image/jpeg'
            data = base64.b64encode(f.read_bytes()).decode('utf-8')
            return {"success": True, "data_url": f"data:{mime};base64,{data}"}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def _add_defender_exclusion(self, file_path: str):
        """Добавляет файл и его папку в исключения Windows Defender через PowerShell.

        Безопасность:
        • file_path/folder_path валидируются — корневой диск (C:\\) не исключается
        • Пути экранируются одинарными кавычками для PowerShell
        """
        try:
            folder_path = os.path.dirname(file_path)
            # Защита: не исключать корень диска (типа C:\) — это снизит безопасность ОС
            drive, tail = os.path.splitdrive(folder_path)
            if not tail or tail.strip('\\/') == '':
                logger.warning(f"_add_defender_exclusion: отказ исключать корень диска '{folder_path}'")
                return
            # Экранируем одинарные кавычки в путях ( заменяем на '' )
            safe_folder = folder_path.replace("'", "''")
            safe_file = file_path.replace("'", "''")
            ps_script = (
                f"Add-MpPreference -ExclusionPath '{safe_folder}'; "
                f"Add-MpPreference -ExclusionProcess '{safe_file}'"
            )
            result = subprocess.run(
                ["powershell", "-NonInteractive", "-WindowStyle", "Hidden",
                 "-ExecutionPolicy", "Bypass",
                 "-Command", ps_script],
                capture_output=True, timeout=15
            )
            if result.returncode == 0:
                logger.info(f"_add_defender_exclusion: OK — {file_path}")
            else:
                stderr = result.stderr.decode("utf-8", errors="replace").strip()
                logger.warning(f"_add_defender_exclusion: code={result.returncode} — {stderr[:200]}")
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

    def update_server(self, server_number):
        """Сохраняет выбранный сервер"""
        self.launcher.config['last_server'] = server_number
        self.launcher.save_config()
        return {"success": True}

    def update_launch_params(self, params):
        self.launcher.config['launch_params'] = params
        self.launcher.save_config()
        return {"success": True}

    def read_launch_params(self):
        """Возвращает параметры запуска"""
        return self.launcher.config.get('launch_params', {})

    def _download_icon(self, icon_url, server_id):
        """Скачивает иконку сервера в локальный кэш, возвращает data: URI."""
        if not icon_url:
            return ''
        try:
            cache_dir = _get_icon_cache_dir()
            ext = Path(icon_url).suffix.split('?')[0]
            if ext.lower() not in ('.png', '.jpg', '.jpeg', '.webp', '.ico'):
                ext = '.png'
            local_path = cache_dir / f"server_{server_id}{ext}"
            b64_path = cache_dir / f"server_{server_id}.b64"
            
            # Если есть готовый base64 — возвращаем сразу
            if b64_path.exists() and b64_path.stat().st_size > 0:
                return b64_path.read_text(encoding='ascii').strip()
            
            # Если есть исходный файл — кодируем и сохраняем base64
            if local_path.exists() and local_path.stat().st_size > 0:
                mime = {'png': 'image/png', 'jpg': 'image/jpeg', 'jpeg': 'image/jpeg', 
                        'webp': 'image/webp', 'ico': 'image/x-icon'}.get(ext[1:], 'image/png')
                b64 = base64.b64encode(local_path.read_bytes()).decode('ascii')
                data_uri = f"data:{mime};base64,{b64}"
                b64_path.write_text(data_uri, encoding='ascii')
                return data_uri
        except Exception as e:
            logger.warning(f"Icon cache check failed for {icon_url}: {e}")
        return ''  # Нет в кэше — вернём пусто, фоллбэк покажет номер

    def _prefetch_all_icons(self, servers):
        """Фоновая предзагрузка всех иконок серверов."""
        def _bg():
            for s in servers:
                icon_url = s.get('icon')
                server_id = s.get('number') or s.get('serverNumber') or s.get('id')
                if not icon_url or not server_id:
                    continue
                try:
                    cache_dir = _get_icon_cache_dir()
                    ext = Path(icon_url).suffix.split('?')[0]
                    if ext.lower() not in ('.png', '.jpg', '.jpeg', '.webp', '.ico'):
                        ext = '.png'
                    local_path = cache_dir / f"server_{server_id}{ext}"
                    if local_path.exists() and local_path.stat().st_size > 0:
                        continue
                    resp = requests.get(icon_url, timeout=10)
                    if resp.status_code == 200 and resp.content:
                        with open(local_path, 'wb') as f:
                            f.write(resp.content)
                except Exception:
                    pass
        Thread(target=_bg, daemon=True).start()

    def get_servers(self):
        # Локальный кэш с TTL — убирает повторные запросы при рестарте окна и частом обновлении
        cache_attr = '_servers_cache'
        cache_ttl  = 60  # секунд
        now = time.time()
        cached = getattr(self, cache_attr, None)
        if cached and (now - cached['ts']) < cache_ttl:
            # Обновляем иконки в кэшированных данных, если они теперь доступны локально
            servers = cached['data']
            for s in servers:
                if not s.get('icon'):
                    icon_url = s.get('original_icon', '')
                    server_id = s.get('number') or s.get('serverNumber') or s.get('id')
                    if icon_url and server_id:
                        s['icon'] = self._download_icon(icon_url, server_id)
            return servers

        headers = {'User-Agent': 'ArizonaLauncher/1.0'}
        if cached:
            if cached.get('etag'):
                headers['If-None-Match'] = cached['etag']
            if cached.get('last_modified'):
                headers['If-Modified-Since'] = cached['last_modified']

        try:
            resp = requests.get(
                "https://arizona-ping.react.group/desktop/ping/Arizona/ping.json",
                timeout=10, headers=headers            )
            # 304 Not Modified — отдаём кэшированные данные
            if resp.status_code == 304 and cached:
                cached['ts'] = now
                setattr(self, cache_attr, cached)
                return cached['data']
            if resp.status_code != 200:
                logger.error(f"Server fetch HTTP {resp.status_code}")
                return cached['data'] if cached else None

            data = resp.json()
            server_list = data.get('query', data) if isinstance(data, dict) else data
            if not isinstance(server_list, list):
                return cached['data'] if cached else None

            servers = []
            for s in server_list:
                if not isinstance(s, dict): continue
                server_id = s.get('number') or s.get('serverNumber') or s.get('id', 1)
                icon_url = s.get('icon', '')
                servers.append({
                    'number': server_id,
                    'name': s.get('name', 'Server'),
                    'online': s.get('online') or s.get('playersOnline', 0),
                    'queue': s.get('queue') or s.get('queueLength', 0),
                    'recommended': s.get('recomend') or s.get('recommended') or False,
                    'ip': s.get('ip', f"server{server_id}.arizona-rp.com"),
                    'port': s.get('port', 7777),
                    'maxplayers': s.get('maxplayers') or s.get('maxPlayers') or 1000,
                    'original_icon': icon_url,
                    'icon': self._download_icon(icon_url, server_id) if icon_url else '',
                })

            # Сохраняем в кэш вместе с ETag/Last-Modified для условных запросов
            setattr(self, cache_attr, {
                'ts': now,
                'data': servers,
                'etag': resp.headers.get('ETag'),
                'last_modified': resp.headers.get('Last-Modified'),
            })
            # Предзагружаем иконки в фоне
            self._prefetch_all_icons(servers)
            return servers
        except Exception as e:
            logger.error(f"Server fetch error: {e}")
            return cached['data'] if cached else None

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
                    }
                )
                try:
                    text = response.content.decode('utf-8')
                except UnicodeDecodeError:
                    text = response.content.decode('windows-1251', errors='replace')

                logger.info(f"Статус ответа: {response.status_code}")

                if response.status_code == 200 and text.strip():
                    return {
                        "success": True,
                        "text": text
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
    def preview_patches_backup(self, filename): return self.launcher.preview_patches_backup(filename)

    # ===== ArizonaPatches Management API =====

    def check_patches_files(self):
        """Проверяет наличие файлов патчей (JSON и DLL)."""
        return self.launcher.check_patches_files()

    def check_patches_status(self):
        """Проверяет статус патчей: missing / outdated_v1 / current"""
        return self.launcher.check_patches_status()

    def download_and_install_patches(self, version="v2"):
        """Скачивает и устанавливает патчи с прогрессом."""
        # Коллбэк для отправки прогресса в JS
        def _send(stage, progress=0, message=""):
            try:
                w = getattr(self, '_window', None)
                if w:
                    js = f"window._onPatchesInstallProgress && window._onPatchesInstallProgress({json.dumps({'stage': stage, 'progress': progress, 'message': message})})"
                    w.evaluate_js(js)
            except Exception as e:
                logger.warning(f"_send patches progress error: {e}")
        
        return self.launcher.download_and_install_patches("v2", progress_callback=_send)

    def get_patches_latest_version(self):
        """Проверяет последнюю доступную версию патчей на GitHub."""
        return self.launcher.get_patches_latest_version()

    def check_patches_status_api(self):
        """API метод для JS — возвращает статус патчей."""
        logger.info("[check_patches_status_api] Запрос статуса патчей")
        try:
            status = self.launcher.check_patches_status()
            logger.info(f"[check_patches_status_api] Статус: {status.get('status')}")
            return {"success": True, "status": status}
        except Exception as e:
            logger.error(f"check_patches_status_api error: {e}")
            return {"success": False, "message": str(e)}

    def get_patches_latest_version_api(self):
        """API метод для JS — проверка последней версии на GitHub."""
        logger.info("[get_patches_latest_version_api] Запрос последней версии")
        try:
            result = self.launcher.get_patches_latest_version()
            logger.info(f"[get_patches_latest_version_api] Результат: {result}")
            return result
        except Exception as e:
            logger.error(f"get_patches_latest_version_api error: {e}")
            return {"success": False, "message": str(e)}

    def check_patches_available_api(self, version="v2"):
        """API метод для JS — проверка доступности патчей на GitHub."""
        try:
            return self.launcher.check_patches_available(version)
        except Exception as e:
            logger.error(f"check_patches_available_api error: {e}")
            return {"success": False, "available": False, "message": str(e)}

    def get_window_size(self):
        """Возвращает сохранённый размер окна (для восстановления после fullscreen и т.п.)."""
        return self.launcher.config.get('launcher_settings', {}).get('window_size', [1285, 732])

    def save_layout_order(self, order):
        """Сохраняет порядок элементов главного меню."""
        if not isinstance(order, list):
            return {"success": False, "message": "order must be a list"}
        self.launcher.config.setdefault('launcher_settings', {})['layout_order'] = order
        self.launcher.save_config()
        logger.info(f"[save_layout_order] {order}")
        return {"success": True}

    def get_layout_order(self):
        """Возвращает сохранённый порядок элементов главного меню."""
        order = self.launcher.config.get('launcher_settings', {}).get('layout_order', [])
        return order

    def fetch_patch_presets(self):
        """Загружает configs.txt с GitHub и парсит список пресетов"""
        CONFIGS_URL = "https://raw.githubusercontent.com/worteng/ArizonaLauncher/main/configs.txt"
        try:
            logger.info(f"fetch_patch_presets: запрос {CONFIGS_URL}")
            resp = requests.get(CONFIGS_URL, timeout=10, headers={"Cache-Control": "no-cache"})
            try:
                text = resp.content.decode('utf-8')
            except UnicodeDecodeError:
                text = resp.content.decode('windows-1251', errors='replace')
            text = self._fix_mojibake(text)
            logger.info(f"fetch_patch_presets: статус {resp.status_code}, размер {len(text)} байт")
            if resp.status_code == 404:
                return {"success": False, "message": "Файл configs.txt не найден на GitHub (404). Создай его в репозитории."}
            if resp.status_code != 200:
                return {"success": False, "message": f"GitHub вернул HTTP {resp.status_code}"}
            presets = self._parse_catalog_txt(text)
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

    def fetch_patches_schema(self):
        """Загружает patches_schema.json с GitHub — схему метаданных настроек патчей V2.

        Это data-driven описание UI: категории, настройки (id/title/description/category/type/default/conflicts).
        При ошибке/404 фронтенд падает на зашитый fallback в index.html.

        Возвращает: {"success": True, "data": {"version", "categories", "settings"}} или {"success": False, "message"}
        """
        # Кэш в памяти — не дёргаем GitHub при каждом открытии вкладки
        if getattr(self, '_patches_schema_cache', None):
            return {"success": True, "data": self._patches_schema_cache, "cached": True}

        SCHEMA_URL = "https://raw.githubusercontent.com/worteng/ArizonaLauncher/main/patches_schema.json"
        try:
            logger.info(f"fetch_patches_schema: запрос {SCHEMA_URL}")
            resp = requests.get(SCHEMA_URL, timeout=10, headers={"Cache-Control": "no-cache"})
            if resp.status_code == 404:
                return {"success": False, "message": "patches_schema.json не найден на GitHub (404)"}
            if resp.status_code != 200:
                return {"success": False, "message": f"GitHub вернул HTTP {resp.status_code}"}
            try:
                data = resp.json()
            except ValueError as e:
                logger.warning(f"fetch_patches_schema: некорректный JSON: {e}")
                return {"success": False, "message": "Некорректный JSON в patches_schema.json"}

            # Минимальная валидация структуры
            if not isinstance(data, dict) or 'settings' not in data or 'categories' not in data:
                return {"success": False, "message": "Схема должна содержать 'categories' и 'settings'"}
            if not isinstance(data['settings'], list) or not isinstance(data['categories'], list):
                return {"success": False, "message": "'categories' и 'settings' должны быть массивами"}

            logger.info(f"fetch_patches_schema: загружено категорий={len(data['categories'])}, настроек={len(data['settings'])}")
            self._patches_schema_cache = data
            return {"success": True, "data": data}
        except requests.exceptions.ConnectionError:
            return {"success": False, "message": "Нет подключения к интернету"}
        except requests.exceptions.Timeout:
            return {"success": False, "message": "Превышено время ожидания (GitHub не отвечает)"}
        except Exception as e:
            logger.error(f"fetch_patches_schema error: {e}")
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
            resp = requests.get(url, timeout=15)
            resp.encoding = 'utf-8'
            if resp.status_code != 200:
                return {"success": False, "message": f"Ошибка загрузки: HTTP {resp.status_code}", "stage": "downloading"}

            raw = resp.text
            cleaned = re.sub(r"^\s*//.*", "", raw, flags=re.MULTILINE)
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
                resp = requests.get(url, timeout=10, headers={"Cache-Control": "no-cache"})
                try:
                    text = resp.content.decode('utf-8')
                except UnicodeDecodeError:
                    text = resp.content.decode('windows-1251', errors='replace')
                text = self._fix_mojibake(text)
                logger.info(f"fetch_moonloader_catalog: статус {resp.status_code}")
                if resp.status_code != 200:
                    continue
                scripts = self._parse_catalog_txt(text)
                if scripts:
                    logger.info(f"fetch_moonloader_catalog: {len(scripts)} скриптов из {url}")
                    return {"success": True, "data": scripts}
            except Exception as e:
                logger.warning(f"fetch_moonloader_catalog {url}: {e}")
        return {"success": False, "message": "Нет соединения с GitHub или каталог пуст"}


    @staticmethod
    def _fix_mojibake(text):
        """Исправляет двойное кодирование: UTF-8 → CP1251 → UTF-8.

        Применяется ТОЛЬКО когда вход содержит явные маркеры mojibake —
        символы Ð/Ñ (0xC3 0x90/0xC3 0x91 в UTF-8, показанные как Latin-1).
        Если вход уже валидный UTF-8 с кириллицей — возвращаем как есть,
        чтобы не испортить корректный текст."""
        if not text:
            return text
        # Маркер mojibake: латинские Ð (U+00D0) или Ñ (U+00D1), за которыми
        # идёт другой символ из диапазона 0x80-0xBF. Эти последовательности
        # не встречаются в нормальном русском тексте.
        if not re.search(r'[\u00C0-\u00DF][\u0080-\u00BF]', text):
            return text
        try:
            fixed = text.encode('cp1251').decode('utf-8')
            if any('\u0400' <= c <= '\u04ff' for c in fixed):
                return fixed
        except (UnicodeDecodeError, UnicodeEncodeError):
            pass
        return text

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
            resp = requests.get(url, timeout=30)
            if resp.status_code != 200:
                return {"success": False, "message": f"Ошибка загрузки: HTTP {resp.status_code}"}
            safe_name = _safe_basename(filename)
            dest = os.path.join(ml_dir, safe_name)
            with open(dest, 'wb') as f:
                f.write(resp.content)
            return {"success": True, "message": f"Установлен: {filename}"}
        except Exception as e:
            logger.error(f"install_moonloader_script error: {e}")
            return {"success": False, "message": str(e)}

    # ---- БИБЛИОТЕКИ ----

    def fetch_libraries_catalog(self):
        """Загружает libraries.txt с GitHub"""
        LIBRARIES_URL = "https://raw.githubusercontent.com/worteng/ArizonaLauncher/main/libraries.txt"
        try:
            resp = requests.get(LIBRARIES_URL, timeout=10,
                                headers={"Cache-Control": "no-cache"})
            try:
                text = resp.content.decode('utf-8')
            except UnicodeDecodeError:
                text = resp.content.decode('windows-1251', errors='replace')
            text = self._fix_mojibake(text)
            if resp.status_code == 404:
                return {"success": False, "message": "Файл libraries.txt не найден (404)"}
            if resp.status_code != 200:
                return {"success": False, "message": f"GitHub вернул HTTP {resp.status_code}"}
            items = self._parse_catalog_txt(text)
            logger.info(f"fetch_libraries_catalog: {len(items)} библиотек")
            return {"success": True, "data": items}
        except requests.exceptions.ConnectionError:
            return {"success": False, "message": "Нет подключения к интернету"}
        except Exception as e:
            logger.error(f"fetch_libraries_catalog: {e}")
            return {"success": False, "message": str(e)}

    def _get_lib_dir(self):
        """Канонический путь к папке библиотек MoonLoader (lib/, fallback libraries/)."""
        ml_dir = self._get_moonloader_dir()
        if not ml_dir:
            return None, None
        # Приоритет: существующая непустая папка. Иначе — каноническая lib/.
        for cand in ('lib', 'libraries'):
            p = os.path.join(ml_dir, cand)
            if os.path.isdir(p):
                try:
                    if any(os.scandir(p)):
                        return p, cand
                except OSError:
                    pass
        # Ни одна не существует с содержимым — создаём каноническую lib/
        canon = os.path.join(ml_dir, 'lib')
        return canon, 'lib'

    def install_library(self, name, url):
        """Скачивает библиотеку и распаковывает в moonloader/lib/ (или libraries/)."""
        ml_dir = self._get_moonloader_dir()
        if not ml_dir:
            return {"success": False, "message": "Папка moonloader не найдена"}
        lib_dir, _ = self._get_lib_dir()
        os.makedirs(lib_dir, exist_ok=True)
        try:
            # Защита от повторной загрузки: если либа с таким именем уже есть
            installed = self.list_installed_libraries().get("data", [])
            if any(l["name"] == name for l in installed):
                logger.info(f"install_library: {name} уже установлена, пропускаю")
                return {"success": True, "skipped": True, "message": f"Библиотека {name} уже установлена"}
            resp = requests.get(url, timeout=30)
            if resp.status_code != 200:
                return {"success": False, "message": f"Ошибка загрузки: HTTP {resp.status_code}"}
            # Сохраняем во временный файл
            import tempfile, zipfile, io
            safe_name = _safe_basename(name)
            tmp_fd, tmp = tempfile.mkstemp(suffix='.zip', prefix=f'{safe_name}_lib_')
            os.close(tmp_fd)
            with open(tmp, 'wb') as f:
                f.write(resp.content)
            # Распаковываем если это zip
            if zipfile.is_zipfile(tmp):
                with zipfile.ZipFile(tmp, 'r') as z:
                    _safe_extract(z, lib_dir)
            else:
                # Просто копируем файл
                dest = os.path.join(lib_dir, safe_name)
                with open(tmp, 'rb') as src, open(dest, 'wb') as dst:
                    dst.write(src.read())
            os.remove(tmp)
            return {"success": True, "skipped": False, "message": f"Библиотека {name} установлена"}
        except Exception as e:
            logger.error(f"install_library error: {e}")
            return {"success": False, "message": str(e)}

    def list_installed_libraries(self):
        """Сканирует moonloader/lib/ (или libraries/) и возвращает установленные либы.

        Возвращает: {"success": bool, "data": [{"name", "files": [str], "size": int}, ...], "message": str}
        """
        ml_dir = self._get_moonloader_dir()
        if not ml_dir:
            return {"success": False, "message": "Папка moonloader не найдена", "data": []}
        lib_dir, dir_name = self._get_lib_dir()
        if not lib_dir or not os.path.isdir(lib_dir):
            return {"success": True, "data": []}
        logger.info(f"list_installed_libraries: сканирую {lib_dir}")
        libs = {}
        allowed_ext = ('.dll', '.lua', '.luac', '.so', '.cs')
        def _scan(path, prefix=''):
            try:
                entries = list(os.scandir(path))
            except OSError:
                return
            for entry in entries:
                if entry.name.startswith('.') or entry.name == '__MACOSX':
                    continue
                if entry.is_dir():
                    _scan(entry.path, prefix=prefix or entry.name)
                elif entry.is_file():
                    ext = os.path.splitext(entry.name)[1].lower()
                    if ext not in allowed_ext:
                        continue
                    name = prefix or os.path.splitext(entry.name)[0]
                    try:
                        rel = os.path.relpath(entry.path, lib_dir).replace('\\', '/')
                        size = entry.stat().st_size
                    except OSError:
                        continue
                    libs.setdefault(name, {"name": name, "files": [], "size": 0})
                    libs[name]["files"].append(rel)
                    libs[name]["size"] += size
        _scan(lib_dir)
        return {"success": True, "data": list(libs.values())}

    def uninstall_library(self, name):
        """Удаляет либу из moonloader/lib/ (или libraries/) по имени."""
        if not name or name in ('.', '..', '/', '\\') or '/' in name or '\\' in name:
            return {"success": False, "message": "Некорректное имя библиотеки"}
        ml_dir = self._get_moonloader_dir()
        if not ml_dir:
            return {"success": False, "message": "Папка moonloader не найдена"}
        lib_dir, dir_name = self._get_lib_dir()
        if not lib_dir or not os.path.isdir(lib_dir):
            return {"success": False, "message": f"Папка {dir_name or 'lib'}/ не существует"}
        installed = self.list_installed_libraries().get("data", [])
        target = next((l for l in installed if l["name"] == name), None)
        if not target:
            return {"success": False, "message": f"Библиотека {name} не найдена"}
        removed = 0
        for rel in target["files"]:
            p = os.path.join(lib_dir, rel)
            try:
                os.remove(p)
                removed += 1
            except OSError as e:
                logger.warning(f"uninstall_library: не удалось удалить {p}: {e}")
        # Подметаем пустые родительские папки
        try:
            first_path = os.path.dirname(os.path.join(lib_dir, target["files"][0])) if target["files"] else lib_dir
        except (OSError, IndexError):
            first_path = lib_dir
        cur = first_path
        while cur and cur != lib_dir:
            try:
                if os.path.isdir(cur) and not os.listdir(cur):
                    os.rmdir(cur)
                else:
                    break
            except OSError:
                break
            cur = os.path.dirname(cur)
        return {"success": True, "message": f"Библиотека {name} удалена ({removed} файл.)"}

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
                                headers={"Cache-Control": "no-cache"})
            try:
                text = resp.content.decode('utf-8')
            except UnicodeDecodeError:
                text = resp.content.decode('windows-1251', errors='replace')
            text = self._fix_mojibake(text)
            if resp.status_code == 404:
                return {"success": False, "message": "Файл others.txt не найден на GitHub (404)"}
            if resp.status_code != 200:
                return {"success": False, "message": f"GitHub вернул HTTP {resp.status_code}"}
            items = self._parse_catalog_txt(text)
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
            resp = requests.get(url, timeout=30)
            if resp.status_code != 200:
                return {"success": False, "message": f"Ошибка загрузки: HTTP {resp.status_code}"}
            safe_name = _safe_basename(filename)
            out_path = os.path.join(dest_dir, safe_name)
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
            safe_name = _safe_basename(filename)
            file_path = os.path.join(dest_dir, safe_name)
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
            safe_name = _safe_basename(filename)
            dest = os.path.join(ml_dir, safe_name)
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
                # Ключ отсутствует — продолжаем поиск
                continue
        return False
    except ImportError:
        # winreg недоступен (не Windows) — не блокируем
        return True
    except Exception as e:
        # Неожиданная ошибка — логируем и не блокируем
        logger.warning(f"_check_vcredist unexpected error: {e}")
        return True


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
    except ImportError:
        # winreg недоступен (не Windows) — не блокируем
        return True
    except Exception as e:
        # Неожиданная ошибка — логируем и не блокируем
        logger.warning(f"_check_webview2 unexpected error: {e}")
        return True


def _show_dependency_dialog(missing: list):
    """Показывает нативное PyQt5-окно со ссылками на скачивание зависимостей.
    Возвращает True если пользователь нажал 'Продолжить', False если 'Выход'."""
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
    title = QLabel("⚠  Требуются дополнительные компоненты")
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
            "icon": "⚙"
        },
        "webview2": {
            "name": "Microsoft Edge WebView2 Runtime",
            "desc": "Движок для отображения интерфейса лаунчера",
            "url": "https://go.microsoft.com/fwlink/p/?LinkId=2124703",
            "icon": "◉"
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
        dl_btn = QPushButton("▼ Скачать")
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
    force_first  = "-First" in sys.argv

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

    # ── Debug-сервер (только при явном запросе) ───────────────────
    # Локальный HTTP-сервер на 127.0.0.1:8765 для дёрганья backend-функций
    # без GUI. Полезно для тестирования логики обновлений/патчей.
    # Запускается при: флаг --debug ИЛИ env ARIZONA_LAUNCHER_DEBUG=1.
    if DEBUG:
        try:
            _app_dir = _get_app_dir()
            if _app_dir not in sys.path:
                sys.path.insert(0, _app_dir)
            import debug_server
            port = int(os.environ.get('ARIZONA_DEBUG_PORT', '8765'))
            debug_server.start_debug_server(app, port=port)
            logger.info(f"[debug] Сервер запущен на http://127.0.0.1:{port}")
        except Exception as e:
            print(f"[DEBUG-SERVER ERROR] {e}")
            import traceback
            traceback.print_exc()
            logger.warning(f"Не удалось запустить debug-сервер: {e}", exc_info=True)

    # При первом запуске — пробуем найти игру автоматически
    auto_found = False
    if (is_first_run or force_first) and not force_deps:
        auto_found = app.launcher.auto_detect_game_paths()
        if auto_found:
            logger.info(f"Авто-обнаружение: {app.launcher.game_path}")
        else:
            logger.info("Авто-обнаружение: игра не найдена, пользователь укажет вручную")

    def _on_loaded():
        """После загрузки страницы открываем панель первого запуска."""
        import time as _t, json as _json
        _t.sleep(0.2)
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
        saved_title = app.launcher.config.get('launcher_settings', {}).get('window_title', 'Arizona RP Launcher')
        # Восстанавливаем сохранённый размер окна (если есть)
        saved_size = app.launcher.config.get('launcher_settings', {}).get('window_size')
        if isinstance(saved_size, (list, tuple)) and len(saved_size) == 2:
            init_w, init_h = int(saved_size[0]), int(saved_size[1])
            # Защита от вырожденных значений
            init_w = max(1032, min(init_w, 4000))
            init_h = max(583,  min(init_h, 4000))
        else:
            init_w, init_h = 1285, 732
        index_url = os.path.join(_get_app_dir(), 'index.html')
        window = webview.create_window(saved_title, index_url, js_api=app, width=init_w, height=init_h,
                                       resizable=True, fullscreen=False, min_size=(1032, 583))
        app._window = window
        # Устанавливаем иконку лаунчера
        ico_path = os.path.join(_get_app_dir(), 'icon.ico')
        if os.path.exists(ico_path):
            try:
                window.configure(icon=ico_path)
            except Exception:
                pass

        # Запоминаем размер окна (с дебаунсом, чтобы не спамить запись на диск при ресайзе)
        _resize_save_timer = [None]
        def _on_resized(width, height):
            def _save():
                try:
                    with app.launcher._cfg_lock:
                        if not app.launcher.config.get('launcher_settings'):
                            app.launcher.config['launcher_settings'] = {}
                        app.launcher.config['launcher_settings']['window_size'] = [int(width), int(height)]
                        app.launcher.save_config()
                        logger.debug(f"window size saved: {width}x{height}")
                except Exception as ex:
                    logger.warning(f"save window size failed: {ex}")
            # Дебаунс: 400ms после последнего resize-события
            if _resize_save_timer[0] is not None:
                _resize_save_timer[0].cancel()
            _resize_save_timer[0] = threading.Timer(0.4, _save)
            _resize_save_timer[0].daemon = True
            _resize_save_timer[0].start()
        try:
            window.events.resized += _on_resized
        except Exception as ex:
            logger.warning(f"window resize event hook failed: {ex}")

        if is_first_run or force_first:
            window.events.loaded += _on_loaded
        gui = os.environ.get('ARIZONA_LAUNCHER_GUI', 'edgechromium')
        webview.start(debug=DEBUG, gui=gui)
    except Exception as e:
        logger.error(f"Error: {e}")
        if sys.stdin and sys.stdin.isatty():
            input("Press Enter to exit...")

if __name__ == '__main__':
    main()
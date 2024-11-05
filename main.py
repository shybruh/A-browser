import sys
import json
import os
import winreg
import logging
from PyQt5.QtCore import Qt, QUrl, QSize, QTimer
from PyQt5.QtWidgets import (QApplication, QMainWindow, QTabWidget, QShortcut, QToolButton, QLineEdit, QVBoxLayout,
                             QWidget, QHBoxLayout, QDialog, QTextBrowser, QLabel, QPushButton, QComboBox, QMessageBox)
from PyQt5.QtWebEngineWidgets import QWebEngineView, QWebEngineSettings, QWebEngineProfile
from PyQt5.QtGui import QKeySequence, QFont, QIcon
from PyQt5.QtWidgets import QMenu
from PyQt5.QtWidgets import QFileDialog
from PyQt5.QtGui import QGuiApplication
import aria2p
from PyQt5.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QListWidget, QProgressBar
import subprocess
import psutil
import atexit
import ctypes
import win32con
import win32api

logging.basicConfig(filename='browser_log.txt', level=logging.DEBUG,
                    format='%(asctime)s - %(levelname)s - %(message)s')

class DownloadManager(QDialog):
    logging.info("DownloadManager initialized")
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Download Manager')
        self.setGeometry(100, 100, 600, 400)
        self.aria2 = aria2p.API(aria2p.Client(host="http://localhost", port=6800, secret=""))

        layout = QVBoxLayout(self)

        self.download_list = QListWidget()
        self.download_list.itemSelectionChanged.connect(self.update_buttons_state)
        layout.addWidget(self.download_list)

        self.progress_bar = QProgressBar()
        layout.addWidget(self.progress_bar)

        status_layout = QHBoxLayout()
        self.percentage_label = QLabel("0%")
        self.speed_label = QLabel("0 B/s")
        status_layout.addWidget(self.percentage_label)
        status_layout.addWidget(self.speed_label)
        layout.addLayout(status_layout)

        button_layout = QHBoxLayout()

        self.start_button = QPushButton("Start")
        self.start_button.setObjectName("start_download")
        self.start_button.clicked.connect(self.start_download)
        button_layout.addWidget(self.start_button)

        self.pause_button = QPushButton("Pause")
        self.pause_button.setObjectName("pause_download")
        self.pause_button.clicked.connect(self.pause_download)
        button_layout.addWidget(self.pause_button)

        self.remove_button = QPushButton("Remove")
        self.remove_button.setObjectName("remove_download")
        self.remove_button.clicked.connect(self.remove_download)
        button_layout.addWidget(self.remove_button)

        layout.addLayout(button_layout)

        self.update_download_list()
        self.update_buttons_state()

        self.update_timer = QTimer(self)
        self.update_timer.timeout.connect(self.update_download_status)
        self.update_timer.start(1000)  # Update every second

    def update_buttons_state(self):
        selected = self.download_list.currentItem() is not None
        self.start_button.setEnabled(selected)
        self.pause_button.setEnabled(selected)
        self.remove_button.setEnabled(selected)

    def get_selected_download(self):
        item = self.download_list.currentItem()
        if item:
            download_name = item.text().split(" - ")[0]
            return next((d for d in self.aria2.get_downloads() if d.name == download_name), None)
        return None

    def start_download(self):
        logging.info("start_download")
        download = self.get_selected_download()
        if download:
            self.aria2.resume([download])
            self.update_download_list()
            self.update_download_status()

    def pause_download(self):
        logging.info("pause_download")
        download = self.get_selected_download()
        if download:
            self.aria2.pause([download])
            self.update_download_list()
            self.update_download_status()

    def remove_download(self):
        logging.info("remove_download")
        download = self.get_selected_download()
        if download:
            self.aria2.remove([download])
            self.update_download_list()
            self.update_download_status()

    def update_download_list(self):
        logging.info("update_download_list")
        self.download_list.clear()
        downloads = self.aria2.get_downloads()
        for download in downloads:
            self.download_list.addItem(f"{download.name} - {download.status}")
        self.update_buttons_state()

    def update_download_status(self):
        download = self.get_selected_download()
        if download:
            percentage = download.progress
            download_speed = download.download_speed

            self.progress_bar.setValue(int(percentage))
            self.percentage_label.setText(f"{percentage:.1f}%")
            self.speed_label.setText(f"{self.format_speed(download_speed)}")
        else:
            self.progress_bar.setValue(0)
            self.percentage_label.setText("0%")
            self.speed_label.setText("0 B/s")

    def format_speed(self, speed):
        if speed < 1024:
            return f"{speed:.2f} B/s"
        elif speed < 1024 * 1024:
            return f"{speed / 1024:.2f} KB/s"
        else:
            return f"{speed / (1024 * 1024):.2f} MB/s"

    def add_download(self, url, filename):
        download_dir = self.get_windows_download_folder()
        full_path = os.path.join(download_dir, filename)

        options = {
            "dir": download_dir,
            "out": filename,
            "max-connection-per-server": "16",
        }

        self.aria2.add_uris([url], options=options)
        self.update_download_list()
        self.update_download_status()

    @staticmethod
    def get_windows_download_folder():
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                r'SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders') as key:
                download_dir = winreg.QueryValueEx(key, '{374DE290-123F-4565-9164-39C4925E467B}')[0]
            return download_dir
        except Exception:
            return os.path.expanduser('~\\Downloads')

class Settings:
    def __init__(self):
        self.settings_file = 'browser_settings.json'
        self.data = self.load_settings()
        self.data.setdefault('bookmarks',{})

    def load_settings(self):
        default_settings = {
            'default_search_engine': 'Google',
            'search_engines': {
                'Google': 'https://www.google.com/search?q=',
                'Bing': 'https://www.bing.com/search?q=',
                'DuckDuckGo': 'https://duckduckgo.com/?q='
            },
            'history': [],
            'dns_servers': {
                'Default': '',
                'Google': '8.8.8.8',
                'Cloudflare': '1.1.1.1',
                'OpenDNS': '208.67.222.222'
            },
            'current_dns': 'Default'
        }

        if os.path.exists(self.settings_file):
            try:
                with open(self.settings_file, 'r') as f:
                    return json.load(f)
            except json.JSONDecodeError as e:
                logging.error(f"Error reading {self.settings_file}: {str(e)}")
                return default_settings
        else:
            return default_settings

    def save_settings(self):
        try:
            with open(self.settings_file, 'w') as f:
                json.dump(self.data, f, indent=4)
            logging.info("Settings saved successfully")
        except Exception as e:
            logging.error(f"Error saving settings: {str(e)}")
            raise

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value
        self.save_settings()

    def add_bookmark(self, url, title):
        self.data['bookmarks'][url] = title
        self.save_settings()

    def remove_bookmark(self, url):
        if url in self.data['bookmarks']:
            del self.data['bookmarks'][url]
            self.save_settings()

    def get_bookmarks(self):
        return self.data['bookmarks']

    def get_adblock_enabled(self):
        return self.data('adblock_enabled',True)
    def set_adblock_enabled(self, enabled):
        self.data['adblock_enabled'] = enabled
        self.save_settings()


class Browser(QMainWindow):
    def __init__(self):
        super().__init__()
        self.start_aria2_rpc_server()
        atexit.register(self.stop_aria2_rpc_server)
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        #self.setWindowFlags(Qt.FramelessWindowHint)
        #self.setWindowTitle('Personalis aurory')
        self.setGeometry(100, 100, 1200, 800)
        try:
            self.settings = Settings()
            self.browser_history = self.settings.get('history', [])
            self.search_engines = self.settings.get('search_engines', {})
            self.default_search_engine = self.settings.get('default_search_engine', 'Google')
            self.dns_servers = self.settings.get('dns_servers', {})
            self.current_dns = self.settings.get('current_dns', 'Default')
        except Exception as e:
            logging.error(f"Error initializing settings: {str(e)}")
            QMessageBox.critical(self, "Error", f"Failed to load settings: {str(e)}")
            sys.exit(1)

        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.layout = QVBoxLayout(self.central_widget)
        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.setMovable(True)
        self.tabs.setElideMode(Qt.ElideRight)
        self.tabs.setUsesScrollButtons(True)
        self.tabs.setStyleSheet(
            "QTabBar::tab { max-width: 100px; text-align: left; padding-left: 10px; padding-right: 20px; }")
        self.tabs.tabCloseRequested.connect(self.close_tab)
        self.download_manager = DownloadManager(self)
        self.shortcut_next = QShortcut(QKeySequence('Alt+Right'), self)
        self.shortcut_next.activated.connect(self.next_tab)
        self.dragging = False
        self.drag_position = None
        self.shortcut_prev = QShortcut(QKeySequence('Alt+Left'), self)
        self.shortcut_prev.activated.connect(self.prev_tab)
        self.init_ui()
        self.add_new_tab(self.search_engines[self.default_search_engine])
        self.apply_dns_settings()
        self.corner_widget = self.create_corner_widget()
        self.tabs.setCornerWidget(self.corner_widget, Qt.TopRightCorner)
    def resizeEvent(self, event):
        super().resizeEvent(event)
    def start_aria2_rpc_server(self):
        if self.is_aria2_running():
            print("aria2c is already running")
            logging.info("aria2c is already running")
            return

        try:
            current_dir = os.path.dirname(os.path.abspath(__file__))
            if sys.platform.startswith('win'):
                aria2_path = os.path.join(current_dir, 'aria2', 'aria2c.exe')
            else:
                aria2_path = os.path.join(current_dir, 'aria2', 'aria2c')

            if not os.path.exists(aria2_path):
                raise FileNotFoundError(f"aria2c executable not found at {aria2_path}")

            command = [aria2_path, "--enable-rpc", "--rpc-listen-all"]
            if sys.platform.startswith('win'):
                self.aria2_process = subprocess.Popen(command, creationflags=subprocess.CREATE_NO_WINDOW)
            else:
                self.aria2_process = subprocess.Popen(command)

            print(f"Aria2 RPC server started successfully from {aria2_path}")
            logging.info(f"Aria2 RPC server started successfully from {aria2_path}")
        except FileNotFoundError as e:
            print(f"Error: {str(e)}. Please make sure aria2 is in the correct location.")
            logging.error(f"Error: {str(e)}. Please make sure aria2 is in the correct location.")
        except Exception as e:
            print(f"Error starting aria2 RPC server: {str(e)}")
            logging.error(f"Error starting aria2 RPC server: {str(e)}")

    def stop_aria2_rpc_server(self):
        if self.aria2_process:
            self.aria2_process.terminate()
            try:
                self.aria2_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.aria2_process.kill()
            print("Aria2 RPC server stopped")
            logging.info("Aria2 RPC server stopped")

    def is_aria2_running(self):
        for proc in psutil.process_iter(['name']):
            if proc.info['name'] == 'aria2c' or proc.info['name'] == 'aria2c.exe':
                return True
        return False

    def closeEvent(self, event):
        self.stop_aria2_rpc_server()
        super().closeEvent(event)
    def create_download_button(self):
        download_button = QToolButton(self)
        download_button.setObjectName("download_button")
        #download_button.setText("↓")
        download_button.setIcon(QIcon('icons/google material icons/baseline-download.svg'))
        download_button.setToolTip("Open Download Manager")
        download_button.clicked.connect(self.open_download_manager)
        download_button.setFixedSize(25, 25)
        return download_button

    def open_download_manager(self):
        self.download_manager.show()
    def init_ui(self):
        nav_address_layout = QHBoxLayout()

        back_button = self.create_navigation_button("", self.go_back)
        back_button.setIcon(QIcon('icons/google material icons/chevron-left.svg'))
        back_button.setObjectName("back_button")
        back_button.setToolTip("Go back")

        forward_button = self.create_navigation_button("", self.go_forward)
        forward_button.setIcon(QIcon('icons/google material icons/chevron-right.svg'))
        forward_button.setObjectName("forward_button")
        forward_button.setToolTip("Go forward")

        nav_address_layout.addWidget(back_button)
        nav_address_layout.addWidget(forward_button)

        refresh_button = self.create_refresh_button()
        nav_address_layout.addWidget(refresh_button)

        self.address_bar = QLineEdit()
        self.address_bar.returnPressed.connect(self.navigate_to_url)
        nav_address_layout.addWidget(self.address_bar)

        # Add the new tab and settings buttons to the right of the address bar
        add_tab_button = self.create_add_tab_button()
        bookmark_button = self.create_bookmark_button()
        download_button = self.create_download_button()
        settings_button = self.create_settings_button()

        nav_address_layout.addWidget(add_tab_button)
        nav_address_layout.addWidget(bookmark_button)
        nav_address_layout.addWidget(download_button)
        nav_address_layout.addWidget(settings_button)


        self.layout.addWidget(self.tabs)
        self.layout.addLayout(nav_address_layout)

        font = QFont('JetBrains Mono', 10)
        self.address_bar.setFont(font)
        self.tabs.setFont(font)

    def create_download_button(self):
        download_button = QToolButton(self)
        download_button.setObjectName("download_button")
        #download_button.setText("↓")
        download_button.setIcon(QIcon('icons/google material icons/baseline-download.svg'))
        download_button.setToolTip("Open Download Manager")
        download_button.clicked.connect(self.open_download_manager)
        download_button.setFixedSize(25, 25)
        return download_button

    def open_download_manager(self):
        self.download_manager.show()
    def create_corner_widget(self):
        corner_widget = QWidget()
        corner_layout = QHBoxLayout(corner_widget)
        corner_layout.setContentsMargins(0, 0, 0, 0)
        corner_layout.setSpacing(0)

        minimize_button = QPushButton("")
        minimize_button.setIcon(QIcon('icons/google material icons/baseline-minimize.svg'))
        minimize_button.setObjectName("min_button")
        maximize_button = QPushButton("")
        maximize_button.setIcon(QIcon('icons/google material icons/screen-maximise.svg'))
        maximize_button.setObjectName("max_button")
        close_button = QPushButton("")
        close_button.setIcon(QIcon('icons/google material icons/close.svg'))
        close_button.setObjectName("browser_close_button")
        for button in (minimize_button, maximize_button, close_button):
            corner_layout.addWidget(button)
        minimize_button.clicked.connect(self.showMinimized)
        maximize_button.clicked.connect(self.toggle_maximize)
        close_button.clicked.connect(self.close)

        return corner_widget

    def toggle_maximize(self):
        if self.isMaximized():
            self.showNormal()
            # Restore frameless hint when not maximized
            self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
            self.setAttribute(Qt.WA_TranslucentBackground)
        else:
            # Remove frameless hint when maximizing

            self.setAttribute(Qt.WA_TranslucentBackground)
            self.showMaximized()
        self.update_maximize_button()
        # Ensure the window is visible after changing flags
        self.show()

    def update_maximize_button(self):
        maximize_button = self.corner_widget.findChild(QPushButton, "max_button")
        if maximize_button:
            if self.isMaximized():
                maximize_button.setIcon(QIcon('icons/google material icons/screen-minimise.svg'))
            else:
                maximize_button.setIcon(QIcon('icons/google material icons/screen-maximise.svg'))

    def snap_to_edge(self):
        margin = 10  # pixels
        screen = QGuiApplication.primaryScreen().geometry()
        window = self.geometry()

        # Snap to left half
        if window.left() <= margin:
            self.setGeometry(0, 0, screen.width() // 2, screen.height())
        # Snap to right half
        elif window.right() >= screen.width() - margin:
            self.setGeometry(screen.width() // 2, 0, screen.width() // 2, screen.height())
        # Snap to top
        elif window.top() <= margin:
            self.showMaximized()
        # Restore if dragged away from edges
        elif self.isMaximized():
            self.showNormal()
            # Center the window
            self.setGeometry(
                screen.width() // 4,
                screen.height() // 4,
                screen.width() // 2,
                screen.height() // 2
            )
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.dragging = True
            self.drag_position = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton and self.dragging:
            new_pos = event.globalPos() - self.drag_position
            self.move(new_pos)
            event.accept()
        elif event.buttons() == Qt.NoButton:
            self.snap_to_edge()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.dragging = False
            self.snap_to_edge()
            event.accept()

    def nativeEvent(self, eventType, message):
        retval, result = super().nativeEvent(eventType, message)
        if eventType == "windows_generic_MSG":
            msg = ctypes.wintypes.MSG.from_address(message.__int__())
            if msg.message == win32con.WM_NCHITTEST:
                x = win32api.LOWORD(msg.lParam) - self.frameGeometry().x()
                y = win32api.HIWORD(msg.lParam) - self.frameGeometry().y()
                w, h = self.width(), self.height()
                lx = x < 8
                rx = x > w - 8
                ty = y < 8
                by = y > h - 8

                if lx and ty:
                    return True, win32con.HTTOPLEFT
                if rx and by:
                    return True, win32con.HTBOTTOMRIGHT
                if rx and ty:
                    return True, win32con.HTTOPRIGHT
                if lx and by:
                    return True, win32con.HTBOTTOMLEFT
                if ty:
                    return True, win32con.HTTOP
                if by:
                    return True, win32con.HTBOTTOM
                if lx:
                    return True, win32con.HTLEFT
                if rx:
                    return True, win32con.HTRIGHT
        return retval, result
    def create_navigation_button(self, text, slot):
        button = QToolButton(self)
        button.setText(text)
        button.clicked.connect(slot)
        button.setFixedSize(25, 25)
        return button

    def go_back(self):
        current_tab = self.tabs.currentWidget()
        if isinstance(current_tab, QWebEngineView) and current_tab.history().canGoBack():
            current_tab.history().back()

    def go_forward(self):
        current_tab = self.tabs.currentWidget()
        if isinstance(current_tab, QWebEngineView) and current_tab.history().canGoForward():
            current_tab.history().forward()

    def closeEvent(self, event):
        try:
            self.settings.set('history', self.browser_history)
        except Exception as e:
            logging.error(f"Error saving history on close: {str(e)}")
            QMessageBox.warning(self, "Warning", f"Failed to save history: {str(e)}")
        event.accept()

    def create_add_tab_button(self):
        add_tab_button = QToolButton(self)
        add_tab_button.setObjectName("add_tab_button")
        add_tab_button.setIcon(QIcon('icons/google material icons/baseline-add.svg'))
        #add_tab_button.setText("+")
        add_tab_button.setToolTip("Add new tab")
        add_tab_button.clicked.connect(lambda: self.add_new_tab())
        add_tab_button.setFixedSize(25, 25)
        return add_tab_button

    def create_settings_button(self):
        settings_button = QToolButton(self)
        settings_button.setObjectName("settings_button")
        settings_button.setIcon(QIcon('icons/google material icons/baseline-settings.svg'))
        #settings_button.setText("!")
        settings_button.setToolTip("Settings")
        settings_button.clicked.connect(self.open_settings_dialog)
        settings_button.setFixedSize(25, 25)
        return settings_button

    def refresh_current_page(self):
        if self.tabs.currentWidget():
            self.tabs.currentWidget().reload()

    def create_refresh_button(self):
        refresh_button = QToolButton(self)
        refresh_button.setObjectName("refresh_button")
        #refresh_button.setText("⟳")
        refresh_button.setIcon(QIcon('icons/google material icons/baseline-refresh.svg'))
        refresh_button.setToolTip("Refresh current page")
        refresh_button.clicked.connect(self.refresh_current_page)
        return refresh_button

    def add_new_tab(self, url=None):
        if url is None:
            url = self.search_engines[self.default_search_engine]
        browser = QWebEngineView()
        settings = browser.settings()

        settings.setAttribute(QWebEngineSettings.JavascriptEnabled, True)
        settings.setAttribute(QWebEngineSettings.JavascriptCanOpenWindows, True)
        settings.setAttribute(QWebEngineSettings.JavascriptCanAccessClipboard, True)
        browser.setUrl(QUrl(url))
        i = self.tabs.addTab(browser, "New Tab")
        self.tabs.setCurrentIndex(i)
        browser.titleChanged.connect(lambda title, browser=browser: self.update_tab_title(title, browser))
        browser.urlChanged.connect(lambda q, browser=browser: self.update_address_bar(q, browser))
        browser.urlChanged.connect(lambda q, browser=browser: self.url_changed(q, browser))
        browser.page().profile().downloadRequested.connect(self.handle_download_request)

    def handle_download_request(self, download):
        url = download.url().toString()
        suggested_filename = download.suggestedFileName()

        if not suggested_filename:
            suggested_filename = os.path.basename(url)

        # Ensure the filename has an extension
        if '.' not in suggested_filename:
            content_type = download.mimeType()
            extension = self.get_extension_for_mime_type(content_type)
            if extension:
                suggested_filename += f'.{extension}'

        download_dir = self.download_manager.get_windows_download_folder()
        default_path = os.path.join(download_dir, suggested_filename)

        file_path, _ = QFileDialog.getSaveFileName(self, "Save File", default_path, "All Files (*.*)")

        if file_path:
            filename = os.path.basename(file_path)
            self.download_manager.add_download(url, filename)
            self.open_download_manager()

    @staticmethod
    def get_extension_for_mime_type(mime_type):
        # This is a basic mapping. You might want to expand this or use a more comprehensive library.
        mime_to_ext = {
            'text/html': 'html',
            'text/plain': 'txt',
            'application/pdf': 'pdf',
            'image/jpeg': 'jpg',
            'image/png': 'png',
            'application/zip': 'zip',
            # Add more mappings as needed
        }
        return mime_to_ext.get(mime_type, '')
    def update_tab_title(self, title, browser):
        index = self.tabs.indexOf(browser)
        self.tabs.setTabText(index, title)

    def close_tab(self, index):
        if self.tabs.count() > 1:
            self.tabs.removeTab(index)

    def next_tab(self):
        current_index = self.tabs.currentIndex()
        next_index = (current_index + 1) % self.tabs.count()
        self.tabs.setCurrentIndex(next_index)

    def prev_tab(self):
        current_index = self.tabs.currentIndex()
        prev_index = (current_index - 1) % self.tabs.count()
        self.tabs.setCurrentIndex(prev_index)

    def navigate_to_url(self):
        url = self.address_bar.text()
        if '.' in url:
            if not url.startswith(('http://', 'https://')):
                url = 'http://' + url
            self.tabs.currentWidget().setUrl(QUrl(url))
        else:
            search_url = self.search_engines.get(self.default_search_engine, 'https://www.google.com/search?q=') + url
            self.tabs.currentWidget().setUrl(QUrl(search_url))

    def url_changed(self, q, browser):
        url = q.toString()
        if url not in self.browser_history:
            self.browser_history.append(url)
            try:
                self.settings.set('history', self.browser_history)
            except Exception as e:
                logging.error(f"Error saving history: {str(e)}")
                QMessageBox.warning(self, "Warning", f"Failed to save history: {str(e)}")

    def update_address_bar(self, q, browser=None):
        if browser != self.tabs.currentWidget():
            return
        self.address_bar.setText(q.toString())
        self.address_bar.setCursorPosition(0)

    def open_settings_dialog(self):
        dialog = SettingsDialog(self)
        dialog.search_engine_combo.addItems(self.search_engines.keys())
        dialog.search_engine_combo.setCurrentText(self.default_search_engine)

        # Populate the dns_servers dictionary
        self.dns_servers = {
            "Google DNS": "8.8.8.8",
            "Cloudflare DNS": "1.1.1.1",
            "Quad9 DNS": "9.9.9.9",
            # Add more DNS servers as needed
        }
        bookmark_button = QPushButton("Manage Bookmarks")
        bookmark_button.clicked.connect(self.open_bookmark_manager)
        dialog.dns_combo.addItems(self.dns_servers.keys())
        dialog.dns_combo.setCurrentText(self.current_dns)

        dialog.update_history(self.browser_history)

        print("DNS Servers:", self.dns_servers)
        logging.debug(f"Opening settings dialog with current DNS: {self.current_dns}")

        if dialog.exec_():
            try:
                new_search_engine = dialog.search_engine_combo.currentText()
                new_dns = dialog.dns_combo.currentText()

                logging.debug(f"New settings - Search Engine: {new_search_engine}, DNS: {new_dns}")

                if new_search_engine != self.default_search_engine or new_dns != self.current_dns:
                    self.default_search_engine = new_search_engine
                    self.current_dns = new_dns
                    self.settings.set('default_search_engine', self.default_search_engine)
                    self.settings.set('current_dns', self.current_dns)
                    self.apply_dns_settings()

                    logging.debug("Settings saved and applied")
                else:
                    logging.debug("No changes in settings")
                    self.browser_history = self.settings.get('history',[])
            except Exception as e:
                logging.error(f"Error saving settings: {str(e)}")
                QMessageBox.critical(self, "Error", f"Failed to save settings: {str(e)}")

    def create_bookmark_button(self):
        bookmark_button = QToolButton(self)
        bookmark_button.setObjectName("bookmark_button")
        bookmark_button.setIcon(QIcon('icons/google material icons/bookmarks.svg'))
        #bookmark_button.setText("*")
        bookmark_button.setToolTip("Bookmark this page")
        bookmark_button.clicked.connect(self.toggle_bookmark)
        bookmark_button.setContextMenuPolicy(Qt.CustomContextMenu)
        bookmark_button.customContextMenuRequested.connect(self.show_bookmark_context_menu)
        bookmark_button.setFixedSize(25, 25)
        return bookmark_button

    def show_bookmark_context_menu(self, position):
        context_menu = QMenu(self)
        manage_action = context_menu.addAction("Manage Bookmarks")
        action = context_menu.exec_(self.sender().mapToGlobal(position))
        if action == manage_action:
            self.open_bookmark_manager()
    def toggle_bookmark(self):
        current_url = self.tabs.currentWidget().url().toString()
        current_title = self.tabs.tabText(self.tabs.currentIndex())

        if current_url in self.settings.get_bookmarks():
            self.settings.remove_bookmark(current_url)
            QMessageBox.information(self, "Bookmark Removed", f"Removed bookmark for: {current_title}")
        else:
            self.settings.add_bookmark(current_url, current_title)
            QMessageBox.information(self, "Bookmark Added", f"Added bookmark for: {current_title}")
    def open_bookmark_manager(self):
        manager = BookmarkManager(self)
        manager.exec_()

    def clear_history(self):
        self.browser_history.clear()
        try:
            self.settings.set('history', [])
            logging.info("Browsing history cleared and saved")
        except Exception as e:
            logging.error(f"Error saving cleared history: {str(e)}")
            QMessageBox.warning(self, "Warning", f"Failed to save cleared history: {str(e)}")
    def apply_dns_settings(self):
        print("apply_dns_settings called")  # Temporary print statement for debugging
        logging.debug("apply_dns_settings called")
        dns_server = self.dns_servers.get(self.current_dns, '')
        profile = QWebEngineProfile.defaultProfile()

        logging.debug(f"Applying DNS settings: {self.current_dns} - {dns_server}")

        if dns_server:
            print("if statement called")
            # Set custom DNS server
            os.environ['QTWEBENGINE_CHROMIUM_FLAGS'] = f'--host-resolver-rules="MAP * {dns_server}"'
            logging.debug(f"Set custom DNS server: {dns_server}")

            # Disable browser cache to ensure DNS changes take effect
            profile.setHttpCacheType(QWebEngineProfile.NoCache)
            logging.debug("Disabled browser cache")
        else:
            # Clear custom DNS settings
            os.environ.pop('QTWEBENGINE_CHROMIUM_FLAGS', None)
            logging.debug("Cleared custom DNS settings")

            # Re-enable browser cache
            profile.setHttpCacheType(QWebEngineProfile.DiskHttpCache)
            logging.debug("Re-enabled browser cache")

        # Clear existing DNS cache
        profile.clearAllVisitedLinks()
        profile.clearHttpCache()
        logging.debug("Cleared DNS cache")

        # Reload all tabs
        print("reload tabs called")
        for i in range(self.tabs.count()):
            if isinstance(self.tabs.widget(i), QWebEngineView):
                self.tabs.widget(i).reload()
        logging.debug("Reloaded all tabs")


from PyQt5.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QListWidget, QPushButton, QInputDialog


class BookmarkManager(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.setWindowTitle('Bookmark Manager')
        self.setGeometry(100, 100, 400, 300)

        layout = QVBoxLayout(self)

        self.bookmark_list = QListWidget()
        layout.addWidget(self.bookmark_list)

        button_layout = QHBoxLayout()

        open_button = QPushButton("Open")
        open_button.clicked.connect(self.open_bookmark)
        open_button.setObjectName("bookmark_open_button")
        button_layout.addWidget(open_button)

        edit_button = QPushButton("Edit")
        edit_button.clicked.connect(self.edit_bookmark)
        edit_button.setObjectName("bookmark_edit_button")
        button_layout.addWidget(edit_button)

        remove_button = QPushButton("Remove")
        remove_button.clicked.connect(self.remove_bookmark)
        remove_button.setObjectName("bookmark_remove_button")
        button_layout.addWidget(remove_button)
        layout.addLayout(button_layout)

        self.update_bookmark_list()

    def update_bookmark_list(self):
        self.bookmark_list.clear()
        for url, title in self.parent.settings.get_bookmarks().items():
            self.bookmark_list.addItem(f"{title} ({url})")

    def open_bookmark(self):
        current_item = self.bookmark_list.currentItem()
        if current_item:
            url = current_item.text().split("(")[-1][:-1]
            self.parent.add_new_tab(url)
            self.close()

    def edit_bookmark(self):
        current_item = self.bookmark_list.currentItem()
        if current_item:
            old_title, url = current_item.text().rsplit(" (", 1)
            url = url[:-1]  # Remove the closing parenthesis
            new_title, ok = QInputDialog.getText(self, "Edit Bookmark", "Enter new title:", text=old_title)
            if ok and new_title:
                self.parent.settings.remove_bookmark(url)
                self.parent.settings.add_bookmark(url, new_title)
                self.update_bookmark_list()

    def remove_bookmark(self):
        current_item = self.bookmark_list.currentItem()
        if current_item:
            url = current_item.text().split("(")[-1][:-1]
            self.parent.settings.remove_bookmark(url)
            self.update_bookmark_list()
class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Settings')
        self.setGeometry(100, 100, 600, 400)
        self.parent = parent

        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("Select Default Search Engine:"))
        self.search_engine_combo = QComboBox(self)
        layout.addWidget(self.search_engine_combo)

        layout.addWidget(QLabel("Select DNS Server:"))
        self.dns_combo = QComboBox(self)
        layout.addWidget(self.dns_combo)

        layout.addWidget(QLabel("Browser History:"))
        self.history_text = QTextBrowser(self)
        self.history_text.setOpenExternalLinks(False)
        self.history_text.anchorClicked.connect(self.handle_link_click)
        self.history_text.setFocusPolicy(Qt.NoFocus)
        layout.addWidget(self.history_text)

        # Add Clear History button
        self.clear_history_button = QPushButton("Clear History")
        self.clear_history_button.setObjectName("clear_history_button")
        self.clear_history_button.clicked.connect(self.clear_history)
        layout.addWidget(self.clear_history_button)

        # Add Bookmark Manager button
        self.bookmark_manager_button = QPushButton("Manage Bookmarks")
        self.bookmark_manager_button.setObjectName("manage_bookmark_button")
        self.bookmark_manager_button.clicked.connect(self.open_bookmark_manager)
        layout.addWidget(self.bookmark_manager_button)

        button_layout = QHBoxLayout()
        save_button = QPushButton("Save")
        save_button.setObjectName("save_button")
        save_button.clicked.connect(self.save_settings)
        close_button = QPushButton("Close")
        close_button.setObjectName("close_button")
        close_button.clicked.connect(self.reject)
        button_layout.addWidget(save_button)
        button_layout.addWidget(close_button)
        layout.addLayout(button_layout)

    def update_history(self, history):
        history_html = "<br>".join([f'<a href="{url}">{url}</a>' for url in history])
        self.history_text.setHtml(history_html)

    def handle_link_click(self, url):
        self.history_text.blockSignals(True)
        self.parent.add_new_tab(url.toString())
        self.history_text.blockSignals(False)

    def save_settings(self):
        logging.debug("Save button clicked")
        self.accept()

    def clear_history(self):
        reply = QMessageBox.question(self, 'Clear History',
                                     "Are you sure you want to clear all browsing history?",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)

        if reply == QMessageBox.Yes:
            self.parent.browser_history.clear()
            self.update_history([])
            self.parent.settings.set('history', [])
            logging.debug("Browsing history cleared")
            QMessageBox.information(self, "History Cleared", "Your browsing history has been cleared.")
    def open_bookmark_manager(self):
        self.parent.open_bookmark_manager()
import sys

def exception_hook(exctype, value, traceback):
    logging.error("Uncaught exception", exc_info=(exctype, value, traceback))
    sys.__excepthook__(exctype, value, traceback)


if __name__ == '__main__':
    app = QApplication(sys.argv)
    with open('style.qss', 'r') as f:
        app.setStyleSheet(f.read())
    sys.excepthook = exception_hook
    browser = Browser()
    browser.show()
    sys.exit(app.exec_())
    #old
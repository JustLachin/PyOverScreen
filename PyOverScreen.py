import sys
import os
import json
import time
import ctypes
from ctypes import wintypes
from pathlib import Path
from tempfile import TemporaryDirectory
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QLabel, QLineEdit, QPushButton, 
                             QCheckBox, QSlider, QGroupBox, QFormLayout, QSpinBox,
                             QFrame, QSizePolicy, QListWidget, QListWidgetItem,
                             QInputDialog, QMessageBox, QFileDialog, QComboBox,
                             QTabWidget, QTableWidget, QTableWidgetItem, QHeaderView)
from PySide6.QtCore import Qt, QUrl, QPoint, QRect, QSize, QSettings, Signal, QSignalBlocker, QTimer
from PySide6.QtGui import QIcon, QFont, QFontDatabase, QColor, QPalette, QMouseEvent
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEngineSettings
from PySide6.QtMultimedia import QSoundEffect, QMediaPlayer, QAudioOutput
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtGui import QIcon, QFont, QFontDatabase, QColor, QPalette, QMouseEvent, QDesktopServices, QMovie

ASSET_ROOT = Path(__file__).resolve().parent
WINDOWS = sys.platform == "win32"
LINUX = sys.platform.startswith("linux")

if LINUX:
    from x11_windows import connect_x11


class ResizeHandle(QFrame):
    """A widget in the admin panel to resize the overlay by dragging."""
    resized = Signal(QPoint)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(100, 100)
        self.setFrameShape(QFrame.StyledPanel)
        self.setStyleSheet("""
            ResizeHandle {
                background-color: #333;
                border: 2px dashed #555;
                border-radius: 10px;
            }
            ResizeHandle:hover {
                background-color: #444;
                border-color: #0078d4;
            }
        """)
        
        layout = QVBoxLayout(self)
        label = QLabel("DRAG TO\nRESIZE")
        label.setAlignment(Qt.AlignCenter)
        label.setStyleSheet("color: #aaa; font-weight: bold; font-size: 8pt;")
        layout.addWidget(label)
        
        self.dragging = False
        self.last_pos = QPoint()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.dragging = True
            self.last_pos = event.globalPosition().toPoint()

    def mouseMoveEvent(self, event):
        if self.dragging:
            current_pos = event.globalPosition().toPoint()
            delta = current_pos - self.last_pos
            self.resized.emit(delta)
            self.last_pos = current_pos

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.dragging = False

    def paintEvent(self, event):
        """Standard paint event to prevent 'Painter not active' errors."""
        super().paintEvent(event)

class MoveHandle(QFrame):
    """A widget in the admin panel to move the overlay by dragging."""
    moved = Signal(QPoint)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(100, 100)
        self.setFrameShape(QFrame.StyledPanel)
        self.setStyleSheet("""
            MoveHandle {
                background-color: #333;
                border: 2px dashed #555;
                border-radius: 10px;
            }
            MoveHandle:hover {
                background-color: #444;
                border-color: #0078d4;
            }
        """)
        
        layout = QVBoxLayout(self)
        label = QLabel("DRAG TO\nMOVE")
        label.setAlignment(Qt.AlignCenter)
        label.setStyleSheet("color: #aaa; font-weight: bold; font-size: 8pt;")
        layout.addWidget(label)
        
        self.dragging = False
        self.last_pos = QPoint()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.dragging = True
            self.last_pos = event.globalPosition().toPoint()

    def mouseMoveEvent(self, event):
        if self.dragging:
            current_pos = event.globalPosition().toPoint()
            delta = current_pos - self.last_pos
            self.moved.emit(delta)
            self.last_pos = current_pos

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.dragging = False

    def paintEvent(self, event):
        """Standard paint event to prevent 'Painter not active' errors."""
        super().paintEvent(event)

class OverlayWindow(QMainWindow):
    def __init__(self, overlay_id, name="New Overlay", x11=None):
        super().__init__()
        self.overlay_id = overlay_id
        self.name = name
        self.setWindowTitle(f"PyOverScreen - {name}")
        
        self.loop_media = True
        self.volume = 50
        self.zoom_factor = 1.0
        self.current_source = ""
        self.target_hwnd = None
        self.target_title = None
        self.target_pid = None
        self.x11 = x11
        self.x11_target_id = None
        self.x11_target = None
        self.profile_position = QPoint(100, 100)
        
        # Window settings
        self.setWindowFlags(
            Qt.Window |
            Qt.FramelessWindowHint | 
            Qt.WindowStaysOnTopHint |
            Qt.Tool | # Helps staying above fullscreen apps
            Qt.WindowTransparentForInput
        )
        
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_NoSystemBackground)
        
        # Browser setup
        self.browser = QWebEngineView()
        self.browser.page().setBackgroundColor(Qt.transparent)
        
        # Native Video Player (Browser-independent)
        self.video_player = QMediaPlayer()
        self.video_output = QVideoWidget()
        self.audio_output = QAudioOutput()
        self.video_player.setVideoOutput(self.video_output)
        self.video_player.setAudioOutput(self.audio_output)
        self.video_player.mediaStatusChanged.connect(self.on_media_status_changed)
        
        # Native GIF/Image Player
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setStyleSheet("background: transparent;")
        self.gif_movie = None

        # Container to switch between Browser, Video, and Image
        self.stack = QWidget()
        self.stack_layout = QVBoxLayout(self.stack)
        self.stack_layout.setContentsMargins(0,0,0,0)
        self.stack_layout.addWidget(self.browser)
        self.stack_layout.addWidget(self.video_output)
        self.stack_layout.addWidget(self.image_label)
        
        self.video_output.hide()
        self.image_label.hide()
        
        self.setCentralWidget(self.stack)
        
        # Windows-specific TopMost reinforcement
        self.topmost_timer = QTimer(self)
        self.topmost_timer.timeout.connect(self.ensure_topmost)
        if WINDOWS or self.x11:
            self.topmost_timer.start(200)
        
    def on_media_status_changed(self, status):
        if status == QMediaPlayer.EndOfMedia and self.loop_media:
            self.video_player.setPosition(0)
            self.video_player.play()

    def on_gif_frame_changed(self, frame_no):
        if not self.gif_movie: return
        # If we reached the last frame and loop is disabled, stop it
        if not self.loop_media:
            if frame_no >= self.gif_movie.frameCount() - 1:
                self.gif_movie.stop()

    def showEvent(self, event):
        super().showEvent(event)
        self.ensure_topmost()

    def paintEvent(self, event):
        """Fix QPainter errors for translucent windows."""
        from PySide6.QtGui import QPainter
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        # We don't need to draw anything, just keep the painter active
        painter.end()

    def ensure_topmost(self):
        """Force the window to be at the very top of the Z-order using WinAPI."""
        if WINDOWS:
            try:
                hwnd = self.winId()
                
                # 1. Recovery: If HWND is invalid, try to find it by title and PID
                if self.target_hwnd and not ctypes.windll.user32.IsWindow(self.target_hwnd):
                    self.recover_target_hwnd()

                # SWP_NOSIZE=1, SWP_NOMOVE=2, SWP_NOACTIVATE=16, SWP_SHOWWINDOW=64, SWP_NOOWNERZORDER=512
                flags = 0x0001 | 0x0002 | 0x0010 | 0x0040 | 0x0200
                
                # 2. Aggressive SetWindowPos
                # HWND_TOPMOST = -1
                ctypes.windll.user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, flags)
                
                # Style Flags Enforcement
                current_style = ctypes.windll.user32.GetWindowLongW(hwnd, -20) # GWL_EXSTYLE
                # WS_EX_TOPMOST=0x8, WS_EX_TOOLWINDOW=0x80, WS_EX_LAYERED=0x80000, WS_EX_NOACTIVATE=0x08000000
                target_style = current_style | 0x00000008 | 0x00000080 | 0x00080000 | 0x08000000
                
                if self.windowFlags() & Qt.WindowTransparentForInput:
                    target_style |= 0x00000020 # WS_EX_TRANSPARENT
                else:
                    target_style &= ~0x00000020
                
                if current_style != target_style:
                    ctypes.windll.user32.SetWindowLongW(hwnd, -20, target_style)
                
                # 3. Specific Target Loyalty
                if self.target_hwnd and ctypes.windll.user32.IsWindow(self.target_hwnd):
                    foreground_hwnd = ctypes.windll.user32.GetForegroundWindow()
                    
                    # If target or overlay is foreground (though overlay shouldn't be), force topmost
                    if foreground_hwnd == self.target_hwnd or foreground_hwnd == hwnd:
                        # HWND_TOPMOST = -1
                        ctypes.windll.user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, flags)
                        # Also try HWND_TOP (0) to ensure it's above other topmost windows
                        ctypes.windll.user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, flags)
                        
                        # Extra Force: BringWindowToTop
                        ctypes.windll.user32.BringWindowToTop(hwnd)
                        
                        # ADVANCED: Thread Input Attachment (Forces Z-order sync)
                        try:
                            target_thread = ctypes.windll.user32.GetWindowThreadProcessId(self.target_hwnd, None)
                            current_thread = ctypes.windll.kernel32.GetCurrentThreadId()
                            if target_thread != current_thread:
                                ctypes.windll.user32.AttachThreadInput(current_thread, target_thread, True)
                                ctypes.windll.user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, flags)
                                ctypes.windll.user32.AttachThreadInput(current_thread, target_thread, False)
                        except: pass
                
                # Dynamic Timer: Faster if target is active
                if self.target_hwnd and ctypes.windll.user32.GetForegroundWindow() == self.target_hwnd:
                    if self.topmost_timer.interval() != 100:
                        self.topmost_timer.setInterval(100)
                else:
                    if self.topmost_timer.interval() != 200:
                        self.topmost_timer.setInterval(200)

                # Ensure visibility
                if not self.isVisible() or self.isMinimized():
                    self.show()
                    self.raise_()
                    
            except Exception as e:
                print(f"Topmost error: {e}")

        elif self.x11 and self.x11_target and self.isVisible():
            if self.x11.should_raise(int(self.winId()), self.x11_target_id, self.x11_target):
                self.raise_()

    def recover_target_hwnd(self):
        """Try to re-find the target window handle if it was lost."""
        if not self.target_title: return
        
        def enum_handler(hwnd, lparam):
            if ctypes.windll.user32.IsWindowVisible(hwnd):
                length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
                if length > 0:
                    buff = ctypes.create_unicode_buffer(length + 1)
                    ctypes.windll.user32.GetWindowTextW(hwnd, buff, length + 1)
                    title = buff.value
                    if title == self.target_title:
                        pid = ctypes.wintypes.DWORD()
                        ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                        if not self.target_pid or pid.value == self.target_pid:
                            self.target_hwnd = hwnd
                            return False # Stop enumerating
            return True

        ENUM_WINDOWS_PROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        ctypes.windll.user32.EnumWindows(ENUM_WINDOWS_PROC(enum_handler), 0)

    def set_interactive(self, interactive):
        """Toggle between interactive (mouse clicks) and click-through."""
        geometry = self.geometry()
        flags = self.windowFlags()
        if interactive:
            flags &= ~Qt.WindowTransparentForInput
            self.setWindowFlags(flags)
        else:
            flags |= Qt.WindowTransparentForInput
            self.setWindowFlags(flags)
        
        # After changing flags, we must re-show and re-apply attributes
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setGeometry(geometry)
        self.show()
        self.ensure_topmost()

    def load_url(self, url_str):
        self.current_source = url_str
        # Stop existing players
        self.video_player.stop()
        if self.gif_movie:
            self.gif_movie.stop()
        self.image_label.clear()
        
        if not url_str.strip():
            self.video_output.hide()
            self.image_label.hide()
            self.browser.show()
            self.browser.setHtml("")
            return
            
        # Clean URL/Path
        url_str = url_str.strip()
        
        # Check if it's a local file
        is_local = False
        potential_path = url_str
        url = QUrl(url_str)
        if url.isLocalFile():
            potential_path = url.toLocalFile()
            is_local = True
        else:
            potential_path = os.path.expanduser(url_str)
            is_local = os.path.isfile(potential_path)
        if is_local:
            potential_path = os.path.abspath(potential_path)

        if is_local:
            file_url = QUrl.fromLocalFile(potential_path)
            ext = potential_path.lower().split('.')[-1]
            
            if ext in ['mp4', 'webm', 'ogg', 'mov', 'mkv', 'avi']:
                # NATIVE VIDEO PLAYER (NO HTML)
                self.browser.hide()
                self.image_label.hide()
                self.video_output.show()
                
                self.video_player.setSource(file_url)
                self.audio_output.setVolume(self.volume / 100.0)
                self.video_player.play()
                
            elif ext == 'gif':
                # NATIVE GIF PLAYER
                self.browser.hide()
                self.video_output.hide()
                self.image_label.show()
                
                self.gif_movie = QMovie(potential_path)
                self.image_label.setMovie(self.gif_movie)
                
                # Connect frame change to handle non-looping GIFs
                self.gif_movie.frameChanged.connect(self.on_gif_frame_changed)
                self.gif_movie.start()
                
            elif ext in ['png', 'jpg', 'jpeg', 'webp']:
                # NATIVE IMAGE PLAYER
                self.browser.hide()
                self.video_output.hide()
                self.image_label.show()
                
                pixmap = QIcon(potential_path).pixmap(self.size())
                self.image_label.setPixmap(pixmap)
                self.image_label.setScaledContents(True)
            else:
                self.browser.show()
                self.video_output.hide()
                self.image_label.hide()
                self.browser.setUrl(file_url)
        else:
            self.browser.show()
            self.video_output.hide()
            self.image_label.hide()
            if not url_str.startswith(('http://', 'https://', 'file://')):
                url_str = 'https://' + url_str
            self.browser.setUrl(QUrl(url_str))
            
    def update_zoom(self, factor):
        self.zoom_factor = factor
        self.browser.setZoomFactor(factor)
        
    def set_media_settings(self, loop, volume):
        self.loop_media = loop
        self.volume = volume
        
        # Native video updates
        self.audio_output.setVolume(volume / 100.0)
        
        # GIF loop updates
        if self.gif_movie:
            if loop:
                try: self.gif_movie.finished.connect(self.gif_movie.start)
                except: pass
            else:
                try: self.gif_movie.finished.disconnect(self.gif_movie.start)
                except: pass

        # Browser updates (for chat)
        script = f"""
        var v = document.getElementById('v'); 
        if(v) {{ 
            v.loop = {'true' if loop else 'false'}; 
            v.volume = {volume / 100.0}; 
        }}
        """
        self.browser.page().runJavaScript(script)

class AdminPanel(QMainWindow):
    def __init__(self, settings=None):
        super().__init__()
        self.settings = settings if settings is not None else QSettings("PyOverScreen", "Config", self)
        platform = QApplication.platformName()
        self.wayland = LINUX and platform.startswith("wayland")
        self.x11 = connect_x11() if LINUX and platform == "xcb" else None
        self.setWindowTitle("PyOverScreen - Admin Panel")
        self.setMinimumSize(800, 650)
        
        self.overlays = {} # overlay_id -> OverlayWindow
        self.current_overlay_id = None
        self.is_loading = False
        
        # Load assets
        self.load_fonts()
        self.setup_sounds()
        
        self.init_ui()
        self.load_all_settings()

    def load_fonts(self):
        font_dir = ASSET_ROOT / "Fonts"
        # Explicitly load all fonts in the Fonts directory
        if os.path.exists(font_dir):
            for font_file in os.listdir(font_dir):
                if font_file.endswith(('.ttf', '.otf', '.ttc')):
                    path = os.path.join(font_dir, font_file)
                    QFontDatabase.addApplicationFont(path)
        
        # Prefer Segoe UI Variable or Segoe UI from the Fonts folder
        preferred = ["Segoe UI Variable Text", "Segoe UI", "Calibri", "Arial"]
        for p in preferred:
            if p in QFontDatabase.families():
                self.custom_font = QFont(p, 10)
                QApplication.setFont(self.custom_font)
                return
        
        self.custom_font = QFont("Arial", 10)
        QApplication.setFont(self.custom_font)

    def setup_sounds(self):
        self.sounds = {}
        sound_dir = ASSET_ROOT / "src" / "SND01-sine-sound-pack"
        sound_files = {
            "click": "button.wav",
            "notify": "notification.wav",
            "select": "select.wav",
            "reset": "caution.wav",
            "delete": "disabled.wav",
            "add": "celebration.wav"
        }
        for key, name in sound_files.items():
            path = os.path.join(sound_dir, name)
            if os.path.exists(path):
                effect = QSoundEffect()
                effect.setSource(QUrl.fromLocalFile(path))
                self.sounds[key] = effect

    def play_sound(self, name):
        if name in self.sounds:
            self.sounds[name].play()

    def get_icon(self, name):
        path = ASSET_ROOT / "src" / "regular-free-icon-svgs" / f"{name}.svg"
        if os.path.exists(path):
            return QIcon(str(path))
        return QIcon()

    def init_ui(self):
        # Topmost reinforcement timer (every 2 seconds)
        self.tm_timer = QTimer(self)
        self.tm_timer.timeout.connect(self.ensure_all_topmost)
        self.tm_timer.start(2000)

        self.setStyleSheet("""
            QMainWindow { background-color: #1e1e1e; color: #ffffff; }
            QGroupBox { border: 1px solid #333; border-radius: 8px; margin-top: 15px; font-weight: bold; color: #0078d4; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 3px; }
            QLabel { color: #ccc; }
            QLineEdit { background-color: #2d2d2d; border: 1px solid #3d3d3d; border-radius: 4px; padding: 5px; color: white; }
            QLineEdit:focus { border: 1px solid #0078d4; }
            QPushButton { background-color: #333; border: none; border-radius: 4px; padding: 8px 15px; color: white; min-width: 80px; }
            QPushButton:hover { background-color: #444; }
            QPushButton#applyBtn { background-color: #0078d4; }
            /* Farklı Renklerde +Add Butonları */
            QPushButton#addBtnSidebarTop { background-color: #e67e22; font-weight: bold; font-size: 11pt; border: 2px solid white; border-radius: 5px; }
            QPushButton#addBtnSidebarBottom { background-color: #9b59b6; font-weight: bold; font-size: 11pt; border: 2px solid white; border-radius: 5px; min-height: 45px; }
            QPushButton#addBtnTabCorner { background-color: #1abc9c; font-weight: bold; font-size: 10pt; border: 1px solid white; padding: 5px 15px; margin-right: 10px; }
            
            QPushButton#deleteBtn { background-color: #dc3545; }
            QPushButton#mediaBtn { background-color: #555; font-size: 9pt; min-width: 100px; }
            QPushButton#mediaBtn:hover { background-color: #666; }
            QSpinBox { background-color: #2d2d2d; border: 1px solid #3d3d3d; border-radius: 4px; padding: 3px; color: white; }
            QCheckBox { spacing: 10px; }
            QSlider::handle:horizontal { background: #0078d4; width: 18px; border-radius: 9px; margin: -5px 0; }
            QListWidget { background-color: #252526; border: 1px solid #333; border-radius: 4px; color: white; outline: none; }
            QListWidget::item { padding: 10px; border-bottom: 1px solid #333; }
            QListWidget::item:selected { background-color: #37373d; color: #0078d4; font-weight: bold; }
        """)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Tabs for Admin Panel
        self.tabs = QTabWidget()
        
        # ADD BUTTON IN TAB CORNER (RED BOX 1)
        self.btn_add_tab_corner = QPushButton("+ ADD NEW OVERLAY")
        self.btn_add_tab_corner.setObjectName("addBtnTabCorner")
        self.btn_add_tab_corner.clicked.connect(lambda: self.add_new_overlay())
        self.tabs.setCornerWidget(self.btn_add_tab_corner, Qt.TopRightCorner)
        
        self.tabs.setStyleSheet("""
            QTabWidget::pane { border: none; background: #1e1e1e; }
            QTabBar::tab { 
                background: #252526; color: #aaa; padding: 12px 30px; 
                font-weight: bold; border-right: 1px solid #333;
            }
            QTabBar::tab:selected { background: #1e1e1e; color: #0078d4; border-bottom: 2px solid #0078d4; }
            QTabBar::tab:hover { background: #2d2d2d; }
        """)

        # --- Tab 1: Control Center ---
        self.control_tab = QWidget()
        control_layout = QHBoxLayout(self.control_tab)
        control_layout.setContentsMargins(0,0,0,0)
        control_layout.setSpacing(0)

        # --- Sidebar (Left) ---
        sidebar = QFrame()
        sidebar.setFixedWidth(280)
        sidebar.setStyleSheet("background-color: #252526; border-right: 1px solid #333;")
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setSpacing(10)

        # Logo/Title
        logo_label = QLabel("PyOverScreen")
        logo_label.setStyleSheet("font-size: 20pt; font-weight: bold; color: #0078d4; margin-bottom: 5px;")
        logo_label.setAlignment(Qt.AlignCenter)
        sidebar_layout.addWidget(logo_label)

        # Overlay List
        list_header = QHBoxLayout()
        list_header.addWidget(QLabel("OVERLAYS"))
        list_header.addStretch()
        self.btn_add = QPushButton("+ ADD")
        self.btn_add.setObjectName("addBtnSidebarTop")
        self.btn_add.setFixedSize(90, 35)
        self.btn_add.clicked.connect(lambda: self.add_new_overlay())
        list_header.addWidget(self.btn_add)
        sidebar_layout.addLayout(list_header)

        self.overlay_list = QListWidget()
        self.overlay_list.setObjectName("overlayList")
        self.overlay_list.currentRowChanged.connect(self.on_overlay_selected)
        self.overlay_list.setDragDropMode(QListWidget.InternalMove)
        self.overlay_list.model().rowsMoved.connect(self.on_order_changed)
        sidebar_layout.addWidget(self.overlay_list)

        # Management Buttons
        mgmt_row = QHBoxLayout()
        self.btn_delete = QPushButton("Delete")
        self.btn_delete.setIcon(self.get_icon("trash"))
        self.btn_delete.clicked.connect(self.delete_current_overlay)
        self.btn_duplicate = QPushButton("Clone")
        self.btn_duplicate.setIcon(self.get_icon("copy"))
        self.btn_duplicate.clicked.connect(self.duplicate_current_overlay)
        mgmt_row.addWidget(self.btn_delete)
        mgmt_row.addWidget(self.btn_duplicate)
        sidebar_layout.addLayout(mgmt_row)

        order_row = QHBoxLayout()
        self.btn_up = QPushButton("Up")
        self.btn_up.setIcon(self.get_icon("arrow-up"))
        self.btn_up.clicked.connect(lambda: self.move_item(-1))
        self.btn_down = QPushButton("Down")
        self.btn_down.setIcon(self.get_icon("arrow-down"))
        self.btn_down.clicked.connect(lambda: self.move_item(1))
        order_row.addWidget(self.btn_up)
        order_row.addWidget(self.btn_down)
        sidebar_layout.addLayout(order_row)
        
        sidebar_layout.addStretch()

        # GitHub Promotion Section
        promo_group = QFrame()
        promo_group.setStyleSheet("""
            QFrame {
                background-color: #2d2d2d;
                border: 2px solid #0078d4;
                border-radius: 10px;
                margin: 5px;
            }
        """)
        promo_layout = QVBoxLayout(promo_group)
        
        promo_label = QLabel("NEW UPDATES!")
        promo_label.setStyleSheet("color: #0078d4; font-weight: bold; border: none; margin: 0;")
        promo_label.setAlignment(Qt.AlignCenter)
        promo_layout.addWidget(promo_label)

        btn_click_me = QPushButton("🚀 CLICK ME!")
        btn_click_me.setStyleSheet("""
            QPushButton {
                background-color: #0078d4;
                color: white;
                font-weight: bold;
                font-size: 11pt;
                padding: 10px;
                border-radius: 5px;
                min-width: 0;
            }
            QPushButton:hover {
                background-color: #0086ed;
            }
        """)
        btn_click_me.clicked.connect(lambda: QDesktopServices.openUrl(QUrl("https://github.com/JustLachin/PyOverScreen")))
        promo_layout.addWidget(btn_click_me)
        
        github_label = QLabel("Download Latest Version")
        github_label.setStyleSheet("font-size: 8pt; color: #888; border: none;")
        github_label.setAlignment(Qt.AlignCenter)
        promo_layout.addWidget(github_label)

        sidebar_layout.addWidget(promo_group)

        # FOURTH ADD BUTTON - SIDEBAR BOTTOM (RED BOX 3)
        self.btn_add_sidebar_bottom = QPushButton("+ ADD NEW OVERLAY")
        self.btn_add_sidebar_bottom.setObjectName("addBtnSidebarBottom")
        self.btn_add_sidebar_bottom.clicked.connect(lambda: self.add_new_overlay())
        sidebar_layout.addWidget(self.btn_add_sidebar_bottom)

        control_layout.addWidget(sidebar)

        # --- Content Area (Right) ---
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setSpacing(15)

        # Header
        header_layout = QHBoxLayout()
        icon_label = QLabel()
        icon_label.setPixmap(self.get_icon("monitor").pixmap(32, 32))
        self.title_label = QLabel("PyOverScreen - Control Panel")
        self.title_label.setStyleSheet("font-size: 18pt; font-weight: bold; color: #0078d4;")
        header_layout.addWidget(icon_label)
        header_layout.addWidget(self.title_label)
        header_layout.addStretch()
        content_layout.addLayout(header_layout)

        # Settings Group
        self.config_group = QGroupBox("Overlay Configuration")
        self.config_group.setEnabled(False)
        config_layout = QVBoxLayout()

        # URL
        url_layout = QVBoxLayout()
        url_header = QHBoxLayout()
        url_header.addWidget(QLabel("Source URL / Media Path:"))
        url_header.addStretch()
        self.btn_select_media = QPushButton("Select Media")
        self.btn_select_media.setObjectName("mediaBtn")
        self.btn_select_media.setFixedWidth(120)
        self.btn_select_media.setIcon(self.get_icon("image"))
        self.btn_select_media.clicked.connect(self.select_media_file)
        url_header.addWidget(self.btn_select_media)
        url_layout.addLayout(url_header)
        
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("Enter Chat Overlay URL (YouTube/Kick/etc.) or select a file")
        url_layout.addWidget(self.url_input)
        config_layout.addLayout(url_layout)

        # Layout Controls
        layout_row = QHBoxLayout()
        form_layout = QFormLayout()
        self.spin_x = QSpinBox()
        self.spin_x.setRange(-5000, 10000)
        self.spin_y = QSpinBox()
        self.spin_y.setRange(-5000, 10000)
        self.spin_w = QSpinBox()
        self.spin_w.setRange(50, 5000)
        self.spin_h = QSpinBox()
        self.spin_h.setRange(50, 5000)
        
        form_layout.addRow("Pos X:", self.spin_x)
        form_layout.addRow("Pos Y:", self.spin_y)
        form_layout.addRow("Width:", self.spin_w)
        form_layout.addRow("Height:", self.spin_h)
        layout_row.addLayout(form_layout)

        # Handles
        handles_layout = QVBoxLayout()
        handles_layout.setSpacing(10)
        self.move_handle = MoveHandle()
        self.move_handle.moved.connect(self.on_handle_moved)
        self.resize_handle = ResizeHandle()
        self.resize_handle.resized.connect(self.on_handle_resized)
        handles_layout.addWidget(self.move_handle)
        handles_layout.addWidget(self.resize_handle)
        layout_row.addLayout(handles_layout)
        config_layout.addLayout(layout_row)

        # Display Settings
        display_layout = QVBoxLayout()
        
        # Zoom / Scale
        zoom_row = QHBoxLayout()
        zoom_row.addWidget(QLabel("Scale (Zoom):"))
        self.slider_zoom = QSlider(Qt.Horizontal)
        self.slider_zoom.setRange(25, 300)
        self.slider_zoom.setValue(100)
        self.slider_zoom.valueChanged.connect(self.on_zoom_changed)
        zoom_row.addWidget(self.slider_zoom)
        self.lbl_zoom = QLabel("100%")
        zoom_row.addWidget(self.lbl_zoom)
        display_layout.addLayout(zoom_row)
        
        # Opacity
        opacity_row = QHBoxLayout()
        opacity_row.addWidget(QLabel("Opacity:"))
        self.slider_opacity = QSlider(Qt.Horizontal)
        self.slider_opacity.setRange(5, 100)
        self.slider_opacity.valueChanged.connect(self.on_opacity_changed)
        opacity_row.addWidget(self.slider_opacity)
        display_layout.addLayout(opacity_row)
        
        # Game Target (New Feature)
        game_group = QGroupBox("Target Game (Force Visibility)")
        game_layout = QVBoxLayout()
        
        game_info = QLabel("If overlay is hidden in Fullscreen, select the game window below:")
        game_info.setStyleSheet("font-size: 8pt; color: #888;")
        game_layout.addWidget(game_info)
        
        game_row = QHBoxLayout()
        self.combo_games = QComboBox()
        self.combo_games.addItem("None (Standard TopMost)", 0)
        self.btn_refresh_games = QPushButton()
        self.btn_refresh_games.setIcon(self.get_icon("rotate-right"))
        self.btn_refresh_games.setFixedWidth(30)
        self.btn_refresh_games.clicked.connect(self.refresh_window_list)
        
        game_row.addWidget(self.combo_games, 1)
        game_row.addWidget(self.btn_refresh_games)
        game_layout.addLayout(game_row)
        
        self.combo_games.currentIndexChanged.connect(self.on_game_target_changed)
        game_group.setLayout(game_layout)
        display_layout.addWidget(game_group)
        game_group.setVisible(WINDOWS or self.x11 is not None)
        
        # Interactivity Lock
        self.check_lock = QCheckBox("Lock Overlay (Non-interactive / Click-through)")
        self.check_lock.setChecked(True)
        self.check_lock.toggled.connect(self.on_lock_changed)
        display_layout.addWidget(self.check_lock)
        
        if self.wayland:
            for control in (self.spin_x, self.spin_y, self.move_handle):
                control.setEnabled(False)
            notice = QLabel(
                "Wayland controls overlay position and stacking. "
                "Use --x11 for XWayland window targeting."
            )
            notice.setWordWrap(True)
            display_layout.addWidget(notice)

        config_layout.addLayout(display_layout)
        
        # Media Settings
        media_group = QGroupBox("Media Settings (GIF/Video)")
        media_layout = QVBoxLayout()
        
        self.check_loop = QCheckBox("Loop Media")
        self.check_loop.setChecked(True)
        self.check_loop.stateChanged.connect(self.on_media_settings_changed)
        media_layout.addWidget(self.check_loop)
        
        vol_row = QHBoxLayout()
        vol_row.addWidget(QLabel("Volume:"))
        self.slider_volume = QSlider(Qt.Horizontal)
        self.slider_volume.setRange(0, 100)
        self.slider_volume.setValue(50)
        self.slider_volume.valueChanged.connect(self.on_media_settings_changed)
        vol_row.addWidget(self.slider_volume)
        media_layout.addLayout(vol_row)
        
        media_group.setLayout(media_layout)
        config_layout.addWidget(media_group)

        # Profile Settings
        profile_group = QGroupBox("Profile Management")
        profile_layout = QHBoxLayout()
        self.btn_load_profile = QPushButton("Load Profile")
        self.btn_save_profile_as = QPushButton("Save Profile As")
        self.btn_load_profile.clicked.connect(self.load_profile_from_file)
        self.btn_save_profile_as.clicked.connect(self.save_profile_to_file)
        profile_layout.addWidget(self.btn_load_profile)
        profile_layout.addWidget(self.btn_save_profile_as)
        profile_group.setLayout(profile_layout)
        config_layout.addWidget(profile_group)

        # Buttons
        btn_layout = QHBoxLayout()
        self.btn_apply = QPushButton("Apply & Save")
        self.btn_apply.setObjectName("applyBtn")
        self.btn_apply.setIcon(self.get_icon("check"))
        self.btn_apply.clicked.connect(self.save_current_settings)
        
        self.btn_rename = QPushButton("Rename")
        self.btn_rename.setIcon(self.get_icon("pencil"))
        self.btn_rename.clicked.connect(self.rename_current_overlay)
        
        btn_layout.addWidget(self.btn_apply)
        btn_layout.addWidget(self.btn_rename)
        config_layout.addLayout(btn_layout)

        self.config_group.setLayout(config_layout)
        content_layout.addWidget(self.config_group)

        # Footer
        footer_layout = QVBoxLayout()
        
        # Disclaimer
        disclaimer = QLabel("WARNING: Use at your own risk. We are not responsible for any bans or issues in games/software.")
        disclaimer.setAlignment(Qt.AlignCenter)
        disclaimer.setStyleSheet("color: #d9534f; font-size: 7pt; font-weight: bold; margin-top: 5px;")
        footer_layout.addWidget(disclaimer)
        
        # GitHub Link
        github_link = QLabel('<a href="https://github.com/JustLachin/PyOverScreen" style="color: #0078d4; text-decoration: none;">GitHub: JustLachin/PyOverScreen</a>')
        github_link.setAlignment(Qt.AlignCenter)
        github_link.setOpenExternalLinks(True)
        github_link.setStyleSheet("font-size: 9pt; margin-bottom: 5px;")
        footer_layout.addWidget(github_link)

        content_layout.addLayout(footer_layout)
        control_layout.addWidget(content)

        # --- Tab 2: Target Center ---
        self.target_tab = QWidget()
        target_tab_layout = QVBoxLayout(self.target_tab)
        
        target_header = QHBoxLayout()
        target_title = QLabel("TARGET CENTER")
        target_title.setStyleSheet("font-size: 20pt; font-weight: bold; color: #0078d4;")
        target_header.addWidget(target_title)
        target_header.addStretch()
        
        self.btn_refresh_target_center = QPushButton("Refresh Windows")
        self.btn_refresh_target_center.setIcon(self.get_icon("rotate-right"))
        self.btn_refresh_target_center.clicked.connect(self.refresh_target_center)
        target_header.addWidget(self.btn_refresh_target_center)
        target_tab_layout.addLayout(target_header)
        
        target_info = QLabel("Double-click a window to set it as the target for the selected overlay.")
        target_info.setStyleSheet("color: #888; font-style: italic;")
        target_tab_layout.addWidget(target_info)
        
        self.process_table = QTableWidget(0, 3)
        self.process_table.setHorizontalHeaderLabels(["Icon", "Window Title", "Window ID"])
        self.process_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.process_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.process_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.process_table.doubleClicked.connect(self.on_process_double_clicked)
        target_tab_layout.addWidget(self.process_table)

        # Add tabs to main layout
        self.tabs.addTab(self.control_tab, "CONTROL CENTER")
        if WINDOWS or self.x11:
            self.tabs.addTab(self.target_tab, "TARGET CENTER")
        main_layout.addWidget(self.tabs)

        # Real-time sync connections
        for sb in [self.spin_x, self.spin_y, self.spin_w, self.spin_h]:
            sb.valueChanged.connect(self.sync_overlay_geometry)

        self.setWindowIcon(self.get_icon("monitor"))

    # --- Overlay Management ---

    def add_new_overlay(self, name=None, config=None):
        # name can be bool (False) if called directly from clicked signal without lambda
        if name is None or isinstance(name, bool):
            name, ok = QInputDialog.getText(self, "Add Overlay", "Overlay Name:")
            if not ok or not name:
                return
        
        overlay_id = str(hash(name + str(time.time_ns()))) if config is None else config.get('id')
        
        overlay = OverlayWindow(overlay_id, name, self.x11)
        self.overlays[overlay_id] = overlay
        
        item = QListWidgetItem(name)
        item.setData(Qt.UserRole, overlay_id)
        self.overlay_list.addItem(item)
        
        if config:
            self.apply_config_to_overlay(overlay, config)
        else:
            # Default new config
            overlay.setGeometry(100, 100, 400, 600)
            overlay.show()
        
        self.play_sound("add")
        self.overlay_list.setCurrentItem(item)

    def duplicate_current_overlay(self):
        """Clone the currently selected overlay with all its settings."""
        item = self.overlay_list.currentItem()
        if not item:
            return
        
        source_id = item.data(Qt.UserRole)
        source_overlay = self.overlays[source_id]
        
        # Create a new config based on the current state of the source overlay
        geom = source_overlay.geometry()
        pos = source_overlay.profile_position if self.wayland else geom.topLeft()
        config = {
            'id': str(hash(item.text() + " (Clone)" + str(time.time_ns()))),
            'name': item.text() + " (Clone)",
            'url': source_overlay.current_source,
            'x': geom.x() + 20, # Offset slightly
            'y': geom.y() + 20,
            'w': geom.width(),
            'h': geom.height(),
            'opacity': int(source_overlay.windowOpacity() * 100),
            'zoom': source_overlay.zoom_factor,
            'locked': bool(source_overlay.windowFlags() & Qt.WindowTransparentForInput),
            'target_hwnd': source_overlay.target_hwnd,
            'target_title': source_overlay.target_title,
            'target_pid': source_overlay.target_pid,
            'x11_target': source_overlay.x11_target,
            'loop': source_overlay.loop_media,
            'volume': source_overlay.volume
        }
        
        self.add_new_overlay(config['name'], config)
        self.save_all_settings()

    def delete_current_overlay(self):
        item = self.overlay_list.currentItem()
        if not item:
            return
        
        res = QMessageBox.question(self, "Delete Overlay", f"Are you sure you want to delete '{item.text()}'?", 
                                   QMessageBox.Yes | QMessageBox.No)
        if res == QMessageBox.No:
            return
            
        overlay_id = item.data(Qt.UserRole)
        overlay = self.overlays.pop(overlay_id)
        overlay.close()
        
        self.overlay_list.takeItem(self.overlay_list.row(item))
        self.play_sound("delete")
        self.save_all_settings()

    def rename_current_overlay(self):
        item = self.overlay_list.currentItem()
        if not item:
            return
        
        new_name, ok = QInputDialog.getText(self, "Rename Overlay", "New Name:", text=item.text())
        if ok and new_name:
            item.setText(new_name)
            overlay_id = item.data(Qt.UserRole)
            self.overlays[overlay_id].setWindowTitle(f"PyOverScreen - {new_name}")
            self.save_all_settings()

    def on_overlay_selected(self, index):
        if index < 0:
            self.config_group.setEnabled(False)
            self.current_overlay_id = None
            return
        
        self.is_loading = True
        item = self.overlay_list.item(index)
        self.current_overlay_id = item.data(Qt.UserRole)
        overlay = self.overlays[self.current_overlay_id]
        
        # Update UI fields from overlay state
        self.url_input.setText(overlay.current_source)
        geom = overlay.geometry()
        pos = overlay.profile_position if self.wayland else geom.topLeft()
        self.spin_x.setValue(pos.x())
        self.spin_y.setValue(pos.y())
        self.spin_w.setValue(geom.width())
        self.spin_h.setValue(geom.height())
        
        self.slider_opacity.setValue(int(overlay.windowOpacity() * 100))
        self.slider_zoom.setValue(int(overlay.zoom_factor * 100))
        self.lbl_zoom.setText(f"{int(overlay.zoom_factor * 100)}%")
        
        self.check_loop.setChecked(overlay.loop_media)
        self.slider_volume.setValue(overlay.volume)
        
        self.refresh_window_list()

        is_locked = bool(overlay.windowFlags() & Qt.WindowTransparentForInput)
        self.check_lock.setChecked(is_locked)
        
        self.config_group.setEnabled(True)
        self.play_sound("select")
        self.is_loading = False

    # --- Controls Sync ---

    def on_handle_moved(self, delta):
        if self.is_loading or not self.current_overlay_id: return
        self.spin_x.setValue(self.spin_x.value() + delta.x())
        self.spin_y.setValue(self.spin_y.value() + delta.y())

    def on_handle_resized(self, delta):
        if self.is_loading or not self.current_overlay_id: return
        self.spin_w.setValue(self.spin_w.value() + delta.x())
        self.spin_h.setValue(self.spin_h.value() + delta.y())

    def on_opacity_changed(self, value):
        if self.is_loading or not self.current_overlay_id: return
        self.overlays[self.current_overlay_id].setWindowOpacity(value / 100.0)

    def target_windows(self):
        if self.x11:
            windows = self.x11.list_windows()
        elif WINDOWS:
            windows = []

            def enum_handler(hwnd, lparam):
                if ctypes.windll.user32.IsWindowVisible(hwnd):
                    length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
                    if length > 0:
                        buff = ctypes.create_unicode_buffer(length + 1)
                        ctypes.windll.user32.GetWindowTextW(hwnd, buff, length + 1)
                        title = buff.value
                        if title and "PyOverScreen" not in title:
                            pid = wintypes.DWORD()
                            ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                            windows.append((title, hwnd, pid.value, ""))
                return True

            enum_proc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
            ctypes.windll.user32.EnumWindows(enum_proc(enum_handler), 0)
        else:
            windows = []

        return sorted(windows, key=lambda window: window[0].casefold())

    def refresh_window_list(self):
        if not self.current_overlay_id:
            return

        overlay = self.overlays[self.current_overlay_id]
        selected = 0
        with QSignalBlocker(self.combo_games):
            self.combo_games.clear()
            self.combo_games.addItem("None (Standard TopMost)")
            for window in self.target_windows():
                title, window_id, _, wm_class = window
                self.combo_games.addItem(title, window)
                if self.x11:
                    if window_id == overlay.x11_target_id or (
                        selected == 0 and overlay.x11_target == (title, wm_class)
                    ):
                        selected = self.combo_games.count() - 1
                elif window_id == overlay.target_hwnd:
                    selected = self.combo_games.count() - 1
            self.combo_games.setCurrentIndex(selected)

    def set_overlay_target(self, window):
        overlay = self.overlays[self.current_overlay_id]
        title, window_id, pid, wm_class = window or (None, None, None, None)
        if self.x11:
            overlay.x11_target_id = window_id
            overlay.x11_target = (title, wm_class) if window_id is not None else None
        elif WINDOWS:
            overlay.target_hwnd = window_id
            overlay.target_title = title
            overlay.target_pid = pid
        self.save_all_settings()

    def on_game_target_changed(self, index):
        if not self.is_loading and self.current_overlay_id:
            self.set_overlay_target(self.combo_games.itemData(index))

    def refresh_target_center(self):
        windows = self.target_windows()
        self.process_table.setRowCount(len(windows))
        for row, window in enumerate(windows):
            title, window_id, pid, _ = window
            icon = QTableWidgetItem()
            icon.setIcon(self.get_icon("monitor"))
            title_item = QTableWidgetItem(f"{title} (PID: {pid})" if pid else title)
            id_item = QTableWidgetItem(hex(window_id))
            id_item.setData(Qt.UserRole, window)
            self.process_table.setItem(row, 0, icon)
            self.process_table.setItem(row, 1, title_item)
            self.process_table.setItem(row, 2, id_item)

    def on_process_double_clicked(self, index):
        if not self.current_overlay_id:
            QMessageBox.warning(self, "Warning", "Select an overlay in Control Center first.")
            return
        item = self.process_table.item(index.row(), 2)
        if item:
            self.set_overlay_target(item.data(Qt.UserRole))
            self.tabs.setCurrentIndex(0)
            self.refresh_window_list()

    def on_lock_changed(self, locked):
        if not self.is_loading and self.current_overlay_id:
            self.overlays[self.current_overlay_id].set_interactive(not locked)
            self.save_all_settings()

    def on_zoom_changed(self, value):
        if self.is_loading or not self.current_overlay_id: return
        factor = value / 100.0
        self.overlays[self.current_overlay_id].update_zoom(factor)
        self.lbl_zoom.setText(f"{value}%")

    def on_media_settings_changed(self):
        if self.is_loading or not self.current_overlay_id: return
        loop = self.check_loop.isChecked()
        volume = self.slider_volume.value()
        self.overlays[self.current_overlay_id].set_media_settings(loop, volume)

    def select_media_file(self):
        if not self.current_overlay_id: return
        
        file_path, _ = QFileDialog.getOpenFileName(
            self, 
            "Select Media File", 
            "", 
            "Media Files (*.mp4 *.webm *.gif *.png *.jpg *.jpeg *.webp *.mkv *.mov);;All Files (*)"
        )
        
        if file_path:
            self.url_input.setText(file_path)
            # Trigger update immediately
            self.save_current_settings()

    def ensure_all_topmost(self):
        """Iterate through all active overlays and force them to top."""
        for overlay in self.overlays.values():
            if overlay.isVisible():
                overlay.ensure_topmost()

    def sync_overlay_geometry(self):
        if self.is_loading or not self.current_overlay_id: return
        overlay = self.overlays[self.current_overlay_id]
        size = QSize(self.spin_w.value(), self.spin_h.value())
        if self.wayland:
            overlay.resize(size)
        else:
            overlay.setGeometry(QRect(QPoint(self.spin_x.value(), self.spin_y.value()), size))

    def apply_config_to_overlay(self, overlay, config):
        overlay.profile_position = QPoint(config.get('x', 100), config.get('y', 100))
        size = QSize(config.get('w', 400), config.get('h', 600))
        if self.wayland:
            overlay.resize(size)
        else:
            overlay.setGeometry(QRect(overlay.profile_position, size))
        overlay.setWindowOpacity(config.get('opacity', 100) / 100.0)
        overlay.update_zoom(config.get('zoom', 1.0))
        overlay.set_media_settings(config.get('loop', True), config.get('volume', 50))
        overlay.set_interactive(not config.get('locked', True))
        
        # Target persistence
        overlay.target_hwnd = config.get('target_hwnd', None)
        overlay.target_title = config.get('target_title', None)
        overlay.target_pid = config.get('target_pid', None)
        identity = config.get('x11_target')
        if isinstance(identity, (list, tuple)) and len(identity) == 2:
            if all(isinstance(value, str) for value in identity):
                overlay.x11_target = tuple(identity)
        
        # Load URL after settings to ensure media settings are applied
        overlay.load_url(config.get('url', ''))
        overlay.show()

    # --- Settings & Profile Management ---

    def move_item(self, direction):
        row = self.overlay_list.currentRow()
        if row < 0: return
        target = row + direction
        if 0 <= target < self.overlay_list.count():
            item = self.overlay_list.takeItem(row)
            self.overlay_list.insertItem(target, item)
            self.overlay_list.setCurrentRow(target)
            self.on_order_changed()

    def on_order_changed(self, *args):
        # Update Z-Order (raise windows in list order)
        for i in range(self.overlay_list.count()):
            oid = self.overlay_list.item(i).data(Qt.UserRole)
            self.overlays[oid].raise_()
        self.save_all_settings()

    def load_profile_from_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Load Profile", "", "PyOverScreen Profile (*.json)")
        if path:
            try:
                with open(path, 'r') as f:
                    data = json.load(f)
                    self.load_profile_data(data)
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to load profile: {e}")

    def save_profile_to_file(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save Profile", "", "PyOverScreen Profile (*.json)")
        if path:
            if not path.endswith('.json'): path += '.json'
            data = self.get_profile_data()
            try:
                with open(path, 'w') as f:
                    json.dump(data, f, indent=4)
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to save profile: {e}")

    def get_profile_data(self):
        data = []
        for i in range(self.overlay_list.count()):
            item = self.overlay_list.item(i)
            oid = item.data(Qt.UserRole)
            overlay = self.overlays[oid]
            geom = overlay.geometry()
            pos = overlay.profile_position if self.wayland else geom.topLeft()
            data.append({
                'id': oid,
                'name': item.text(),
                'url': overlay.current_source,
                'x': pos.x(),
                'y': pos.y(),
                'w': geom.width(),
                'h': geom.height(),
                'opacity': int(overlay.windowOpacity() * 100),
                'zoom': overlay.zoom_factor,
                'locked': bool(overlay.windowFlags() & Qt.WindowTransparentForInput),
                'target_hwnd': overlay.target_hwnd,
                'target_title': overlay.target_title,
                'target_pid': overlay.target_pid,
                'x11_target': overlay.x11_target,
                'loop': overlay.loop_media,
                'volume': overlay.volume
            })
        return data

    def load_profile_data(self, data):
        # Clear existing
        for oid in list(self.overlays.keys()):
            self.overlays[oid].close()
        self.overlays.clear()
        self.overlay_list.clear()
        
        for config in data:
            self.add_new_overlay(config['name'], config)

    def save_current_settings(self):
        if not self.current_overlay_id: return
        overlay = self.overlays[self.current_overlay_id]
        overlay.load_url(self.url_input.text())
        self.play_sound("notify")
        self.save_all_settings()

    def save_all_settings(self):
        if self.is_loading: return
        data = self.get_profile_data()
        self.settings.setValue("overlays_json", json.dumps(data))

    def load_all_settings(self):
        json_str = self.settings.value("overlays_json", "[]")
        try:
            configs = json.loads(json_str)
            if not configs:
                # Add a default one if empty
                self.add_new_overlay("Default Chat")
            else:
                for conf in configs:
                    self.add_new_overlay(conf['name'], conf)
        except:
            self.add_new_overlay("Default Chat")

def run_smoke_test(app, settings_dir):
    # Start with the default overlay without touching the user profile.
    settings = QSettings(str(Path(settings_dir) / "smoke.ini"), QSettings.IniFormat)
    admin = AdminPanel(settings)
    admin.show()
    if admin.get_icon("monitor").pixmap(24, 24).isNull() or len(admin.sounds) != 6:
        return 2

    overlay = next(iter(admin.overlays.values()))
    geometry = overlay.geometry()
    admin.check_lock.setChecked(False)
    if overlay.windowFlags() & Qt.WindowTransparentForInput:
        return 4
    admin.check_lock.setChecked(True)
    if not overlay.windowFlags() & Qt.WindowTransparentForInput:
        return 4
    if not admin.wayland and overlay.geometry() != geometry:
        return 4

    target_title = os.environ.get("PYOVERSCREEN_SMOKE_X11_TARGET")
    if target_title:
        admin.refresh_window_list()
        index = admin.combo_games.findText(target_title)
        if index < 1:
            print("The X11 fixture is missing from the target selector.", file=sys.stderr)
            return 5
        admin.combo_games.setCurrentIndex(index)
        admin.refresh_window_list()
        profile_target = admin.get_profile_data()[0]["x11_target"]
        if admin.combo_games.currentText() != target_title or profile_target[0] != target_title:
            return 5

    page = overlay.browser.page()

    def check_page(loaded):
        if loaded:
            page.runJavaScript(
                "document.title",
                lambda title: app.exit(0) if title == "PyOverScreen startup test" else None,
            )

    page.loadFinished.connect(check_page)
    QTimer.singleShot(0, lambda: overlay.browser.setHtml("<title>PyOverScreen startup test</title>"))
    QTimer.singleShot(20000, lambda: app.exit(3))
    return app.exec()


if __name__ == "__main__":
    if LINUX and "--x11" in sys.argv:
        if not os.environ.get("DISPLAY"):
            sys.exit("--x11 requires a running X11 or XWayland display.")
        sys.argv.remove("--x11")
        os.environ["QT_QPA_PLATFORM"] = "xcb"

    app = QApplication(sys.argv)
    app.setApplicationName("PyOverScreen")
    app.setOrganizationName("PyOverScreen")
    app.setStyle("Fusion")
    
    if sys.argv[1:] == ["--smoke-test"]:
        with TemporaryDirectory() as settings_dir:
            sys.exit(run_smoke_test(app, settings_dir))

    admin = AdminPanel()
    admin.show()
    sys.exit(app.exec())

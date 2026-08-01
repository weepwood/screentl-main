"""Windows desktop UI with system tray support and persistent settings."""

import datetime
import json
import os
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .utils import screenshot
from .video import make_video

try:
    import pystray
    from PIL import Image, ImageDraw
except ImportError:  # The application remains usable without a tray dependency.
    pystray = None
    Image = None
    ImageDraw = None


APP_NAME = 'Screenshot Time-lapse'


class ScreenshotTimeLapseApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_NAME)
        self.geometry('780x650')
        self.minsize(700, 560)

        self.capture_stop = threading.Event()
        self.capture_pause = threading.Event()
        self.capture_pause.set()
        self.capture_thread = None
        self.video_thread = None
        self.capture_count = 0
        self.last_capture = None
        self.tray_icon = None
        self.is_exiting = False

        self.folder_var = tk.StringVar(value=datetime.date.today().strftime('%Y-%m-%d'))
        self.interval_var = tk.StringVar(value='30')
        self.fps_var = tk.StringVar(value='25')
        self.audio_var = tk.StringVar(value='audio')
        self.text_var = tk.StringVar(value=datetime.date.today().strftime('%Y-%m-%d'))
        self.startup_var = tk.BooleanVar(value=False)
        self.minimize_to_tray_var = tk.BooleanVar(value=True)
        self.status_var = tk.StringVar(value='就绪')
        self.detail_var = tk.StringVar(value='尚未开始截屏')
        self.status_var.trace_add('write', self._update_tray_title)

        self.config_path = self._get_config_path()
        self._load_config()
        self._configure_style()
        self._build_ui()
        self._start_tray()
        self.protocol('WM_DELETE_WINDOW', self._on_close)

    @staticmethod
    def _get_config_path():
        app_data = Path(os.environ.get('APPDATA', Path.home() / 'AppData' / 'Roaming'))
        return app_data / 'ScreenshotTimeLapse' / 'config.json'

    def _configure_style(self):
        style = ttk.Style(self)
        try:
            style.theme_use('vista')
        except tk.TclError:
            pass
        style.configure('Title.TLabel', font=('Segoe UI', 18, 'bold'))
        style.configure('Section.TLabelframe.Label', font=('Segoe UI', 10, 'bold'))
        style.configure('Accent.TButton', padding=(12, 7))

    def _build_ui(self):
        root = ttk.Frame(self, padding=20)
        root.pack(fill='both', expand=True)
        root.columnconfigure(0, weight=1)
        root.rowconfigure(4, weight=1)

        ttk.Label(root, text=APP_NAME, style='Title.TLabel').grid(row=0, column=0, sticky='w')
        ttk.Label(root, text='定时记录工作过程，生成可回顾的延时视频').grid(
            row=1, column=0, sticky='w', pady=(4, 16))

        capture = ttk.LabelFrame(root, text='定时截屏', style='Section.TLabelframe', padding=12)
        capture.grid(row=2, column=0, sticky='ew', pady=(0, 12))
        capture.columnconfigure(1, weight=1)
        self._path_row(capture, 0, '保存目录', self.folder_var)
        ttk.Label(capture, text='间隔（秒）').grid(row=1, column=0, sticky='w', pady=(10, 0))
        ttk.Spinbox(capture, from_=1, to=86400, textvariable=self.interval_var, width=12).grid(
            row=1, column=1, sticky='w', pady=(10, 0))
        buttons = ttk.Frame(capture)
        buttons.grid(row=2, column=0, columnspan=3, sticky='w', pady=(14, 0))
        self.start_button = ttk.Button(buttons, text='开始截屏', command=self.start_capture,
                                       style='Accent.TButton')
        self.start_button.pack(side='left')
        self.stop_button = ttk.Button(buttons, text='停止截屏', command=self.stop_capture, state='disabled')
        self.stop_button.pack(side='left', padx=(8, 0))
        self.pause_button = ttk.Button(buttons, text='暂停', command=self.pause_capture, state='disabled')
        self.pause_button.pack(side='left', padx=(8, 0))
        ttk.Button(buttons, text='打开目录', command=self.open_capture_folder).pack(side='left', padx=(8, 0))

        video = ttk.LabelFrame(root, text='生成视频', style='Section.TLabelframe', padding=12)
        video.grid(row=3, column=0, sticky='new', pady=(0, 12))
        video.columnconfigure(1, weight=1)
        self._path_row(video, 0, '截图目录', self.folder_var, browse=False)
        self._path_row(video, 1, '音乐目录', self.audio_var)
        ttk.Label(video, text='视频帧率').grid(row=2, column=0, sticky='w', pady=(10, 0))
        ttk.Spinbox(video, from_=1, to=120, textvariable=self.fps_var, width=12).grid(
            row=2, column=1, sticky='w', pady=(10, 0))
        ttk.Label(video, text='标题文字').grid(row=3, column=0, sticky='w', pady=(10, 0))
        ttk.Entry(video, textvariable=self.text_var).grid(row=3, column=1, sticky='ew', pady=(10, 0))
        self.video_button = ttk.Button(video, text='生成 video.mp4', command=self.start_video,
                                       style='Accent.TButton')
        self.video_button.grid(row=4, column=0, sticky='w', pady=(14, 0))
        ttk.Button(video, text='打开设置', command=self.show_settings).grid(
            row=4, column=1, sticky='w', padx=(8, 0), pady=(14, 0))

        log_frame = ttk.LabelFrame(root, text='运行日志', style='Section.TLabelframe', padding=8)
        log_frame.grid(row=4, column=0, sticky='nsew')
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        self.log_text = tk.Text(log_frame, height=8, state='disabled', wrap='word',
                                background='#f7f7f7', relief='flat')
        self.log_text.grid(row=0, column=0, sticky='nsew')
        scrollbar = ttk.Scrollbar(log_frame, orient='vertical', command=self.log_text.yview)
        scrollbar.grid(row=0, column=1, sticky='ns')
        self.log_text.configure(yscrollcommand=scrollbar.set)

        status = ttk.Frame(root)
        status.grid(row=5, column=0, sticky='ew', pady=(10, 0))
        status.columnconfigure(0, weight=1)
        ttk.Label(status, textvariable=self.status_var, foreground='#333').grid(row=0, column=0, sticky='w')
        ttk.Label(status, textvariable=self.detail_var, foreground='#666').grid(row=0, column=1, sticky='e')

    def _path_row(self, parent, row, label, variable, browse=True):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky='w')
        ttk.Entry(parent, textvariable=variable).grid(row=row, column=1, sticky='ew', padx=(12, 8))
        if browse:
            ttk.Button(parent, text='选择…', command=lambda: self._choose_folder(variable)).grid(
                row=row, column=2, sticky='e')

    def _choose_folder(self, variable):
        selected = filedialog.askdirectory(initialdir=variable.get() or '.')
        if selected:
            variable.set(selected)

    def _load_config(self):
        try:
            with self.config_path.open('r', encoding='utf-8') as f:
                config = json.load(f)
            for name, variable in (
                ('folder', self.folder_var), ('interval', self.interval_var),
                ('fps', self.fps_var), ('audio', self.audio_var), ('text', self.text_var),
            ):
                if name in config:
                    variable.set(str(config[name]))
            self.startup_var.set(bool(config.get('startup', False)))
            self.minimize_to_tray_var.set(bool(config.get('minimize_to_tray', True)))
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            pass

    def _save_config(self):
        config = {
            'folder': self.folder_var.get(), 'interval': self.interval_var.get(),
            'fps': self.fps_var.get(), 'audio': self.audio_var.get(), 'text': self.text_var.get(),
            'startup': self.startup_var.get(), 'minimize_to_tray': self.minimize_to_tray_var.get(),
        }
        try:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            with self.config_path.open('w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
        except OSError as exc:
            self._log(f'配置保存失败：{exc}')

    def _log(self, message):
        self.log_text.configure(state='normal')
        self.log_text.insert('end', message.rstrip() + '\n')
        self.log_text.see('end')
        self.log_text.configure(state='disabled')

    def _thread_log(self, message):
        self.after(0, lambda: self._log(message))

    def start_capture(self):
        if self.capture_thread and self.capture_thread.is_alive():
            return
        try:
            interval = int(self.interval_var.get())
            if interval <= 0:
                raise ValueError
        except ValueError:
            messagebox.showerror('参数错误', '截屏间隔必须是大于 0 的整数。')
            return
        folder = self.folder_var.get().strip()
        if not folder:
            messagebox.showerror('参数错误', '请选择截图保存目录。')
            return

        self._save_config()
        self.capture_stop.clear()
        self.capture_pause.set()
        self.capture_count = 0
        self.capture_thread = threading.Thread(
            target=self._capture_worker, args=(folder, interval), daemon=True)
        self.capture_thread.start()
        self.start_button.configure(state='disabled')
        self.stop_button.configure(state='normal')
        self.pause_button.configure(state='normal', text='暂停')
        self.status_var.set('正在截屏…')
        self._log(f'开始截屏：{folder}，间隔 {interval} 秒')

    def _capture_worker(self, folder, interval):
        try:
            screenshot(folder=folder, interval=interval, stop_event=self.capture_stop,
                       pause_event=self.capture_pause, on_capture=self._capture_received)
            self._thread_log('截屏已停止')
        except Exception as exc:
            self._thread_log(f'截屏失败：{exc}')
        finally:
            self.after(0, self._capture_finished)

    def _capture_received(self, image_path):
        self.capture_count += 1
        self.last_capture = image_path
        self._thread_log(f'已截取第 {self.capture_count} 张：{image_path.name}')
        self.after(0, lambda: self.detail_var.set(f'已截取 {self.capture_count} 张'))

    def stop_capture(self):
        self.capture_stop.set()
        self.capture_pause.set()
        self.status_var.set('正在停止截屏…')

    def pause_capture(self):
        if self.capture_pause.is_set():
            self.capture_pause.clear()
            self.pause_button.configure(text='继续')
            self.status_var.set('截屏已暂停')
            self._log('截屏已暂停')
        else:
            self.capture_pause.set()
            self.pause_button.configure(text='暂停')
            self.status_var.set('正在截屏…')
            self._log('截屏已继续')

    def _capture_finished(self):
        self.start_button.configure(state='normal')
        self.stop_button.configure(state='disabled')
        self.pause_button.configure(state='disabled', text='暂停')
        self.status_var.set('就绪')

    def open_capture_folder(self):
        folder = Path(self.folder_var.get().strip())
        if not folder.is_dir():
            messagebox.showinfo('目录不存在', '截图目录尚未创建。开始截屏后即可打开。')
            return
        try:
            os.startfile(str(folder))
        except OSError as exc:
            messagebox.showerror('打开失败', str(exc))

    def start_video(self):
        if self.video_thread and self.video_thread.is_alive():
            return
        try:
            fps = int(self.fps_var.get())
            if fps <= 0:
                raise ValueError
        except ValueError:
            messagebox.showerror('参数错误', '视频帧率必须是大于 0 的整数。')
            return
        folder = self.folder_var.get().strip()
        if not folder:
            messagebox.showerror('参数错误', '请选择截图目录。')
            return

        self._save_config()
        self.video_button.configure(state='disabled')
        self.status_var.set('正在生成视频…')
        self._log(f'开始生成视频：{folder}')
        self.video_thread = threading.Thread(
            target=self._video_worker,
            args=(folder, fps, self.audio_var.get().strip(), self.text_var.get()), daemon=True)
        self.video_thread.start()

    def _video_worker(self, folder, fps, audio, text):
        try:
            output = make_video(folder=folder, fps=fps, audio_loc=audio, text=text)
            self._thread_log(f'视频已生成：{Path(output).resolve()}')
        except Exception as exc:
            self._thread_log(f'视频生成失败：{exc}')
        finally:
            self.after(0, self._video_finished)

    def _video_finished(self):
        self.video_button.configure(state='normal')
        self.status_var.set('就绪')

    def show_settings(self):
        dialog = tk.Toplevel(self)
        dialog.title('设置')
        dialog.transient(self)
        dialog.grab_set()
        dialog.resizable(False, False)
        frame = ttk.Frame(dialog, padding=18)
        frame.pack(fill='both', expand=True)
        frame.columnconfigure(1, weight=1)

        ttk.Label(frame, text='截图存放位置').grid(row=0, column=0, sticky='w', pady=5)
        ttk.Entry(frame, textvariable=self.folder_var, width=46).grid(row=0, column=1, padx=10, pady=5)
        ttk.Button(frame, text='选择…', command=lambda: self._choose_folder(self.folder_var)).grid(row=0, column=2, pady=5)
        ttk.Label(frame, text='截屏间隔（秒）').grid(row=1, column=0, sticky='w', pady=5)
        ttk.Spinbox(frame, from_=1, to=86400, textvariable=self.interval_var, width=12).grid(row=1, column=1, sticky='w', padx=10, pady=5)
        ttk.Label(frame, text='音乐目录').grid(row=2, column=0, sticky='w', pady=5)
        ttk.Entry(frame, textvariable=self.audio_var, width=46).grid(row=2, column=1, padx=10, pady=5)
        ttk.Button(frame, text='选择…', command=lambda: self._choose_folder(self.audio_var)).grid(row=2, column=2, pady=5)
        ttk.Checkbutton(frame, text='随 Windows 开机启动', variable=self.startup_var).grid(row=3, column=0, columnspan=3, sticky='w', pady=(12, 4))
        ttk.Checkbutton(frame, text='关闭窗口时最小化到右下角托盘', variable=self.minimize_to_tray_var).grid(row=4, column=0, columnspan=3, sticky='w', pady=4)
        ttk.Label(frame, text='配置文件保存在用户 AppData 目录中。').grid(row=5, column=0, columnspan=3, sticky='w', pady=(10, 4))

        buttons = ttk.Frame(frame)
        buttons.grid(row=6, column=0, columnspan=3, sticky='e', pady=(12, 0))
        ttk.Button(buttons, text='取消', command=dialog.destroy).pack(side='right')
        ttk.Button(buttons, text='保存', style='Accent.TButton', command=lambda: self._save_settings(dialog)).pack(side='right', padx=(0, 8))

    def _save_settings(self, dialog):
        try:
            if int(self.interval_var.get()) <= 0:
                raise ValueError
        except ValueError:
            messagebox.showerror('参数错误', '截屏间隔必须是大于 0 的整数。', parent=dialog)
            return
        self._save_config()
        self._set_startup(self.startup_var.get())
        self._log('设置已保存')
        dialog.destroy()

    def _startup_command(self):
        if getattr(sys, 'frozen', False):
            return f'"{Path(sys.executable).resolve()}"'
        script = Path(__file__).resolve().parent.parent / 'app.py'
        return f'"{Path(sys.executable).resolve()}" "{script}"'

    def _set_startup(self, enabled):
        if os.name != 'nt':
            self._log('当前系统不是 Windows，无法设置开机启动')
            return
        try:
            import winreg
            key_path = r'Software\Microsoft\Windows\CurrentVersion\Run'
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE) as key:
                if enabled:
                    winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, self._startup_command())
                else:
                    try:
                        winreg.DeleteValue(key, APP_NAME)
                    except FileNotFoundError:
                        pass
        except OSError as exc:
            self._log(f'开机启动设置失败：{exc}')

    def _start_tray(self):
        if pystray is None or Image is None:
            self._log('未安装 pystray，托盘功能不可用')
            return
        image = Image.new('RGB', (64, 64), '#2563eb')
        draw = ImageDraw.Draw(image)
        draw.rectangle((14, 16, 50, 48), fill='white')
        draw.rectangle((20, 22, 44, 28), fill='#2563eb')
        draw.rectangle((20, 33, 38, 39), fill='#2563eb')
        menu = pystray.Menu(
            pystray.MenuItem('打开窗口', lambda icon, item: self.after(0, self.show_window)),
            pystray.MenuItem('开始截屏', lambda icon, item: self.after(0, self.start_capture)),
            pystray.MenuItem('停止截屏', lambda icon, item: self.after(0, self.stop_capture)),
            pystray.MenuItem('设置', lambda icon, item: self.after(0, self.show_settings)),
            pystray.MenuItem('退出', lambda icon, item: self.after(0, self.exit_app)),
        )
        self.tray_icon = pystray.Icon('screentl', image, APP_NAME, menu)
        threading.Thread(target=self.tray_icon.run, daemon=True).start()
        self._update_tray_title()

    def _update_tray_title(self, *_args):
        if self.tray_icon is not None:
            self.tray_icon.title = f'{APP_NAME} - {self.status_var.get()}'

    def show_window(self):
        self.deiconify()
        self.lift()
        self.focus_force()

    def _on_close(self):
        if self.minimize_to_tray_var.get() and self.tray_icon is not None:
            self.withdraw()
            self._log('程序已最小化到右下角托盘')
        else:
            self.exit_app()

    def exit_app(self):
        if self.is_exiting:
            return
        self.is_exiting = True
        self._save_config()
        self.capture_stop.set()
        self.capture_pause.set()
        if self.tray_icon is not None:
            self.tray_icon.stop()
        self.destroy()


def main():
    app = ScreenshotTimeLapseApp()
    app.mainloop()


if __name__ == '__main__':
    main()

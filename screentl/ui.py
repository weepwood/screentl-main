"""Tkinter desktop interface for Screenshot Time-lapse."""

import datetime
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .utils import screenshot
from .video import make_video


class ScreenshotTimeLapseApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('Screenshot Time-lapse')
        self.geometry('760x620')
        self.minsize(680, 520)

        self.capture_stop = threading.Event()
        self.capture_thread = None
        self.video_thread = None

        self.folder_var = tk.StringVar(value=datetime.date.today().strftime('%Y-%m-%d'))
        self.interval_var = tk.StringVar(value='30')
        self.fps_var = tk.StringVar(value='25')
        self.audio_var = tk.StringVar(value='audio')
        self.text_var = tk.StringVar(value=datetime.date.today().strftime('%Y-%m-%d'))
        self.status_var = tk.StringVar(value='就绪')

        self._configure_style()
        self._build_ui()
        self.protocol('WM_DELETE_WINDOW', self._on_close)

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

        ttk.Label(root, text='Screenshot Time-lapse', style='Title.TLabel').grid(
            row=0, column=0, sticky='w')
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

        ttk.Label(root, textvariable=self.status_var, foreground='#555').grid(
            row=5, column=0, sticky='w', pady=(10, 0))

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

        self.capture_stop.clear()
        self.capture_thread = threading.Thread(
            target=self._capture_worker, args=(folder, interval), daemon=True)
        self.capture_thread.start()
        self.start_button.configure(state='disabled')
        self.stop_button.configure(state='normal')
        self.status_var.set('正在截屏…')
        self._log(f'开始截屏：{folder}，间隔 {interval} 秒')

    def _capture_worker(self, folder, interval):
        try:
            screenshot(folder=folder, interval=interval, stop_event=self.capture_stop)
            self._thread_log('截屏已停止')
        except Exception as exc:
            self._thread_log(f'截屏失败：{exc}')
        finally:
            self.after(0, self._capture_finished)

    def stop_capture(self):
        self.capture_stop.set()
        self.status_var.set('正在停止截屏…')

    def _capture_finished(self):
        self.start_button.configure(state='normal')
        self.stop_button.configure(state='disabled')
        self.status_var.set('就绪')

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

        self.video_button.configure(state='disabled')
        self.status_var.set('正在生成视频…')
        self._log(f'开始生成视频：{folder}')
        self.video_thread = threading.Thread(
            target=self._video_worker,
            args=(folder, fps, self.audio_var.get().strip(), self.text_var.get()),
            daemon=True,
        )
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

    def _on_close(self):
        if self.capture_thread and self.capture_thread.is_alive():
            self.capture_stop.set()
        self.destroy()


def main():
    app = ScreenshotTimeLapseApp()
    app.mainloop()


if __name__ == '__main__':
    main()

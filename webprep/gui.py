"""Tk desktop interface; all image work runs outside the Tk event loop."""
from collections import Counter
from queue import Empty, Queue
from threading import Thread
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

from . import Settings, make_layout, process_batch, scan_sources


def run_batch(sources, output, settings, overwrite, dry_run, events):
    """Run the existing safe pipeline and emit UI-independent progress events."""
    try:
        layout = make_layout(sources, output or None)
        photos = scan_sources(layout)
        events.put(('scanned', (len(photos), str(layout.output))))
        results = process_batch(
            photos, layout, settings, overwrite=overwrite, dry_run=dry_run,
            on_result=lambda result: events.put(('result', result)),
        )
        events.put(('done', (Counter(r.status for r in results), dry_run)))
    except Exception as exc:
        events.put(('error', str(exc)))


class App:
    def __init__(self, root):
        self.root = root
        self.running = False
        self.events = Queue()
        root.title('WebPrep — Photo Web Downscaler')
        root.geometry('850x680')
        root.minsize(650, 550)
        root.protocol('WM_DELETE_WINDOW', self.close)
        frame = ttk.Frame(root, padding=16)
        frame.pack(fill='both', expand=True)
        ttk.Label(frame, text='Create web JPEGs', font=('', 18, 'bold')).pack(anchor='w')
        ttk.Label(frame, text='Select source folders. Originals are preserved.').pack(anchor='w', pady=(4, 12))
        self.sources = tk.Listbox(frame, height=5, selectmode=tk.EXTENDED)
        self.sources.pack(fill='x')
        buttons = ttk.Frame(frame)
        buttons.pack(fill='x', pady=6)
        self.controls = []
        self.button(buttons, 'Add source folder…', self.add_source).pack(side='left')
        self.button(buttons, 'Remove selected', self.remove_sources).pack(side='left', padx=8)
        ttk.Label(frame, text='Output folder (leave blank for shared parent/web)').pack(anchor='w', pady=(8, 3))
        output_row = ttk.Frame(frame)
        output_row.pack(fill='x')
        self.output = tk.StringVar()
        entry = ttk.Entry(output_row, textvariable=self.output)
        entry.pack(side='left', fill='x', expand=True)
        self.controls.append(entry)
        self.button(output_row, 'Browse…', self.choose_output).pack(side='left', padx=(8, 0))
        settings_row = ttk.Frame(frame)
        settings_row.pack(fill='x', pady=12)
        self.size = tk.StringVar(value='2048')
        self.quality = tk.StringVar(value='82')
        for label, variable, maximum in [('Maximum edge (px)', self.size, 65535), ('JPEG quality', self.quality, 95)]:
            ttk.Label(settings_row, text=label).pack(side='left', padx=(0, 6))
            spin = ttk.Spinbox(settings_row, from_=1, to=maximum, textvariable=variable, width=8)
            spin.pack(side='left', padx=(0, 16))
            self.controls.append(spin)
        self.overwrite = tk.BooleanVar()
        check = ttk.Checkbutton(frame, text='Overwrite existing web copies', variable=self.overwrite)
        check.pack(anchor='w')
        self.controls.append(check)
        actions = ttk.Frame(frame)
        actions.pack(fill='x', pady=12)
        self.button(actions, 'Preview (no files written)', lambda: self.start(True)).pack(side='left')
        self.button(actions, 'Process images', lambda: self.start(False)).pack(side='left', padx=8)
        self.status = tk.StringVar(value='Ready')
        ttk.Label(frame, textvariable=self.status, wraplength=780).pack(anchor='w')
        self.progress = ttk.Progressbar(frame, mode='determinate')
        self.progress.pack(fill='x', pady=6)
        self.log = ScrolledText(frame, height=12, state='disabled', wrap='word')
        self.log.pack(fill='both', expand=True)
        root.after(100, self.poll)

    def button(self, parent, text, command):
        button = ttk.Button(parent, text=text, command=command)
        self.controls.append(button)
        return button

    def add_source(self):
        path = filedialog.askdirectory(parent=self.root, title='Choose source folder')
        if path and path not in self.sources.get(0, tk.END):
            self.sources.insert(tk.END, path)

    def remove_sources(self):
        for index in reversed(self.sources.curselection()):
            self.sources.delete(index)

    def choose_output(self):
        path = filedialog.askdirectory(parent=self.root, title='Choose output folder', mustexist=False)
        if path:
            self.output.set(path)

    def write(self, text):
        self.log.configure(state='normal')
        self.log.insert(tk.END, text + '\n')
        self.log.see(tk.END)
        self.log.configure(state='disabled')

    def start(self, dry_run):
        if self.running:
            return
        sources = self.sources.get(0, tk.END)
        try:
            if not sources:
                raise ValueError('Add at least one source folder.')
            settings = Settings(int(self.size.get()), int(self.quality.get()))
        except ValueError as exc:
            messagebox.showerror('Check settings', str(exc), parent=self.root)
            return
        if self.overwrite.get() and not dry_run:
            if not messagebox.askyesno('Overwrite web copies?', 'Existing web copies may be replaced. Continue?', parent=self.root):
                return
        self.running = True
        for control in self.controls:
            control.configure(state='disabled')
        self.sources.configure(state='disabled')
        self.completed = 0
        self.progress.configure(value=0, mode='indeterminate')
        self.progress.start()
        self.status.set('Scanning and validating folders…')
        self.write('\nPreview started' if dry_run else '\nProcessing started')
        Thread(target=run_batch, args=(sources, self.output.get().strip(), settings,
               self.overwrite.get(), dry_run, self.events), daemon=True).start()

    def finish(self):
        self.running = False
        self.progress.stop()
        for control in self.controls:
            control.configure(state='normal')
        self.sources.configure(state='normal')

    def poll(self):
        try:
            while True:
                kind, data = self.events.get_nowait()
                if kind == 'scanned':
                    self.total, output = data
                    self.progress.stop()
                    self.progress.configure(mode='determinate', maximum=max(1, self.total), value=0)
                    self.write(f'Output: {output}\nImages found: {self.total}')
                    self.status.set(f'Processing 0 of {self.total} images')
                elif kind == 'result':
                    self.completed += 1
                    self.progress.configure(value=self.completed)
                    self.status.set(f'Processed {self.completed} of {self.total} images')
                    self.write(f'{data.status}: {data.job.photo.source}\n  → {data.job.destination}')
                    if data.message:
                        self.write('  ' + data.message)
                    for warning in data.warnings:
                        self.write('  Warning: ' + warning)
                elif kind == 'done':
                    counts, dry_run = data
                    summary = ', '.join(f'{status}: {count}' for status, count in counts.items()) or 'No images found'
                    heading = 'Preview complete — no files written.' if dry_run else 'Processing complete.'
                    if counts['ERROR'] or counts['COLLISION']:
                        heading += ' Some images need attention; see the log.'
                    self.status.set(heading)
                    self.write(heading + '\n' + summary)
                    self.finish()
                elif kind == 'error':
                    self.finish()
                    self.status.set('Stopped — see error details.')
                    self.write('ERROR: ' + data + '\nProcessing stopped. Earlier outputs may have been written.')
                    messagebox.showerror('Processing stopped', data, parent=self.root)
        except Empty:
            pass
        self.root.after(100, self.poll)

    def close(self):
        if self.running:
            messagebox.showinfo('Processing in progress', 'Wait for processing to finish before closing WebPrep.', parent=self.root)
        else:
            self.root.destroy()


def main():
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        raise SystemExit(f'Cannot open the desktop GUI: {exc}\nUse a desktop session; WSL requires WSLg support.') from exc
    App(root)
    root.mainloop()


if __name__ == '__main__':
    main()

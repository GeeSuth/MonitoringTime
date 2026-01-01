"""
Windows Time Tracker - Background Application
A minimal desktop application that runs in background with a floating timer widget.

Requirements:
pip install psutil pygetwindow pystray pillow

Usage:
python time_tracker.py
"""

import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
import sqlite3
import json
from datetime import datetime, timedelta
import psutil
import threading
import time
import webbrowser
import os
from pathlib import Path
import pystray
from PIL import Image, ImageDraw
import sys

class FloatingWidget(tk.Toplevel):
    """Floating timer widget that stays on top"""
    
    def __init__(self, parent, root):
        super().__init__(root)
        self.app = parent
        
        # Window configuration
        self.overrideredirect(True)  # Remove window decorations
        self.attributes('-topmost', True)  # Always on top
        self.attributes('-alpha', 0.95)  # Slightly transparent
        
        # Position in top-right corner
        screen_width = self.winfo_screenwidth()
        self.geometry(f"280x350+{screen_width-300}+20")
        
        # Make draggable
        self.bind('<Button-1>', self.start_move)
        self.bind('<B1-Motion>', self.do_move)
        
        # Main frame with gradient-like background
        self.main_frame = tk.Frame(self, bg='#2d3748', bd=2, relief='raised')
        self.main_frame.pack(fill='both', expand=True)
        
        # Task name
        self.task_label = tk.Label(
            self.main_frame, text="No Task", font=('Arial', 10, 'bold'),
            bg='#2d3748', fg='#ffffff'
        )
        self.task_label.pack(pady=(8, 2))
        
        # Timer
        self.timer_label = tk.Label(
            self.main_frame, text="00:00:00", font=('Arial', 20, 'bold'),
            bg='#2d3748', fg='#4fd1c5'
        )
        self.timer_label.pack(pady=2)
        
        # Remaining time
        self.remaining_label = tk.Label(
            self.main_frame, text="", font=('Arial', 8),
            bg='#2d3748', fg='#a0aec0'
        )
        self.remaining_label.pack(pady=2)
        
        # Progress bar
        self.progress_canvas = tk.Canvas(
            self.main_frame, height=8, bg='#1a202c', highlightthickness=0
        )
        self.progress_canvas.pack(fill='x', padx=10, pady=(0, 5))

        # Separator
        ttk.Separator(self.main_frame, orient='horizontal').pack(fill='x', padx=10, pady=5)

        # --- Subtasks ---
        subtask_container = tk.Frame(self.main_frame, bg='#2d3748')
        subtask_container.pack(fill='both', expand=True, padx=10, pady=(0, 10))

        # Subtask Add
        add_frame = tk.Frame(subtask_container, bg='#2d3748')
        add_frame.pack(fill='x', pady=5)
        self.new_subtask_entry = tk.Entry(
            add_frame, font=('Arial', 9), bg='#1a202c', fg='white',
            insertbackground='white', bd=1, relief='solid'
        )
        self.new_subtask_entry.pack(side='left', fill='x', expand=True, ipady=3)
        self.new_subtask_entry.bind("<Return>", lambda e: self.add_subtask())

        # Subtask List
        self.subtask_canvas = tk.Canvas(
            subtask_container, bg='#2d3748', highlightthickness=0
        )
        self.subtask_scrollbar = ttk.Scrollbar(
            subtask_container, orient='vertical', command=self.subtask_canvas.yview
        )
        self.subtask_list_frame = tk.Frame(self.subtask_canvas, bg='#2d3748')

        self.subtask_list_frame.bind(
            '<Configure>',
            lambda e: self.subtask_canvas.configure(scrollregion=self.subtask_canvas.bbox('all'))
        )
        self.subtask_canvas.create_window((0, 0), window=self.subtask_list_frame, anchor='nw')
        self.subtask_canvas.configure(yscrollcommand=self.subtask_scrollbar.set)
        
        self.subtask_canvas.pack(side='left', fill='both', expand=True)
        self.subtask_scrollbar.pack(side='right', fill='y')
        
        # Bind right-click menu to all major widgets
        for widget in [self.main_frame, self.task_label, self.timer_label, 
                       self.remaining_label, self.progress_canvas, self.subtask_canvas]:
            widget.bind('<Button-3>', self.show_task_menu)
        
        # For dragging
        self.x = 0
        self.y = 0
        self.current_subtasks_cache = []
        self.current_task_name_cache = ""

    def add_subtask(self):
        subtask_name = self.new_subtask_entry.get().strip()
        if not subtask_name:
            return
            
        task = self.app.tasks[self.app.current_task_index]
        if 'subtasks' not in task:
            task['subtasks'] = []
            
        task['subtasks'].append({'name': subtask_name, 'completed': False})
        self.new_subtask_entry.delete(0, 'end')
        self.render_subtasks(task)

    def render_subtasks(self, task):
        for widget in self.subtask_list_frame.winfo_children():
            widget.destroy()

        if 'subtasks' not in task or not task['subtasks']:
            tk.Label(
                self.subtask_list_frame, text="No subtasks yet.", 
                bg='#2d3748', fg='#a0aec0', font=('Arial', 8)
            ).pack(pady=10)
            return

        for i, subtask in enumerate(task['subtasks']):
            subtask_frame = tk.Frame(self.subtask_list_frame, bg='#2d3748')
            subtask_frame.pack(fill='x', anchor='w', pady=1)

            def toggle_subtask_handler(event=None, idx=i):
                task['subtasks'][idx]['completed'] = not task['subtasks'][idx]['completed']
                self.render_subtasks(task)

            if subtask['completed']:
                checkmark_text = "✓"
                fg_color = '#718096'
                font_config = ('Arial', 9, 'overstrike')
            else:
                checkmark_text = "○"
                fg_color = '#a0aec0'
                font_config = ('Arial', 9)

            checkmark_label = tk.Label(
                subtask_frame, text=checkmark_text, font=('Arial', 12),
                bg='#2d3748', fg='#4fd1c5', padx=5
            )
            checkmark_label.pack(side='left')
            checkmark_label.bind("<Button-1>", toggle_subtask_handler)
            
            text_label = tk.Label(
                subtask_frame, text=subtask['name'], font=font_config,
                fg=fg_color, bg='#2d3748', anchor='w', justify='left'
            )
            text_label.pack(side='left', fill='x', expand=True)
            text_label.bind("<Button-1>", toggle_subtask_handler)

            delete_btn = tk.Button(
                subtask_frame, text="✕", font=('Arial', 8),
                bg='#2d3748', fg='#c53030', bd=0,
                activebackground='#2d3748', activeforeground='#fc8181',
                cursor='hand2', command=lambda idx=i: self.delete_subtask(task, idx)
            )
            delete_btn.pack(side='right', padx=5)

    def delete_subtask(self, task, index):
        if messagebox.askyesno("Confirm", "Delete this subtask?", parent=self):
            task['subtasks'].pop(index)
            self.render_subtasks(task)
        
    def start_move(self, event):
        self.x = event.x
        self.y = event.y
        
    def do_move(self, event):
        deltax = event.x - self.x
        deltay = event.y - self.y
        x = self.winfo_x() + deltax
        y = self.winfo_y() + deltay
        self.geometry(f"+{x}+{y}")
        
    def show_task_menu(self, event):
        """Show right-click context menu for tasks"""
        task_menu = tk.Menu(self, tearoff=0, bg="#f0f0f0", fg="black",
                            activebackground='#4fd1c5', activeforeground='white')

        if self.app.tasks:
            for i, task in enumerate(self.app.tasks):
                label = f"  {task['name']}"
                if i == self.app.current_task_index:
                    label = f"✓ {task['name']}"
                
                task_menu.add_command(
                    label=label,
                    command=lambda idx=i: self.app.switch_to_task(idx)
                )
            task_menu.add_separator()

        pause_label = "Resume" if not self.app.is_running else "Pause"
        task_menu.add_command(label=pause_label, command=self.app.toggle_pause)
        task_menu.add_command(label="Settings...", command=self.app.show_main_window)
        task_menu.add_separator()
        task_menu.add_command(label="Exit", command=self.app.quit_app)

        try:
            task_menu.tk_popup(event.x_root, event.y_root)
        finally:
            task_menu.grab_release()

    def update_display(self, task, elapsed_seconds, is_running):
        """Update widget display"""
        task_name = task['name']
        planned_minutes = task['minutes']

        self.task_label.config(text=task_name[:25])
        
        # Format timer
        hours = elapsed_seconds // 3600
        minutes = (elapsed_seconds % 3600) // 60
        seconds = elapsed_seconds % 60
        self.timer_label.config(text=f"{hours:02d}:{minutes:02d}:{seconds:02d}")
        
        # Update remaining time
        planned_seconds = planned_minutes * 60
        remaining = planned_seconds - elapsed_seconds
        
        if remaining > 0:
            rem_min = remaining // 60
            rem_sec = remaining % 60
            self.remaining_label.config(
                text=f"{rem_min}m {rem_sec}s left",
                fg='#68d391'
            )
        else:
            self.remaining_label.config(
                text="Time exceeded!",
                fg='#fc8181'
            )
            # Flash effect when time exceeded
            if elapsed_seconds % 2 == 0:
                self.main_frame.config(bg='#742a2a')
                for w in [self.task_label, self.timer_label, self.remaining_label]:
                    w.config(bg='#742a2a')
            else:
                self.main_frame.config(bg='#2d3748')
                for w in [self.task_label, self.timer_label, self.remaining_label]:
                    w.config(bg='#2d3748')
        
        # Update progress bar
        progress_percent = min((elapsed_seconds / planned_seconds), 1.0) if planned_seconds > 0 else 0
        width = self.progress_canvas.winfo_width()
        self.progress_canvas.delete('all')
        self.progress_canvas.create_rectangle(0, 0, width, 8, fill='#1a202c', outline='')
        fill_color = '#fc8181' if remaining < 0 else '#4fd1c5'
        self.progress_canvas.create_rectangle(
            0, 0, width * progress_percent, 8, fill=fill_color, outline=''
        )
        
        # Update subtasks if needed
        subtasks_json = json.dumps(task.get('subtasks', []))
        if task_name != self.current_task_name_cache or subtasks_json != self.current_subtasks_cache:
            self.current_task_name_cache = task_name
            self.current_subtasks_cache = subtasks_json
            self.render_subtasks(task)


class TimeTrackerApp:
    def __init__(self):
        # Hidden root window
        self.root = tk.Tk()
        self.root.withdraw()  # Hide main window
        
        # Database setup
        self.db_path = "time_tracker.db"
        self.init_database()
        
        # Application state
        self.total_minutes = 0
        self.end_time = None
        self.tasks = []
        self.current_task_index = 0
        self.is_running = False
        self.elapsed_seconds = 0
        self.session_start_time = None
        self.session_id = None
        self.process_tracking = {}
        self.setup_session_minutes = 0
        self.setup_total_task_minutes = 0
        
        # Tracking thread
        self.tracking_thread = None
        self.stop_tracking_flag = False
        
        # Floating widget
        self.floating_widget = None
        
        # System tray icon
        self.setup_tray_icon()
        
        # Show setup on first run
        self.root.after(100, self.show_setup_dialog)
        
    def setup_tray_icon(self):
        """Setup system tray icon"""
        # Create icon image
        image = Image.new('RGB', (64, 64), color='#4fd1c5')
        draw = ImageDraw.Draw(image)
        draw.rectangle([16, 16, 48, 48], fill='#2d3748')
        
        # Create menu
        menu = pystray.Menu(
            pystray.MenuItem('Show Timer', self.show_floating_widget),
            pystray.MenuItem('Hide Timer', self.hide_floating_widget),
            pystray.MenuItem('Settings', self.show_main_window),
            pystray.MenuItem('Report', self.generate_report),
            pystray.MenuItem('History', self.view_history),
            pystray.MenuItem('Exit', self.quit_app)
        )
        
        self.icon = pystray.Icon('TimeTracker', image, 'Time Tracker', menu)
        
        # Run icon in separate thread
        threading.Thread(target=self.icon.run, daemon=True).start()
        
    def init_database(self):
        """Initialize SQLite database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS task_templates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                default_minutes INTEGER NOT NULL,
                color TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                total_minutes INTEGER,
                start_time TIMESTAMP,
                end_time TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS session_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER,
                task_name TEXT,
                planned_minutes INTEGER,
                actual_seconds INTEGER,
                completed BOOLEAN,
                processes TEXT,
                FOREIGN KEY (session_id) REFERENCES sessions(id)
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sub_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_task_id INTEGER,
                name TEXT NOT NULL,
                completed BOOLEAN NOT NULL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (session_task_id) REFERENCES session_tasks(id) ON DELETE CASCADE
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS daily_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER,
                report_date DATE,
                report_html TEXT,
                total_planned_minutes INTEGER,
                total_actual_minutes INTEGER,
                tasks_count INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (session_id) REFERENCES sessions(id)
            )
        ''')
        
        conn.commit()
        conn.close()
        
    def _parse_time(self, time_str):
        now = datetime.now()
        time_str_upper = time_str.upper()
        is_pm = "PM" in time_str_upper
        is_am = "AM" in time_str_upper
        
        time_str = time_str_upper.replace("PM", "").replace("AM", "").strip()
        
        try:
            parts = list(map(int, time_str.split(':')))
            h, m = parts[0], parts[1]

            if is_pm and h != 12:
                h += 12
            elif is_am and h == 12:
                h = 0
            
            if h > 23: return None

            end = now.replace(hour=h, minute=m, second=0, microsecond=0)
            if end <= now:
                end += timedelta(days=1)
            return end
        except (ValueError, IndexError):
            return None

    def _update_remaining_time(self):
        remaining = int(self.setup_session_minutes - self.setup_total_task_minutes)
        
        text = f"Unallocated Time: {remaining} min"
        color = '#2d3748' if remaining >= 0 else '#c53030'
        
        self.remaining_time_label.config(text=text, fg=color)

    def show_setup_dialog(self):
        """Show initial setup dialog"""
        setup_window = tk.Toplevel(self.root)
        setup_window.title("Time Tracker Setup")
        setup_window.geometry("500x600")
        setup_window.configure(bg='#f7fafc')
        
        # Header
        header_frame = tk.Frame(setup_window, bg='#4fd1c5', height=80)
        header_frame.pack(fill='x')
        header_frame.pack_propagate(False)
        
        tk.Label(
            header_frame,
            text="⏰ Time Tracker Setup",
            font=('Arial', 18, 'bold'),
            bg='#4fd1c5',
            fg='white'
        ).pack(expand=True)
        
        # Content frame
        content = tk.Frame(setup_window, bg='#f7fafc', padx=20, pady=20)
        content.pack(fill='both', expand=True)
        
        # Session End time
        tk.Label(
            content,
            text="Session End Time:",
            font=('Arial', 11),
            bg='#f7fafc'
        ).pack(anchor='w', pady=(10, 5))
        
        time_frame = tk.Frame(content, bg='#f7fafc')
        time_frame.pack(fill='x', pady=(0, 15))
        
        time_picker_frame = tk.Frame(time_frame, bg='#f7fafc')

        hour_values = [str(i) for i in range(1, 13)]
        minute_values = [f"{i:02d}" for i in range(60)]
        ampm_values = ["AM", "PM"]

        hour_cb = ttk.Combobox(time_picker_frame, width=3, font=('Arial', 11), values=hour_values, state="readonly")
        minute_cb = ttk.Combobox(time_picker_frame, width=3, font=('Arial', 11), values=minute_values)
        ampm_cb = ttk.Combobox(time_picker_frame, width=4, font=('Arial', 11), values=ampm_values, state="readonly")

        now = datetime.now()
        default_end = (now + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)

        h12 = default_end.hour % 12
        if h12 == 0: h12 = 12
        hour_cb.set(str(h12))
        minute_cb.set(f"{default_end.minute:02d}")
        ampm_cb.set(default_end.strftime("%p"))

        hour_cb.pack(side='left', padx=(0,2))
        tk.Label(time_picker_frame, text=":", bg='#f7fafc', font=('Arial', 11, 'bold')).pack(side='left')
        minute_cb.pack(side='left', padx=2)
        ampm_cb.pack(side='left', padx=(2,0))

        time_picker_frame.pack(side='left')
        
        duration_label = tk.Label(
            time_frame,
            text="",
            font=('Arial', 10),
            bg='#f7fafc',
            fg='#718096'
        )
        duration_label.pack(side='left', padx=10)

        self.remaining_time_label = tk.Label(
            content,
            text="Unallocated Time: 0 min",
            font=('Arial', 10, 'bold'),
            bg='#f7fafc',
            fg='#2d3748'
        )
        self.remaining_time_label.pack(anchor='w', pady=(5, 5))

        def update_duration_label(*args):
            try:
                h = hour_cb.get()
                m = minute_cb.get()
                ampm = ampm_cb.get()
                if not (h and m and ampm):
                    return
                time_str = f"{h}:{m} {ampm}"
                end_time = self._parse_time(time_str)
                if end_time:
                    duration = end_time - datetime.now()
                    total_minutes = duration.total_seconds() / 60
                    self.setup_session_minutes = total_minutes
                    if total_minutes > 0:
                        hours = int(total_minutes / 60)
                        minutes = int(total_minutes % 60)
                        duration_label.config(text=f"(≈ {hours}h {minutes}m)")
                    else:
                        duration_label.config(text="(in the past!)")
                else:
                    self.setup_session_minutes = 0
                    duration_label.config(text="(invalid time)")
            except (ValueError, tk.TclError):
                 self.setup_session_minutes = 0
                 duration_label.config(text="(invalid time)")
            self._update_remaining_time()


        hour_cb.bind("<<ComboboxSelected>>", update_duration_label)
        minute_cb.bind("<<ComboboxSelected>>", update_duration_label)
        minute_cb.bind("<KeyRelease>", update_duration_label)
        ampm_cb.bind("<<ComboboxSelected>>", update_duration_label)
        
        # Load templates button
        tk.Button(
            content,
            text="📋 Load Saved Tasks",
            font=('Arial', 10),
            bg='#e6fffa',
            fg='#234e52',
            bd=0,
            padx=15,
            pady=8,
            cursor='hand2',
            command=lambda: self.load_templates_to_setup(task_list_frame)
        ).pack(pady=(0, 10))
        
        # Tasks section
        tk.Label(
            content,
            text="Tasks:",
            font=('Arial', 11, 'bold'),
            bg='#f7fafc'
        ).pack(anchor='w', pady=(10, 5))
        
        # Scrollable task list
        task_canvas = tk.Canvas(content, bg='white', highlightthickness=1, 
                                highlightbackground='#e2e8f0')
        task_scrollbar = tk.Scrollbar(content, orient='vertical', 
                                      command=task_canvas.yview)
        task_list_frame = tk.Frame(task_canvas, bg='white')
        
        task_list_frame.bind(
            '<Configure>',
            lambda e: task_canvas.configure(scrollregion=task_canvas.bbox('all'))
        )
        
        task_canvas.create_window((0, 0), window=task_list_frame, anchor='nw')
        task_canvas.configure(yscrollcommand=task_scrollbar.set)
        
        task_canvas.pack(side='left', fill='both', expand=True)
        task_scrollbar.pack(side='right', fill='y')
        
        # Add task button
        def add_task_to_setup():
            self.add_task_row_setup(task_list_frame)
            
        tk.Button(
            content,
            text="+ Add Task",
            font=('Arial', 10),
            bg='#4fd1c5',
            fg='white',
            bd=0,
            padx=20,
            pady=8,
            cursor='hand2',
            command=add_task_to_setup
        ).pack(pady=10)
        
        # Bottom buttons
        button_frame = tk.Frame(setup_window, bg='#f7fafc', pady=15)
        button_frame.pack(fill='x')
        
        tk.Button(
            button_frame,
            text="💾 Save as Template",
            font=('Arial', 10),
            bg='#edf2f7',
            fg='#2d3748',
            bd=0,
            padx=20,
            pady=10,
            cursor='hand2',
            command=lambda: self.save_template_from_setup(task_list_frame)
        ).pack(side='left', padx=(20, 5))
        
        tk.Button(
            button_frame,
            text="▶ Start Tracking",
            font=('Arial', 11, 'bold'),
            bg='#38b2ac',
            fg='white',
            bd=0,
            padx=30,
            pady=10,
            cursor='hand2',
            command=lambda: self.start_from_setup(setup_window, f"{hour_cb.get()}:{minute_cb.get()} {ampm_cb.get()}", task_list_frame)
        ).pack(side='right', padx=(5, 20))
        
        # Add initial task row and update labels
        self.add_task_row_setup(task_list_frame, name="First Task")
        update_duration_label()

        setup_window.protocol("WM_DELETE_WINDOW", self.quit_app)
        
    def add_task_row_setup(self, parent, name="", minutes="30"):
        """Add task row in setup dialog"""
        row = tk.Frame(parent, bg='white', pady=5, padx=10)
        row.pack(fill='x', pady=2)
        
        name_entry = tk.Entry(row, font=('Arial', 10), width=25)
        name_entry.insert(0, name)
        name_entry.pack(side='left', padx=5)
        
        tk.Label(row, text="min:", bg='white', font=('Arial', 9)).pack(side='left')
        
        minutes_entry = tk.Entry(row, font=('Arial', 10), width=8)
        minutes_entry.insert(0, minutes)
        minutes_entry.pack(side='left', padx=5)
        minutes_entry.bind("<KeyRelease>", lambda e: self._update_total_task_minutes(parent)) # Bind KeyRelease

        # Using a wrapper function to pass task_list_frame
        def delete_row_and_update():
            row.destroy()
            self._update_total_task_minutes(parent)

        tk.Button(
            row,
            text="✕",
            font=('Arial', 10),
            bg='#fed7d7',
            fg='#c53030',
            bd=0,
            padx=8,
            pady=2,
            cursor='hand2',
            command=delete_row_and_update
        ).pack(side='left', padx=5)

        self._update_total_task_minutes(parent) # Update after adding a new row
        
    def load_templates_to_setup(self, task_list_frame):
        """Load templates into setup dialog"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT DISTINCT name, default_minutes FROM task_templates')
        templates = cursor.fetchall()
        conn.close()
        
        if not templates:
            messagebox.showinfo("Info", "No saved templates found")
            return
            
        # Clear existing
        for widget in task_list_frame.winfo_children():
            widget.destroy()
            
        # Load templates
        for name, minutes in templates:
            # Re-use add_task_row_setup with loaded data
            self.add_task_row_setup(task_list_frame, name=name, minutes=str(minutes))
            
        self._update_total_task_minutes(task_list_frame) # Update after loading templates
            
    def _update_total_task_minutes(self, task_list_frame):
        total_minutes = 0
        for row in task_list_frame.winfo_children():
            entries = [w for w in row.winfo_children() if isinstance(w, tk.Entry)]
            if len(entries) >= 2: # Assuming the second Entry is minutes
                try:
                    total_minutes += int(entries[1].get())
                except ValueError:
                    pass
        self.setup_total_task_minutes = total_minutes
        self._update_remaining_time()
            
    def save_template_from_setup(self, task_list_frame):
        """Save tasks as template"""
        tasks = self.get_tasks_from_setup(task_list_frame)
        if not tasks:
            messagebox.showwarning("Warning", "No tasks to save!")
            return
            
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        for task in tasks:
            cursor.execute('''
                INSERT INTO task_templates (name, default_minutes, color)
                VALUES (?, ?, ?)
            ''', (task['name'], task['minutes'], '#4fd1c5'))
            
        conn.commit()
        conn.close()
        
        messagebox.showinfo("Success", "Tasks saved as template!")
        
    def get_tasks_from_setup(self, task_list_frame):
        """Get tasks from setup dialog"""
        tasks = []
        for row in task_list_frame.winfo_children():
            entries = [w for w in row.winfo_children() if isinstance(w, tk.Entry)]
            if len(entries) >= 2:
                try:
                    name = entries[0].get().strip()
                    minutes = int(entries[1].get())
                    if name and minutes > 0:
                        tasks.append({'name': name, 'minutes': minutes, 'subtasks': []})
                except ValueError:
                    pass
        return tasks
        
    def start_from_setup(self, setup_window, end_time_str, task_list_frame):
        """Start tracking from setup dialog"""
        end_time = self._parse_time(end_time_str)

        if not end_time:
            messagebox.showerror("Error", "Invalid end time format. Use HH:MM or H:MM AM/PM.")
            return

        total_minutes = (end_time - datetime.now()).total_seconds() / 60
        if total_minutes <= 0:
            messagebox.showerror("Error", "End time must be in the future!")
            return
            
        self.tasks = self.get_tasks_from_setup(task_list_frame)
        
        if not self.tasks:
            messagebox.showerror("Error", "Please add at least one task!")
            return

        sum_task_minutes = sum(task['minutes'] for task in self.tasks)
        if int(total_minutes) != sum_task_minutes:
            diff = abs(int(total_minutes) - sum_task_minutes)
            message = (
                f"The total time for tasks ({sum_task_minutes} minutes) does not match "
                f"the session duration ({int(total_minutes)} minutes).\n\n"
                f"Difference: {diff} minutes.\n\n"
                "Do you want to start the session anyway?"
            )
            if not messagebox.askyesno("Time Mismatch", message, parent=setup_window):
                return

        self.total_minutes = total_minutes
        self.end_time = end_time
            
        setup_window.destroy()
        self.start_tracking()
        
    def start_tracking(self):
        """Start tracking session"""
        # Save session
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO sessions (total_minutes, start_time)
            VALUES (?, ?)
        ''', (self.total_minutes, datetime.now()))
        self.session_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        self.current_task_index = 0
        self.elapsed_seconds = 0
        self.session_start_time = datetime.now()
        self.is_running = True
        
        # Start tracking thread
        self.stop_tracking_flag = False
        self.tracking_thread = threading.Thread(target=self.tracking_loop, daemon=True)
        self.tracking_thread.start()
        
        # Show floating widget
        self.show_floating_widget()
        
    def tracking_loop(self):
        """Background tracking thread"""
        while not self.stop_tracking_flag:
            if self.is_running:
                self.elapsed_seconds += 1
                
                # Track processes every 10 seconds
                if self.elapsed_seconds % 10 == 0:
                    self.track_active_process()
                    
                # Update widget
                if self.floating_widget and self.floating_widget.winfo_exists():
                    self.root.after(0, self.update_floating_widget)
                    
            time.sleep(1)
            
    def track_active_process(self):
        """Track active window/process"""
        try:
            import pygetwindow as gw
            active_window = gw.getActiveWindow()
            if active_window:
                process_name = active_window.title
                
                if self.current_task_index < len(self.tasks):
                    task_name = self.tasks[self.current_task_index]['name']
                    
                    if task_name not in self.process_tracking:
                        self.process_tracking[task_name] = []
                        
                    self.process_tracking[task_name].append({
                        'process': process_name,
                        'timestamp': datetime.now().isoformat()
                    })
        except Exception as e:
            print(f"Process tracking error: {e}")
            
    def update_floating_widget(self):
        """Update floating widget display"""
        if self.current_task_index >= len(self.tasks):
            return
            
        task = self.tasks[self.current_task_index]
        
        if self.floating_widget and self.floating_widget.winfo_exists():
            self.floating_widget.update_display(
                task,
                self.elapsed_seconds,
                self.is_running
            )
            
    def show_floating_widget(self):
        """Show floating timer widget"""
        if not self.floating_widget or not self.floating_widget.winfo_exists():
            self.floating_widget = FloatingWidget(self, self.root)
        else:
            self.floating_widget.deiconify()
            
    def hide_floating_widget(self):
        """Hide floating widget"""
        if self.floating_widget and self.floating_widget.winfo_exists():
            self.floating_widget.withdraw()
            
    def toggle_pause(self):
        """Toggle pause/resume"""
        self.is_running = not self.is_running
        
    def prev_task(self):
        """Move to previous task, cycling."""
        if not self.tasks or len(self.tasks) <= 1:
            return
        new_index = (self.current_task_index - 1 + len(self.tasks)) % len(self.tasks)
        self.switch_to_task(new_index)

    def next_task(self):
        """Move to next task, cycling."""
        if not self.tasks or len(self.tasks) <= 1:
            return
        new_index = (self.current_task_index + 1) % len(self.tasks)
        self.switch_to_task(new_index)
            
    def show_main_window(self):
        """Show task switcher and controls"""
        control_window = tk.Toplevel(self.root)
        control_window.title("Time Tracker Controls")
        control_window.geometry("400x500")
        control_window.configure(bg='#f7fafc')
        
        # Header
        header = tk.Frame(control_window, bg='#4fd1c5', height=60)
        header.pack(fill='x')
        header.pack_propagate(False)
        
        tk.Label(
            header,
            text="⚙️ Controls",
            font=('Arial', 16, 'bold'),
            bg='#4fd1c5',
            fg='white'
        ).pack(expand=True)
        
        content = tk.Frame(control_window, bg='#f7fafc', padx=20, pady=20)
        content.pack(fill='both', expand=True)
        
        # Task switcher
        tk.Label(
            content,
            text="Switch to Task:",
            font=('Arial', 11, 'bold'),
            bg='#f7fafc'
        ).pack(anchor='w', pady=(0, 10))
        
        for i, task in enumerate(self.tasks):
            status = "✓" if i < self.current_task_index else \
                    "▶" if i == self.current_task_index else "⏳"
            
            btn_bg = '#38b2ac' if i == self.current_task_index else '#e6fffa'
            btn_fg = 'white' if i == self.current_task_index else '#234e52'
            
            tk.Button(
                content,
                text=f"{status} {task['name']} ({task['minutes']} min)",
                font=('Arial', 10),
                bg=btn_bg,
                fg=btn_fg,
                bd=0,
                padx=15,
                pady=10,
                cursor='hand2',
                anchor='w',
                command=lambda idx=i: self.switch_to_task(idx)
            ).pack(fill='x', pady=2)
            
        # Actions
        tk.Label(
            content,
            text="Actions:",
            font=('Arial', 11, 'bold'),
            bg='#f7fafc'
        ).pack(anchor='w', pady=(20, 10))
        
        actions = [
            ("📊 Generate Report", self.generate_report),
            ("📚 View History", self.view_history),
            ("🔄 New Session", self.new_session),
            ("❌ End Session", self.end_session)
        ]
        
        for text, command in actions:
            tk.Button(
                content,
                text=text,
                font=('Arial', 10),
                bg='#edf2f7',
                fg='#2d3748',
                bd=0,
                padx=15,
                pady=10,
                cursor='hand2',
                anchor='w',
                command=command
            ).pack(fill='x', pady=2)
            
    def switch_to_task(self, task_index):
        """Switch to different task"""
        if task_index == self.current_task_index:
            return
            
        if self.current_task_index < len(self.tasks):
            self.tasks[self.current_task_index]['actual_seconds'] = self.elapsed_seconds
            
        self.current_task_index = task_index
        self.elapsed_seconds = self.tasks[task_index].get('actual_seconds', 0)
        self.update_floating_widget()
        
    def new_session(self):
        """Start new session"""
        if messagebox.askyesno("Confirm", "End current session and start new one?"):
            self.stop_tracking_flag = True
            self.hide_floating_widget()
            self.show_setup_dialog()
            
    def end_session(self):
        """End current session"""
        if messagebox.askyesno("Confirm", "End current session?"):
            self.generate_report()
            self.stop_tracking_flag = True
            self.hide_floating_widget()
            
    def generate_report(self):
        """Generate HTML report and save to database"""
        if not self.session_id:
            messagebox.showwarning("Warning", "No active session")
            return
            
        # Calculate totals
        total_actual_seconds = 0
        
        # Save task data
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        for i, task in enumerate(self.tasks):
            actual_seconds = task.get('actual_seconds', 0)
            if i == self.current_task_index:
                actual_seconds = self.elapsed_seconds
                
            total_actual_seconds += actual_seconds
            
            processes = json.dumps(self.process_tracking.get(task['name'], []))
            
            cursor.execute('''
                INSERT INTO session_tasks 
                (session_id, task_name, planned_minutes, actual_seconds, completed, processes)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (self.session_id, task['name'], task['minutes'], 
                  actual_seconds, i <= self.current_task_index, processes))
            
            session_task_id = cursor.lastrowid
            
            subtasks = task.get('subtasks', [])
            if subtasks:
                for subtask in subtasks:
                    cursor.execute('''
                        INSERT INTO sub_tasks (session_task_id, name, completed)
                        VALUES (?, ?, ?)
                    ''', (session_task_id, subtask['name'], subtask['completed']))
                  
        cursor.execute('''
            UPDATE sessions SET end_time = ? WHERE id = ?
        ''', (datetime.now(), self.session_id))
        
        conn.commit()
        
        # Create HTML report
        html_content = self.create_html_report_content()
        
        # Save report to database
        report_date = datetime.now().date()
        total_actual_minutes = total_actual_seconds / 60
        
        cursor.execute('''
            INSERT INTO daily_reports 
            (session_id, report_date, report_html, total_planned_minutes, 
             total_actual_minutes, tasks_count)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (self.session_id, report_date, html_content, 
              self.total_minutes, total_actual_minutes, len(self.tasks)))
        
        conn.commit()
        conn.close()
        
        # Save to file and open
        report_path = f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
            
        webbrowser.open(f'file://{os.path.abspath(report_path)}')
        messagebox.showinfo("Success", f"Report generated and saved to database!\n{report_path}")
        
    def create_html_report_content(self):
        """Create HTML report"""
        html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Time Tracking Report</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 40px 20px;
        }}
        .container {{
            max-width: 1000px;
            margin: 0 auto;
        }}
        .header {{
            background: white;
            padding: 40px;
            border-radius: 20px;
            margin-bottom: 30px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
        }}
        .header h1 {{
            font-size: 36px;
            color: #2d3748;
            margin-bottom: 10px;
        }}
        .header .date {{
            color: #718096;
            font-size: 16px;
        }}
        .stats {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }}
        .stat-card {{
            background: white;
            padding: 30px;
            border-radius: 15px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.2);
        }}
        .stat-value {{
            font-size: 48px;
            font-weight: bold;
            color: #667eea;
            margin-bottom: 10px;
        }}
        .stat-label {{
            color: #718096;
            font-size: 14px;
            text-transform: uppercase;
            letter-spacing: 1px;
        }}
        .tasks-section {{
            background: white;
            padding: 40px;
            border-radius: 20px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
        }}
        .task-item {{
            padding: 25px;
            border-bottom: 1px solid #e2e8f0;
            transition: background 0.3s;
        }}
        .task-item:hover {{
            background: #f7fafc;
        }}
        .task-item:last-child {{
            border-bottom: none;
        }}
        .task-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 15px;
        }}
        .task-name {{
            font-size: 20px;
            font-weight: bold;
            color: #2d3748;
        }}
        .task-status {{
            padding: 6px 12px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: bold;
        }}
        .status-completed {{ background: #c6f6d5; color: #22543d; }}
        .status-exceeded {{ background: #fed7d7; color: #742a2a; }}
        .status-good {{ background: #bee3f8; color: #2c5282; }}
        .task-times {{
            display: flex;
            gap: 30px;
            margin-bottom: 15px;
            color: #4a5568;
        }}
        .progress-bar {{
            width: 100%;
            height: 12px;
            background: #e2e8f0;
            border-radius: 10px;
            overflow: hidden;
            margin-bottom: 15px;
        }}
        .progress-fill {{
            height: 100%;
            background: linear-gradient(90deg, #667eea, #764ba2);
            border-radius: 10px;
            transition: width 0.5s;
        }}
        .progress-exceeded {{
            background: linear-gradient(90deg, #fc8181, #f56565) !important;
        }}
        .subtasks {{
            background: #f7fafc;
            padding: 15px;
            border-radius: 10px;
            font-size: 13px;
            color: #4a5568;
            margin-top: 15px;
        }}
        .subtasks-title {{
            font-weight: bold;
            margin-bottom: 8px;
            color: #2d3748;
        }}
        .subtask-item {{
            padding: 5px 0;
            border-bottom: 1px solid #e2e8f0;
        }}
        .subtask-item:last-child {{
            border-bottom: none;
        }}
        .subtask-item.completed {{
            text-decoration: line-through;
            color: #a0aec0;
        }}
        .processes {{
            background: #f7fafc;
            padding: 15px;
            border-radius: 10px;
            font-size: 13px;
            color: #4a5568;
            margin-top: 15px;
        }}
        .processes-title {{
            font-weight: bold;
            margin-bottom: 8px;
            color: #2d3748;
        }}
        .process-item {{
            padding: 5px 0;
            border-bottom: 1px solid #e2e8f0;
        }}
        .process-item:last-child {{
            border-bottom: none;
        }}
        @media print {{
            body {{ background: white; }}
            .header, .stat-card, .tasks-section {{ box-shadow: none; }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>⏱️ Time Tracking Report</h1>
            <div class="date">{datetime.now().strftime('%A, %B %d, %Y at %I:%M %p')}</div>
        </div>
        
        <div class="stats">
            <div class="stat-card">
                <div class="stat-value">{self.total_minutes}</div>
                <div class="stat-label">Planned Minutes</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{len(self.tasks)}</div>
                <div class="stat-label">Total Tasks</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{self.current_task_index + 1}</div>
                <div class="stat-label">Tasks Worked On</div>
            </div>
        </div>
        
        <div class="tasks-section">
            <h2 style="margin-bottom: 30px; color: #2d3748;">Task Details</h2>
"""
        
        for i, task in enumerate(self.tasks):
            actual_seconds = task.get('actual_seconds', 0)
            if i == self.current_task_index:
                actual_seconds = self.elapsed_seconds
                
            actual_minutes = actual_seconds / 60
            planned_minutes = task['minutes']
            progress_percent = (actual_minutes / planned_minutes) * 100 if planned_minutes > 0 else 0
            
            if i < self.current_task_index:
                status = '<span class="task-status status-completed">✓ Completed</span>'
            elif progress_percent > 100:
                status = '<span class="task-status status-exceeded">⚠️ Exceeded</span>'
            else:
                status = '<span class="task-status status-good">✓ On Track</span>'
            
            exceeded_class = 'progress-exceeded' if progress_percent > 100 else ''
            
            # Get process data
            processes = self.process_tracking.get(task['name'], [])
            process_summary = {}
            for p in processes:
                proc = p['process'][:60]
                process_summary[proc] = process_summary.get(proc, 0) + 1
            
            top_processes = sorted(process_summary.items(), key=lambda x: x[1], reverse=True)[:5]
            
            process_html = ""
            if top_processes:
                process_html = '<div class="processes"><div class="processes-title">🖥️ Active Windows:</div>'
                for proc, count in top_processes:
                    process_html += f'<div class="process-item">• {proc} <span style="color: #a0aec0;">({count} times)</span></div>'
                process_html += '</div>'

            # Subtasks HTML
            subtasks = task.get('subtasks', [])
            subtasks_html = ""
            if subtasks:
                completed_count = sum(1 for s in subtasks if s['completed'])
                subtasks_html = f'''
                <div class="subtasks">
                    <div class="subtasks-title">Subtasks ({completed_count}/{len(subtasks)} completed)</div>
                '''
                for subtask in subtasks:
                    if subtask['completed']:
                        subtasks_html += f'<div class="subtask-item completed">✓ {subtask["name"]}</div>'
                    else:
                        subtasks_html += f'<div class="subtask-item">○ {subtask["name"]}</div>'
                subtasks_html += '</div>'
            
            html_content += f"""
            <div class="task-item">
                <div class="task-header">
                    <div class="task-name">{task['name']}</div>
                    {status}
                </div>
                <div class="task-times">
                    <div><strong>Planned:</strong> {planned_minutes:.0f} min</div>
                    <div><strong>Actual:</strong> {actual_minutes:.1f} min</div>
                    <div><strong>Difference:</strong> {actual_minutes - planned_minutes:+.1f} min</div>
                </div>
                <div class="progress-bar">
                    <div class="progress-fill {exceeded_class}" style="width: {min(progress_percent, 100)}%"></div>
                </div>
                {subtasks_html}
                {process_html}
            </div>
"""
        
        html_content += """
        </div>
    </div>
</body>
</html>
"""
        
        return html_content
        
    def view_history(self):
        """View report history"""
        history_window = tk.Toplevel(self.root)
        history_window.title("Report History")
        history_window.geometry("800x600")
        history_window.configure(bg='#f7fafc')
        
        # Header
        header = tk.Frame(history_window, bg='#4fd1c5', height=60)
        header.pack(fill='x')
        header.pack_propagate(False)
        
        tk.Label(
            header,
            text="📚 Report History",
            font=('Arial', 16, 'bold'),
            bg='#4fd1c5',
            fg='white'
        ).pack(expand=True)
        
        # Content
        content = tk.Frame(history_window, bg='#f7fafc', padx=20, pady=20)
        content.pack(fill='both', expand=True)
        
        # Fetch reports from database
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT dr.id, dr.report_date, dr.total_planned_minutes, 
                   dr.total_actual_minutes, dr.tasks_count, dr.created_at,
                   s.start_time, s.end_time
            FROM daily_reports dr
            JOIN sessions s ON dr.session_id = s.id
            ORDER BY dr.created_at DESC
            LIMIT 50
        ''')
        reports = cursor.fetchall()
        conn.close()
        
        if not reports:
            tk.Label(
                content,
                text="No reports found in history",
                font=('Arial', 12),
                bg='#f7fafc',
                fg='#718096'
            ).pack(pady=50)
            return
        
        # Create treeview
        tree_frame = tk.Frame(content, bg='white')
        tree_frame.pack(fill='both', expand=True)
        
        scrollbar = tk.Scrollbar(tree_frame)
        scrollbar.pack(side='right', fill='y')
        
        tree = ttk.Treeview(
            tree_frame,
            columns=('Date', 'Planned', 'Actual', 'Tasks', 'Start', 'End'),
            show='headings',
            yscrollcommand=scrollbar.set
        )
        
        tree.heading('Date', text='Report Date')
        tree.heading('Planned', text='Planned (min)')
        tree.heading('Actual', text='Actual (min)')
        tree.heading('Tasks', text='Tasks')
        tree.heading('Start', text='Start Time')
        tree.heading('End', text='End Time')
        
        tree.column('Date', width=100)
        tree.column('Planned', width=100)
        tree.column('Actual', width=100)
        tree.column('Tasks', width=80)
        tree.column('Start', width=150)
        tree.column('End', width=150)
        
        scrollbar.config(command=tree.yview)
        
        # Insert data
        for report in reports:
            report_id, report_date, planned, actual, tasks, created_at, start_time, end_time = report
            
            start_display = datetime.fromisoformat(start_time).strftime('%I:%M %p') if start_time else 'N/A'
            end_display = datetime.fromisoformat(end_time).strftime('%I:%M %p') if end_time else 'N/A'
            
            tree.insert('', 'end', values=(
                report_date,
                f"{planned}",
                f"{actual:.1f}",
                tasks,
                start_display,
                end_display
            ), tags=(report_id,))
        
        tree.pack(fill='both', expand=True)
        
        # Buttons
        button_frame = tk.Frame(content, bg='#f7fafc')
        button_frame.pack(fill='x', pady=(10, 0))
        
        def view_selected_report():
            selection = tree.selection()
            if not selection:
                messagebox.showwarning("Warning", "Please select a report")
                return
            
            report_id = tree.item(selection[0])['tags'][0]
            
            # Fetch report HTML
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('SELECT report_html, report_date FROM daily_reports WHERE id = ?', (report_id,))
            result = cursor.fetchone()
            conn.close()
            
            if result:
                html_content, report_date = result
                report_path = f"report_history_{report_date}.html"
                with open(report_path, 'w', encoding='utf-8') as f:
                    f.write(html_content)
                webbrowser.open(f'file://{os.path.abspath(report_path)}')
        
        def delete_selected_report():
            selection = tree.selection()
            if not selection:
                messagebox.showwarning("Warning", "Please select a report")
                return
            
            if messagebox.askyesno("Confirm", "Delete selected report?"):
                report_id = tree.item(selection[0])['tags'][0]
                
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                cursor.execute('DELETE FROM daily_reports WHERE id = ?', (report_id,))
                conn.commit()
                conn.close()
                
                tree.delete(selection[0])
                messagebox.showinfo("Success", "Report deleted")
        
        tk.Button(
            button_frame,
            text="👁️ View Report",
            font=('Arial', 10),
            bg='#38b2ac',
            fg='white',
            bd=0,
            padx=20,
            pady=8,
            cursor='hand2',
            command=view_selected_report
        ).pack(side='left', padx=5)
        
        tk.Button(
            button_frame,
            text="🗑️ Delete Report",
            font=('Arial', 10),
            bg='#fc8181',
            fg='white',
            bd=0,
            padx=20,
            pady=8,
            cursor='hand2',
            command=delete_selected_report
        ).pack(side='left', padx=5)
        
        tk.Button(
            button_frame,
            text="Close",
            font=('Arial', 10),
            bg='#edf2f7',
            fg='#2d3748',
            bd=0,
            padx=20,
            pady=8,
            cursor='hand2',
            command=history_window.destroy
        ).pack(side='right', padx=5)
        
    def quit_app(self):
        """Quit application"""
        self.stop_tracking_flag = True
        if self.floating_widget:
            self.floating_widget.destroy()
        self.icon.stop()
        self.root.quit()
        
    def run(self):
        """Run application"""
        self.root.mainloop()


def main():
    app = TimeTrackerApp()
    app.run()

if __name__ == "__main__":
    main()

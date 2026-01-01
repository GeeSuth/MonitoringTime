"""
Windows Time Tracker - Background Application
A minimal desktop application that runs in background with a floating timer widget.

Requirements:
pip install psutil pygetwindow pystray pillow customtkinter

Usage:
python time_tracker.py
"""

import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
import customtkinter
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

# --- UI Classes ---
class FloatingWidget(customtkinter.CTkToplevel):
    """Floating timer widget that stays on top"""
    
    def __init__(self, parent, root):
        super().__init__(root)
        self.app = parent
        
        # Window configuration
        self.overrideredirect(True)
        self.attributes('-topmost', True)
        
        # Position in top-right corner
        screen_width = self.winfo_screenwidth()
        self.geometry(f"280x350+{screen_width-300}+20")
        
        # Make draggable
        self.bind('<Button-1>', self.start_move)
        self.bind('<B1-Motion>', self.do_move)
        
        self.configure(fg_color='#2d3748')

        # Task name
        self.task_label = customtkinter.CTkLabel(
            self, text="No Task", font=('Arial', 12, 'bold'),
        )
        self.task_label.pack(pady=(8, 2), padx=10, fill='x')
        
        # Timer
        self.timer_label = customtkinter.CTkLabel(
            self, text="00:00:00", font=('Arial', 24, 'bold'),
            text_color='#4fd1c5'
        )
        self.timer_label.pack(pady=2)
        
        # Remaining time
        self.remaining_label = customtkinter.CTkLabel(
            self, text="", font=('Arial', 10),
            text_color='#a0aec0'
        )
        self.remaining_label.pack(pady=2)
        
        # Progress bar
        self.progress_bar = customtkinter.CTkProgressBar(self, height=8)
        self.progress_bar.set(0)
        self.progress_bar.pack(fill='x', padx=10, pady=(5, 5))

        # Separator
        customtkinter.CTkFrame(self, height=1, fg_color='gray').pack(fill='x', padx=10, pady=5)

        # Subtasks
        subtask_container = customtkinter.CTkFrame(self, fg_color='transparent')
        subtask_container.pack(fill='both', expand=True, padx=10, pady=(0, 10))

        add_frame = customtkinter.CTkFrame(subtask_container, fg_color='transparent')
        add_frame.pack(fill='x', pady=5)
        self.new_subtask_entry = customtkinter.CTkEntry(
            add_frame, font=('Arial', 10), placeholder_text="Add a subtask..."
        )
        self.new_subtask_entry.pack(side='left', fill='x', expand=True, ipady=3)
        self.new_subtask_entry.bind("<Return>", lambda e: self.add_subtask())

        self.subtask_list_frame = customtkinter.CTkScrollableFrame(subtask_container, fg_color='transparent')
        self.subtask_list_frame.pack(fill='both', expand=True)

        for widget in [self, self.task_label, self.timer_label, self.remaining_label, self.progress_bar]:
            widget.bind('<Button-3>', self.show_task_menu)
        
        self.x = 0
        self.y = 0
        self.current_subtasks_cache = ""
        self.current_task_name_cache = ""

    def add_subtask(self):
        subtask_name = self.new_subtask_entry.get().strip()
        if not subtask_name or not self.app.tasks:
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
            customtkinter.CTkLabel(
                self.subtask_list_frame, text="No subtasks yet.", 
                text_color='#a0aec0', font=('Arial', 9)
            ).pack(pady=10)
            return

        for i, subtask in enumerate(task['subtasks']):
            subtask_frame = customtkinter.CTkFrame(self.subtask_list_frame, fg_color='transparent')
            subtask_frame.pack(fill='x', anchor='w', pady=1)

            def toggle_subtask_handler(event=None, idx=i):
                task['subtasks'][idx]['completed'] = not task['subtasks'][idx]['completed']
                self.render_subtasks(task)

            if subtask['completed']:
                checkmark_text = "✓"
                fg_color = '#718096'
                font_style = 'overstrike'
            else:
                checkmark_text = "○"
                fg_color = '#a0aec0'
                font_style = 'normal'

            checkmark_label = customtkinter.CTkLabel(
                subtask_frame, text=checkmark_text, font=('Arial', 14),
                text_color='#4fd1c5'
            )
            checkmark_label.pack(side='left')
            checkmark_label.bind("<Button-1>", toggle_subtask_handler)
            
            text_label = customtkinter.CTkLabel(
                subtask_frame, text=subtask['name'], font=('Arial', 10, font_style),
                text_color=fg_color, anchor='w', justify='left'
            )
            text_label.pack(side='left', fill='x', expand=True, padx=5)
            text_label.bind("<Button-1>", toggle_subtask_handler)

            delete_btn = customtkinter.CTkButton(
                subtask_frame, text="✕", font=('Arial', 12),
                fg_color='transparent', text_color='#c53030',
                hover_color='#4a2a2a', width=20,
                command=lambda idx=i: self.delete_subtask(task, idx)
            )
            delete_btn.pack(side='right')

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
        task_menu = tk.Menu(self, tearoff=0, bg="#2d3748", fg="white",
                            activebackground='#4fd1c5', activeforeground='white',
                            font=('Arial', 10))

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
        task_name = task['name']
        planned_minutes = task['minutes']

        self.task_label.configure(text=task_name[:30])
        
        hours, rem = divmod(elapsed_seconds, 3600)
        minutes, seconds = divmod(rem, 60)
        self.timer_label.configure(text=f"{int(hours):02d}:{int(minutes):02d}:{int(seconds):02d}")
        
        planned_seconds = planned_minutes * 60
        remaining = planned_seconds - elapsed_seconds
        
        if remaining > 0:
            rem_min, rem_sec = divmod(remaining, 60)
            self.remaining_label.configure(
                text=f"{int(rem_min)}m {int(rem_sec)}s left",
                text_color='#68d391'
            )
        else:
            self.remaining_label.configure(text="Time exceeded!", text_color='#fc8181')
        
        if remaining < 0 and elapsed_seconds % 2 == 0:
            self.configure(fg_color='#742a2a')
        else:
            self.configure(fg_color='#2d3748')

        progress_percent = min((elapsed_seconds / planned_seconds), 1.0) if planned_seconds > 0 else 0
        self.progress_bar.set(progress_percent)
        self.progress_bar.configure(progress_color='#fc8181' if remaining < 0 else '#4fd1c5')
        
        subtasks_json = json.dumps(task.get('subtasks', []))
        if task_name != self.current_task_name_cache or subtasks_json != self.current_subtasks_cache:
            self.current_task_name_cache = task_name
            self.current_subtasks_cache = subtasks_json
            self.render_subtasks(task)


class SetupWindow(customtkinter.CTkToplevel):
    def __init__(self, app):
        super().__init__(app.root)
        self.app = app
        
        self.title("Time Tracker Setup")
        self.geometry("500x600")

        customtkinter.CTkLabel(self, text="⏰ Time Tracker Setup", font=('Arial', 24, 'bold'), text_color="#4fd1c5").pack(pady=20)
        
        content = customtkinter.CTkFrame(self, fg_color="transparent")
        content.pack(fill='both', expand=True, padx=20)
        
        customtkinter.CTkLabel(content, text="Session End Time:").pack(anchor='w', pady=(10, 5))
        
        time_frame = customtkinter.CTkFrame(content, fg_color="transparent")
        time_frame.pack(fill='x', pady=(0, 5))
        
        now = datetime.now()
        default_end = (now + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
        h12 = default_end.hour % 12
        if h12 == 0: h12 = 12

        self.hour_cb = customtkinter.CTkComboBox(time_frame, width=70, values=[str(i) for i in range(1, 13)])
        self.hour_cb.set(str(h12))
        self.minute_cb = customtkinter.CTkComboBox(time_frame, width=70, values=[f"{i:02d}" for i in range(60)])
        self.minute_cb.set(f"{default_end.minute:02d}")
        self.ampm_cb = customtkinter.CTkComboBox(time_frame, width=70, values=["AM", "PM"], state="readonly")
        self.ampm_cb.set(default_end.strftime("%p"))
        
        self.hour_cb.pack(side='left', padx=(0,5))
        self.minute_cb.pack(side='left', padx=5)
        self.ampm_cb.pack(side='left', padx=5)

        self.duration_label = customtkinter.CTkLabel(time_frame, text="")
        self.duration_label.pack(side='left', padx=10)

        for cb in [self.hour_cb, self.minute_cb, self.ampm_cb]:
            cb.configure(command=self._update_duration_label)

        self.remaining_time_label = customtkinter.CTkLabel(content, text="Unallocated Time: 0 min")
        self.remaining_time_label.pack(anchor='w', pady=(5, 5))

        customtkinter.CTkButton(content, text="📋 Load Saved Tasks", command=self._load_templates).pack(pady=10)
        
        customtkinter.CTkLabel(content, text="Tasks:").pack(anchor='w', pady=(10, 5))
        
        self.task_list_frame = customtkinter.CTkScrollableFrame(content)
        self.task_list_frame.pack(fill='both', expand=True)

        customtkinter.CTkButton(content, text="+ Add Task", command=self._add_task_row).pack(pady=10)
        
        button_frame = customtkinter.CTkFrame(self, fg_color="transparent")
        button_frame.pack(fill='x', pady=15, padx=20)
        
        customtkinter.CTkButton(button_frame, text="💾 Save as Template", command=self._save_template).pack(side='left', expand=True, padx=5)
        customtkinter.CTkButton(button_frame, text="▶ Start Tracking", command=self._start_tracking, fg_color="#38b2ac").pack(side='right', expand=True, padx=5)
        
        self._add_task_row(name="First Task")
        self._update_duration_label()

        self.protocol("WM_DELETE_WINDOW", self.app.quit_app)

    def _parse_time(self, time_str):
        now = datetime.now()
        try:
            end = datetime.strptime(f"{now.date()} {time_str}", "%Y-%m-%d %I:%M %p")
            if end <= now:
                end += timedelta(days=1)
            return end
        except ValueError:
            return None

    def _update_duration_label(self, *args):
        time_str = f"{self.hour_cb.get()}:{self.minute_cb.get()} {self.ampm_cb.get()}"
        end_time = self._parse_time(time_str)
        if end_time:
            duration = end_time - datetime.now()
            total_minutes = duration.total_seconds() / 60
            self.app.setup_session_minutes = total_minutes
            if total_minutes > 0:
                hours, minutes = divmod(total_minutes, 60)
                self.duration_label.configure(text=f"(≈ {int(hours)}h {int(minutes)}m)")
            else:
                self.duration_label.configure(text="(in the past!)")
        else:
            self.app.setup_session_minutes = 0
            self.duration_label.configure(text="(invalid time)")
        self._update_remaining_time()

    def _update_remaining_time(self):
        remaining = int(self.app.setup_session_minutes - self.app.setup_total_task_minutes)
        text = f"Unallocated Time: {remaining} min"
        color = 'white' if remaining >= 0 else '#fc8181'
        self.remaining_time_label.configure(text=text, text_color=color)

    def _add_task_row(self, name="", minutes="30"):
        row = customtkinter.CTkFrame(self.task_list_frame, fg_color="transparent")
        row.pack(fill='x', pady=2)
        
        name_entry = customtkinter.CTkEntry(row, placeholder_text="Task Name")
        name_entry.insert(0, name)
        name_entry.pack(side='left', padx=5, fill='x', expand=True)
        
        minutes_entry = customtkinter.CTkEntry(row, width=70)
        minutes_entry.insert(0, minutes)
        minutes_entry.pack(side='left', padx=5)
        minutes_entry.bind("<KeyRelease>", lambda e: self._update_total_task_minutes())

        def delete_row():
            row.destroy()
            self._update_total_task_minutes()

        customtkinter.CTkButton(row, text="✕", width=30, fg_color="#c53030", command=delete_row).pack(side='left', padx=5)
        self._update_total_task_minutes()

    def _load_templates(self):
        templates = self.app.get_task_templates()
        if not templates:
            messagebox.showinfo("Info", "No saved templates found")
            return
            
        for widget in self.task_list_frame.winfo_children():
            widget.destroy()
            
        for name, minutes in templates:
            self._add_task_row(name=name, minutes=str(minutes))
            
        self._update_total_task_minutes()

    def _update_total_task_minutes(self):
        total_minutes = 0
        for row in self.task_list_frame.winfo_children():
            entries = [w for w in row.winfo_children() if isinstance(w, customtkinter.CTkEntry)]
            if len(entries) >= 2:
                try:
                    total_minutes += int(entries[1].get())
                except ValueError:
                    pass
        self.app.setup_total_task_minutes = total_minutes
        self._update_remaining_time()
            
    def _save_template(self):
        tasks = self._get_tasks()
        if not tasks:
            messagebox.showwarning("Warning", "No tasks to save!")
            return
        
        self.app.save_tasks_as_template(tasks)
        messagebox.showinfo("Success", "Tasks saved as template!")
        
    def _get_tasks(self):
        tasks = []
        for row in self.task_list_frame.winfo_children():
            entries = [w for w in row.winfo_children() if isinstance(w, customtkinter.CTkEntry)]
            if len(entries) >= 2:
                try:
                    name = entries[0].get().strip()
                    minutes = int(entries[1].get())
                    if name and minutes > 0:
                        tasks.append({'name': name, 'minutes': minutes, 'subtasks': []})
                except ValueError:
                    pass
        return tasks
        
    def _start_tracking(self):
        end_time_str = f"{self.hour_cb.get()}:{self.minute_cb.get()} {self.ampm_cb.get()}"
        end_time = self._parse_time(end_time_str)

        if not end_time:
            messagebox.showerror("Error", "Invalid end time format. Use HH:MM AM/PM.")
            return

        total_minutes = (end_time - datetime.now()).total_seconds() / 60
        if total_minutes <= 0:
            messagebox.showerror("Error", "End time must be in the future!")
            return
            
        tasks = self._get_tasks()
        
        if not tasks:
            messagebox.showerror("Error", "Please add at least one task!")
            return

        sum_task_minutes = sum(task['minutes'] for task in tasks)
        if int(total_minutes) != sum_task_minutes:
            diff = abs(int(total_minutes) - sum_task_minutes)
            message = (
                f"Total task time ({sum_task_minutes} min) doesn't match session duration ({int(total_minutes)} min).\n"
                f"Difference: {diff} minutes.\n\nContinue?"
            )
            if not messagebox.askyesno("Time Mismatch", message, parent=self):
                return
        
        self.app.start_session(tasks, total_minutes, end_time)
        self.withdraw()

class ControlWindow(customtkinter.CTkToplevel):
    def __init__(self, app):
        super().__init__(app.root)
        self.app = app
        
        self.title("Time Tracker Controls")
        self.geometry("400x500")

        customtkinter.CTkLabel(self, text="⚙️ Controls", font=('Arial', 24, 'bold')).pack(pady=20)
        
        content = customtkinter.CTkFrame(self, fg_color="transparent")
        content.pack(fill='both', expand=True, padx=20)
        
        customtkinter.CTkLabel(content, text="Switch to Task:").pack(anchor='w', pady=(0, 10))
        
        for i, task in enumerate(self.app.tasks):
            status = "✓" if i < self.app.current_task_index else "▶" if i == self.app.current_task_index else "⏳"
            fg_color = '#38b2ac' if i == self.app.current_task_index else 'transparent'
            
            customtkinter.CTkButton(
                content,
                text=f"{status} {task['name']} ({task['minutes']} min)",
                fg_color=fg_color,
                anchor='w',
                command=lambda idx=i: self.app.switch_to_task(idx)
            ).pack(fill='x', pady=2)
            
        customtkinter.CTkLabel(content, text="Actions:").pack(anchor='w', pady=(20, 10))
        
        actions_frame = customtkinter.CTkFrame(content, fg_color="transparent")
        actions_frame.pack(fill='both', expand=True)

        actions = [
            ("📊 Generate Report", self.app.generate_report),
            ("📚 View History", self.app.view_history),
            ("🔄 New Session", self.app.new_session),
            ("❌ End Session", self.app.end_session)
        ]
        
        for text, command in actions:
            customtkinter.CTkButton(actions_frame, text=text, anchor='w', command=command).pack(fill='x', pady=2)

class HistoryWindow(customtkinter.CTkToplevel):
    def __init__(self, app):
        super().__init__(app.root)
        self.app = app
        self.db_path = app.db_path
        
        self.title("Report History")
        self.geometry("800x600")

        customtkinter.CTkLabel(self, text="📚 Report History", font=('Arial', 24, 'bold')).pack(pady=20)
        
        content = customtkinter.CTkFrame(self, fg_color="transparent")
        content.pack(fill='both', expand=True, padx=20)
        
        reports = self._fetch_reports()
        
        if not reports:
            customtkinter.CTkLabel(content, text="No reports found in history").pack(pady=50)
            return
        
        tree_frame = customtkinter.CTkFrame(content)
        tree_frame.pack(fill='both', expand=True)

        style = ttk.Style()
        style.theme_use("default")
        style.configure("Treeview", background="#2a2d2e", foreground="white", fieldbackground="#2a2d2e", borderwidth=0)
        style.map('Treeview', background=[('selected', '#2a2d2e')], foreground=[('selected', '#4fd1c5')])
        style.configure("Treeview.Heading", background="#2a2d2e", foreground="white", relief="flat")
        style.map("Treeview.Heading", background=[('active', '#3a3d3e')])

        scrollbar = customtkinter.CTkScrollbar(tree_frame)
        scrollbar.pack(side='right', fill='y')
        
        self.tree = ttk.Treeview(
            tree_frame,
            columns=('Date', 'Planned', 'Actual', 'Tasks', 'Start', 'End'),
            show='headings',
            yscrollcommand=scrollbar.set,
            selectmode="browse"
        )
        
        self.tree.heading('Date', text='Report Date')
        self.tree.heading('Planned', text='Planned (min)')
        self.tree.heading('Actual', text='Actual (min)')
        self.tree.heading('Tasks', text='Tasks')
        self.tree.heading('Start', text='Start Time')
        self.tree.heading('End', text='End Time')
        
        for col in self.tree['columns']:
            self.tree.column(col, width=100)

        scrollbar.configure(command=self.tree.yview)
        
        for report in reports:
            report_id, report_date, planned, actual, tasks, created_at, start_time, end_time = report
            start_display = datetime.fromisoformat(start_time).strftime('%I:%M %p') if start_time else 'N/A'
            end_display = datetime.fromisoformat(end_time).strftime('%I:%M %p') if end_time else 'N/A'
            self.tree.insert('', 'end', values=(report_date, f"{planned}", f"{actual:.1f}", tasks, start_display, end_display), tags=(report_id,))
        
        self.tree.pack(fill='both', expand=True)
        
        button_frame = customtkinter.CTkFrame(content, fg_color="transparent")
        button_frame.pack(fill='x', pady=(10, 0))
        
        customtkinter.CTkButton(button_frame, text="👁️ View Report", command=self._view_report).pack(side='left', padx=5)
        customtkinter.CTkButton(button_frame, text="🗑️ Delete Report", command=self._delete_report, fg_color="#c53030").pack(side='left', padx=5)
        customtkinter.CTkButton(button_frame, text="Close", command=self.destroy).pack(side='right', padx=5)

    def _fetch_reports(self):
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
        return reports

    def _view_report(self):
        selection = self.tree.selection()
        if not selection:
            messagebox.showwarning("Warning", "Please select a report")
            return
        
        report_id = self.tree.item(selection[0])['tags'][0]
        
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
    
    def _delete_report(self):
        selection = self.tree.selection()
        if not selection:
            messagebox.showwarning("Warning", "Please select a report")
            return
        
        if messagebox.askyesno("Confirm", "Delete selected report?"):
            report_id = self.tree.item(selection[0])['tags'][0]
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('DELETE FROM daily_reports WHERE id = ?', (report_id,))
            conn.commit()
            conn.close()
            
            self.tree.delete(selection[0])
            messagebox.showinfo("Success", "Report deleted")


class TimeTrackerApp:
    def __init__(self):
        customtkinter.set_appearance_mode("dark")
        customtkinter.set_default_color_theme("blue")

        self.root = customtkinter.CTk()
        self.root.withdraw()
        
        self.db_path = "time_tracker.db"
        self.init_database()
        
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
        
        self.tracking_thread = None
        self.stop_tracking_flag = False
        
        self.floating_widget = None
        self.setup_window = None
        self.control_window = None
        self.history_window = None
        
        self.setup_tray_icon()
        
        self.root.after(100, self.show_setup_dialog)
        
    def setup_tray_icon(self):
        image = Image.new('RGB', (64, 64), color='#4fd1c5')
        draw = ImageDraw.Draw(image)
        draw.rectangle([16, 16, 48, 48], fill='#2d3748')
        
        menu = pystray.Menu(
            pystray.MenuItem('Show Timer', lambda: self.root.after(0, self.show_floating_widget)),
            pystray.MenuItem('Hide Timer', lambda: self.root.after(0, self.hide_floating_widget)),
            pystray.MenuItem('Settings', lambda: self.root.after(0, self.show_main_window)),
            pystray.MenuItem('Report', lambda: self.root.after(0, self.generate_report)),
            pystray.MenuItem('History', lambda: self.root.after(0, self.view_history)),
            pystray.MenuItem('Exit', lambda: self.root.after(0, self.quit_app))
        )
        
        self.icon = pystray.Icon('TimeTracker', image, 'Time Tracker', menu)
        threading.Thread(target=self.icon.run, daemon=True).start()
        
    def init_database(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''CREATE TABLE IF NOT EXISTS task_templates (id INTEGER PRIMARY KEY, name TEXT NOT NULL, default_minutes INTEGER NOT NULL)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS sessions (id INTEGER PRIMARY KEY, total_minutes INTEGER, start_time TIMESTAMP, end_time TIMESTAMP)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS session_tasks (id INTEGER PRIMARY KEY, session_id INTEGER, task_name TEXT, planned_minutes INTEGER, actual_seconds INTEGER, completed BOOLEAN, processes TEXT)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS sub_tasks (id INTEGER PRIMARY KEY, session_task_id INTEGER, name TEXT, completed BOOLEAN)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS daily_reports (id INTEGER PRIMARY KEY, session_id INTEGER, report_date DATE, report_html TEXT, total_planned_minutes INTEGER, total_actual_minutes INTEGER, tasks_count INTEGER)''')
        
        conn.commit()
        conn.close()

    def show_setup_dialog(self):
        if self.setup_window is None or not self.setup_window.winfo_exists():
            self.setup_window = SetupWindow(self)
        self.setup_window.deiconify()

    def start_session(self, tasks, total_minutes, end_time):
        self.tasks = tasks
        self.total_minutes = total_minutes
        self.end_time = end_time
        self.start_tracking()

    def start_tracking(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('INSERT INTO sessions (total_minutes, start_time) VALUES (?, ?)', (self.total_minutes, datetime.now()))
        self.session_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        self.current_task_index = 0
        self.elapsed_seconds = 0
        self.session_start_time = datetime.now()
        self.is_running = True
        
        self.stop_tracking_flag = False
        self.tracking_thread = threading.Thread(target=self.tracking_loop, daemon=True)
        self.tracking_thread.start()
        
        self.show_floating_widget()
        
    def tracking_loop(self):
        while not self.stop_tracking_flag:
            if self.is_running:
                self.elapsed_seconds += 1
                
                if self.elapsed_seconds % 10 == 0:
                    self.track_active_process()
                    
                if self.floating_widget and self.floating_widget.winfo_exists():
                    self.root.after(0, self.update_floating_widget)
                    
            time.sleep(1)
            
    def track_active_process(self):
        try:
            import pygetwindow as gw
            active_window = gw.getActiveWindow()
            if active_window and self.current_task_index < len(self.tasks):
                task_name = self.tasks[self.current_task_index]['name']
                if task_name not in self.process_tracking:
                    self.process_tracking[task_name] = []
                self.process_tracking[task_name].append({'process': active_window.title, 'timestamp': datetime.now().isoformat()})
        except Exception as e:
            print(f"Process tracking error: {e}")
            
    def update_floating_widget(self):
        if self.current_task_index < len(self.tasks) and self.floating_widget and self.floating_widget.winfo_exists():
            task = self.tasks[self.current_task_index]
            self.floating_widget.update_display(task, self.elapsed_seconds, self.is_running)
            
    def show_floating_widget(self):
        if not self.floating_widget or not self.floating_widget.winfo_exists():
            self.floating_widget = FloatingWidget(self, self.root)
        self.floating_widget.deiconify()
            
    def hide_floating_widget(self):
        if self.floating_widget and self.floating_widget.winfo_exists():
            self.floating_widget.withdraw()
            
    def toggle_pause(self):
        self.is_running = not self.is_running
        
    def switch_to_task(self, task_index):
        if task_index == self.current_task_index or not (0 <= task_index < len(self.tasks)):
            return
            
        if self.current_task_index < len(self.tasks):
            self.tasks[self.current_task_index]['actual_seconds'] = self.elapsed_seconds
            
        self.current_task_index = task_index
        self.elapsed_seconds = self.tasks[task_index].get('actual_seconds', 0)
        self.update_floating_widget()
        
    def show_main_window(self):
        if self.control_window is None or not self.control_window.winfo_exists():
            self.control_window = ControlWindow(self)
        self.control_window.deiconify()
            
    def new_session(self):
        if messagebox.askyesno("Confirm", "End current session and start new one?"):
            self.stop_tracking_flag = True
            self.hide_floating_widget()
            self.show_setup_dialog()
            
    def end_session(self):
        if messagebox.askyesno("Confirm", "End current session?"):
            self.generate_report()
            self.stop_tracking_flag = True
            self.hide_floating_widget()
            
    def generate_report(self):
        if not self.session_id:
            messagebox.showwarning("Warning", "No active session")
            return
            
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        total_actual_seconds = 0
        for i, task in enumerate(self.tasks):
            actual_seconds = self.elapsed_seconds if i == self.current_task_index else task.get('actual_seconds', 0)
            total_actual_seconds += actual_seconds
            processes = json.dumps(self.process_tracking.get(task['name'], []))
            
            cursor.execute('INSERT INTO session_tasks (session_id, task_name, planned_minutes, actual_seconds, completed, processes) VALUES (?, ?, ?, ?, ?, ?)',
                           (self.session_id, task['name'], task['minutes'], actual_seconds, i <= self.current_task_index, processes))
            
            session_task_id = cursor.lastrowid
            if 'subtasks' in task:
                for subtask in task['subtasks']:
                    cursor.execute('INSERT INTO sub_tasks (session_task_id, name, completed) VALUES (?, ?, ?)',
                                   (session_task_id, subtask['name'], subtask['completed']))
                  
        cursor.execute('UPDATE sessions SET end_time = ? WHERE id = ?', (datetime.now(), self.session_id))
        conn.commit()
        
        html_content = self.create_html_report_content()
        total_actual_minutes = total_actual_seconds / 60
        
        cursor.execute('INSERT INTO daily_reports (session_id, report_date, report_html, total_planned_minutes, total_actual_minutes, tasks_count) VALUES (?, ?, ?, ?, ?, ?)',
                       (self.session_id, datetime.now().date(), html_content, self.total_minutes, total_actual_minutes, len(self.tasks)))
        
        conn.commit()
        conn.close()
        
        report_path = f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
        with open(report_path, 'w', encoding='utf-8') as f: f.write(html_content)
            
        webbrowser.open(f'file://{os.path.abspath(report_path)}')
        messagebox.showinfo("Success", f"Report generated!\n{report_path}")
        
    def create_html_report_content(self):
        # This method is long but is for generating a static HTML file. No need to refactor for now.
        return f"""
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
        .container {{ max-width: 1000px; margin: 0 auto; }}
        .header {{ background: white; padding: 40px; border-radius: 20px; margin-bottom: 30px; box-shadow: 0 20px 60px rgba(0,0,0,0.3); }}
        .header h1 {{ font-size: 36px; color: #2d3748; margin-bottom: 10px; }}
        .header .date {{ color: #718096; font-size: 16px; }}
        .stats {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin-bottom: 30px; }}
        .stat-card {{ background: white; padding: 30px; border-radius: 15px; box-shadow: 0 10px 30px rgba(0,0,0,0.2); }}
        .stat-value {{ font-size: 48px; font-weight: bold; color: #667eea; margin-bottom: 10px; }}
        .stat-label {{ color: #718096; font-size: 14px; text-transform: uppercase; letter-spacing: 1px; }}
        .tasks-section {{ background: white; padding: 40px; border-radius: 20px; box-shadow: 0 20px 60px rgba(0,0,0,0.3); }}
        .task-item {{ padding: 25px; border-bottom: 1px solid #e2e8f0; }}
        .task-item:last-child {{ border-bottom: none; }}
        .task-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px; }}
        .task-name {{ font-size: 20px; font-weight: bold; color: #2d3748; }}
        .task-status {{ padding: 6px 12px; border-radius: 20px; font-size: 12px; font-weight: bold; }}
        .status-completed {{ background: #c6f6d5; color: #22543d; }}
        .status-exceeded {{ background: #fed7d7; color: #742a2a; }}
        .status-good {{ background: #bee3f8; color: #2c5282; }}
        .task-times {{ display: flex; gap: 30px; margin-bottom: 15px; color: #4a5568; }}
        .progress-bar {{ width: 100%; height: 12px; background: #e2e8f0; border-radius: 10px; overflow: hidden; margin-bottom: 15px; }}
        .progress-fill {{ height: 100%; background: linear-gradient(90deg, #667eea, #764ba2); border-radius: 10px; }}
        .progress-exceeded {{ background: linear-gradient(90deg, #fc8181, #f56565) !important; }}
        .subtasks, .processes {{ background: #f7fafc; padding: 15px; border-radius: 10px; font-size: 13px; color: #4a5568; margin-top: 15px; }}
        .subtasks-title, .processes-title {{ font-weight: bold; margin-bottom: 8px; color: #2d3748; }}
        .subtask-item, .process-item {{ padding: 5px 0; border-bottom: 1px solid #e2e8f0; }}
        .subtask-item:last-child, .process-item:last-child {{ border-bottom: none; }}
        .subtask-item.completed {{ text-decoration: line-through; color: #a0aec0; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>⏱️ Time Tracking Report</h1>
            <div class="date">{datetime.now().strftime('%A, %B %d, %Y at %I:%M %p')}</div>
        </div>
        <div class="stats">
            <div class="stat-card"><div class="stat-value">{int(self.total_minutes)}</div><div class="stat-label">Planned Minutes</div></div>
            <div class="stat-card"><div class="stat-value">{len(self.tasks)}</div><div class="stat-label">Total Tasks</div></div>
            <div class="stat-card"><div class="stat-value">{self.current_task_index + 1}</div><div class="stat-label">Tasks Worked On</div></div>
        </div>
        <div class="tasks-section"><h2 style="margin-bottom: 30px; color: #2d3748;">Task Details</h2>
        {''.join(self.get_task_html())}
        </div>
    </div>
</body>
</html>"""
        
    def get_task_html(self):
        task_html_parts = []
        for i, task in enumerate(self.tasks):
            actual_seconds = self.elapsed_seconds if i == self.current_task_index else task.get('actual_seconds', 0)
            actual_minutes = actual_seconds / 60
            planned_minutes = task['minutes']
            progress_percent = (actual_minutes / planned_minutes) * 100 if planned_minutes > 0 else 0
            status = ('<span class="task-status status-completed">✓ Completed</span>' if i < self.current_task_index else 
                      '<span class="task-status status-exceeded">⚠️ Exceeded</span>' if progress_percent > 100 else 
                      '<span class="task-status status-good">✓ On Track</span>')
            exceeded_class = 'progress-exceeded' if progress_percent > 100 else ''
            
            top_processes = sorted(self.process_tracking.get(task['name'], []), key=lambda p: p['timestamp'], reverse=True)[:5]
            process_html = ""
            if top_processes:
                process_html = '<div class="processes"><div class="processes-title">🖥️ Active Windows:</div>' + ''.join([f'<div class="process-item">• {p["process"][:60]}</div>' for p in top_processes]) + '</div>'

            subtasks = task.get('subtasks', [])
            subtasks_html = ""
            if subtasks:
                completed_count = sum(1 for s in subtasks if s['completed'])
                subtasks_html = f'<div class="subtasks"><div class="subtasks-title">Subtasks ({completed_count}/{len(subtasks)})</div>' + ''.join([f'<div class="subtask-item {"completed" if s["completed"] else ""}">{"✓" if s["completed"] else "○"} {s["name"]}</div>' for s in subtasks]) + '</div>'
            
            task_html_parts.append(f"""
            <div class="task-item">
                <div class="task-header"><div class="task-name">{task['name']}</div>{status}</div>
                <div class="task-times">
                    <div><strong>Planned:</strong> {planned_minutes:.0f} min</div>
                    <div><strong>Actual:</strong> {actual_minutes:.1f} min</div>
                    <div><strong>Difference:</strong> {actual_minutes - planned_minutes:+.1f} min</div>
                </div>
                <div class="progress-bar"><div class="progress-fill {exceeded_class}" style="width: {min(progress_percent, 100)}%"></div></div>
                {subtasks_html}{process_html}
            </div>""")
        return task_html_parts

    def view_history(self):
        if self.history_window is None or not self.history_window.winfo_exists():
            self.history_window = HistoryWindow(self)
        self.history_window.deiconify()

    def get_task_templates(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT name, default_minutes FROM task_templates ORDER BY name')
        templates = cursor.fetchall()
        conn.close()
        return templates

    def save_tasks_as_template(self, tasks):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.executemany('INSERT INTO task_templates (name, default_minutes) VALUES (?, ?)', 
                           [(task['name'], task['minutes']) for task in tasks])
        conn.commit()
        conn.close()
        
    def quit_app(self):
        self.stop_tracking_flag = True
        if self.floating_widget: self.floating_widget.destroy()
        if self.setup_window: self.setup_window.destroy()
        if self.control_window: self.control_window.destroy()
        if self.history_window: self.history_window.destroy()
        self.icon.stop()
        self.root.quit()
        
    def run(self):
        self.root.mainloop()

def main():
    app = TimeTrackerApp()
    app.run()

if __name__ == "__main__":
    main()

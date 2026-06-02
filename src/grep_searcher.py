import os
import re
import threading
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GLib, Pango

class GrepSearcherPopup(Gtk.Window):
    def __init__(self, parent_window):
        super().__init__(type=Gtk.WindowType.TOPLEVEL)
        self.parent_window = parent_window
        self.set_transient_for(parent_window)
        self.set_modal(True)
        self.set_decorated(False)
        self.set_default_size(700, 450)
        self.set_position(Gtk.WindowPosition.CENTER_ON_PARENT)
        
        self.search_thread = None
        self.search_cancelled = threading.Event()
        
        # Main layout
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        main_box.set_border_width(12)
        self.add(main_box)
        
        # Search entry
        self.entry = Gtk.Entry()
        self.entry.set_placeholder_text("Search text in files...")
        self.entry.set_icon_from_icon_name(Gtk.EntryIconPosition.PRIMARY, "system-search")
        self.entry.connect("changed", self.on_search_changed)
        self.entry.connect("key-press-event", self.on_entry_key_press)
        main_box.pack_start(self.entry, False, False, 0)
        
        # Options
        options_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self.cb_case = Gtk.CheckButton(label="Match Case")
        self.cb_case.connect("toggled", self.on_option_toggled)
        self.cb_regex = Gtk.CheckButton(label="Regular Expression")
        self.cb_regex.connect("toggled", self.on_option_toggled)
        
        options_box.pack_start(self.cb_case, False, False, 0)
        options_box.pack_start(self.cb_regex, False, False, 0)
        main_box.pack_start(options_box, False, False, 0)
        
        # Results area
        self.scrolled = Gtk.ScrolledWindow()
        self.scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        
        self.listbox = Gtk.ListBox()
        self.listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.listbox.connect("row-activated", self.on_row_activated)
        self.scrolled.add(self.listbox)
        main_box.pack_start(self.scrolled, True, True, 0)
        
        # Status Label
        self.lbl_status = Gtk.Label(label="Type query to search...")
        self.lbl_status.set_halign(Gtk.Align.START)
        self.lbl_status.get_style_context().add_class("dim-label")
        main_box.pack_end(self.lbl_status, False, False, 0)
        
        self.apply_premium_styles()
        
        self.matched_results = []
        self.project_root = self.get_project_root()
        
        self.show_all()

    def get_project_root(self):
        current = self.parent_window.get_current_tab()
        if current and current["filepath"]:
            path = current["filepath"]
            curr = os.path.dirname(os.path.abspath(path))
            while curr != os.path.dirname(curr):
                if os.path.exists(os.path.join(curr, ".git")):
                    return curr
                curr = os.path.dirname(curr)
            return os.path.dirname(os.path.abspath(path))
        return os.getcwd()

    def apply_premium_styles(self):
        is_dark = getattr(self.parent_window, 'is_dark', True)
        css_provider = Gtk.CssProvider()
        
        if is_dark:
            css = b"""
            window {
                background-color: #1e1e2e;
                border: 2px solid #45475a;
                border-radius: 12px;
            }
            entry {
                background-color: #313244;
                color: #cdd6f4;
                border: 1px solid #45475a;
                border-radius: 6px;
                padding: 8px;
                font-size: 1.1em;
            }
            entry:focus {
                border-color: #b4befe;
            }
            checkbutton {
                color: #a6adc8;
            }
            list {
                background-color: #1e1e2e;
            }
            row {
                background-color: #1e1e2e;
                color: #cdd6f4;
                border-radius: 4px;
                padding: 6px 10px;
                border-bottom: 1px solid #313244;
            }
            row:hover {
                background-color: #313244;
            }
            row:selected {
                background-color: #45475a;
                color: #f5c2e7;
            }
            label.dim-label {
                color: #7f849c;
                font-size: 0.85em;
            }
            label.highlight-title {
                font-weight: bold;
                color: #89dceb;
            }
            label.highlight-line {
                color: #f9e2af;
                font-weight: bold;
            }
            label.highlight-snippet {
                color: #a6adc8;
                font-family: Monospace;
            }
            """
        else:
            css = b"""
            window {
                background-color: #eff1f5;
                border: 2px solid #bcc0cc;
                border-radius: 12px;
            }
            entry {
                background-color: #e6e9ef;
                color: #4c4f69;
                border: 1px solid #bcc0cc;
                border-radius: 6px;
                padding: 8px;
                font-size: 1.1em;
            }
            entry:focus {
                border-color: #7287fd;
            }
            checkbutton {
                color: #5c5f77;
            }
            list {
                background-color: #eff1f5;
            }
            row {
                background-color: #eff1f5;
                color: #4c4f69;
                border-radius: 4px;
                padding: 6px 10px;
                border-bottom: 1px solid #e6e9ef;
            }
            row:hover {
                background-color: #e6e9ef;
            }
            row:selected {
                background-color: #ccd0da;
                color: #7287fd;
            }
            label.dim-label {
                color: #8c8fa1;
                font-size: 0.85em;
            }
            label.highlight-title {
                font-weight: bold;
                color: #04a5e5;
            }
            label.highlight-line {
                color: #df8e1d;
                font-weight: bold;
            }
            label.highlight-snippet {
                color: #5c5f77;
                font-family: Monospace;
            }
            """
        css_provider.load_from_data(css)
        self.get_style_context().add_provider(css_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    def on_search_changed(self, entry):
        text = entry.get_text()
        self.trigger_search(text)

    def on_option_toggled(self, button):
        text = self.entry.get_text()
        self.trigger_search(text)

    def trigger_search(self, query):
        # Cancel previous search
        self.search_cancelled.set()
        
        # Clear listbox
        for child in self.listbox.get_children():
            self.listbox.remove(child)
            
        self.matched_results = []
        
        if not query:
            self.lbl_status.set_text("Type query to search...")
            return
            
        self.lbl_status.set_text("Searching...")
        self.search_cancelled = threading.Event()
        
        case_sensitive = self.cb_case.get_active()
        use_regex = self.cb_regex.get_active()
        
        self.search_thread = threading.Thread(
            target=self.run_search_thread,
            args=(query, case_sensitive, use_regex, self.search_cancelled),
            daemon=True
        )
        self.search_thread.start()

    def run_search_thread(self, query, case_sensitive, use_regex, cancelled):
        root = self.project_root
        exclude_dirs = {
            '.git', '__pycache__', '.idea', 'node_modules',
            'build', 'dist', '.vscode', '.gradle', 'target', 'venv', 'env'
        }
        exclude_exts = {
            '.pyc', '.o', '.so', '.a', '.class', '.png', '.jpg', '.jpeg',
            '.gif', '.zip', '.tar', '.gz', '.pdf', '.db', '.sqlite'
        }
        
        # Compile regex if needed
        rx = None
        if use_regex:
            try:
                flags = 0 if case_sensitive else re.IGNORECASE
                rx = re.compile(query, flags)
            except Exception as e:
                GLib.idle_add(self.lbl_status.set_text, f"Invalid regex pattern: {e}")
                return
        else:
            q_lower = query.lower()
            
        results = []
        limit = 100  # Cap results at 100 for responsiveness
        
        try:
            for dirpath, dirnames, filenames in os.walk(root):
                if cancelled.is_set():
                    return
                dirnames[:] = [d for d in dirnames if d not in exclude_dirs]
                
                for f in filenames:
                    if cancelled.is_set():
                        return
                    ext = os.path.splitext(f)[1].lower()
                    if ext in exclude_exts:
                        continue
                        
                    abs_path = os.path.join(dirpath, f)
                    rel_path = os.path.relpath(abs_path, root)
                    
                    try:
                        # Scan file lines
                        with open(abs_path, 'r', encoding='utf-8', errors='ignore') as file_obj:
                            for idx, line in enumerate(file_obj, 1):
                                if cancelled.is_set():
                                    return
                                matched = False
                                if rx:
                                    if rx.search(line):
                                        matched = True
                                else:
                                    if case_sensitive:
                                        if query in line:
                                            matched = True
                                    else:
                                        if q_lower in line.lower():
                                            matched = True
                                            
                                if matched:
                                    results.append((rel_path, abs_path, idx, line.strip()))
                                    if len(results) >= limit:
                                        break
                    except Exception as fe:
                        # Ignore unreadable files
                        pass
                        
                    if len(results) >= limit:
                        break
                if len(results) >= limit:
                    break
        except Exception as e:
            print(f"[GrepSearcher] Error during walk: {e}")
            
        if not cancelled.is_set():
            GLib.idle_add(self.on_search_finished, results, len(results) >= limit)

    def on_search_finished(self, results, hit_limit):
        self.matched_results = results
        
        for rel_path, abs_path, line_no, snippet in results:
            row_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            
            # File path box
            meta_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
            lbl_file = Gtk.Label(label=os.path.basename(rel_path))
            lbl_file.set_halign(Gtk.Align.START)
            lbl_file.get_style_context().add_class("highlight-title")
            
            lbl_path = Gtk.Label(label=os.path.dirname(rel_path))
            lbl_path.set_halign(Gtk.Align.START)
            lbl_path.get_style_context().add_class("dim-label")
            lbl_path.set_ellipsize(Pango.EllipsizeMode.END)
            
            meta_box.pack_start(lbl_file, False, False, 0)
            meta_box.pack_start(lbl_path, False, False, 0)
            
            # Match Line Info Box
            lbl_line = Gtk.Label(label=f"L{line_no}:")
            lbl_line.get_style_context().add_class("highlight-line")
            lbl_line.set_width_chars(6)
            lbl_line.set_xalign(1.0)
            
            # Snippet Preview Box
            lbl_snippet = Gtk.Label(label=snippet)
            lbl_snippet.set_halign(Gtk.Align.START)
            lbl_snippet.get_style_context().add_class("highlight-snippet")
            lbl_snippet.set_ellipsize(Pango.EllipsizeMode.END)
            
            row_box.pack_start(meta_box, False, False, 0)
            row_box.pack_start(lbl_line, False, False, 0)
            row_box.pack_start(lbl_snippet, True, True, 0)
            
            row = Gtk.ListBoxRow()
            row.add(row_box)
            self.listbox.add(row)
            
        self.show_all()
        
        # Select first row
        first_row = self.listbox.get_row_at_index(0)
        if first_row:
            self.listbox.select_row(first_row)
            
        status_text = f"Found {len(results)} matches"
        if hit_limit:
            status_text += " (capped at 100)"
        status_text += f" in: {os.path.basename(self.project_root)}"
        self.lbl_status.set_text(status_text)

    def on_entry_key_press(self, entry, event):
        keyname = Gdk.keyval_name(event.keyval)
        if keyname == "Escape":
            self.search_cancelled.set()
            self.destroy()
            return True
        elif keyname == "Up":
            self.move_selection(-1)
            return True
        elif keyname == "Down":
            self.move_selection(1)
            return True
        elif keyname in ("Return", "KP_Enter"):
            selected = self.listbox.get_selected_row()
            if selected:
                self.on_row_activated(self.listbox, selected)
            return True
        return False

    def move_selection(self, step):
        selected = self.listbox.get_selected_row()
        if not selected:
            return
        idx = selected.get_index()
        new_idx = idx + step
        if 0 <= new_idx < len(self.matched_results):
            row = self.listbox.get_row_at_index(new_idx)
            self.listbox.select_row(row)
            
            # Scroll adjustments
            adj = self.scrolled.get_vadjustment()
            row_rect = row.get_allocation()
            adj.clamp_page(row_rect.y, row_rect.y + row_rect.height)

    def on_row_activated(self, listbox, row):
        idx = row.get_index()
        if 0 <= idx < len(self.matched_results):
            rel_path, abs_path, line_no, snippet = self.matched_results[idx]
            if os.path.exists(abs_path):
                # Open tab
                already_open = False
                target_tab = None
                for t in self.parent_window.tabs:
                    if t["filepath"] == abs_path:
                        page_num = self.parent_window.editor_notebook.page_num(t["scrolled"])
                        self.parent_window.editor_notebook.set_current_page(page_num)
                        target_tab = t
                        already_open = True
                        break
                if not already_open:
                    target_tab = self.parent_window.add_editor_tab(abs_path)
                
                # Navigate cursor to specific line number (line_no is 1-indexed)
                if target_tab:
                    GLib.idle_add(self.scroll_to_line, target_tab["view"], line_no)
                    
            self.search_cancelled.set()
            self.destroy()

    def scroll_to_line(self, view, line_no):
        buffer = view.get_buffer()
        # line_no - 1 because iter_at_line is 0-indexed
        iter_line = buffer.get_iter_at_line(line_no - 1)
        buffer.place_cursor(iter_line)
        view.scroll_to_iter(iter_line, 0.0, True, 0.5, 0.5)
        view.grab_focus()

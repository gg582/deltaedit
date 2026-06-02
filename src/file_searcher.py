import os
import threading
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GLib, Pango

class FileSearcherPopup(Gtk.Window):
    def __init__(self, parent_window):
        super().__init__(type=Gtk.WindowType.TOPLEVEL)
        self.parent_window = parent_window
        self.set_transient_for(parent_window)
        self.set_modal(True)
        self.set_decorated(False)
        self.set_default_size(600, 400)
        self.set_position(Gtk.WindowPosition.CENTER_ON_PARENT)
        
        # Main layout
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        main_box.set_border_width(12)
        self.add(main_box)
        
        # Search entry
        self.entry = Gtk.Entry()
        self.entry.set_placeholder_text("Search files by name... (Fuzzy matching)")
        self.entry.set_icon_from_icon_name(Gtk.EntryIconPosition.PRIMARY, "system-search")
        self.entry.connect("changed", self.on_search_changed)
        self.entry.connect("key-press-event", self.on_entry_key_press)
        main_box.pack_start(self.entry, False, False, 0)
        
        # Results area
        self.scrolled = Gtk.ScrolledWindow()
        self.scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        
        self.listbox = Gtk.ListBox()
        self.listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.listbox.connect("row-activated", self.on_row_activated)
        self.scrolled.add(self.listbox)
        main_box.pack_start(self.scrolled, True, True, 0)
        
        # Status Label
        self.lbl_status = Gtk.Label(label="Scanning directory...")
        self.lbl_status.set_halign(Gtk.Align.START)
        self.lbl_status.get_style_context().add_class("dim-label")
        main_box.pack_end(self.lbl_status, False, False, 0)
        
        self.apply_premium_styles()
        
        self.all_files = []
        self.matched_files = []
        
        self.show_all()
        
        # Find directory to index
        self.project_root = self.get_project_root()
        
        # Run indexing in background thread
        threading.Thread(target=self.index_project_files, daemon=True).start()

    def get_project_root(self):
        # 1. Try Git root of current file
        current = self.parent_window.get_current_tab()
        if current and current["filepath"]:
            path = current["filepath"]
            curr = os.path.dirname(os.path.abspath(path))
            while curr != os.path.dirname(curr):
                if os.path.exists(os.path.join(curr, ".git")):
                    return curr
                curr = os.path.dirname(curr)
            return os.path.dirname(os.path.abspath(path))
            
        # 2. Try current working dir
        return os.getcwd()

    def apply_premium_styles(self):
        is_dark = getattr(self.parent_window, 'is_dark', True)
        css_provider = Gtk.CssProvider()
        
        # Set border radius and color palette depending on theme
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
                color: #cba6f7;
            }
            label.highlight-subtitle {
                font-size: 0.85em;
                color: #a6adc8;
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
                color: #8839ef;
            }
            label.highlight-subtitle {
                font-size: 0.85em;
                color: #5c5f77;
            }
            """
        css_provider.load_from_data(css)
        self.get_style_context().add_provider(css_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    def index_project_files(self):
        root = self.project_root
        exclude_dirs = {
            '.git', '__pycache__', '.idea', 'node_modules',
            'build', 'dist', '.vscode', '.gradle', 'target', 'venv', 'env'
        }
        exclude_exts = {
            '.pyc', '.o', '.so', '.a', '.class', '.png', '.jpg', '.jpeg',
            '.gif', '.zip', '.tar', '.gz', '.pdf', '.db', '.sqlite'
        }
        
        temp_files = []
        try:
            for dirpath, dirnames, filenames in os.walk(root):
                # Prune excluded directories
                dirnames[:] = [d for d in dirnames if d not in exclude_dirs]
                
                for f in filenames:
                    ext = os.path.splitext(f)[1].lower()
                    if ext in exclude_exts:
                        continue
                    abs_path = os.path.join(dirpath, f)
                    rel_path = os.path.relpath(abs_path, root)
                    temp_files.append((f, rel_path, abs_path))
        except Exception as e:
            print(f"[FileSearcher] Indexing error: {e}")
            
        GLib.idle_add(self.on_indexing_finished, temp_files)

    def on_indexing_finished(self, files):
        self.all_files = files
        self.lbl_status.set_text(f"Indexed {len(files)} files in: {os.path.basename(self.project_root)}")
        self.filter_results("")

    def fuzzy_match_score(self, query, filename, rel_path):
        query = query.lower()
        f_lower = filename.lower()
        r_lower = rel_path.lower()
        
        if not query:
            return 0
            
        # Basic contains matches
        if query == f_lower:
            return 1000  # Exact filename match
        if query == r_lower:
            return 900   # Exact path match
        if query in f_lower:
            return 500 + (100 - len(f_lower))
        if query in r_lower:
            return 300 + (100 - len(r_lower))
            
        # Sequence match score
        t_idx = 0
        score = 0
        matches = 0
        for char in query:
            found = r_lower.find(char, t_idx)
            if found == -1:
                return -1
            distance = found - t_idx
            score += (10 - min(distance, 9))
            t_idx = found + 1
            matches += 1
            
        return score + matches * 10

    def filter_results(self, text):
        # Clear listbox
        for child in self.listbox.get_children():
            self.listbox.remove(child)
            
        if not text:
            # Show first 20 files
            results = self.all_files[:20]
        else:
            scored = []
            for item in self.all_files:
                score = self.fuzzy_match_score(text, item[0], item[1])
                if score >= 0:
                    scored.append((score, item))
            scored.sort(key=lambda x: x[0], reverse=True)
            results = [item for _, item in scored[:20]]
            
        self.matched_files = results
        
        for name, rel_path, abs_path in results:
            row_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            
            lbl_title = Gtk.Label(label=name)
            lbl_title.set_halign(Gtk.Align.START)
            lbl_title.get_style_context().add_class("highlight-title")
            
            lbl_sub = Gtk.Label(label=rel_path)
            lbl_sub.set_halign(Gtk.Align.START)
            lbl_sub.get_style_context().add_class("highlight-subtitle")
            lbl_sub.set_ellipsize(Pango.EllipsizeMode.END)
            
            row_box.pack_start(lbl_title, False, False, 0)
            row_box.pack_start(lbl_sub, False, False, 0)
            
            row = Gtk.ListBoxRow()
            row.add(row_box)
            self.listbox.add(row)
            
        self.show_all()
        
        # Select first row
        first_row = self.listbox.get_row_at_index(0)
        if first_row:
            self.listbox.select_row(first_row)

    def on_search_changed(self, entry):
        text = entry.get_text().strip()
        self.filter_results(text)

    def on_entry_key_press(self, entry, event):
        keyname = Gdk.keyval_name(event.keyval)
        if keyname == "Escape":
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
        if 0 <= new_idx < len(self.matched_files):
            row = self.listbox.get_row_at_index(new_idx)
            self.listbox.select_row(row)
            
            # Clamp scrollbar
            adj = self.scrolled.get_vadjustment()
            row_rect = row.get_allocation()
            adj.clamp_page(row_rect.y, row_rect.y + row_rect.height)

    def on_row_activated(self, listbox, row):
        idx = row.get_index()
        if 0 <= idx < len(self.matched_files):
            name, rel_path, abs_path = self.matched_files[idx]
            if os.path.exists(abs_path):
                # Open or switch to tab
                already_open = False
                for t in self.parent_window.tabs:
                    if t["filepath"] == abs_path:
                        page_num = self.parent_window.editor_notebook.page_num(t["scrolled"])
                        self.parent_window.editor_notebook.set_current_page(page_num)
                        already_open = True
                        break
                if not already_open:
                    self.parent_window.add_editor_tab(abs_path)
            self.destroy()

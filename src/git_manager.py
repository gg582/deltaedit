import os
import subprocess
import threading
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, Pango, GLib

class GitPanel(Gtk.Box):
    def __init__(self, app_window):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.app_window = app_window
        self.set_border_width(8)
        
        # Upper control bar
        ctrl_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.git_label = Gtk.Label(label="No Git Repository Detected")
        self.git_label.set_halign(Gtk.Align.START)
        
        btn_refresh = Gtk.Button.new_from_icon_name("view-refresh", Gtk.IconSize.BUTTON)
        btn_refresh.set_tooltip_text("Refresh Git Status")
        btn_refresh.connect("clicked", lambda w: self.refresh_git_status())
        
        ctrl_box.pack_start(self.git_label, True, True, 0)
        ctrl_box.pack_end(btn_refresh, False, False, 0)
        self.pack_start(ctrl_box, False, False, 0)
        
        # Files split pane (Top: Status Files list, Bottom: Diff view)
        split_paned = Gtk.Paned(orientation=Gtk.Orientation.VERTICAL)
        split_paned.set_position(150)
        self.pack_start(split_paned, True, True, 0)
        
        # Top half: TreeView of files
        files_scroll = Gtk.ScrolledWindow()
        files_scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        
        self.git_store = Gtk.ListStore(str, str, str) # [Status Text, File Path, Absolute Path]
        self.git_tree = Gtk.TreeView(model=self.git_store)
        
        col_status = Gtk.TreeViewColumn("Status", Gtk.CellRendererText(), text=0)
        col_status.set_width(80)
        self.git_tree.append_column(col_status)
        
        col_file = Gtk.TreeViewColumn("File", Gtk.CellRendererText(), text=1)
        self.git_tree.append_column(col_file)
        
        self.git_tree.connect("row-activated", self.on_git_file_activated)
        self.git_tree.get_selection().connect("changed", self.on_git_selection_changed)
        
        files_scroll.add(self.git_tree)
        split_paned.pack1(files_scroll, resize=True, shrink=False)
        
        # Bottom half: Diff viewer
        diff_scroll = Gtk.ScrolledWindow()
        self.diff_buffer = Gtk.TextBuffer()
        self.diff_view = Gtk.TextView(buffer=self.diff_buffer)
        self.diff_view.set_editable(False)
        font_desc = Pango.FontDescription("Monospace 10")
        self.diff_view.override_font(font_desc)
        diff_scroll.add(self.diff_view)
        
        split_paned.pack2(diff_scroll, resize=True, shrink=True)
        
        # Bottom workflow controls (Commit, Stage)
        actions_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        
        btn_stage_selected = Gtk.Button.new_with_label("Stage Selected")
        btn_stage_selected.connect("clicked", self.on_git_stage_selected)
        btn_unstage_selected = Gtk.Button.new_with_label("Unstage Selected")
        btn_unstage_selected.connect("clicked", self.on_git_unstage_selected)
        
        stage_buttons_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        stage_buttons_box.pack_start(btn_stage_selected, True, True, 0)
        stage_buttons_box.pack_start(btn_unstage_selected, True, True, 0)
        actions_box.pack_start(stage_buttons_box, False, False, 0)
        
        commit_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.commit_entry = Gtk.Entry()
        self.commit_entry.set_placeholder_text("Commit message...")
        btn_commit = Gtk.Button.new_with_label("Commit")
        btn_commit.connect("clicked", self.on_git_commit_clicked)
        
        commit_box.pack_start(self.commit_entry, True, True, 0)
        commit_box.pack_end(btn_commit, False, False, 0)
        actions_box.pack_start(commit_box, False, False, 0)
        
        # Git Remote & Branch controls
        remote_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.branch_combo = Gtk.ComboBoxText()
        self.branch_combo.set_tooltip_text("Switch Branch")
        self.branch_combo.connect("changed", self.on_branch_changed)
        self.updating_branches = False
        
        btn_pull = Gtk.Button.new_with_label("Pull")
        btn_pull.set_tooltip_text("Pull from remote repository")
        btn_pull.connect("clicked", self.on_git_pull_clicked)
        
        btn_push = Gtk.Button.new_with_label("Push")
        btn_push.set_tooltip_text("Push to remote repository")
        btn_push.connect("clicked", self.on_git_push_clicked)
        
        remote_box.pack_start(self.branch_combo, True, True, 0)
        remote_box.pack_start(btn_pull, False, False, 0)
        remote_box.pack_start(btn_push, False, False, 0)
        actions_box.pack_start(remote_box, False, False, 0)
        
        self.pack_end(actions_box, False, False, 0)


    def refresh_git_status(self):
        current = self.app_window.get_current_tab()
        if not current or not current["filepath"]:
            self.git_label.set_text("No File Open")
            self.git_store.clear()
            self.diff_buffer.set_text("")
            return
            
        git_root = self.get_git_root(current["filepath"])
        if not git_root:
            self.git_label.set_text("Not a Git Repository")
            self.git_store.clear()
            self.diff_buffer.set_text("")
            return
            
        self.git_label.set_text(f"Git: {os.path.basename(git_root)}")
        self.git_store.clear()
        self.diff_buffer.set_text("")
        self.update_branch_list(git_root)
        
        stdout, stderr = self.run_git_command(git_root, ["status", "--porcelain"])
        if stderr:
            self.diff_buffer.set_text(f"Error running git: {stderr}")
            return
            
        lines = stdout.split("\n")
        status_map = {
            "M ": "Staged (Mod)",
            "A ": "Staged (Add)",
            "D ": "Staged (Del)",
            " R": "Renamed",
            " C": "Copied",
            "M": "Modified",
            "D": "Deleted",
            "??": "Untracked",
            "UU": "Conflict"
        }
        
        for line in lines:
            if not line:
                continue
            status_code = line[:2]
            rel_path = line[3:]
            
            if rel_path.startswith('"') and rel_path.endswith('"'):
                rel_path = rel_path[1:-1]
                
            abs_path = os.path.join(git_root, rel_path)
            
            status_text = "Unknown"
            for code, desc in status_map.items():
                if status_code.startswith(code) or status_code.endswith(code):
                    status_text = desc
                    break
                    
            self.git_store.append([status_text, rel_path, abs_path])

    def get_git_root(self, filepath):
        if not filepath:
            return None
        curr = os.path.dirname(os.path.abspath(filepath))
        while curr != os.path.dirname(curr):
            if os.path.exists(os.path.join(curr, ".git")):
                return curr
            curr = os.path.dirname(curr)
        return None

    def run_git_command(self, git_root, args):
        try:
            res = subprocess.run(
                ["git"] + args,
                cwd=git_root,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            return res.stdout, res.stderr
        except Exception as e:
            return "", str(e)

    def on_git_selection_changed(self, selection):
        model, treeiter = selection.get_selected()
        if treeiter is not None:
            status = model[treeiter][0]
            rel_path = model[treeiter][1]
            
            current = self.app_window.get_current_tab()
            if current and current["filepath"]:
                git_root = self.get_git_root(current["filepath"])
                if git_root:
                    self.show_git_diff(git_root, rel_path, status)

    def show_git_diff(self, git_root, rel_path, status):
        self.diff_buffer.set_text("")
        
        is_dark = getattr(self.app_window, 'is_dark', True)
        tag_add = self.diff_buffer.create_tag("diff_add", foreground="#a6e3a1" if is_dark else "#40a02b")
        tag_del = self.diff_buffer.create_tag("diff_del", foreground="#f38ba8" if is_dark else "#d20f39")
        tag_hdr = self.diff_buffer.create_tag("diff_hdr", foreground="#89b4fa" if is_dark else "#1e66f5", weight=Pango.Weight.BOLD)
        
        args = ["diff"]
        if "Staged" in status:
            args.append("--cached")
        args.append(rel_path)
        
        stdout, stderr = self.run_git_command(git_root, args)
        
        if not stdout and not stderr:
            if "Untracked" in status:
                abs_path = os.path.join(git_root, rel_path)
                try:
                    with open(abs_path, 'r', encoding='utf-8') as f:
                        lines = f.readlines()
                    stdout = "--- /dev/null\n+++ " + rel_path + "\n"
                    for line in lines:
                        stdout += "+" + line
                except:
                    stdout = "Could not read untracked file."
            else:
                stdout = "No differences found."
                
        lines = stdout.split("\n")
        for line in lines:
            end_iter = self.diff_buffer.get_end_iter()
            if line.startswith("+") and not line.startswith("+++"):
                self.diff_buffer.insert_with_tags(end_iter, line + "\n", tag_add)
            elif line.startswith("-") and not line.startswith("---"):
                self.diff_buffer.insert_with_tags(end_iter, line + "\n", tag_del)
            elif line.startswith("@@"):
                self.diff_buffer.insert_with_tags(end_iter, line + "\n", tag_hdr)
            else:
                self.diff_buffer.insert(end_iter, line + "\n")

    def on_git_file_activated(self, tree, path, column):
        model = tree.get_model()
        treeiter = model.get_iter(path)
        abs_path = model[treeiter][2]
        if os.path.exists(abs_path):
            already_open = False
            for t in self.app_window.tabs:
                if t["filepath"] == abs_path:
                    page_num = self.app_window.editor_notebook.page_num(t["scrolled"])
                    self.app_window.editor_notebook.set_current_page(page_num)
                    already_open = True
                    break
            if not already_open:
                self.app_window.add_editor_tab(abs_path)

    def on_git_stage_selected(self, button):
        selection = self.git_tree.get_selection()
        model, treeiter = selection.get_selected()
        if treeiter is not None:
            rel_path = model[treeiter][1]
            current = self.app_window.get_current_tab()
            if current and current["filepath"]:
                git_root = self.get_git_root(current["filepath"])
                if git_root:
                    self.run_git_command(git_root, ["add", rel_path])
                    self.refresh_git_status()

    def on_git_unstage_selected(self, button):
        selection = self.git_tree.get_selection()
        model, treeiter = selection.get_selected()
        if treeiter is not None:
            rel_path = model[treeiter][1]
            current = self.app_window.get_current_tab()
            if current and current["filepath"]:
                git_root = self.get_git_root(current["filepath"])
                if git_root:
                    self.run_git_command(git_root, ["reset", "HEAD", rel_path])
                    self.refresh_git_status()

    def on_git_commit_clicked(self, button):
        msg = self.commit_entry.get_text().strip()
        if not msg:
            dialog = Gtk.MessageDialog(
                transient_for=self.app_window,
                flags=0,
                message_type=Gtk.MessageType.WARNING,
                buttons=Gtk.ButtonsType.OK,
                text="Empty Commit Message"
            )
            dialog.run()
            dialog.destroy()
            return
            
        current = self.app_window.get_current_tab()
        if current and current["filepath"]:
            git_root = self.get_git_root(current["filepath"])
            if git_root:
                stdout, stderr = self.run_git_command(git_root, ["commit", "-m", msg])
                self.commit_entry.set_text("")
                self.refresh_git_status()
                dialog = Gtk.MessageDialog(
                    transient_for=self.app_window,
                    flags=0,
                    message_type=Gtk.MessageType.INFO,
                    buttons=Gtk.ButtonsType.OK,
                    text="Commit Successful" if not stderr else "Commit Result"
                )
                dialog.format_secondary_text(stdout if not stderr else stderr)
                dialog.run()
                dialog.destroy()

    def update_branch_list(self, git_root):
        self.updating_branches = True
        self.branch_combo.remove_all()
        
        stdout, stderr = self.run_git_command(git_root, ["branch", "--no-color"])
        if not stdout:
            self.updating_branches = False
            return
            
        branches = []
        current_idx = 0
        for line in stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            if line.startswith("*"):
                branch_name = line[1:].strip()
                current_idx = len(branches)
            else:
                branch_name = line
            branches.append(branch_name)
            self.branch_combo.append_text(branch_name)
            
        if branches:
            self.branch_combo.set_active(current_idx)
        self.updating_branches = False

    def on_branch_changed(self, combo):
        if self.updating_branches:
            return
        branch_name = combo.get_active_text()
        if not branch_name:
            return
            
        current = self.app_window.get_current_tab()
        if not current or not current["filepath"]:
            return
        git_root = self.get_git_root(current["filepath"])
        if not git_root:
            return
            
        # Run checkout in thread to avoid freezing UI
        threading.Thread(target=self._run_checkout_thread, args=(git_root, branch_name), daemon=True).start()
        
    def _run_checkout_thread(self, git_root, branch_name):
        stdout, stderr = self.run_git_command(git_root, ["checkout", branch_name])
        GLib.idle_add(self._on_checkout_finished, stdout, stderr)
        
    def _on_checkout_finished(self, stdout, stderr):
        self.refresh_git_status()
        
        # Reload open tabs in case they modified outside
        for tab in self.app_window.tabs:
            if tab["filepath"] and os.path.exists(tab["filepath"]):
                try:
                    with open(tab["filepath"], 'r', encoding='utf-8') as f:
                        content = f.read()
                    buffer = tab["view"].get_buffer()
                    insert_mark = buffer.get_insert()
                    offset = buffer.get_iter_at_mark(insert_mark).get_offset()
                    
                    buffer.set_text(content)
                    
                    new_iter = buffer.get_iter_at_offset(min(offset, len(content)))
                    buffer.place_cursor(new_iter)
                except Exception as e:
                    print(f"Error reloading {tab['filepath']}: {e}")
                    
        msg = stderr if stderr else stdout
        dialog = Gtk.MessageDialog(
            transient_for=self.app_window,
            flags=0,
            message_type=Gtk.MessageType.INFO,
            buttons=Gtk.ButtonsType.OK,
            text="Branch Checkout Result"
        )
        dialog.format_secondary_text(msg)
        dialog.run()
        dialog.destroy()

    def on_git_pull_clicked(self, button):
        current = self.app_window.get_current_tab()
        if not current or not current["filepath"]:
            return
        git_root = self.get_git_root(current["filepath"])
        if not git_root:
            return
        
        button.set_sensitive(False)
        threading.Thread(target=self._run_pull_thread, args=(git_root, button), daemon=True).start()
        
    def _run_pull_thread(self, git_root, button):
        stdout, stderr = self.run_git_command(git_root, ["pull"])
        GLib.idle_add(self._on_pull_push_finished, "Git Pull Result", stdout, stderr, button)
        
    def on_git_push_clicked(self, button):
        current = self.app_window.get_current_tab()
        if not current or not current["filepath"]:
            return
        git_root = self.get_git_root(current["filepath"])
        if not git_root:
            return
        
        button.set_sensitive(False)
        threading.Thread(target=self._run_push_thread, args=(git_root, button), daemon=True).start()
        
    def _run_push_thread(self, git_root, button):
        stdout, stderr = self.run_git_command(git_root, ["push"])
        GLib.idle_add(self._on_pull_push_finished, "Git Push Result", stdout, stderr, button)
        
    def _on_pull_push_finished(self, title, stdout, stderr, button):
        button.set_sensitive(True)
        self.refresh_git_status()
        msg = stdout if stdout else ""
        if stderr:
            msg += "\n" + stderr
        dialog = Gtk.MessageDialog(
            transient_for=self.app_window,
            flags=0,
            message_type=Gtk.MessageType.INFO,
            buttons=Gtk.ButtonsType.OK,
            text=title
        )
        dialog.format_secondary_text(msg)
        dialog.run()
        dialog.destroy()

#!/usr/bin/python3
import gi
import sys
import os
import shutil
import subprocess
import threading
import json
import urllib.parse

gi.require_version('Gtk', '3.0')
gi.require_version('GtkSource', '4')
gi.require_version('Vte', '2.91')

# Detect WebKit2 version dynamically
try:
    gi.require_version('WebKit2', '4.1')
except ValueError:
    try:
        gi.require_version('WebKit2', '4.0')
    except ValueError:
        pass

from gi.repository import Gtk, Gdk, GtkSource, Vte, GLib, Pango
from gi.repository import WebKit2 as WebKit

# Optional markdown package
try:
    import markdown
    HAS_MARKDOWN = True
except ImportError:
    HAS_MARKDOWN = False

# Optional tree-sitter package
try:
    import tree_sitter
    HAS_TREE_SITTER = True
except ImportError:
    HAS_TREE_SITTER = False

from lsp import LSPManager
from highlighter import TreeSitterHighlighter
from popup import AutocompletePopup
from git_manager import GitPanel
from file_searcher import FileSearcherPopup
from grep_searcher import GrepSearcherPopup
class AppWindow(Gtk.ApplicationWindow):
    def __init__(self, *args, **kwargs):
        files = kwargs.pop("files", [])
        super().__init__(*args, **kwargs)
        self.set_default_size(1250, 850)
        
        self.lsp_manager = LSPManager(self)
        self.tabs = []
        
        # Load directories fallback config
        self.setup_config()
        
        # Setup CSS provider
        self.css_provider = Gtk.CssProvider()
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(),
            self.css_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
        
        # Determine initial theme
        self.is_dark = self.check_system_dark()
        self.apply_theme()
        
        # Connect to system theme changes
        settings = Gtk.Settings.get_default()
        settings.connect("notify::gtk-theme-name", self.on_system_theme_changed)
        settings.connect("notify::gtk-application-prefer-dark-theme", self.on_system_theme_changed)
        
        # HeaderBar Setup
        self.create_headerbar()
        
        # Accelerators (shortcuts)
        self.setup_accelerators()
        
        # Layout splits
        self.main_paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        self.main_paned.set_position(900)
        self.add(self.main_paned)
        
        # Left inner paned: File Tree + Editor
        self.left_paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        self.left_paned.set_position(220)
        
        # File Tree
        self.file_tree_store = Gtk.TreeStore(str, str, str, bool)
        self.file_tree_view = Gtk.TreeView(model=self.file_tree_store)
        self.file_tree_view.set_headers_visible(False)
        
        renderer_icon = Gtk.CellRendererPixbuf()
        renderer_text = Gtk.CellRendererText()
        column = Gtk.TreeViewColumn()
        column.pack_start(renderer_icon, False)
        column.pack_start(renderer_text, True)
        column.add_attribute(renderer_icon, "icon-name", 0)
        column.add_attribute(renderer_text, "text", 1)
        self.file_tree_view.append_column(column)
        self.file_tree_view.connect("row-activated", self.on_tree_item_activated)
        
        self.file_tree_scrolled = Gtk.ScrolledWindow()
        self.file_tree_scrolled.set_size_request(180, -1)
        self.file_tree_scrolled.add(self.file_tree_view)
        
        self.left_paned.pack1(self.file_tree_scrolled, resize=False, shrink=False)
        
        # Left Panel: Editor Tabs
        self.editor_notebook = Gtk.Notebook()
        self.editor_notebook.connect("switch-page", self.on_tab_switched)
        self.left_paned.pack2(self.editor_notebook, resize=True, shrink=False)
        
        self.main_paned.pack1(self.left_paned, resize=True, shrink=False)
        
        self.current_folder = None
        self.view_mode = "split"
        
        # Right Panel: Utility Tabs
        self.tools_notebook = Gtk.Notebook()
        self.main_paned.pack2(self.tools_notebook, resize=True, shrink=True)
        
        # Web Browser tab
        self.create_web_tab()
        
        # Terminal tab
        self.create_terminal_tab()
        
        # Helper/Encoding tab
        self.create_helper_tab()
        
        # Git tab
        self.git_panel = GitPanel(self)
        self.tools_notebook.append_page(self.git_panel, Gtk.Label(label="Git"))
        
        # Load command line files or empty tab
        if files:
            for filepath in files:
                self.add_editor_tab(filepath)
        else:
            self.add_editor_tab()
            
        self.show_all()

    def setup_config(self):
        self.conf_dir = os.path.expanduser("~/.config/dedit")
        os.makedirs(self.conf_dir, exist_ok=True)
        
        enc_file = os.path.join(self.conf_dir, "encoding.editconf")
        if not os.path.exists(enc_file):
            if os.path.exists("/etc/dedit/encoding.editconf"):
                try:
                    shutil.copy("/etc/dedit/encoding.editconf", enc_file)
                except:
                    pass
            else:
                with open(enc_file, 'w', encoding='utf-8') as f:
                    f.write("utf-8\n")
                    
        try:
            with open(enc_file, 'r', encoding='utf-8') as f:
                self.encDefined = f.readline().strip()
        except:
            self.encDefined = 'utf-8'

        self.help_file = os.path.join(self.conf_dir, "help.txt")
        try:
            with open(self.help_file, 'w', encoding='utf-8') as f:
                f.write("=== DeltaEdit Quick Help ===\n\nShortcuts:\n  Ctrl+N : New File\n  Ctrl+O : Open File\n  Ctrl+Shift+D : Open Folder\n  Ctrl+S : Save File\n  Ctrl+W : Close Current Tab\n  Ctrl+Shift+P : Preview Current Document\n  Ctrl+K : Cut Current Line\n  Ctrl+P : Search File (Fuzzy)\n  Ctrl+Shift+F : Search Text (Grep)\n  Ctrl+Z : Undo\n  Ctrl+Y : Redo\n  Ctrl+Left  : Focus Right Panel (Tools)\n  Ctrl+Right : Focus Left Panel (Editor)\n  Ctrl+Up    : Restore Split View\n\nWeb + Editor Integration:\n  - Right click on text selection to search Google in Web Tab.\n  - Press Preview button in Web Browser to preview markdown or HTML live.\n")
        except:
            pass

        # Bookmarks config
        self.bookmarks_file = os.path.join(self.conf_dir, "bookmarks.json")
        self.bookmarks = []
        self.load_bookmarks()

    def check_system_dark(self):
        settings = Gtk.Settings.get_default()
        prefer_dark = settings.get_property("gtk-application-prefer-dark-theme")
        theme_name = settings.get_property("gtk-theme-name")
        if prefer_dark:
            return True
        if theme_name and "dark" in theme_name.lower():
            return True
        return False

    def apply_theme(self):
        settings = Gtk.Settings.get_default()
        settings.set_property("gtk-application-prefer-dark-theme", self.is_dark)

        if self.is_dark:
            css = b"""
            window {
                background-color: #1e1e2e;
                color: #cdd6f4;
            }
            headerbar {
                background: linear-gradient(to bottom, #313244, #1e1e2e);
                border-bottom: 1px solid #45475a;
                color: #cdd6f4;
            }
            headerbar .title {
                font-weight: bold;
                color: #b4befe;
            }
            button {
                background: #313244;
                color: #cdd6f4;
                border: 1px solid #45475a;
                border-radius: 6px;
                padding: 5px 10px;
            }
            button:hover {
                background: #45475a;
                border-color: #585b70;
            }
            entry {
                background: #313244;
                color: #cdd6f4;
                border: 1px solid #45475a;
                border-radius: 6px;
                padding: 5px;
            }
            notebook header {
                background: #181825;
                border-bottom: 1px solid #313244;
            }
            notebook tab {
                background: #181825;
                border: 1px solid #313244;
                border-bottom-width: 0;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                padding: 4px 10px;
                color: #a6adc8;
            }
            notebook tab:active {
                background: #1e1e2e;
                color: #cdd6f4;
                border-color: #45475a;
            }
            """
        else:
            css = b"""
            window {
                background-color: #f4f4f6;
                color: #4c4f69;
            }
            headerbar {
                background: linear-gradient(to bottom, #e6e9ef, #dce0e8);
                border-bottom: 1px solid #bcc0cc;
                color: #4c4f69;
            }
            headerbar .title {
                font-weight: bold;
                color: #7287fd;
            }
            button {
                background: #e6e9ef;
                color: #4c4f69;
                border: 1px solid #bcc0cc;
                border-radius: 6px;
                padding: 5px 10px;
            }
            button:hover {
                background: #ccd0da;
                border-color: #acb0be;
            }
            entry {
                background: #e6e9ef;
                color: #4c4f69;
                border: 1px solid #bcc0cc;
                border-radius: 6px;
                padding: 5px;
            }
            notebook header {
                background: #e6e9ef;
                border-bottom: 1px solid #bcc0cc;
            }
            notebook tab {
                background: #e6e9ef;
                border: 1px solid #bcc0cc;
                border-bottom-width: 0;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                padding: 4px 10px;
                color: #4c4f69;
            }
            notebook tab:active {
                background: #f4f4f6;
                color: #4c4f69;
                border-color: #bcc0cc;
            }
            """
        self.css_provider.load_from_data(css)

    def on_system_theme_changed(self, settings, pspec):
        new_is_dark = self.check_system_dark()
        if new_is_dark != self.is_dark:
            self.is_dark = new_is_dark
            self.apply_theme()
            self.update_editor_schemes()
            if hasattr(self, 'btn_theme'):
                icon_name = "weather-clear-night" if self.is_dark else "weather-clear"
                self.btn_theme.set_image(Gtk.Image.new_from_icon_name(icon_name, Gtk.IconSize.BUTTON))

    def on_theme_toggle_clicked(self, widget):
        self.is_dark = not self.is_dark
        self.apply_theme()
        self.update_editor_schemes()
        if hasattr(self, 'btn_theme'):
            icon_name = "weather-clear-night" if self.is_dark else "weather-clear"
            self.btn_theme.set_image(Gtk.Image.new_from_icon_name(icon_name, Gtk.IconSize.BUTTON))

    def update_editor_schemes(self):
        scheme_manager = GtkSource.StyleSchemeManager.get_default()
        scheme_name = "oblivion" if self.is_dark else "classic"
        scheme = scheme_manager.get_scheme(scheme_name)
        if scheme:
            for tab in self.tabs:
                tab["buffer"].set_style_scheme(scheme)
                if tab["highlighter"]:
                    tab["highlighter"].update_theme(self.is_dark)
                    tab["highlighter"].highlight()

    def destroy_autocomplete_popup(self):
        if hasattr(self, 'autocomplete_popup') and self.autocomplete_popup:
            self.autocomplete_popup.destroy()
            self.autocomplete_popup = None

    def on_view_key_press(self, view, event):
        keyval = event.keyval
        
        # Enter key for smart auto-indentation (when autocomplete is NOT active)
        if keyval in [Gdk.KEY_Return, Gdk.KEY_KP_Enter]:
            if hasattr(self, 'autocomplete_popup') and self.autocomplete_popup and self.autocomplete_popup.get_visible():
                self.autocomplete_popup.confirm_selection()
                return True
            else:
                return self.handle_auto_indent(view)

        # Smart outdent on typing closing brackets: '}', ')', ']'
        elif keyval in [Gdk.KEY_braceright, Gdk.KEY_parenright, Gdk.KEY_bracketright]:
            if self.handle_closing_bracket(view, keyval):
                return True

        # Autocomplete keyboard navigation
        if hasattr(self, 'autocomplete_popup') and self.autocomplete_popup and self.autocomplete_popup.get_visible():
            # Up Arrow
            if keyval == Gdk.KEY_Up:
                self.autocomplete_popup.move_selection(-1)
                return True
                
            # Down Arrow
            elif keyval == Gdk.KEY_Down:
                self.autocomplete_popup.move_selection(1)
                return True
                
            # Tab selection
            elif keyval == Gdk.KEY_Tab:
                self.autocomplete_popup.confirm_selection()
                return True
                
            # Escape
            elif keyval == Gdk.KEY_Escape:
                self.destroy_autocomplete_popup()
                return True
                
        return False

    def handle_closing_bracket(self, view, keyval):
        current = self.get_current_tab()
        if not current:
            return False
            
        buffer = current["buffer"]
        cursor_mark = buffer.get_insert()
        cursor_iter = buffer.get_iter_at_mark(cursor_mark)
        
        line_num = cursor_iter.get_line()
        start_iter = buffer.get_iter_at_line(line_num)
        line_text = buffer.get_text(start_iter, cursor_iter, True)
        
        # Only outdent if the line consists entirely of whitespace before the bracket
        if line_text.strip() == "":
            char_map = {
                Gdk.KEY_braceright: "}",
                Gdk.KEY_parenright: ")",
                Gdk.KEY_bracketright: "]"
            }
            bracket = char_map.get(keyval, "}")
            
            # Remove 4 spaces of indentation if possible
            if len(line_text) >= 4 and line_text.endswith("    "):
                delete_start = cursor_iter.copy()
                delete_start.backward_chars(4)
                
                buffer.begin_user_action()
                buffer.delete(delete_start, cursor_iter)
                buffer.insert(delete_start, bracket)
                buffer.end_user_action()
                
                # Scroll to cursor
                view.scroll_to_mark(cursor_mark, 0.0, False, 0.0, 0.0)
                return True
        return False

    def handle_auto_indent(self, view):
        current = self.get_current_tab()
        if not current:
            return False
            
        buffer = current["buffer"]
        cursor_mark = buffer.get_insert()
        cursor_iter = buffer.get_iter_at_mark(cursor_mark)
        char_offset = cursor_iter.get_offset()
        
        line_num = cursor_iter.get_line()
        start_iter = buffer.get_iter_at_line(line_num)
        line_text = buffer.get_text(start_iter, cursor_iter, True)
        
        # Base indentation of the current line
        base_indent = ""
        for c in line_text:
            if c in [' ', '\t']:
                base_indent += c
            else:
                break
                
        extra_indent = ""
        # Try Tree-Sitter AST context parsing first
        if current["highlighter"] and HAS_TREE_SITTER and current["highlighter"].parser:
            highlighter = current["highlighter"]
            start_all = buffer.get_start_iter()
            end_all = buffer.get_end_iter()
            text_all = buffer.get_text(start_all, end_all, True)
            
            try:
                tree = highlighter.parser.parse(text_all.encode('utf-8'))
                byte_offset = len(text_all[:char_offset].encode('utf-8'))
                
                # Find current node at cursor
                node = tree.root_node.descendant_for_byte_range(byte_offset, byte_offset)
                
                trimmed_prev = line_text.strip()
                
                # C-style or Python indent trigger check:
                if trimmed_prev.endswith('{') or trimmed_prev.endswith('(') or trimmed_prev.endswith('[') or trimmed_prev.endswith(':'):
                    extra_indent = "    "
                else:
                    # Check AST parents for unclosed statement list or parameters
                    parent = node.parent
                    while parent:
                        if parent.type in ['argument_list', 'parameter_list', 'parenthesized_expression', 'compound_statement', 'block']:
                            extra_indent = "    "
                            break
                        parent = parent.parent
            except Exception as e:
                print(f"[TreeSitter] Advanced indent failed: {e}")
        else:
            # Fallback simple indentation rules
            trimmed_prev = line_text.strip()
            if trimmed_prev.endswith('{') or trimmed_prev.endswith('(') or trimmed_prev.endswith('[') or trimmed_prev.endswith(':'):
                extra_indent = "    "
                
        # Handle Enter right between { and } for dual spacing layout
        next_iter = cursor_iter.copy()
        is_between_brackets = False
        if next_iter.get_char() == '}':
            trimmed_prev = line_text.strip()
            if trimmed_prev.endswith('{'):
                is_between_brackets = True
                
        buffer.begin_user_action()
        if is_between_brackets:
            # Insert double newline, indent the middle, and keep bracket on bottom line
            buffer.insert(cursor_iter, "\n" + base_indent + extra_indent + "\n" + base_indent)
            # Move cursor back to the middle line
            back_iter = buffer.get_iter_at_mark(cursor_mark)
            back_iter.backward_line()
            back_iter.forward_to_line_end()
            buffer.place_cursor(back_iter)
        else:
            buffer.insert(cursor_iter, "\n" + base_indent + extra_indent)
        buffer.end_user_action()
        
        view.scroll_to_mark(cursor_mark, 0.0, False, 0.0, 0.0)
        return True

    def trigger_autocomplete(self, tab_info):
        self.autocomplete_timeout_id = None
        
        current = self.get_current_tab()
        if not current or current["filepath"] != tab_info["filepath"]:
            return False
            
        buffer = tab_info["buffer"]
        cursor_iter = buffer.get_iter_at_mark(buffer.get_insert())
        
        if cursor_iter.get_line_offset() == 0:
            self.destroy_autocomplete_popup()
            return False
            
        prev_iter = cursor_iter.copy()
        prev_iter.backward_char()
        char = prev_iter.get_char()
        
        import string
        allowed_chars = string.ascii_letters + string.digits + "_."
        if char not in allowed_chars:
            self.destroy_autocomplete_popup()
            return False
            
        line = cursor_iter.get_line()
        col = cursor_iter.get_line_offset()
        
        params = {
            "textDocument": {
                "uri": f"file://{os.path.abspath(tab_info['filepath'])}"
            },
            "position": {
                "line": line,
                "character": col
            }
        }
        
        self.lsp_manager.send_request_with_callback(
            tab_info["filepath"],
            "textDocument/completion",
            params,
            lambda res: self.on_completion_response(tab_info, res)
        )
        return False

    def on_completion_response(self, tab_info, result):
        current = self.get_current_tab()
        if not current or current["filepath"] != tab_info["filepath"]:
            return
            
        if not result:
            self.destroy_autocomplete_popup()
            return
            
        items = []
        if isinstance(result, dict):
            items = result.get("items", [])
        elif isinstance(result, list):
            items = result
            
        if not items:
            self.destroy_autocomplete_popup()
            return
            
        items = items[:50]
        
        if not hasattr(self, 'autocomplete_popup') or not self.autocomplete_popup:
            self.autocomplete_popup = AutocompletePopup(current["view"])
            
        self.autocomplete_popup.populate_items(items)


    def create_headerbar(self):
        self.hb = Gtk.HeaderBar()
        self.hb.set_show_close_button(True)
        self.hb.props.title = "DeltaEdit"
        self.set_titlebar(self.hb)

        # Left controls
        btn_new = Gtk.Button.new_from_icon_name("document-new", Gtk.IconSize.BUTTON)
        btn_new.set_tooltip_text("Create New File (Ctrl+N)")
        btn_new.connect("clicked", lambda w: self.add_editor_tab())
        self.hb.pack_start(btn_new)

        btn_open = Gtk.Button.new_from_icon_name("document-open", Gtk.IconSize.BUTTON)
        btn_open.set_tooltip_text("Open File (Ctrl+O)")
        btn_open.connect("clicked", self.on_open_clicked)
        self.hb.pack_start(btn_open)

        btn_save = Gtk.Button.new_from_icon_name("document-save", Gtk.IconSize.BUTTON)
        btn_save.set_tooltip_text("Save Current File (Ctrl+S)")
        btn_save.connect("clicked", self.on_save_clicked)
        self.hb.pack_start(btn_save)

        btn_save_as = Gtk.Button.new_from_icon_name("document-save-as", Gtk.IconSize.BUTTON)
        btn_save_as.set_tooltip_text("Save File As (Ctrl+Shift+S)")
        btn_save_as.connect("clicked", self.on_save_as_clicked)
        self.hb.pack_start(btn_save_as)

        btn_combine = Gtk.Button.new_with_label("Combine")
        btn_combine.set_tooltip_text("Append another file content to the end of this file")
        btn_combine.connect("clicked", self.on_combine_clicked)
        self.hb.pack_start(btn_combine)

        btn_open_folder = Gtk.Button.new_from_icon_name("folder-open", Gtk.IconSize.BUTTON)
        btn_open_folder.set_tooltip_text("Open Folder (Ctrl+Shift+D)")
        btn_open_folder.connect("clicked", self.on_open_folder_clicked)
        self.hb.pack_start(btn_open_folder)

        # Right controls
        self.hb_url_entry = Gtk.Entry()
        self.hb_url_entry.set_placeholder_text("Enter URL...")
        self.hb_url_entry.set_tooltip_text("Type URL and press Enter to open in Web Browser")
        self.hb_url_entry.set_width_chars(28)
        self.hb_url_entry.connect("activate", self.on_hb_url_activated)
        self.hb.pack_end(self.hb_url_entry)

        btn_info = Gtk.Button.new_from_icon_name("help-about", Gtk.IconSize.BUTTON)
        btn_info.connect("clicked", self.on_info_clicked)
        self.hb.pack_end(btn_info)

        btn_shortcuts = Gtk.Button.new_from_icon_name("help-contents", Gtk.IconSize.BUTTON)
        btn_shortcuts.set_tooltip_text("Shortcuts Help")
        btn_shortcuts.connect("clicked", self.show_shortcuts_popup)
        self.hb.pack_end(btn_shortcuts)

        self.btn_theme = Gtk.Button.new_from_icon_name("weather-clear-night" if self.is_dark else "weather-clear", Gtk.IconSize.BUTTON)
        self.btn_theme.set_tooltip_text("Toggle Light/Dark Theme")
        self.btn_theme.connect("clicked", self.on_theme_toggle_clicked)
        self.hb.pack_end(self.btn_theme)

        btn_memo = Gtk.Button.new_with_label("External Memo")
        btn_memo.set_tooltip_text("Launch GMemo app")
        btn_memo.connect("clicked", self.on_external_memo_clicked)
        self.hb.pack_end(btn_memo)

    def show_shortcuts_popup(self, widget):
        dialog = Gtk.MessageDialog(
            transient_for=self,
            flags=0,
            message_type=Gtk.MessageType.INFO,
            buttons=Gtk.ButtonsType.OK,
            text="DeltaEdit Shortcuts"
        )
        dialog.format_secondary_text(
            "• Ctrl + N : Create New File\n"
            "• Ctrl + O : Open File\n"
            "• Ctrl + Shift + D : Open Folder\n"
            "• Ctrl + S : Save File\n"
            "• Ctrl + Shift + S : Save File As\n"
            "• Ctrl + W : Close Current Tab\n"
            "• Ctrl + Shift + P : Preview Current Document\n"
            "• Ctrl + K : Cut Current Line\n"
            "• Ctrl + P : Search File (Fuzzy)\n"
            "• Ctrl + Shift + F : Search Text (Grep)\n"
            "• Ctrl + Z : Undo\n"
            "• Ctrl + Y : Redo\n"
            "• Ctrl + Left  : Focus Right Panel (Tools)\n"
            "• Ctrl + Right : Focus Left Panel (Editor)\n"
            "• Ctrl + Up    : Restore Split View"
        )
        dialog.run()
        dialog.destroy()

    def setup_accelerators(self):
        accel = Gtk.AccelGroup()
        self.add_accel_group(accel)
        
        # Ctrl+N : New
        key, mod = Gtk.accelerator_parse("<Control>n")
        accel.connect(key, mod, Gtk.AccelFlags.VISIBLE, lambda *a: self.add_editor_tab())
        
        # Ctrl+O : Open
        key, mod = Gtk.accelerator_parse("<Control>o")
        accel.connect(key, mod, Gtk.AccelFlags.VISIBLE, lambda *a: self.on_open_clicked(None))
        
        # Ctrl+S : Save
        key, mod = Gtk.accelerator_parse("<Control>s")
        accel.connect(key, mod, Gtk.AccelFlags.VISIBLE, lambda *a: self.on_save_clicked(None))
        
        # Ctrl+Shift+S : Save As
        key, mod = Gtk.accelerator_parse("<Control><Shift>s")
        accel.connect(key, mod, Gtk.AccelFlags.VISIBLE, lambda *a: self.on_save_as_clicked(None))

        # Ctrl+W : Close Current Tab
        key, mod = Gtk.accelerator_parse("<Control>w")
        accel.connect(key, mod, Gtk.AccelFlags.VISIBLE, lambda *a: self.close_current_tab())
        
        # Ctrl+Shift+P : Preview
        key, mod = Gtk.accelerator_parse("<Control><Shift>p")
        accel.connect(key, mod, Gtk.AccelFlags.VISIBLE, lambda *a: self.on_preview_clicked(None))
        
        # Ctrl+K : Cut Line
        key, mod = Gtk.accelerator_parse("<Control>k")
        accel.connect(key, mod, Gtk.AccelFlags.VISIBLE, lambda *a: self.cut_current_line())
        
        # Ctrl+P : Search File (Fuzzy)
        key, mod = Gtk.accelerator_parse("<Control>p")
        accel.connect(key, mod, Gtk.AccelFlags.VISIBLE, lambda *a: self.open_file_searcher())
        
        # Ctrl+Shift+F : Search Text (Grep)
        key, mod = Gtk.accelerator_parse("<Control><Shift>f")
        accel.connect(key, mod, Gtk.AccelFlags.VISIBLE, lambda *a: self.open_grep_searcher())
        
        # Ctrl+Shift+D : Open Folder
        key, mod = Gtk.accelerator_parse("<Control><Shift>d")
        accel.connect(key, mod, Gtk.AccelFlags.VISIBLE, lambda *a: self.on_open_folder_clicked(None))
        
        # Ctrl+Z : Undo
        key, mod = Gtk.accelerator_parse("<Control>z")
        accel.connect(key, mod, Gtk.AccelFlags.VISIBLE, lambda *a: self.undo_action())
        
        # Ctrl+Y : Redo
        key, mod = Gtk.accelerator_parse("<Control>y")
        accel.connect(key, mod, Gtk.AccelFlags.VISIBLE, lambda *a: self.redo_action())
        
        # Ctrl+Left : Show Tools (Right) Fullscreen
        key, mod = Gtk.accelerator_parse("<Control>Left")
        accel.connect(key, mod, Gtk.AccelFlags.VISIBLE, lambda *a: self.show_tools_full())
        
        # Ctrl+Right : Show Editor (Left) Fullscreen
        key, mod = Gtk.accelerator_parse("<Control>Right")
        accel.connect(key, mod, Gtk.AccelFlags.VISIBLE, lambda *a: self.show_editor_full())
        
        # Ctrl+Up : Restore Split View
        key, mod = Gtk.accelerator_parse("<Control>Up")
        accel.connect(key, mod, Gtk.AccelFlags.VISIBLE, lambda *a: self.show_split())

    def open_file_searcher(self):
        popup = FileSearcherPopup(self)
        popup.show_all()

    def open_grep_searcher(self):
        popup = GrepSearcherPopup(self)
        popup.show_all()

    def cut_current_line(self):
        current = self.get_current_tab()
        if not current:
            return
        buffer = current["buffer"]
        
        cursor_mark = buffer.get_insert()
        cursor_iter = buffer.get_iter_at_mark(cursor_mark)
        line_num = cursor_iter.get_line()
        
        start_iter = buffer.get_iter_at_line(line_num)
        end_iter = start_iter.copy()
        
        end_iter.forward_to_line_end()
        
        next_iter = end_iter.copy()
        if next_iter.forward_char():
            end_iter = next_iter
            
        text = buffer.get_text(start_iter, end_iter, True)
        
        clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        clipboard.set_text(text, -1)
        
        buffer.begin_user_action()
        buffer.delete(start_iter, end_iter)
        buffer.end_user_action()

    def paste_from_clipboard(self):
        current = self.get_current_tab()
        if not current:
            return
        buffer = current["buffer"]
        
        clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        buffer.begin_user_action()
        buffer.paste_clipboard(clipboard, None, True)
        buffer.end_user_action()

    def undo_action(self):
        current = self.get_current_tab()
        if not current:
            return
        buffer = current["buffer"]
        if buffer.can_undo():
            buffer.undo()

    def redo_action(self):
        current = self.get_current_tab()
        if not current:
            return
        buffer = current["buffer"]
        if buffer.can_redo():
            buffer.redo()

    def create_web_tab(self):
        web_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        
        # Controls Bar
        toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)
        btn_back = Gtk.Button.new_from_icon_name("go-previous", Gtk.IconSize.MENU)
        btn_back.connect("clicked", lambda w: self.webview.go_back())
        btn_forward = Gtk.Button.new_from_icon_name("go-next", Gtk.IconSize.MENU)
        btn_forward.connect("clicked", lambda w: self.webview.go_forward())
        btn_refresh = Gtk.Button.new_from_icon_name("view-refresh", Gtk.IconSize.MENU)
        btn_refresh.connect("clicked", lambda w: self.webview.reload())
        
        self.url_entry = Gtk.Entry()
        self.url_entry.set_placeholder_text("Type URL or search query and press Enter")
        self.url_entry.connect("activate", self.on_url_activated)
        
        btn_preview = Gtk.Button.new_with_label("Preview Current")
        btn_preview.set_tooltip_text("Live preview Markdown or HTML (Ctrl+P)")
        btn_preview.connect("clicked", self.on_preview_clicked)
        
        btn_bookmark_add = Gtk.Button.new_from_icon_name("bookmark-new", Gtk.IconSize.MENU)
        btn_bookmark_add.set_tooltip_text("Add Current Page to Bookmarks")
        btn_bookmark_add.connect("clicked", self.on_bookmark_add_clicked)
        
        btn_bookmark_remove = Gtk.Button.new_from_icon_name("list-remove", Gtk.IconSize.MENU)
        btn_bookmark_remove.set_tooltip_text("Remove Selected Bookmark")
        btn_bookmark_remove.connect("clicked", self.on_bookmark_remove_clicked)
        
        self.bookmark_combo = Gtk.ComboBoxText()
        self.bookmark_combo.set_tooltip_text("Select a bookmark")
        self.bookmark_combo.connect("changed", self.on_bookmark_selected)
        self.refresh_bookmark_combo()

        toolbar.pack_start(btn_back, False, False, 0)
        toolbar.pack_start(btn_forward, False, False, 0)
        toolbar.pack_start(btn_refresh, False, False, 0)
        toolbar.pack_start(self.url_entry, True, True, 0)
        toolbar.pack_start(btn_preview, False, False, 0)
        toolbar.pack_start(btn_bookmark_add, False, False, 0)
        toolbar.pack_start(btn_bookmark_remove, False, False, 0)
        toolbar.pack_start(self.bookmark_combo, False, False, 0)
        
        web_box.pack_start(toolbar, False, False, 0)
        
        # WebView Scrolled Window
        scrolled = Gtk.ScrolledWindow()
        self.webview = WebKit.WebView()
        self.webview.load_uri("https://www.google.com")
        scrolled.add(self.webview)
        web_box.pack_start(scrolled, True, True, 0)
        
        # Sync URL bar on navigation
        self.webview.connect("load-changed", self.on_web_load_changed)
        
        self.tools_notebook.append_page(web_box, Gtk.Label(label="Web Browser"))

    def create_terminal_tab(self):
        self.terminal = Vte.Terminal()
        self.terminal.spawn_sync(
            Vte.PtyFlags.DEFAULT,
            os.environ['HOME'],
            ["/bin/bash"],
            [],
            GLib.SpawnFlags.DO_NOT_REAP_CHILD,
            None,
            None,
        )
        # Style terminal slightly dark
        self.terminal.set_color_background(Gdk.RGBA(0.1, 0.1, 0.15, 1.0))
        self.terminal.set_color_foreground(Gdk.RGBA(0.8, 0.8, 0.95, 1.0))
        
        scrolled = Gtk.ScrolledWindow()
        scrolled.add(self.terminal)
        self.tools_notebook.append_page(scrolled, Gtk.Label(label="Terminal"))

    def create_helper_tab(self):
        helper_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        helper_box.set_border_width(8)
        
        # Encoding config
        enc_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        enc_lbl = Gtk.Label(label="Default Encoding: ")
        self.paper_encoding = Gtk.Entry()
        self.paper_encoding.set_text(self.encDefined)
        enc_btn = Gtk.Button.new_with_label("Apply Encoding")
        enc_btn.connect("clicked", self.on_apply_encoding_clicked)
        
        enc_box.pack_start(enc_lbl, False, False, 0)
        enc_box.pack_start(self.paper_encoding, True, True, 0)
        enc_box.pack_start(enc_btn, False, False, 0)
        
        helper_box.pack_start(enc_box, False, False, 0)
        
        # Help file viewer
        help_lbl = Gtk.Label(label="DeltaEdit Documentation")
        help_lbl.set_halign(Gtk.Align.START)
        helper_box.pack_start(help_lbl, False, False, 0)
        
        self.help_buffer = Gtk.TextBuffer()
        help_view = Gtk.TextView(buffer=self.help_buffer)
        help_view.set_editable(False)
        help_view.set_wrap_mode(Gtk.WrapMode.WORD)
        
        scrolled = Gtk.ScrolledWindow()
        scrolled.add(help_view)
        helper_box.pack_start(scrolled, True, True, 0)
        
        # Load help file content
        self.load_help_content()
        
        self.tools_notebook.append_page(helper_box, Gtk.Label(label="Help & Encoding"))

    def load_help_content(self):
        try:
            with open(self.help_file, 'r', encoding='utf-8') as f:
                content = f.read()
                self.help_buffer.set_text(content)
        except Exception as e:
            self.help_buffer.set_text(f"Error loading help file: {e}")

    def on_apply_encoding_clicked(self, widget):
        self.encDefined = self.paper_encoding.get_text().strip()
        enc_file = os.path.join(self.conf_dir, "encoding.editconf")
        try:
            with open(enc_file, 'w', encoding='utf-8') as f:
                f.write(self.encDefined + "\n")
            dialog = Gtk.MessageDialog(
                transient_for=self,
                flags=0,
                message_type=Gtk.MessageType.INFO,
                buttons=Gtk.ButtonsType.OK,
                text="Encoding Updated"
            )
            dialog.format_secondary_text(f"Default encoding changed to '{self.encDefined}'")
            dialog.run()
            dialog.destroy()
        except Exception as e:
            print("Failed to save encoding configurations:", e)

    def add_editor_tab(self, filepath=None):
        buffer = GtkSource.Buffer()
        
        # Configure Syntax styles
        scheme_manager = GtkSource.StyleSchemeManager.get_default()
        scheme = scheme_manager.get_scheme("oblivion" if self.is_dark else "classic")
        if scheme:
            buffer.set_style_scheme(scheme)

        # Setup Diagnostics Styles in buffer
        tag_err = buffer.create_tag("lsp_error", underline=Pango.Underline.SINGLE, foreground="red")
        tag_warn = buffer.create_tag("lsp_warning", underline=Pango.Underline.SINGLE, foreground="orange")
        
        view = GtkSource.View(height_request=1, width_request=1, buffer=buffer)
        view.set_show_line_numbers(True)
        view.set_highlight_current_line(True)
        view.set_auto_indent(False)
        view.set_indent_on_tab(True)
        view.set_tab_width(4)
        
        font_desc = Pango.FontDescription("Monospace 11")
        view.override_font(font_desc)
        
        # Connect key-press-event to intercept keys for custom autocomplete popup
        view.connect("key-press-event", self.on_view_key_press)
        
        # Scrolled window wrapper
        scrolled = Gtk.ScrolledWindow()
        scrolled.add(view)
        
        # Init Tree-Sitter semantic highlighter if available
        highlighter = TreeSitterHighlighter(buffer, filepath, self.is_dark) if filepath else None

        tab_info = {
            "filepath": filepath,
            "buffer": buffer,
            "view": view,
            "scrolled": scrolled,
            "label_widget": None,
            "label_title": None,
            "is_modified": False,
            "diagnostics": [],
            "highlighter": highlighter
        }
        
        self.tabs.append(tab_info)
        
        # Create tab title container
        title_str = os.path.basename(filepath) if filepath else "Untitled"
        tab_title_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        tab_title_lbl = Gtk.Label(label=title_str)
        tab_info["label_title"] = tab_title_lbl
        
        close_btn = Gtk.Button.new_from_icon_name("window-close", Gtk.IconSize.MENU)
        close_btn.set_relief(Gtk.ReliefStyle.NONE)
        close_btn.set_can_focus(False)
        close_btn.connect("clicked", self.on_close_btn_clicked, scrolled)
        
        tab_title_box.pack_start(tab_title_lbl, True, True, 0)
        tab_title_box.pack_start(close_btn, False, False, 0)
        tab_title_box.show_all()
        tab_info["label_widget"] = tab_title_box
        
        # Insert page
        page_num = self.editor_notebook.append_page(scrolled, tab_title_box)
        self.editor_notebook.show_all()
        self.editor_notebook.set_current_page(page_num)
        
        # File Open logic
        if filepath and os.path.exists(filepath):
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
            except UnicodeDecodeError:
                try:
                    with open(filepath, 'r', encoding=self.encDefined) as f:
                        content = f.read()
                except Exception as e:
                    content = f"Error opening file: {e}"
            
            buffer.set_text(content)
            # Guess language
            lang_manager = GtkSource.LanguageManager.get_default()
            lang = lang_manager.guess_language(filepath)
            buffer.set_language(lang)
            
            # Semantic highlight trigger
            if highlighter:
                highlighter.highlight()
            
            # Start LSP
            self.lsp_manager.notify_open(filepath, content, lang.get_id() if lang else None)
            
        # Connect modification & connection events
        buffer.connect("changed", self.on_buffer_changed, tab_info)
        view.connect("populate-popup", self.on_editor_popup_menu, tab_info)
        view.connect("query-tooltip", self.on_query_tooltip, tab_info)
        view.set_has_tooltip(True)

    def on_buffer_changed(self, buffer, tab_info):
        if not tab_info["is_modified"]:
            tab_info["is_modified"] = True
            self.update_tab_title(tab_info)
            
        # Semantic highlighting on-change
        if tab_info["highlighter"]:
            tab_info["highlighter"].highlight()

        # LSP text sync
        if tab_info["filepath"]:
            start = buffer.get_start_iter()
            end = buffer.get_end_iter()
            text = buffer.get_text(start, end, True)
            self.lsp_manager.notify_change(tab_info["filepath"], text)
            
            # If popup is visible, filter it instantly. Otherwise, trigger debounced request.
            if hasattr(self, 'autocomplete_popup') and self.autocomplete_popup and self.autocomplete_popup.get_visible():
                self.autocomplete_popup.filter_items()
            
            # Debounced Autocomplete trigger
            if hasattr(self, 'autocomplete_timeout_id') and self.autocomplete_timeout_id:
                GLib.source_remove(self.autocomplete_timeout_id)
                self.autocomplete_timeout_id = None
                
            self.autocomplete_timeout_id = GLib.timeout_add(150, self.trigger_autocomplete, tab_info)

    def update_tab_title(self, tab_info):
        base = os.path.basename(tab_info["filepath"]) if tab_info["filepath"] else "Untitled"
        if tab_info["is_modified"]:
            tab_info["label_title"].set_text(f"*{base}")
        else:
            tab_info["label_title"].set_text(base)

    def get_current_tab(self):
        page_num = self.editor_notebook.get_current_page()
        if page_num != -1 and page_num < len(self.tabs):
            return self.tabs[page_num]
        return None

    def on_close_btn_clicked(self, widget, child_widget):
        page_num = self.editor_notebook.page_num(child_widget)
        if page_num != -1:
            self.close_tab(page_num)

    def close_current_tab(self):
        page_num = self.editor_notebook.get_current_page()
        if page_num != -1:
            self.close_tab(page_num)

    def close_tab(self, page_num):
        self.destroy_autocomplete_popup()
        tab = self.tabs[page_num]
        if tab["is_modified"]:
            dialog = Gtk.MessageDialog(
                transient_for=self,
                flags=0,
                message_type=Gtk.MessageType.QUESTION,
                buttons=Gtk.ButtonsType.YES_NO_CANCEL,
                text="Unsaved Changes"
            )
            dialog.format_secondary_text(f"Do you want to save changes to '{os.path.basename(tab['filepath']) if tab['filepath'] else 'Untitled'}' before closing?")
            response = dialog.run()
            dialog.destroy()
            
            if response == Gtk.ResponseType.YES:
                if not self.save_tab(tab):
                    return
            elif response == Gtk.ResponseType.CANCEL:
                return

        # Stop LSP server if active
        if tab["filepath"]:
            self.lsp_manager.stop_server_for_file(tab["filepath"])

        self.editor_notebook.remove_page(page_num)
        self.tabs.pop(page_num)
        
        # Fallback to keep one empty editor tab active
        if self.editor_notebook.get_n_pages() == 0:
            self.add_editor_tab()

    def on_open_clicked(self, widget):
        dialog = Gtk.FileChooserDialog(
            "Open File...",
            self,
            Gtk.FileChooserAction.OPEN,
            (Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OPEN, Gtk.ResponseType.OK)
        )
        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            filepath = dialog.get_filename()
            already_open = False
            for t in self.tabs:
                if t["filepath"] == filepath:
                    page_num = self.editor_notebook.page_num(t["scrolled"])
                    self.editor_notebook.set_current_page(page_num)
                    already_open = True
                    break
            if not already_open:
                self.add_editor_tab(filepath)
        dialog.destroy()

    def on_save_clicked(self, widget):
        current = self.get_current_tab()
        if current:
            self.save_tab(current)

    def on_save_as_clicked(self, widget):
        current = self.get_current_tab()
        if current:
            self.save_tab(current, force_save_as=True)

    def save_tab(self, tab, force_save_as=False):
        if not tab["filepath"] or force_save_as:
            dialog = Gtk.FileChooserDialog(
                "Save File...",
                self,
                Gtk.FileChooserAction.SAVE,
                (Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_SAVE, Gtk.ResponseType.OK)
            )
            if tab["filepath"]:
                dialog.set_filename(tab["filepath"])
            else:
                dialog.set_current_name("Untitled.txt")
                
            response = dialog.run()
            if response == Gtk.ResponseType.OK:
                filepath = dialog.get_filename()
                dialog.destroy()
                tab["filepath"] = filepath
            else:
                dialog.destroy()
                return False

        # Save buffer content
        start = tab["buffer"].get_start_iter()
        end = tab["buffer"].get_end_iter()
        text = tab["buffer"].get_text(start, end, True)
        
        try:
            with open(tab["filepath"], 'w', encoding='utf-8') as f:
                f.write(text)
        except Exception:
            try:
                with open(tab["filepath"], 'w', encoding=self.encDefined) as f:
                    f.write(text)
            except Exception as e:
                err_dialog = Gtk.MessageDialog(
                    transient_for=self,
                    flags=0,
                    message_type=Gtk.MessageType.ERROR,
                    buttons=Gtk.ButtonsType.OK,
                    text="Save Failed"
                )
                err_dialog.format_secondary_text(f"Could not save file: {e}")
                err_dialog.run()
                err_dialog.destroy()
                return False
                
        tab["is_modified"] = False
        self.update_tab_title(tab)
        
        # Re-initialize semantic highlighter
        tab["highlighter"] = TreeSitterHighlighter(tab["buffer"], tab["filepath"])
        if tab["highlighter"]:
            tab["highlighter"].highlight()

        # Configure language and LSP after saving (in case file extension changed)
        lang_manager = GtkSource.LanguageManager.get_default()
        lang = lang_manager.guess_language(tab["filepath"])
        tab["buffer"].set_language(lang)
        self.lsp_manager.notify_open(tab["filepath"], text, lang.get_id() if lang else None)
        return True

    def on_combine_clicked(self, widget):
        current = self.get_current_tab()
        if not current:
            return
            
        dialog = Gtk.FileChooserDialog(
            "Combine File...",
            self,
            Gtk.FileChooserAction.OPEN,
            (Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OPEN, Gtk.ResponseType.OK)
        )
        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            filepath = dialog.get_filename()
            try:
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        impdata = f.read()
                except:
                    with open(filepath, 'r', encoding=self.encDefined) as f:
                        impdata = f.read()
                        
                end_iter = current["buffer"].get_end_iter()
                current["buffer"].insert(end_iter, "\n" + impdata)
            except Exception as e:
                err_dialog = Gtk.MessageDialog(
                    transient_for=self,
                    flags=0,
                    message_type=Gtk.MessageType.ERROR,
                    buttons=Gtk.ButtonsType.OK,
                    text="Combine Error"
                )
                err_dialog.format_secondary_text(f"Could not combine: {e}")
                err_dialog.run()
                err_dialog.destroy()
        dialog.destroy()

    def on_external_memo_clicked(self, widget):
        try:
            subprocess.Popen('gmemo')
        except:
            try:
                subprocess.Popen('/usr/bin/gmemo')
            except Exception as e:
                print("Could not run external GMemo:", e)

    def on_info_clicked(self, widget):
        dialog = Gtk.AboutDialog(transient_for=self)
        dialog.set_program_name("DeltaEdit")
        dialog.set_version("2.0.0")
        dialog.set_comments("Refactored modern web-integrated text editor with LSP and Tree-sitter support.")
        dialog.set_logo_icon_name("help-about")
        dialog.run()
        dialog.destroy()

    def on_tab_switched(self, notebook, page, page_num):
        self.destroy_autocomplete_popup()
        if page_num < len(self.tabs):
            tab = self.tabs[page_num]
            title = os.path.basename(tab["filepath"]) if tab["filepath"] else "Untitled"
            self.hb.props.subtitle = title
            if hasattr(self, 'git_panel'):
                self.git_panel.refresh_git_status()



    def apply_diagnostics(self, file_path, diagnostics):
        matched_tab = None
        for tab in self.tabs:
            if tab["filepath"] and os.path.abspath(tab["filepath"]) == os.path.abspath(file_path):
                matched_tab = tab
                break
                
        if not matched_tab:
            return False
            
        buffer = matched_tab["buffer"]
        start_it = buffer.get_start_iter()
        end_it = buffer.get_end_iter()
        
        # Clear previous markers
        buffer.remove_tag_by_name("lsp_error", start_it, end_it)
        buffer.remove_tag_by_name("lsp_warning", start_it, end_it)
        
        matched_tab["diagnostics"] = diagnostics
        
        for diag in diagnostics:
            rng = diag.get("range", {})
            start_pos = rng.get("start", {})
            end_pos = rng.get("end", {})
            
            s_line = start_pos.get("line", 0)
            s_char = start_pos.get("character", 0)
            e_line = end_pos.get("line", 0)
            e_char = end_pos.get("character", 0)
            
            s_iter = buffer.get_iter_at_line_offset(s_line, s_char)
            e_iter = buffer.get_iter_at_line_offset(e_line, e_char)
            
            severity = diag.get("severity", 1)
            if severity == 1:
                buffer.apply_tag_by_name("lsp_error", s_iter, e_iter)
            else:
                buffer.apply_tag_by_name("lsp_warning", s_iter, e_iter)
                
        return False

    def on_query_tooltip(self, view, x, y, keyboard_mode, tooltip, tab_info):
        coords = view.window_to_buffer_coords(Gtk.TextWindowType.WIDGET, x, y)
        res = view.get_iter_at_location(coords[0], coords[1])
        if not res:
            return False
        iter_at_mouse = res[0]
        
        has_tag = False
        tags = iter_at_mouse.get_tags()
        for t in tags:
            if t.get_property("name") in ["lsp_error", "lsp_warning"]:
                has_tag = True
                break
                
        if not has_tag:
            return False
            
        line = iter_at_mouse.get_line()
        
        tooltip_txt = ""
        for diag in tab_info.get("diagnostics", []):
            rng = diag.get("range", {})
            s_line = rng.get("start", {}).get("line", 0)
            e_line = rng.get("end", {}).get("line", 0)
            
            if s_line <= line <= e_line:
                sev = "Error" if diag.get("severity", 1) == 1 else "Warning"
                tooltip_txt += f"[{sev}] {diag.get('message')}\n"
                
        if tooltip_txt:
            tooltip.set_text(tooltip_txt.strip())
            return True
            
        return False

    def on_url_activated(self, entry):
        url = entry.get_text().strip()
        if not url:
            return
            
        if not (url.startswith("http://") or url.startswith("https://")):
            if "." in url and " " not in url:
                url = "https://" + url
            else:
                query = urllib.parse.quote(url)
                url = f"https://www.google.com/search?q={query}"
                
        self.webview.load_uri(url)

    def on_web_load_changed(self, webview, event):
        if event == WebKit.LoadEvent.COMMITTED:
            uri = webview.get_uri()
            self.url_entry.set_text(uri)

    def on_preview_clicked(self, widget):
        current = self.get_current_tab()
        if not current:
            return
            
        start = current["buffer"].get_start_iter()
        end = current["buffer"].get_end_iter()
        text = current["buffer"].get_text(start, end, True)
        
        filepath = current["filepath"]
        ext = os.path.splitext(filepath)[1].lower() if filepath else ""
        
        # Color palettes for HTML preview based on theme
        bg_color = "#1e1e2e" if self.is_dark else "#f4f4f6"
        text_color = "#cdd6f4" if self.is_dark else "#4c4f69"
        accent_color = "#89b4fa" if self.is_dark else "#7287fd"
        border_color = "#45475a" if self.is_dark else "#bcc0cc"
        code_bg = "#313244" if self.is_dark else "#e6e9ef"
        code_color = "#f38ba8" if self.is_dark else "#d20f39"
        
        html_content = ""
        if ext in ['.md', '.markdown']:
            if HAS_MARKDOWN:
                html_body = markdown.markdown(text)
            else:
                # Basic HTML markdown fallback
                lines = text.split('\n')
                html_body = ""
                for line in lines:
                    if line.startswith('# '):
                        html_body += f"<h1>{line[2:]}</h1>"
                    elif line.startswith('## '):
                        html_body += f"<h2>{line[3:]}</h2>"
                    elif line.startswith('- ') or line.startswith('* '):
                        html_body += f"<li>{line[2:]}</li>"
                    else:
                        html_body += f"<p>{line}</p>"
                        
            html_content = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="utf-8">
                <style>
                    body {{
                        background-color: {bg_color};
                        color: {text_color};
                        font-family: sans-serif;
                        padding: 20px;
                        line-height: 1.6;
                    }}
                    h1, h2, h3 {{ color: {accent_color}; border-bottom: 1px solid {border_color}; padding-bottom: 5px; }}
                    pre {{ background-color: {code_bg}; padding: 10px; border-radius: 6px; border: 1px solid {border_color}; overflow-x: auto; }}
                    code {{ font-family: monospace; background-color: {code_bg}; padding: 2px 4px; border-radius: 4px; color: {code_color}; }}
                    a {{ color: {accent_color}; }}
                </style>
            </head>
            <body>
                {html_body}
            </body>
            </html>
            """
            self.webview.load_html(html_content, "file://")
            self.tools_notebook.set_current_page(0)
            
        elif ext in ['.html', '.htm']:
            self.webview.load_html(text, "file://")
            self.tools_notebook.set_current_page(0)
        else:
            escaped = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            html_content = f"""
            <html>
            <body style="background-color: {bg_color}; color: {text_color}; font-family: monospace; padding: 20px;">
                <pre>{escaped}</pre>
            </body>
            </html>
            """
            self.webview.load_html(html_content, "file://")
            self.tools_notebook.set_current_page(0)

    def on_editor_popup_menu(self, view, popup, tab_info):
        buffer = tab_info["buffer"]
        has_selection, start, end = buffer.get_selection_bounds()
        
        if has_selection:
            selected_text = buffer.get_text(start, end, True).strip()
            if selected_text:
                menu_item = Gtk.MenuItem(label=f"Search Google for '{selected_text[:15]}...'")
                menu_item.connect("clicked", self.on_search_popup_clicked, selected_text)
                popup.append(menu_item)
                popup.show_all()

    def on_search_popup_clicked(self, menu_item, text):
        query = urllib.parse.quote(text)
        url = f"https://www.google.com/search?q={query}"
        self.webview.load_uri(url)
        self.tools_notebook.set_current_page(0)

    def on_hb_url_activated(self, entry):
        url = entry.get_text().strip()
        if not url:
            return
        if not (url.startswith("http://") or url.startswith("https://")):
            if "." in url and " " not in url:
                url = "https://" + url
            else:
                query = urllib.parse.quote(url)
                url = f"https://www.google.com/search?q={query}"
        self.webview.load_uri(url)
        self.tools_notebook.set_current_page(0)

    def on_open_folder_clicked(self, widget):
        dialog = Gtk.FileChooserDialog(
            "Open Folder...",
            self,
            Gtk.FileChooserAction.SELECT_FOLDER,
            (Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OPEN, Gtk.ResponseType.OK)
        )
        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            folder_path = dialog.get_filename()
            self.current_folder = folder_path
            self.populate_file_tree(folder_path)
        dialog.destroy()

    def populate_file_tree(self, root_path):
        self.file_tree_store.clear()
        if not root_path or not os.path.isdir(root_path):
            return

        def add_children(parent_iter, path):
            try:
                entries = sorted(os.listdir(path))
            except Exception:
                return
            dirs = []
            files = []
            for entry in entries:
                if entry.startswith('.'):
                    continue
                full = os.path.join(path, entry)
                if os.path.isdir(full):
                    dirs.append(entry)
                else:
                    files.append(entry)
            for d in dirs:
                full = os.path.join(path, d)
                piter = self.file_tree_store.append(parent_iter, ["folder", d, full, True])
                add_children(piter, full)
            for f in files:
                full = os.path.join(path, f)
                self.file_tree_store.append(parent_iter, ["text-x-generic", f, full, False])

        add_children(None, root_path)

    def on_tree_item_activated(self, treeview, path, column):
        model = treeview.get_model()
        iter_ = model.get_iter(path)
        if not iter_:
            return
        full_path = model[iter_][2]
        is_folder = model[iter_][3]
        if is_folder:
            if treeview.row_expanded(path):
                treeview.collapse_row(path)
            else:
                treeview.expand_row(path, False)
        else:
            if os.path.isfile(full_path):
                self.add_editor_tab(full_path)

    def show_tools_full(self):
        self.left_paned.hide()
        self.tools_notebook.show()
        self.view_mode = "tools"

    def show_editor_full(self):
        self.tools_notebook.hide()
        self.left_paned.show()
        self.view_mode = "editor"

    def show_split(self):
        self.tools_notebook.show()
        self.left_paned.show()
        self.main_paned.set_position(900)
        self.left_paned.set_position(220)
        self.view_mode = "split"

    def load_bookmarks(self):
        if os.path.exists(self.bookmarks_file):
            try:
                with open(self.bookmarks_file, 'r', encoding='utf-8') as f:
                    self.bookmarks = json.load(f)
                    if not isinstance(self.bookmarks, list):
                        self.bookmarks = []
            except Exception:
                self.bookmarks = []
        else:
            self.bookmarks = []

    def save_bookmarks(self):
        try:
            with open(self.bookmarks_file, 'w', encoding='utf-8') as f:
                json.dump(self.bookmarks, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print("Failed to save bookmarks:", e)

    def refresh_bookmark_combo(self):
        if not hasattr(self, 'bookmark_combo') or not self.bookmark_combo:
            return
        # Block changed signal to avoid accidental navigation during refresh
        try:
            self.bookmark_combo.handler_block_by_func(self.on_bookmark_selected)
        except TypeError:
            pass
        self.bookmark_combo.remove_all()
        for bm in self.bookmarks:
            title = bm.get("title", bm.get("url", "Untitled"))
            self.bookmark_combo.append_text(title)
        self.bookmark_combo.set_active(-1)
        try:
            self.bookmark_combo.handler_unblock_by_func(self.on_bookmark_selected)
        except TypeError:
            pass

    def on_bookmark_add_clicked(self, widget):
        uri = self.webview.get_uri()
        if not uri:
            return
        title = self.url_entry.get_text().strip() or uri
        self.bookmarks.append({"title": title, "url": uri})
        self.save_bookmarks()
        self.refresh_bookmark_combo()

    def on_bookmark_remove_clicked(self, widget):
        active = self.bookmark_combo.get_active()
        if active < 0 or active >= len(self.bookmarks):
            return
        self.bookmarks.pop(active)
        self.save_bookmarks()
        self.refresh_bookmark_combo()

    def on_bookmark_selected(self, combo):
        active = combo.get_active()
        if active < 0 or active >= len(self.bookmarks):
            return
        url = self.bookmarks[active].get("url")
        if url:
            self.webview.load_uri(url)
            self.url_entry.set_text(url)


class Application(Gtk.Application):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, application_id="org.dedit", **kwargs)
        
    def do_activate(self):
        files = []
        for arg in sys.argv[1:]:
            if not arg.startswith("-") and os.path.exists(arg):
                files.append(os.path.abspath(arg))
                
        self.window = AppWindow(application=self, files=files)


if __name__ == "__main__":
    app = Application()
    app.run(sys.argv)

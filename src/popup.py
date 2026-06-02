import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk

class AutocompletePopup(Gtk.Window):
    def __init__(self, parent_view):
        super().__init__(type=Gtk.WindowType.POPUP)
        self.view = parent_view
        self.set_transient_for(parent_view.get_toplevel())
        self.set_decorated(False)
        self.set_keep_above(True)
        
        # Scrollable container for ListBox
        self.scrolled = Gtk.ScrolledWindow()
        self.scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.scrolled.set_max_content_height(250)
        self.scrolled.set_propagate_natural_height(True)
        
        self.listbox = Gtk.ListBox()
        self.listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.listbox.connect("row-activated", self.on_row_activated)
        self.scrolled.add(self.listbox)
        self.add(self.scrolled)
        
        self.apply_popup_style()
        self.items = []
        self.raw_items = []
        self.show_all()

    def apply_popup_style(self):
        toplevel = self.view.get_toplevel()
        is_dark = getattr(toplevel, 'is_dark', True)
        
        css_provider = Gtk.CssProvider()
        if is_dark:
            css = b"""
            list {
                background-color: #242538;
                border: 1px solid #45475a;
                border-radius: 6px;
            }
            row {
                padding: 4px 8px;
                color: #cdd6f4;
            }
            row:selected {
                background-color: #313244;
                color: #b4befe;
            }
            label.dim-label {
                color: #585b70;
                font-size: 0.9em;
            }
            """
        else:
            css = b"""
            list {
                background-color: #e6e9ef;
                border: 1px solid #bcc0cc;
                border-radius: 6px;
            }
            row {
                padding: 4px 8px;
                color: #4c4f69;
            }
            row:selected {
                background-color: #ccd0da;
                color: #7287fd;
            }
            label.dim-label {
                color: #9ca0b0;
                font-size: 0.9em;
            }
            """
        css_provider.load_from_data(css)
        self.get_style_context().add_provider(css_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    def get_current_prefix(self):
        buffer = self.view.get_buffer()
        cursor_iter = buffer.get_iter_at_mark(buffer.get_insert())
        
        start_iter = cursor_iter.copy()
        while start_iter.get_line_offset() > 0:
            start_iter.backward_char()
            char = start_iter.get_char()
            if not (char.isalnum() or char == '_'):
                start_iter.forward_char()
                break
        return buffer.get_text(start_iter, cursor_iter, True)

    def populate_items(self, raw_items):
        self.raw_items = raw_items
        self.filter_items()

    def filter_items(self):
        prefix = self.get_current_prefix().lower()
        
        # Clear listbox
        for child in self.listbox.get_children():
            self.listbox.remove(child)
            
        self.items = []
        
        LSP_KIND_MAP = {
            1: ("Text", "📝"),
            2: ("Method", "📦"),
            3: ("Function", "λ"),
            4: ("Constructor", "🛠️"),
            5: ("Field", "🏷️"),
            6: ("Variable", "x"),
            7: ("Class", "🏛️"),
            8: ("Interface", "🔌"),
            9: ("Module", "📦"),
            10: ("Property", "🔧"),
            11: ("Unit", "📏"),
            12: ("Value", "💎"),
            13: ("Enum", "🔢"),
            14: ("Keyword", "🔑"),
            15: ("Snippet", "✂️"),
            16: ("Color", "🎨"),
            17: ("File", "📄"),
            18: ("Reference", "🔗"),
            19: ("Folder", "📂"),
            20: ("EnumMember", "🔢"),
            21: ("Constant", "π"),
            22: ("Struct", "🏗️"),
            23: ("Event", "🔔"),
            24: ("Operator", "±"),
            25: ("TypeParameter", "T")
        }
        
        for item in self.raw_items:
            label = item.get("label", "")
            if prefix and not label.lower().startswith(prefix):
                continue
                
            self.items.append(item)
            
            row_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            
            kind_val = item.get("kind", 1)
            kind_name, icon = LSP_KIND_MAP.get(kind_val, ("Text", "📝"))
            
            lbl_icon = Gtk.Label(label=icon)
            lbl_label = Gtk.Label(label=label)
            lbl_label.set_halign(Gtk.Align.START)
            
            detail = item.get("detail", "")
            if not detail:
                detail = kind_name
            lbl_detail = Gtk.Label(label=detail)
            lbl_detail.set_halign(Gtk.Align.END)
            lbl_detail.get_style_context().add_class("dim-label")
            
            lbl_icon.set_size_request(20, -1)
            
            row_box.pack_start(lbl_icon, False, False, 0)
            row_box.pack_start(lbl_label, True, True, 0)
            row_box.pack_end(lbl_detail, False, False, 0)
            
            self.listbox.add(row_box)
            
        self.show_all()
        
        if self.items:
            self.listbox.select_row(self.listbox.get_row_at_index(0))
            self.position_popup()
            self.show()
        else:
            self.hide()

    def position_popup(self):
        buffer = self.view.get_buffer()
        cursor_iter = buffer.get_iter_at_mark(buffer.get_insert())
        rect = self.view.get_iter_location(cursor_iter)
        
        win_x, win_y = self.view.buffer_to_window_coords(
            Gtk.TextWindowType.TEXT, rect.x, rect.y + rect.height
        )
        
        gdk_win = self.view.get_window(Gtk.TextWindowType.TEXT)
        if not gdk_win:
            return
        origin_x, origin_y = gdk_win.get_origin()
        
        self.move(origin_x + win_x, origin_y + win_y)

    def move_selection(self, step):
        selected_row = self.listbox.get_selected_row()
        if not selected_row:
            return
        idx = selected_row.get_index()
        new_idx = idx + step
        if 0 <= new_idx < len(self.items):
            row_to_select = self.listbox.get_row_at_index(new_idx)
            self.listbox.select_row(row_to_select)
            
            adj = self.scrolled.get_vadjustment()
            row_rect = row_to_select.get_allocation()
            adj.clamp_page(row_rect.y, row_rect.y + row_rect.height)

    def confirm_selection(self):
        selected_row = self.listbox.get_selected_row()
        if not selected_row:
            self.get_toplevel().destroy_autocomplete_popup()
            return
            
        idx = selected_row.get_index()
        if idx >= len(self.items):
            self.get_toplevel().destroy_autocomplete_popup()
            return
            
        item = self.items[idx]
        insert_text = item.get("insertText") or item.get("label", "")
        
        buffer = self.view.get_buffer()
        cursor_iter = buffer.get_iter_at_mark(buffer.get_insert())
        
        start_iter = cursor_iter.copy()
        prefix_len = len(self.get_current_prefix())
        start_iter.backward_chars(prefix_len)
        
        buffer.begin_user_action()
        buffer.delete(start_iter, cursor_iter)
        buffer.insert(start_iter, insert_text)
        buffer.end_user_action()
        
        self.get_toplevel().destroy_autocomplete_popup()

    def on_row_activated(self, listbox, row):
        self.confirm_selection()

#!/usr/bin/python3
import gi
import sys

gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, Pango

class AppWindow(Gtk.ApplicationWindow):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.set_default_size(500, 550)
        
        # Apply dark theme styling
        self.apply_theme()
        
        # HeaderBar
        hb = Gtk.HeaderBar()
        hb.set_show_close_button(True)
        hb.props.title = "GMemo"
        hb.props.subtitle = "Quick Popup Memo"
        self.set_titlebar(hb)
        
        # Text view
        self.buffer = Gtk.TextBuffer()
        self.view = Gtk.TextView(buffer=self.buffer)
        self.view.set_wrap_mode(Gtk.WrapMode.WORD)
        
        # Style text view
        font_desc = Pango.FontDescription("Monospace 11")
        self.view.override_font(font_desc)
        
        scrolled = Gtk.ScrolledWindow()
        scrolled.add(self.view)
        self.add(scrolled)
        
        self.show_all()

    def apply_theme(self):
        css_provider = Gtk.CssProvider()
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
        textview text {
            background-color: #181825;
            color: #cdd6f4;
        }
        """
        css_provider.load_from_data(css)
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(),
            css_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

class Application(Gtk.Application):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, application_id="org.dedit.memo", **kwargs)
        
    def do_activate(self):
        self.window = AppWindow(application=self)

if __name__ == "__main__":
    app = Application()
    app.run(sys.argv)

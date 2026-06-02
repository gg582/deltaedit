#!/usr/bin/python3
import os
import subprocess
from subprocess import call
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk

class WIN(Gtk.Window):
    def __init__(self):
        Gtk.Window.__init__(self, title="INSTALLER")
        _all = Gtk.Button.new_with_label("ALL")
        _all.connect("clicked", self.INST_ALL)
        self.add(_all)

    def INST_ALL(self, widget):
        script_dir = os.path.dirname(os.path.abspath(__file__))
        install_script = os.path.join(script_dir, '..', 'Install.sh')
        try:
            ret = call([install_script])
            if ret != 0:
                raise RuntimeError(f"Install.sh exited with code {ret}")
            ww = Gtk.Window()
            ll = Gtk.Label.new_with_mnemonic("SUCCESSFULLY INSTALLED")
            ww.add(ll)
            ww.connect("destroy", Gtk.main_quit)
            ww.show_all()
            Gtk.main()
        except Exception as e:
            print(f"Install error: {e}")
            w = Gtk.Window()
            l = Gtk.Label.new_with_mnemonic("INSTALL FAILED")
            w.add(l)
            w.connect("destroy", Gtk.main_quit)
            w.show_all()
            Gtk.main()

win = WIN()
win.connect("destroy", Gtk.main_quit)
win.show_all()
Gtk.main()

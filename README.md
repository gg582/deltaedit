# README #

### DeltaEdit - Non-Unicode CJK Text Editor ###

---

## 🌟 Project Description ✨

DeltaEdit is a lightweight, non-Unicode text editor designed specifically 
for CJK (Chinese, Japanese, Korean) languages on Unix-like operating 
systems. It offers:

- Internal browser tab for seamless problem-solving platform integration
- Smart auto-indent functionality
- Syntax highlighting support
- Modularized architecture

---

## 🛠️ Setup Instructions ⚙️

### Dependencies:
Before installing DeltaEdit, ensure you have the following dependencies 
installed:

```
❯ git
❯ python3-gi
❯ gir1.2-webkit2-4.0
❯ python3-pip
❯ gir1.2-gtksource-4
❯ gir1.2-glib-2.0
❯ gir1.2-vte-2.91
```

### Optional Dependencies (for LSP & Tree-Sitter):
For features like code autocomplete, diagnostics, and tree-sitter based highlighting:

- **Tree-Sitter Highlighting & Indent:**
  ```bash
  pip3 install tree-sitter tree-sitter-languages
  ```
- **LSP Servers:**
  - Python: `pylsp` (via pip) or `pyright-langserver` (via npm)
  - C/C++: `clangd`
  - Rust: `rust-analyzer`


### Build & Installation Dependencies:
For compiling the standalone application binaries via Nuitka:
- Python 3 `venv` support (e.g., `python3-venv` on Debian/Ubuntu)
- C Compiler: `gcc` or `clang`
- Binary utility: `patchelf` (Highly recommended for Nuitka standalone packaging)

### Installation:
1. Install system requirements:
   ```bash
   sudo apt install python3-venv gcc patchelf
   ```
2. Run `Installer.py` (or directly run `./Install.sh`) to build and install DeltaEdit.
3. Run `Uninstaller.py` (or `./Uninstall.sh`) to uninstall DeltaEdit.


---

## 🔧 How to Run 🛡️

Run the following commands in your terminal:

```
# To launch the Text Editor
$ dedit

# To open the Memo App
$ gmemo
```

---

## 🤝 Contribution Guidelines ✨

Your contributions are highly welcome! If you'd like to contribute, 
please:

1. Fork the repository.
2. Create a new branch for your feature or bug fix.
3. Commit changes with clear commit messages.
4. Push to the branch and create a Pull Request.

---

## 📧 Contact Information ✉️

For any questions, suggestions, or feedback, feel free to contact:

```
$ gzblues61@gmail.com
```

---

## 💻 Windows Support 🛑

Unfortunately, DeltaEdit currently does not support Windows due to the insufficiency of Python3 Gtk+ 3 implementations on Windows. Stay tuned for future 
updates!

---

### Thank you for choosing DeltaEdit! 🙏

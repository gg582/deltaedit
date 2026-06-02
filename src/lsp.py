import os
import json
import shutil
import threading
import subprocess
from gi.repository import GLib

class LSPManager:
    """Manages LSP servers in the background using subprocesses and JSON-RPC over stdin/stdout."""
    def __init__(self, app_window):
        self.app_window = app_window
        self.servers = {}           # file_path -> subprocess.Popen
        self.threads = {}           # file_path -> threading.Thread
        self.version_counters = {}  # file_path -> int
        self.callbacks = {}         # msg_id -> callback function
        self.next_id = 10           # next JSON-RPC request ID

    def start_server_for_file(self, file_path, lang):
        if not file_path or file_path in self.servers:
            return

        cmd = None
        ext = os.path.splitext(file_path)[1].lower()
        
        if ext == '.rs':
            rust_analyzer = os.path.expanduser("~/.cargo/bin/rust-analyzer")
            if shutil.which(rust_analyzer):
                cmd = [rust_analyzer]
            elif shutil.which("rust-analyzer"):
                cmd = ["rust-analyzer"]
        elif ext == '.py':
            if shutil.which("pylsp"):
                cmd = ["pylsp"]
            elif shutil.which("pyright-langserver"):
                cmd = ["pyright-langserver", "--stdio"]
        elif ext in ['.c', '.cpp', '.h', '.cc']:
            if shutil.which("clangd"):
                cmd = ["clangd"]

        if not cmd:
            return

        try:
            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                bufsize=0
            )
            self.servers[file_path] = proc
            self.version_counters[file_path] = 1

            # Start reading thread
            t = threading.Thread(target=self._read_loop, args=(file_path, proc), daemon=True)
            self.threads[file_path] = t
            t.start()

            # Send initialize message
            self._send_initialize(file_path)
        except Exception as e:
            print(f"[LSP] Failed to start LSP server for {file_path}: {e}")

    def stop_server_for_file(self, file_path):
        proc = self.servers.pop(file_path, None)
        if proc:
            try:
                proc.terminate()
            except:
                pass
        self.threads.pop(file_path, None)
        self.version_counters.pop(file_path, None)

    def notify_open(self, file_path, text, lang):
        self.start_server_for_file(file_path, lang)
        if file_path not in self.servers:
            return

        lang_id = lang if lang else "plaintext"
        ext = os.path.splitext(file_path)[1].lower()
        if ext == '.rs':
            lang_id = "rust"
        elif ext == '.py':
            lang_id = "python"
        elif ext in ['.c', '.cpp', '.h']:
            lang_id = "c"

        params = {
            "textDocument": {
                "uri": f"file://{os.path.abspath(file_path)}",
                "languageId": lang_id,
                "version": self.version_counters[file_path],
                "text": text
            }
        }
        self._send_request(file_path, "textDocument/didOpen", params, is_notification=True)

    def notify_change(self, file_path, text):
        if file_path not in self.servers:
            return
        self.version_counters[file_path] += 1
        params = {
            "textDocument": {
                "uri": f"file://{os.path.abspath(file_path)}",
                "version": self.version_counters[file_path]
            },
            "contentChanges": [
                {
                    "text": text
                }
            ]
        }
        self._send_request(file_path, "textDocument/didChange", params, is_notification=True)

    def _send_initialize(self, file_path):
        root_dir = os.path.dirname(os.path.abspath(file_path))
        params = {
            "processId": os.getpid(),
            "rootUri": f"file://{root_dir}",
            "capabilities": {
                "textDocument": {
                    "publishDiagnostics": {
                        "relatedInformation": True
                    },
                    "completion": {
                        "completionItem": {
                            "snippetSupport": True
                        }
                    }
                }
            }
        }
        self._send_request(file_path, "initialize", params, msg_id=1)

    def send_request_with_callback(self, file_path, method, params, callback):
        if file_path not in self.servers:
            return
        msg_id = self.next_id
        self.next_id += 1
        self.callbacks[msg_id] = callback
        self._send_request(file_path, method, params, msg_id=msg_id)

    def _send_request(self, file_path, method, params, msg_id=None, is_notification=False):
        proc = self.servers.get(file_path)
        if not proc or proc.poll() is not None:
            return

        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params
        }
        if not is_notification:
            payload["id"] = msg_id if msg_id is not None else 100

        try:
            body = json.dumps(payload)
            msg = f"Content-Length: {len(body)}\r\n\r\n{body}"
            proc.stdin.write(msg.encode('utf-8'))
            proc.stdin.flush()
        except Exception as e:
            print(f"[LSP] Error sending message for {file_path}: {e}")

    def _read_loop(self, file_path, proc):
        try:
            while proc.poll() is None:
                header_line = proc.stdout.readline()
                if not header_line:
                    break
                if header_line.startswith(b"Content-Length:"):
                    content_length = int(header_line.split(b":")[1].strip())
                    proc.stdout.readline()  # consume empty line
                    body = proc.stdout.read(content_length)
                    try:
                        msg = json.loads(body.decode('utf-8'))
                        self._handle_msg(file_path, msg)
                    except Exception as json_err:
                        print("[LSP] JSON Parse Error:", json_err)
        except Exception as e:
            print(f"[LSP] Read Loop Error for {file_path}: {e}")

    def _handle_msg(self, file_path, msg):
        if "method" in msg:
            method = msg["method"]
            if method == "textDocument/publishDiagnostics":
                params = msg.get("params", {})
                diagnostics = params.get("diagnostics", [])
                GLib.idle_add(self.app_window.apply_diagnostics, file_path, diagnostics)
        elif "id" in msg:
            msg_id = msg["id"]
            if msg_id in self.callbacks:
                callback = self.callbacks.pop(msg_id)
                GLib.idle_add(callback, msg.get("result"))
            elif msg_id == 1:
                self._send_request(file_path, "initialized", {}, is_notification=True)

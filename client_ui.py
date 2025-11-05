# client_ui.py
# GUI frontend for P2PClient using tkinter.
# Requires client.py and protocol.py in same folder.

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import os
from client import P2PClient

class P2PClientApp:
    def __init__(self, master):
        self.master = master
        self.master.title("🌐 P2P File Sharing Client")
        self.master.geometry("820x600")
        self.master.configure(bg="#f2f6ff")

        self.client = None

        # -------------- UI Layout --------------
        top = ttk.LabelFrame(master, text="Client Configuration", padding=10)
        top.pack(fill="x", padx=10, pady=10)

        ttk.Label(top, text="Name:").grid(row=0, column=0, sticky="e")
        self.name_var = tk.StringVar(value="client1")
        ttk.Entry(top, textvariable=self.name_var, width=15).grid(row=0, column=1, padx=5)

        ttk.Label(top, text="P2P Port:").grid(row=0, column=2, sticky="e")
        self.port_var = tk.IntVar(value=6001)
        ttk.Entry(top, textvariable=self.port_var, width=10).grid(row=0, column=3, padx=5)

        ttk.Button(top, text="Start Client", command=self.start_client).grid(row=0, column=4, padx=10)

        # Middle frame: actions
        mid = ttk.LabelFrame(master, text="Actions", padding=10)
        mid.pack(fill="x", padx=10, pady=5)

        ttk.Button(mid, text="Publish File", command=self.publish_file).grid(row=0, column=0, padx=5)
        ttk.Label(mid, text="File name:").grid(row=0, column=1)
        self.lookup_var = tk.StringVar()
        ttk.Entry(mid, textvariable=self.lookup_var, width=20).grid(row=0, column=2)
        ttk.Button(mid, text="Lookup", command=self.lookup_file).grid(row=0, column=3, padx=5)
        ttk.Label(mid, text="Host:").grid(row=0, column=4)
        self.host_var = tk.StringVar()
        ttk.Entry(mid, textvariable=self.host_var, width=15).grid(row=0, column=5)
        ttk.Button(mid, text="Discover", command=self.discover_host).grid(row=0, column=6, padx=5)
        ttk.Button(mid, text="Ping", command=self.ping_host).grid(row=0, column=7, padx=5)

        ttk.Button(mid, text="Leave", command=self.leave_client).grid(row=0, column=8, padx=10)

        # Log area
        log_frame = ttk.LabelFrame(master, text="Activity Log", padding=5)
        log_frame.pack(fill="both", expand=True, padx=10, pady=10)
        self.log_text = tk.Text(log_frame, wrap="word", height=20, bg="#fafcff", fg="#202020")
        self.log_text.pack(fill="both", expand=True)

        self.log("Ready. Configure and click 'Start Client' to begin.")

    # --------- Backend Control ---------
    def start_client(self):
        if self.client:
            self.log("Client already running.")
            return
        name = self.name_var.get().strip()
        port = self.port_var.get()
        if not name:
            messagebox.showwarning("Input", "Enter a client name.")
            return
        self.client = P2PClient(name, port)
        threading.Thread(target=self._connect_and_start, daemon=True).start()

    def _connect_and_start(self):
        try:
            self.client.start_peer_listener()
            self.client.connect_server()
            self.log(f"✅ Registered with session_id={self.client.session_id}")
        except Exception as e:
            self.log(f"[ERROR] {e}")
            self.client = None

    def publish_file(self):
        if not self.client:
            self.log("Start client first.")
            return
        fname = filedialog.askopenfilename(title="Select file to publish")
        if not fname:
            return
        # copy file into repo dir
        basename = os.path.basename(fname)
        dest = os.path.join(self.client.repo_dir, basename)
        try:
            if not os.path.exists(dest):
                import shutil
                shutil.copy(fname, dest)
            size = os.path.getsize(dest)
            meta = {"fname": basename, "size": size}
            threading.Thread(target=self._do_publish, args=([meta],), daemon=True).start()
        except Exception as e:
            self.log(f"[ERROR] publish: {e}")

    def _do_publish(self, files):
        self.client.publish(files)
        self.log(f"📤 Published {len(files)} file(s).")

    def lookup_file(self):
        if not self.client:
            self.log("Start client first.")
            return
        fname = self.lookup_var.get().strip()
        if not fname:
            return
        self.log(f"🔍 Looking up {fname} ...")
        threading.Thread(target=self._lookup_thread, args=(fname,), daemon=True).start()

    def _lookup_thread(self, fname):
        res = self.client.lookup(fname)
        peers = res.get("peers", [])
        if peers:
            p = peers[0]
            self.log(f"Found {len(peers)} peer(s). Downloading from {p['host']}...")
            self.client.fetch_from_peer(p["ip"], p["p2p_port"], fname)
            self.log("✅ File downloaded successfully.")
        else:
            self.log("No peers found for this file.")

        self.log(str(res))

    def discover_host(self):
        if not self.client:
            self.log("Start client first.")
            return
        host = self.host_var.get().strip()
        if not host:
            return
        self.log(f"🔎 Discovering {host} ...")
        threading.Thread(target=self._discover_thread, args=(host,), daemon=True).start()

    def _discover_thread(self, host):
        res = self.client.discover(host)
        self.log(str(res))

    def ping_host(self):
        if not self.client:
            self.log("Start client first.")
            return
        host = self.host_var.get().strip()
        if not host:
            return
        self.log(f"📡 Pinging {host} ...")
        threading.Thread(target=self._ping_thread, args=(host,), daemon=True).start()

    def _ping_thread(self, host):
        res = self.client.ping(host)
        self.log(str(res))

    def leave_client(self):
        if not self.client:
            return
        self.client.leave()
        self.log("🚪 Left network.")
        self.client = None

    # --------- Logging Helper ---------
    def log(self, msg):
        self.log_text.insert("end", f"[{time.strftime('%H:%M:%S')}] {msg}\n")
        self.log_text.see("end")


if __name__ == "__main__":
    import time
    root = tk.Tk()
    app = P2PClientApp(root)
    root.mainloop()

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import os
from client import P2PClient

class P2PClientApp:
    def __init__(self, root):
        self.root = root
        self.root.title("P2P File Sharing Client")
        self.root.geometry("750x500")
        self.client = None

        # ========== FRAME CONFIGURATION ==========
        frame_config = ttk.LabelFrame(root, text="Client Configuration", padding=10)
        frame_config.pack(fill="x", padx=10, pady=5)

        ttk.Label(frame_config, text="Name:").grid(row=0, column=0, sticky="w")
        self.name_entry = ttk.Entry(frame_config, width=20)
        self.name_entry.insert(0, "client1")
        self.name_entry.grid(row=0, column=1, padx=5)

        ttk.Label(frame_config, text="P2P Port:").grid(row=0, column=2, sticky="w")
        self.port_entry = ttk.Entry(frame_config, width=10)
        self.port_entry.insert(0, "6001")
        self.port_entry.grid(row=0, column=3, padx=5)

        ttk.Button(frame_config, text="Start Client", command=self.start_client).grid(row=0, column=4, padx=10)

        # ========== FRAME ACTIONS ==========
        frame_actions = ttk.LabelFrame(root, text="Actions", padding=10)
        frame_actions.pack(fill="x", padx=10, pady=5)

        ttk.Button(frame_actions, text="Publish File", command=self.publish_file).grid(row=0, column=0, padx=5)

        ttk.Label(frame_actions, text="File name:").grid(row=0, column=1, padx=(15, 5))
        self.filename_entry = ttk.Entry(frame_actions, width=20)
        self.filename_entry.grid(row=0, column=2)

        ttk.Button(frame_actions, text="Lookup", command=self.lookup_file).grid(row=0, column=3, padx=5)

        ttk.Label(frame_actions, text="Host:").grid(row=0, column=4, padx=(15, 5))
        self.host_entry = ttk.Entry(frame_actions, width=15)
        self.host_entry.grid(row=0, column=5)

        ttk.Button(frame_actions, text="Discover", command=self.discover_host).grid(row=0, column=6, padx=5)
        ttk.Button(frame_actions, text="Ping", command=self.ping_host).grid(row=0, column=7, padx=5)
        ttk.Button(frame_actions, text="Leave", command=self.leave_server).grid(row=0, column=8, padx=5)

        # ========== FRAME LOG ==========
        frame_log = ttk.LabelFrame(root, text="Activity Log", padding=10)
        frame_log.pack(fill="both", expand=True, padx=10, pady=5)

        self.log_text = tk.Text(frame_log, wrap="word", bg="#1e1e1e", fg="#dcdcdc", font=("Consolas", 10))
        self.log_text.pack(fill="both", expand=True)

        self.log("[00:00:00] Ready. Configure and click 'Start Client' to begin.")

    # ========== LOG HANDLING ==========
    def log(self, message):
        """Append a log message to text box."""
        self.log_text.insert("end", message + "\n")
        self.log_text.see("end")

    # ========== CLIENT STARTUP ==========
    def start_client(self):
        name = self.name_entry.get().strip()
        port = int(self.port_entry.get().strip())
        if not name:
            messagebox.showwarning("Warning", "Please enter client name.")
            return
        self.client = P2PClient(name, port)
        self.client.log_callback = self.log
        threading.Thread(target=self._start_client_thread, daemon=True).start()

    def _start_client_thread(self):
        try:
            self.client.start_peer_listener()
            self.client.connect_server()
            self.client.start_listen_events()
            self.log(f"Registered with session_id={self.client.session_id}")
        except Exception as e:
            self.log(f"Connection error: {e}")

    # ========== ACTION HANDLERS ==========
    def publish_file(self):
        if not self.client:
            messagebox.showerror("Error", "Client not started.")
            return
        path = filedialog.askopenfilename(title="Select File to Publish")
        if not path:
            return
        fname = os.path.basename(path)
        size = os.path.getsize(path)
        meta = [{"fname": fname, "size": size}]
        self.client.publish(meta)
        self.log(f"Published {fname} ({size} bytes).")

    def lookup_file(self):
        if not self.client:
            messagebox.showerror("Error", "Client not started.")
            return
        fname = self.filename_entry.get().strip()
        if not fname:
            messagebox.showwarning("Warning", "Enter file name to lookup.")
            return
        self.log(f"Looking up {fname} ...")
        reply = self.client.lookup(fname)
        peers = reply.get("peers", [])
        if peers:
            self.log(f"Found {len(peers)} peer(s) for {fname}:")
            for p in peers:
                self.log(f"   • {p['host']} ({p['ip']}:{p['p2p_port']})")
        else:
            self.log("No peers found for this file.")

    def discover_host(self):
        if not self.client:
            messagebox.showerror("Error", "Client not started.")
            return
        host = self.host_entry.get().strip()
        if not host:
            messagebox.showwarning("Warning", "Enter host name to discover.")
            return
        self.log(f"Discovering {host} ...")
        reply = self.client.discover(host)
        files = reply.get("files", [])
        if files:
            self.log(f"{host} has {len(files)} file(s): {[f['fname'] for f in files]}")
        else:
            self.log(f"No files found for host {host}.")

    def ping_host(self):
        if not self.client:
            messagebox.showerror("Error", "Client not started.")
            return
        host = self.host_entry.get().strip()
        if not host:
            messagebox.showwarning("Warning", "Enter host name to ping.")
            return
        self.log(f"Pinging {host} ...")
        reply = self.client.ping(host)
        if reply.get("ok"):
            alive = reply.get("alive", True)
            self.log(f"Host {host} alive={alive}")
        else:
            self.log(f"Ping failed: {reply}")

    def leave_server(self):
        if not self.client:
            return
        self.log("Leaving server ...")
        self.client.leave()
        messagebox.showinfo("Exit", "Client disconnected.")
        self.root.quit()


if __name__ == "__main__":
    root = tk.Tk()
    app = P2PClientApp(root)
    root.mainloop()

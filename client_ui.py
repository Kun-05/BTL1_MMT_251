import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import os
import shutil
from client import P2PClient

class P2PClientApp:
    def __init__(self, root):
        self.root = root
        self.root.title("P2P File Sharing Client")
        self.root.geometry("900x650")
        self.root.configure(bg="#1e1e1e")
        self.client = None
        self.last_lookup_peers = []  # Store peers from last lookup
        
        # Configure style
        self.setup_styles()
        
        # Main container with padding
        main_container = tk.Frame(root, bg="#1e1e1e")
        main_container.pack(fill="both", expand=True, padx=20, pady=20)

        # ========== HEADER ==========
        header = tk.Frame(main_container, bg="#252526")
        header.pack(fill="x", pady=(0, 15))
        
        header_content = tk.Frame(header, bg="#252526")
        header_content.pack(fill="x", padx=20, pady=15)
        
        title_label = tk.Label(header_content, text="P2P FILE SHARING CLIENT", 
                               font=("Consolas", 16, "bold"), 
                               bg="#252526", fg="#00ff00")
        title_label.pack(side="left")
        
        status_frame = tk.Frame(header_content, bg="#252526")
        status_frame.pack(side="right")
        
        self.status_label = tk.Label(status_frame, text="[ DISCONNECTED ]", 
                                     font=("Consolas", 10, "bold"), 
                                     bg="#252526", fg="#ff4444")
        self.status_label.pack()

        # ========== CLIENT CONFIGURATION ==========
        config_frame = tk.Frame(main_container, bg="#252526", highlightbackground="#3e3e42", highlightthickness=1)
        config_frame.pack(fill="x", pady=(0, 15))
        
        config_header = tk.Label(config_frame, text="CLIENT CONFIGURATION", 
                                font=("Consolas", 10, "bold"),
                                bg="#2d2d30", fg="#cccccc", anchor="w", padx=15, pady=8)
        config_header.pack(fill="x")

        config_content = tk.Frame(config_frame, bg="#252526", padx=20, pady=20)
        config_content.pack(fill="x")

        # Name field
        name_frame = tk.Frame(config_content, bg="#252526")
        name_frame.pack(side="left", padx=(0, 30))
        
        tk.Label(name_frame, text="CLIENT NAME", font=("Consolas", 9), 
                bg="#252526", fg="#808080").pack(anchor="w")
        self.name_entry = tk.Entry(name_frame, width=20, font=("Consolas", 10),
                                   bg="#3c3c3c", fg="#ffffff", insertbackground="#ffffff",
                                   relief="flat", highlightbackground="#007acc", highlightthickness=1)
        self.name_entry.insert(0, "")
        self.name_entry.pack(pady=(5, 0))

        # Port field
        port_frame = tk.Frame(config_content, bg="#252526")
        port_frame.pack(side="left", padx=(0, 30))
        
        tk.Label(port_frame, text="P2P PORT", font=("Consolas", 9), 
                bg="#252526", fg="#808080").pack(anchor="w")
        self.port_entry = tk.Entry(port_frame, width=12, font=("Consolas", 10),
                                   bg="#3c3c3c", fg="#ffffff", insertbackground="#ffffff",
                                   relief="flat", highlightbackground="#007acc", highlightthickness=1)
        self.port_entry.insert(0, "")
        self.port_entry.pack(pady=(5, 0))

        # Start button
        self.start_button = tk.Button(config_content, text="START CLIENT", 
                                     command=self.start_client,
                                     font=("Consolas", 10, "bold"), 
                                     bg="#0e639c", fg="#ffffff", 
                                     activebackground="#1177bb",
                                     activeforeground="#ffffff",
                                     relief="flat", padx=30, pady=10,
                                     cursor="hand2", borderwidth=0)
        self.start_button.pack(side="left", pady=(18, 0))

        # ========== FILE OPERATIONS ==========
        file_ops_frame = tk.Frame(main_container, bg="#252526", highlightbackground="#3e3e42", highlightthickness=1)
        file_ops_frame.pack(fill="x", pady=(0, 15))
        
        file_ops_header = tk.Label(file_ops_frame, text="FILE OPERATIONS", 
                                   font=("Consolas", 10, "bold"),
                                   bg="#2d2d30", fg="#cccccc", anchor="w", padx=15, pady=8)
        file_ops_header.pack(fill="x")

        file_ops_content = tk.Frame(file_ops_frame, bg="#252526", padx=20, pady=20)
        file_ops_content.pack(fill="x")

        # Publish button
        self.publish_btn = tk.Button(file_ops_content, text="PUBLISH FILE", 
                                     command=self.publish_file,
                                     font=("Consolas", 9, "bold"), 
                                     bg="#16825d", fg="#ffffff",
                                     activebackground="#1a9870",
                                     activeforeground="#ffffff",
                                     relief="flat", padx=20, pady=8,
                                     cursor="hand2", borderwidth=0, width=15)
        self.publish_btn.pack(side="left", padx=(0, 30))

        # Lookup section
        lookup_frame = tk.Frame(file_ops_content, bg="#252526")
        lookup_frame.pack(side="left")
        
        tk.Label(lookup_frame, text="FILENAME", font=("Consolas", 9), 
                bg="#252526", fg="#808080").pack(side="left", padx=(0, 10))
        self.filename_entry = tk.Entry(lookup_frame, width=25, font=("Consolas", 10),
                                       bg="#3c3c3c", fg="#ffffff", insertbackground="#ffffff",
                                       relief="flat", highlightbackground="#007acc", highlightthickness=1)
        self.filename_entry.pack(side="left", padx=(0, 15))
        
        self.lookup_btn = tk.Button(lookup_frame, text="LOOKUP", 
                                    command=self.lookup_file,
                                    font=("Consolas", 9, "bold"), 
                                    bg="#6e4c9e", fg="#ffffff",
                                    activebackground="#7f5db0",
                                    activeforeground="#ffffff",
                                    relief="flat", padx=20, pady=8,
                                    cursor="hand2", borderwidth=0, width=12)
        self.lookup_btn.pack(side="left", padx=(0, 10))
        
        self.download_btn = tk.Button(lookup_frame, text="DOWNLOAD", 
                                      command=self.download_file,
                                      font=("Consolas", 9, "bold"), 
                                      bg="#0e639c", fg="#ffffff",
                                      activebackground="#1177bb",
                                      activeforeground="#ffffff",
                                      relief="flat", padx=20, pady=8,
                                      cursor="hand2", borderwidth=0, width=12)
        self.download_btn.pack(side="left")

        # ========== PEER OPERATIONS ==========
        peer_ops_frame = tk.Frame(main_container, bg="#252526", highlightbackground="#3e3e42", highlightthickness=1)
        peer_ops_frame.pack(fill="x", pady=(0, 15))
        
        peer_ops_header = tk.Label(peer_ops_frame, text="PEER OPERATIONS", 
                                   font=("Consolas", 10, "bold"),
                                   bg="#2d2d30", fg="#cccccc", anchor="w", padx=15, pady=8)
        peer_ops_header.pack(fill="x")

        peer_ops_content = tk.Frame(peer_ops_frame, bg="#252526", padx=20, pady=20)
        peer_ops_content.pack(fill="x")
        
        # Host entry
        host_frame = tk.Frame(peer_ops_content, bg="#252526")
        host_frame.pack(side="left", padx=(0, 20))
        
        tk.Label(host_frame, text="HOSTNAME", font=("Consolas", 9), 
                bg="#252526", fg="#808080").pack(side="left", padx=(0, 10))
        self.host_entry = tk.Entry(host_frame, width=20, font=("Consolas", 10),
                                   bg="#3c3c3c", fg="#ffffff", insertbackground="#ffffff",
                                   relief="flat", highlightbackground="#007acc", highlightthickness=1)
        self.host_entry.pack(side="left")

        # Operation buttons
        button_config = [
            ("DISCOVER", self.discover_host, "#0e7490"),
            ("PING", self.ping_host, "#b45309"),
            ("LEAVE", self.leave_server, "#b91c1c")
        ]

        for text, cmd, color in button_config:
            btn = tk.Button(peer_ops_content, text=text, command=cmd,
                          font=("Consolas", 9, "bold"), 
                          bg=color, fg="#ffffff",
                          activebackground=self.darken_color(color),
                          activeforeground="#ffffff",
                          relief="flat", padx=20, pady=8,
                          cursor="hand2", borderwidth=0, width=12)
            btn.pack(side="left", padx=(0, 10))

        # ========== ACTIVITY LOG ==========
        log_frame = tk.Frame(main_container, bg="#252526", highlightbackground="#3e3e42", highlightthickness=1)
        log_frame.pack(fill="both", expand=True)
        
        log_header = tk.Label(log_frame, text="ACTIVITY LOG", 
                             font=("Consolas", 10, "bold"),
                             bg="#2d2d30", fg="#cccccc", anchor="w", padx=15, pady=8)
        log_header.pack(fill="x")

        log_content = tk.Frame(log_frame, bg="#1e1e1e", padx=15, pady=15)
        log_content.pack(fill="both", expand=True)
        
        # Log text with scrollbar
        scrollbar = tk.Scrollbar(log_content, bg="#3e3e42")
        scrollbar.pack(side="right", fill="y")
        
        self.log_text = tk.Text(log_content, wrap="word", 
                               bg="#0c0c0c", fg="#00ff00", 
                               font=("Consolas", 10),
                               padx=15, pady=15,
                               relief="flat",
                               insertbackground="#00ff00",
                               yscrollcommand=scrollbar.set)
        self.log_text.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=self.log_text.yview)
        
        # Configure text tags for colored output
        self.log_text.tag_config("success", foreground="#00ff00")
        self.log_text.tag_config("error", foreground="#ff4444")
        self.log_text.tag_config("info", foreground="#00aaff")
        self.log_text.tag_config("warning", foreground="#ffaa00")
        self.log_text.tag_config("default", foreground="#00ff00")

        self.log("[SYSTEM] Ready. Configure and click 'START CLIENT' to begin.", "success")
        self.root.protocol("WM_DELETE_WINDOW", self.leave_server) # Handle window close

    def setup_styles(self):
        """Configure ttk styles for modern look."""
        style = ttk.Style()
        style.theme_use('clam')

    def darken_color(self, hex_color):
        """Darken a hex color by 15%."""
        hex_color = hex_color.lstrip('#')
        rgb = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
        darker = tuple(max(0, int(c * 0.85)) for c in rgb)
        return f"#{darker[0]:02x}{darker[1]:02x}{darker[2]:02x}"

    def update_status(self, connected):
        """Update connection status indicator."""
        if connected:
            self.status_label.config(text="[ CONNECTED ]", fg="#00ff00")
        else:
            self.status_label.config(text="[ DISCONNECTED ]", fg="#ff4444")

    # ========== LOG HANDLING ==========
    def log(self, message, tag="default"):
        """Append a log message to text box with optional tag."""
        if not tag in self.log_text.tag_names():
            tag = "default"
        self.log_text.insert("end", message + "\n", tag)
        self.log_text.see("end")

    # ========== CLIENT STARTUP ==========
    def start_client(self):
        name = self.name_entry.get().strip()
        port_str = self.port_entry.get().strip()
        if not name:
            messagebox.showwarning("Warning", "Please enter client name.")
            return
        try:
            port = int(port_str)
        except ValueError:
            messagebox.showwarning("Warning", "P2P Port must be a number.")
            return

        self.client = P2PClient(name, port)
        self.client.log_callback = self.log
        threading.Thread(target=self._start_client_thread, daemon=True).start()

    def _start_client_thread(self):
        try:
            self.log("[SYSTEM] Starting P2P listener...", "info")
            self.client.start_peer_listener()
            
            self.log("[SYSTEM] Connecting to server...", "info")
            self.client.connect_server()
            
            # CRITICAL: Start the receiver loop *after* connect_server
            self.log("[SYSTEM] Starting message receiver...", "info")
            self.client.start_message_receiver() 
            
            # self.log(f"[SYSTEM] Connected successfully (session_id={self.client.session_id})", "success") # Logged by connect_server
            self.log(f"[SYSTEM] Repo directory: {self.client.repo_dir}", "info")
            self.update_status(True)
            self.start_button.config(state="disabled", bg="#555555")
            
        except ConnectionError as e:
            self.log(f"[ERROR] Connection failed: {e}", "error")
            self.update_status(False)
        except Exception as e:
            self.log(f"[ERROR] Startup error: {e}", "error")
            self.update_status(False)

    # ========== ACTION HANDLERS ==========
    def publish_file(self):
        if not self.client or not self.client.running:
            messagebox.showerror("Error", "Client not connected.")
            return
        
        # Select file from anywhere
        path = filedialog.askopenfilename(title="Select File to Publish")
        if not path:
            return
        
        fname = os.path.basename(path)
        size = os.path.getsize(path)
        
        # Copy file to repo directory
        dest_path = os.path.join(self.client.repo_dir, fname)
        try:
            shutil.copy2(path, dest_path)
            self.log(f"[FILE] Copied {fname} to repo directory", "info")
        except Exception as e:
            self.log(f"[ERROR] Failed to copy file: {e}", "error")
            messagebox.showerror("Error", f"Failed to copy file: {e}")
            return
        
        # Publish metadata to server
        meta = [{"fname": fname, "size": size}]
        # Run in a thread to not block UI
        threading.Thread(target=self.client.publish, args=(meta,), daemon=True).start()
        self.log(f"[PUBLISH] Sending request for {fname} ({size} bytes)...", "info")

    def lookup_file(self):
        if not self.client or not self.client.running:
            messagebox.showerror("Error", "Client not connected.")
            return
        fname = self.filename_entry.get().strip()
        if not fname:
            messagebox.showwarning("Warning", "Enter file name to lookup.")
            return
            
        self.log(f"[LOOKUP] Searching for {fname} ...", "info")
        # Run in a thread to not block UI
        threading.Thread(target=self._lookup_thread, args=(fname,), daemon=True).start()

    def _lookup_thread(self, fname):
        reply = self.client.lookup(fname)
        peers = reply.get("peers", [])
        if peers:
            self.last_lookup_peers = peers  # Store for download
            self.log(f"[LOOKUP] Found {len(peers)} peer(s) for {fname}:", "success")
            for p in peers:
                self.log(f"         > {p['host']} ({p['ip']}:{p['p2p_port']})", "info")
        else:
            self.last_lookup_peers = []
            self.log("[LOOKUP] No peers found for this file.", "warning")

    def download_file(self):
        if not self.client or not self.client.running:
            messagebox.showerror("Error", "Client not connected.")
            return
        fname = self.filename_entry.get().strip()
        if not fname:
            messagebox.showwarning("Warning", "Enter file name to download.")
            return
        if not self.last_lookup_peers:
            messagebox.showwarning("Warning", "Please lookup the file first.")
            return
        
        # Download from first peer
        first_peer = self.last_lookup_peers[0]
        self.log(f"[FETCH] Downloading '{fname}' from {first_peer['host']} ({first_peer['ip']}:{first_peer['p2p_port']}) ...", "info")
        
        # Run in a thread to not block UI
        threading.Thread(target=self._download_thread, args=(first_peer, fname), daemon=True).start()

    def _download_thread(self, peer, fname):
        try:
            success = self.client.fetch_from_peer(peer["ip"], peer["p2p_port"], fname)
            if success:
                self.log(f"[FETCH] ✓ Successfully downloaded '{fname}'", "success")
                self.log(f"[FETCH] Saved to: {os.path.join(self.client.repo_dir, fname)}", "info")
            else:
                self.log(f"[FETCH] ✗ Failed to download '{fname}'", "error")
                self.log(f"[FETCH] Make sure the filename is correct and the peer has the file", "warning")
        except Exception as e:
            self.log(f"[FETCH] ✗ Download error: {e}", "error")

    def discover_host(self):
        if not self.client or not self.client.running:
            messagebox.showerror("Error", "Client not connected.")
            return
        host = self.host_entry.get().strip()
        if not host:
            messagebox.showwarning("Warning", "Enter host name to discover.")
            return
        self.log(f"[DISCOVER] Querying {host} ...", "info")
        # Run in a thread
        threading.Thread(target=self._discover_thread, args=(host,), daemon=True).start()

    def _discover_thread(self, host):
        reply = self.client.discover(host)
        files = reply.get("files", [])
        if files:
            self.log(f"[DISCOVER] {host} has {len(files)} file(s):", "success")
            for f in files:
                self.log(f"         > {f['fname']} ({f.get('size', 0)} bytes)", "info")
        else:
            self.log(f"[DISCOVER] No files found for host {host}.", "warning")

    def ping_host(self):
        if not self.client or not self.client.running:
            messagebox.showerror("Error", "Client not connected.")
            return
        host = self.host_entry.get().strip()
        if not host:
            messagebox.showwarning("Warning", "Enter host name to ping.")
            return
        self.log(f"[PING] Testing connection to {host} ...", "info")
        # Run in a thread
        threading.Thread(target=self._ping_thread, args=(host,), daemon=True).start()

    def _ping_thread(self, host):
        reply = self.client.ping(host)
        if reply.get("ok"):
            alive = reply.get("alive", True)
            self.log(f"[PING] Host {host} alive={alive}", "success")
        else:
            self.log(f"[PING] Failed: {reply}", "error")

    def leave_server(self):
        if self.client:
            self.log("[SYSTEM] Disconnecting from server ...", "warning")
            # Run leave in a thread to avoid blocking UI on exit
            threading.Thread(target=self.client.leave, daemon=True).start()
            self.update_status(False)
        self.root.quit()


if __name__ == "__main__":
    root = tk.Tk()
    app = P2PClientApp(root)
    root.mainloop()
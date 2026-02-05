import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import threading
import time
import os
import sys
import io
import subprocess
import tkinter.font as tkfont
from gurux_common.enums import TraceLevel
from gurux_common.io import Parity, StopBits, BaudRate
from gurux_dlms.enums import InterfaceType, Authentication, Security, Standard, DataType, ObjectType
from gurux_dlms import GXDLMSClient
from gurux_dlms.GXByteBuffer import GXByteBuffer
from gurux_serial.GXSerial import GXSerial
from GXDLMSSecureClient2 import GXDLMSSecureClient2
from GXDLMSReader import GXDLMSReader
from gurux_dlms.GXDLMSConverter import GXDLMSConverter
from gurux_dlms.GXDateTime import GXDateTime
import urllib.parse
import pytest
try:
    import requests
except Exception:
    requests = None

class DLMSGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("DLMS GUI")
        self.client = None
        self.reader = None
        self.media = None
        self.log_path = "logFile.txt"
        self.stop_tail = threading.Event()
        self.test_files = []
        self.azure_url = tk.StringVar()
        self.azure_project = tk.StringVar()
        self.azure_pat = tk.StringVar()
        self._build_ui()

    def _build_ui(self):
        container = tk.PanedWindow(self.root, orient="horizontal")
        container.pack(fill="both", expand=True)
        notebook = ttk.Notebook(container)
        logo_canvas = tk.Canvas(container, width=220, highlightthickness=0)
        container.add(notebook)
        container.add(logo_canvas)
        self._build_logo_sidebar(logo_canvas)
        eng_tab = ttk.Frame(notebook)
        mgr_tab = ttk.Frame(notebook)
        notebook.add(eng_tab, text="Engineering")
        notebook.add(mgr_tab, text="Management")
        eng_nb = ttk.Notebook(eng_tab)
        eng_nb.pack(fill="both", expand=True)
        cfg_tab = ttk.Frame(eng_nb)
        obis_tab = ttk.Frame(eng_nb)
        tests_tab = ttk.Frame(eng_nb)
        bugs_tab = ttk.Frame(eng_nb)
        eng_nb.add(cfg_tab, text="Configuration")
        eng_nb.add(obis_tab, text="OBIS")
        eng_nb.add(tests_tab, text="Tests")
        eng_nb.add(bugs_tab, text="Bugs")
        obis_canvas, obis_inner = self._make_scrollable_tab(obis_tab)
        self._add_watermark(obis_canvas)
        top = ttk.Frame(cfg_tab)
        top.pack(fill="x")
        ttk.Label(top, text="COM Port").grid(row=0, column=0, sticky="w")
        self.port_var = tk.StringVar(value="COM6")
        ttk.Entry(top, textvariable=self.port_var, width=12).grid(row=0, column=1, sticky="w")
        ttk.Label(top, text="Client").grid(row=0, column=2, sticky="w")
        self.client_var = tk.IntVar(value=1)
        ttk.Entry(top, textvariable=self.client_var, width=6).grid(row=0, column=3, sticky="w")
        ttk.Label(top, text="Logical").grid(row=0, column=4, sticky="w")
        self.logical_var = tk.IntVar(value=1)
        ttk.Entry(top, textvariable=self.logical_var, width=6).grid(row=0, column=5, sticky="w")
        ttk.Label(top, text="Physical").grid(row=0, column=6, sticky="w")
        self.physical_var = tk.IntVar(value=18)
        ttk.Entry(top, textvariable=self.physical_var, width=6).grid(row=0, column=7, sticky="w")
        ttk.Label(top, text="Auth").grid(row=0, column=8, sticky="w")
        self.auth_var = tk.StringVar(value="HIGH_GMAC")
        ttk.Combobox(top, textvariable=self.auth_var, values=["NONE","LOW","HIGH","HIGH_GMAC"], width=12).grid(row=0, column=9, sticky="w")
        ttk.Label(top, text="Security").grid(row=0, column=10, sticky="w")
        self.sec_var = tk.StringVar(value="AUTHENTICATION_ENCRYPTION")
        ttk.Combobox(top, textvariable=self.sec_var, values=["NONE","AUTHENTICATION","ENCRYPTION","AUTHENTICATION_ENCRYPTION"], width=24).grid(row=0, column=11, sticky="w")
        ttk.Label(top, text="SystemTitle").grid(row=1, column=0, sticky="w")
        self.st_var = tk.StringVar(value="5341435341435341")
        ttk.Entry(top, textvariable=self.st_var, width=24).grid(row=1, column=1, columnspan=2, sticky="w")
        ttk.Label(top, text="BlockKey").grid(row=1, column=3, sticky="w")
        self.bk_var = tk.StringVar(value="7ADF639CA79632FCA3D7810BE6416ABE")
        ttk.Entry(top, textvariable=self.bk_var, width=40).grid(row=1, column=4, columnspan=3, sticky="w")
        ttk.Label(top, text="AuthKey").grid(row=1, column=7, sticky="w")
        self.ak_var = tk.StringVar(value="245D0F1DF31C4380135AC91D4A22023D")
        ttk.Entry(top, textvariable=self.ak_var, width=40).grid(row=1, column=8, columnspan=3, sticky="w")
        ttk.Label(top, text="Standard").grid(row=2, column=0, sticky="w")
        self.std_var = tk.StringVar(value="ITALY")
        ttk.Combobox(top, textvariable=self.std_var, values=["DLMS","ITALY","INDIA","SAUDI_ARABIA","SPAIN"], width=24).grid(row=2, column=1, sticky="w")
        ttk.Button(top, text="Connect", command=self.connect).grid(row=2, column=2, sticky="w")
        ttk.Button(top, text="Disconnect", command=self.disconnect).grid(row=2, column=3, sticky="w")
        ttk.Button(top, text="Save Assoc View", command=self.save_assoc_view).grid(row=2, column=4, sticky="w")
        left = ttk.Frame(obis_inner)
        left.pack(fill="both", expand=True)
        cols = ("ln","name","type")
        self.tree = ttk.Treeview(left, columns=cols, show="tree headings")
        self.tree.heading("ln", text="Logical Name")
        self.tree.heading("name", text="Name")
        self.tree.heading("type", text="Type")
        self.tree.column("ln", width=150, stretch=True)
        self.tree.column("name", width=280, stretch=True)
        self.tree.column("type", width=140, stretch=True)
        tree_scroll = ttk.Scrollbar(left, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=tree_scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        tree_scroll.pack(side="right", fill="y")
        right = ttk.Frame(obis_inner)
        right.pack(fill="x")
        ttk.Label(right, text="Selected OBIS").grid(row=0, column=0, sticky="w")
        self.sel_ln = tk.StringVar()
        ttk.Entry(right, textvariable=self.sel_ln, width=24).grid(row=0, column=1, sticky="w")
        ttk.Button(right, text="Refresh OBIS", command=self.refresh_obis).grid(row=1, column=0, sticky="w")
        ttk.Label(right, text="Type Meaning").grid(row=2, column=0, sticky="w")
        self.type_desc_label = ttk.Label(right, text="", wraplength=320)
        self.type_desc_label.grid(row=2, column=1, sticky="w")
        rights_frame = ttk.Frame(obis_inner)
        rights_frame.pack(fill="both", expand=True)
        ttk.Label(rights_frame, text="Attributes").pack(anchor="w")
        attrs_wrap = ttk.Frame(rights_frame)
        attrs_wrap.pack(fill="x")
        self.attrs_tree = ttk.Treeview(attrs_wrap, columns=("attr","name","right","dtype","value"), show="headings", height=8)
        self.attrs_tree.heading("attr", text="Attr")
        self.attrs_tree.heading("name", text="Name")
        self.attrs_tree.heading("right", text="Right")
        self.attrs_tree.heading("dtype", text="Type")
        self.attrs_tree.heading("value", text="Value")
        self.attrs_tree.column("attr", width=60, stretch=True)
        self.attrs_tree.column("name", width=220, stretch=True)
        self.attrs_tree.column("right", width=100, stretch=True)
        self.attrs_tree.column("dtype", width=120, stretch=True)
        self.attrs_tree.column("value", width=220, stretch=True)
        self.attrs_tree.pack(side="left", fill="x", expand=True)
        attrs_scroll = ttk.Scrollbar(attrs_wrap, orient="vertical", command=self.attrs_tree.yview)
        attrs_scroll.pack(side="right", fill="y")
        self.attrs_tree.configure(yscrollcommand=attrs_scroll.set)
        self.attrs_tree.bind("<<TreeviewSelect>>", self._on_attr_select)
        attr_ops = ttk.Frame(rights_frame)
        attr_ops.pack(fill="x")
        ttk.Label(attr_ops, text="Selected attribute editor").grid(row=0, column=0, sticky="w")
        self.edit_frame = ttk.Frame(attr_ops)
        self.edit_frame.grid(row=0, column=1, sticky="w")
        self.adv_btn = ttk.Button(attr_ops, text="Advanced Editor...", command=self.open_advanced_editor)
        self.adv_btn.grid(row=0, column=2, sticky="w")
        self.read_btn = ttk.Button(attr_ops, text="Read Selected", command=self.read_selected_attr)
        self.read_btn.grid(row=0, column=3, sticky="w")
        self.write_selected_btn = ttk.Button(attr_ops, text="Write Selected", command=self.write_selected_attr)
        self.write_selected_btn.grid(row=0, column=4, sticky="w")
        ttk.Label(rights_frame, text="Method rights").pack(anchor="w")
        methods_wrap = ttk.Frame(rights_frame)
        methods_wrap.pack(fill="x")
        self.methods_tree = ttk.Treeview(methods_wrap, columns=("method","name","right"), show="headings", height=6)
        self.methods_tree.heading("method", text="Method")
        self.methods_tree.heading("name", text="Name")
        self.methods_tree.heading("right", text="Right")
        self.methods_tree.column("method", width=80, stretch=True)
        self.methods_tree.column("name", width=240, stretch=True)
        self.methods_tree.column("right", width=100, stretch=True)
        self.methods_tree.pack(side="left", fill="x", expand=True)
        methods_scroll = ttk.Scrollbar(methods_wrap, orient="vertical", command=self.methods_tree.yview)
        methods_scroll.pack(side="right", fill="y")
        self.methods_tree.configure(yscrollcommand=methods_scroll.set)
        self.methods_tree.bind("<<TreeviewSelect>>", self._on_method_select)
        method_ops = ttk.Frame(rights_frame)
        method_ops.pack(fill="x")
        ttk.Label(method_ops, text="Param Type").grid(row=0, column=0, sticky="w")
        self.method_type_var = tk.StringVar(value="NONE")
        ttk.Combobox(method_ops, textvariable=self.method_type_var, values=[
            "NONE","BOOLEAN","INT8","INT16","INT32","INT64","UINT8","UINT16","UINT32","UINT64",
            "OCTET_STRING","STRING","STRING_UTF8","BITSTRING","ARRAY","STRUCTURE","DATETIME","DATE","TIME","ENUM","FLOAT32","FLOAT64","BCD","COMPACT_ARRAY"
        ], width=18).grid(row=0, column=1, sticky="w")
        ttk.Label(method_ops, text="Param Value").grid(row=0, column=2, sticky="w")
        self.method_value = tk.StringVar()
        self.method_value_entry = ttk.Entry(method_ops, textvariable=self.method_value, width=30)
        self.method_value_entry.grid(row=0, column=3, sticky="w")
        self.run_method_btn = ttk.Button(method_ops, text="Run Method", command=self.run_selected_method)
        self.run_method_btn.grid(row=0, column=4, sticky="w")
        ttk.Label(rights_frame, text="OBIS Console").pack(anchor="w")
        obis_console_frame = ttk.Frame(rights_frame)
        obis_console_frame.pack(fill="both", expand=True)
        self.obis_console = tk.Text(obis_console_frame, height=8)
        self.obis_console.pack(side="left", fill="both", expand=True)
        obis_scroll = ttk.Scrollbar(obis_console_frame, orient="vertical", command=self.obis_console.yview)
        obis_scroll.pack(side="right", fill="y")
        self.obis_console.configure(yscrollcommand=obis_scroll.set)
        console_frame = ttk.Frame(cfg_tab)
        console_frame.pack(fill="both", expand=True)
        self.console = tk.Text(console_frame, height=12)
        self.console.pack(side="left", fill="both", expand=True)
        main_scroll = ttk.Scrollbar(console_frame, orient="vertical", command=self.console.yview)
        main_scroll.pack(side="right", fill="y")
        self.console.configure(yscrollcommand=main_scroll.set)
        ttk.Button(console_frame, text="Export Console", command=self.export_console).pack(side="left")
        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        tests_top = ttk.Frame(tests_tab)
        tests_top.pack(fill="x")
        ttk.Button(tests_top, text="Add Test File", command=self.add_test_file).pack(side="left")
        ttk.Button(tests_top, text="Clear Test Files", command=self.clear_test_files).pack(side="left")
        self.tests_list = tk.Listbox(tests_tab, selectmode="extended")
        self.tests_list.pack(fill="both", expand=True)
        tests_btns = ttk.Frame(tests_tab)
        tests_btns.pack(fill="x")
        ttk.Button(tests_btns, text="Collect Tests", command=self.collect_tests).pack(side="left")
        ttk.Button(tests_btns, text="Run Selected", command=self.run_selected_tests).pack(side="left")
        bugs_top = ttk.Frame(bugs_tab)
        bugs_top.pack(fill="x")
        ttk.Label(bugs_top, text="Azure URL (full)").grid(row=0, column=0, sticky="w")
        ttk.Entry(bugs_top, textvariable=self.azure_url, width=60).grid(row=0, column=1, sticky="w")
        ttk.Label(bugs_top, text="PAT").grid(row=0, column=2, sticky="w")
        ttk.Entry(bugs_top, textvariable=self.azure_pat, width=40, show="*").grid(row=0, column=3, sticky="w")
        self.bug_text = tk.Text(bugs_tab, height=12)
        self.bug_text.pack(fill="both", expand=True)
        bugs_btns = ttk.Frame(bugs_tab)
        bugs_btns.pack(fill="x")
        ttk.Button(bugs_btns, text="Create Bug", command=self.create_bug).pack(side="left")
        mgr_top = ttk.Frame(mgr_tab)
        mgr_top.pack(fill="x")
        ttk.Label(mgr_top, text="Azure URL (full)").grid(row=0, column=0, sticky="w")
        ttk.Entry(mgr_top, textvariable=self.azure_url, width=60).grid(row=0, column=1, sticky="w")
        ttk.Label(mgr_top, text="PAT").grid(row=0, column=2, sticky="w")
        ttk.Entry(mgr_top, textvariable=self.azure_pat, width=40, show="*").grid(row=0, column=3, sticky="w")
        mgr_btns = ttk.Frame(mgr_tab)
        mgr_btns.pack(fill="x")
        ttk.Button(mgr_btns, text="Fetch Bugs", command=self.fetch_bugs).pack(side="left")
        self.bugs_tree = ttk.Treeview(mgr_tab, columns=("id","title","state","severity"), show="headings")
        self.bugs_tree.heading("id","text")
        self.bugs_tree.heading("title","text")
        self.bugs_tree.heading("state","text")
        self.bugs_tree.heading("severity","text")
        self.bugs_tree.pack(fill="both", expand=True)
        self.stats_label = ttk.Label(mgr_tab, text="")
        self.stats_label.pack(fill="x")
        self._build_helpers()
        # Keep canvas scrollregion up-to-date
        try:
            obis_inner.bind("<Configure>", lambda e: obis_canvas.configure(scrollregion=obis_canvas.bbox("all")))
        except Exception:
            pass
        try:
            for _tab in (cfg_tab, tests_tab, bugs_tab, mgr_tab):
                self._add_tab_watermark(_tab)
        except Exception:
            pass
        try:
            self._add_tab_watermark(eng_tab)
        except Exception:
            pass

    def _trace(self, s):
        self.console.insert("end", s + "\n")
        self.console.see("end")

    def _tail_log(self):
        pos = 0
        while not self.stop_tail.is_set():
            try:
                with open(self.log_path, "r", encoding="utf-8") as f:
                    f.seek(pos)
                    data = f.read()
                    if data:
                        self.console.insert("end", data)
                        self.console.see("end")
                        pos = f.tell()
            except Exception:
                pass
            time.sleep(0.5)

    def connect(self):
        try:
            self.disconnect()
            client = GXDLMSSecureClient2(True)
            client.interfaceType = InterfaceType.HDLC_WITH_MODE_E
            client.useLogicalNameReferencing = True
            client.clientAddress = int(self.client_var.get())
            server = GXDLMSClient.getServerAddress(int(self.logical_var.get()), int(self.physical_var.get()))
            client.serverAddress = server
            auth_name = self.auth_var.get()
            client.authentication = getattr(Authentication, auth_name)
            sec_name = self.sec_var.get()
            client.ciphering.security = getattr(Security, sec_name)
            client.ciphering.systemTitle = GXByteBuffer.hexToBytes(self.st_var.get())
            client.ciphering.blockCipherKey = GXByteBuffer.hexToBytes(self.bk_var.get())
            client.ciphering.authenticationKey = GXByteBuffer.hexToBytes(self.ak_var.get())
            std_name = self.std_var.get()
            client.standard = getattr(Standard, std_name)
            client.useUtc2NormalTime = True
            media = GXSerial(None)
            media.port = self.port_var.get()
            media.baudRate = BaudRate.BAUD_RATE_300
            media.dataBits = 7
            media.parity = Parity.EVEN
            media.stopBits = StopBits.ONE
            reader = GXDLMSReader(client, media, TraceLevel.VERBOSE, "0.0.43.1.0.255")
            self.client = client
            self.reader = reader
            self.media = media
            self.media.open()
            self.reader.initializeConnection()
            self.reader.getAssociationView()
            try:
                conv = GXDLMSConverter(self.client.standard)
                for it in self.client.objects:
                    conv.updateOBISCodeInformation(it)
            except Exception:
                pass
            self._trace("Connected")
            self.refresh_obis()
            self.stop_tail.clear()
            threading.Thread(target=self._tail_log, daemon=True).start()
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def disconnect(self):
        try:
            self.stop_tail.set()
            if self.reader:
                self.reader.close()
            if self.media and self.media.isOpen():
                self.media.close()
        except Exception:
            pass
        self.reader = None
        self.client = None
        self.media = None
        if hasattr(self, "rights_tree"):
            self.rights_tree.delete(*self.rights_tree.get_children())
        if hasattr(self, "methods_tree"):
            self.methods_tree.delete(*self.methods_tree.get_children())
        if hasattr(self, "obis_console"):
            self.obis_console.delete("1.0","end")

    def refresh_obis(self):
        try:
            self.tree.delete(*self.tree.get_children())
            parents = {}
            for obj in self.client.objects:
                ln = obj.logicalName.strip() if obj.logicalName else ""
                t = self._type_name(obj.objectType)
                nm = self._obis_name(obj, ln, t)
                if t not in parents:
                    parents[t] = self.tree.insert("", "end", text=t, values=("", t, ""))
                self.tree.insert(parents[t], "end", text=nm, values=(ln, nm, t))
            for p in parents.values():
                self.tree.item(p, open=True)
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def _on_select(self, event):
        sel = self.tree.selection()
        if not sel:
            return
        vals = self.tree.item(sel[0], "values")
        if vals and vals[0]:
            self.sel_ln.set(vals[0])
            self._populate_rights(vals[0])

    def _find_obj(self, ln):
        target = ln.strip()
        for obj in self.client.objects:
            if (obj.logicalName or "").strip() == target:
                return obj
        return None

    def read_attr(self):
        try:
            ln = self.sel_ln.get()
            obj = self._find_obj(ln)
            if not obj:
                messagebox.showerror("Error", "Object not found")
                return
            idx = int(self.attr_var.get())
            if not self._can_read(obj, idx):
                messagebox.showerror("Error", f"Access denied: Attr {idx} is not readable")
                return
            val = self.reader.read(obj, idx)
            self._trace(f"Read {ln} [{idx}] = {val}")
            self.obis_console.insert("end", f"Read {ln} [{idx}] = {val}\n")
            self.obis_console.see("end")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def write_attr(self):
        try:
            ln = self.sel_ln.get()
            obj = self._find_obj(ln)
            if not obj:
                messagebox.showerror("Error", "Object not found")
                return
            idx = int(self.attr_var.get())
            if not self._can_write(obj, idx):
                messagebox.showerror("Error", f"Access denied: Attr {idx} is not writable")
                return
            val = self.reader.read(obj, idx)
            self.reader.write(obj, idx)
            self._trace(f"Wrote {ln} [{idx}] same value {val}")
            self.obis_console.insert("end", f"Wrote {ln} [{idx}] same value {val}\n")
            self.obis_console.see("end")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def add_test_file(self):
        paths = filedialog.askopenfilenames(filetypes=[("Python","*.py")])
        if not paths:
            return
        self.test_files.extend(paths)
        self._trace(f"Added {len(paths)} files")

    def clear_test_files(self):
        self.test_files = []
        self.tests_list.delete(0, "end")

    def collect_tests(self):
        try:
            self.tests_list.delete(0, "end")
            for p in self.test_files:
                cmd = [sys.executable, "-m", "pytest", "--collect-only", "-q", p]
                res = subprocess.run(cmd, capture_output=True, text=True)
                for line in res.stdout.splitlines():
                    if line and not line.startswith("<") and "::" in line:
                        self.tests_list.insert("end", line.strip())
            self._trace("Collected tests")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def _build_helpers(self):
        self._access_map = {0:"NO_ACCESS",1:"GET",2:"SET",3:"GET/SET"}
        self._type_map = {
            1:"DATA",3:"REGISTER",4:"EXTENDED_REGISTER",5:"DEMAND_REGISTER",
            7:"PROFILE_GENERIC",8:"CLOCK",9:"SCRIPT_TABLE",10:"SCHEDULE",11:"SPECIAL_DAYS_TABLE",
            12:"ASSOCIATION_SHORT_NAME",15:"ASSOCIATION_LOGICAL_NAME",17:"SAP_ASSIGNMENT",18:"IMAGE_TRANSFER",
            20:"ACTIVITY_CALENDAR",22:"ACTION_SCHEDULE",23:"IEC_HDLC_SETUP",40:"PUSH_SETUP",41:"TCP_UDP_SETUP",
            42:"IP4_SETUP",43:"MAC_ADDRESS_SETUP",64:"SECURITY_SETUP",70:"DISCONNECT_CONTROL",8192:"TARIFF_PLAN"
        }
        self._method_access_map = {0:"NoAccess",1:"Access"}
        self._forced_rights = {
            "CLOCK": {4: "GET"},
            "REGISTER": {3: "GET"},
            "EXTENDED_REGISTER": {3: "GET", 4: "GET", 5: "GET"},
            "DEMAND_REGISTER": {2: "GET", 3: "GET", 4: "GET", 5: "GET", 6: "GET", 7: "GET", 8: "GET"},
            "PROFILE_GENERIC": {2: "GET", 3: "GET", 4: "GET", 5: "GET", 6: "GET", 7: "GET", 8: "GET"},
            "SECURITY_SETUP": {2: "GET", 3: "GET", 4: "GET", 5: "GET", 6: "GET"},
            "ASSOCIATION_LOGICAL_NAME": {2:"GET",3:"GET",4:"GET",5:"GET",6:"GET",8:"GET",9:"GET",10:"GET",11:"GET"},
            "SAP_ASSIGNMENT": {2: "GET"}
        }
        self._attr_count_map = {
            "DATA": 2,
            "REGISTER": 4,
            "EXTENDED_REGISTER": 5,
            "DEMAND_REGISTER": 8,
            "PROFILE_GENERIC": 8,
            "CLOCK": 9,
            "ASSOCIATION_LOGICAL_NAME": 11,
            "SECURITY_SETUP": 6,
            "DISCONNECT_CONTROL": 4,
            "TARIFF_PLAN": 3,
            "SAP_ASSIGNMENT": 2,
            "IMAGE_TRANSFER": 7,
            "ACTION_SCHEDULE": 6,
            "ACTIVITY_CALENDAR": 9,
            "SPECIAL_DAYS_TABLE": 3,
            "SCRIPT_TABLE": 4,
            "IEC_HDLC_SETUP": 9,
            "PUSH_SETUP": 7,
            "TCP_UDP_SETUP": 10,
            "IP4_SETUP": 8,
            "MAC_ADDRESS_SETUP": 2
        }
        self._type_desc_map = {
            "DATA":"Generic data holder with single Value",
            "REGISTER":"Scalar/unit numeric value",
            "EXTENDED_REGISTER":"Register with capture time",
            "DEMAND_REGISTER":"Average demand over period",
            "PROFILE_GENERIC":"Cyclic buffer of captured values",
            "CLOCK":"Date/time and DST settings",
            "SCRIPT_TABLE":"Script entries for actions",
            "SCHEDULE":"Time-based script triggers",
            "SPECIAL_DAYS_TABLE":"Overrides for specific dates",
            "ASSOCIATION_LOGICAL_NAME":"Association and user/security context",
            "SAP_ASSIGNMENT":"Service access points list",
            "IMAGE_TRANSFER":"Firmware image transfer",
            "ACTIVITY_CALENDAR":"Season and tariff switching",
            "ACTION_SCHEDULE":"Method invocation schedule",
            "IEC_HDLC_SETUP":"HDLC link layer parameters",
            "PUSH_SETUP":"Automatic push configuration",
            "TCP_UDP_SETUP":"Transport parameters",
            "IP4_SETUP":"IPv4 network configuration",
            "MAC_ADDRESS_SETUP":"MAC address",
            "SECURITY_SETUP":"Security policy and keys",
            "DISCONNECT_CONTROL":"Remote connect/disconnect",
            "TARIFF_PLAN":"Tariff plan definitions"
        }
        self._attr_name_map = {
            "CLOCK": {
                1:"Logical name",2:"Time",3:"Time zone",4:"Status",
                5:"DST begin",6:"DST end",7:"DST deviation",8:"DST enabled",9:"Clock base"
            },
            "DATA": {1:"Logical name",2:"Value"},
            "REGISTER": {1:"Logical name",2:"Value",3:"Scaler unit",4:"Status"},
            "EXTENDED_REGISTER": {1:"Logical name",2:"Value",3:"Scaler unit",4:"Status",5:"Capture time"},
            "DEMAND_REGISTER": {
                1:"Logical name",2:"Current average value",3:"Last average value",4:"Scaler unit",
                5:"Period",6:"Number of periods",7:"Max demand",8:"Max demand time"
            },
            "PROFILE_GENERIC": {
                1:"Logical name",2:"Buffer",3:"Capture objects",4:"Capture period",
                5:"Sort method",6:"Sort object",7:"Entries in use",8:"Profile entries"
            },
            "SECURITY_SETUP": {
                1:"Logical name",2:"Security policy",3:"Security suite",
                4:"Client system title",5:"Server system title",6:"Certificates"
            },
            "DISCONNECT_CONTROL": {
                1:"Logical name",2:"Output state",3:"Control mode",4:"Default mode"
            },
            "TARIFF_PLAN": {
                1:"Logical name",2:"Active plan",3:"Passive plan"
            },
            "ASSOCIATION_LOGICAL_NAME": {
                1:"Logical name",2:"Object list",3:"Associated partners ID",4:"Application context name",
                5:"xDLMS context info",6:"Authentication mechanism name",7:"User name",8:"Association status",
                9:"Security setup reference",10:"User list",11:"Current user"
            }
        }
        self._method_name_map = {
            "CLOCK": {
                1:"Adjust to quarter",2:"Adjust to measure unit",3:"Adjust to minute",
                4:"Adjust to preset time",5:"Preset adjusting time",6:"Shift time"
            },
            "PROFILE_GENERIC": {1:"Capture",2:"Clear"},
            "DISCONNECT_CONTROL": {1:"Remote disconnect",2:"Remote reconnect"},
            "SECURITY_SETUP": {1:"Update key",2:"Activate key"},
            "DEMAND_REGISTER": {1:"Reset"},
            "TARIFF_PLAN": {1:"Activate",2:"Deactivate"}
        }
        self._ln_name_map = {
            "0.0.10.0.0.255":"Global Script"
        }

    def _access_str(self, mode3):
        m = int(mode3)
        r = (m & 1) != 0
        w = (m & 2) != 0
        if r and w:
            return "GET/SET"
        if r:
            return "GET"
        if w:
            return "SET"
        return "NO_ACCESS"

    def _populate_rights(self, ln):
        try:
            obj = self._find_obj(ln)
            if not obj:
                return
            tname = self._type_name(obj.objectType)
            desc = self._type_desc_map.get(tname, "")
            self.type_desc_label.config(text=desc)
            self.attrs_tree.delete(*self.attrs_tree.get_children())
            names = self._get_attribute_names(obj)
            try:
                count = obj.getAttributeCount()
            except Exception:
                count = self._attr_count_map.get(tname, 20)
            for i in range(1, count + 1):
                try:
                    s = self._access_str(obj.getAccess3(i))
                    if tname in self._forced_rights and i in self._forced_rights[tname]:
                        s = self._forced_rights[tname][i]
                    nm = names.get(i, f"Attribute {i}")
                    val = ""
                    dtname = ""
                    try:
                        dt = obj.getUIDataType(i) if hasattr(obj, "getUIDataType") else obj.getDataType(i)
                        dtname = self._dtype_name(dt)
                    except Exception:
                        dtname = ""
                    if s in ("GET","GET/SET"):
                        try:
                            v = self.reader.read(obj, i)
                            val = str(v)
                        except Exception:
                            val = ""
                    if s != "NO_ACCESS":
                        self.attrs_tree.insert("", "end", values=(i, nm, s, dtname, val))
                except Exception:
                    pass
            self.methods_tree.delete(*self.methods_tree.get_children())
            mnames = self._get_method_names(obj)
            try:
                mcount = obj.getMethodCount()
            except Exception:
                mcount = 10
            for i in range(1, mcount + 1):
                try:
                    m = obj.getMethodAccess3(i)
                    s = self._method_access_map.get(int(m), str(m))
                    n = mnames.get(i, f"Method {i}")
                    if s == "Access":
                        self.methods_tree.insert("", "end", values=(i, n, s))
                except Exception:
                    pass
        except Exception:
            pass

    def _can_read(self, obj, idx):
        try:
            s = self._access_str(obj.getAccess3(idx))
            tname = self._type_name(obj.objectType)
            count = self._attr_count_map.get(tname, 20)
            if idx < 1 or idx > count:
                return False
            return s in ("GET","GET/SET")
        except Exception:
            return True

    def _can_write(self, obj, idx):
        try:
            s = self._access_str(obj.getAccess3(idx))
            tname = self._type_name(obj.objectType)
            count = self._attr_count_map.get(tname, 20)
            if idx < 1 or idx > count:
                return False
            if tname in self._forced_rights and idx in self._forced_rights[tname]:
                s = self._forced_rights[tname][idx]
            return s in ("SET","GET/SET")
        except Exception:
            return False

    def _on_attr_select(self, event):
        sel = self.attrs_tree.selection()
        if not sel:
            return
        vals = self.attrs_tree.item(sel[0], "values")
        if vals and len(vals) >= 4:
            idx = int(vals[0])
            self._build_dynamic_editor_for(obj=self._find_obj(self.sel_ln.get()), idx=idx)
            right = str(vals[2])
            can_write = right in ("SET","GET/SET")
            try:
                self.write_selected_btn.state(("!disabled",)) if can_write else self.write_selected_btn.state(("disabled",))
            except Exception:
                pass
        # Also update method run button state on selection
        self._on_method_select(None)

    def _on_method_select(self, event):
        sel = self.methods_tree.selection()
        if not sel:
            try:
                self.run_method_btn.state(("disabled",))
            except Exception:
                pass
            return
        vals = self.methods_tree.item(sel[0], "values")
        if vals and len(vals) >= 3:
            right = str(vals[2])
            can_run = right == "Access"
            try:
                self.run_method_btn.state(("!disabled",)) if can_run else self.run_method_btn.state(("disabled",))
            except Exception:
                pass
            # Auto parameter type/visibility based on selected method
            try:
                obj = self._find_obj(self.sel_ln.get())
                self._setup_method_params(obj, int(vals[0]))
            except Exception:
                pass
        else:
            try:
                self.run_method_btn.state(("disabled",))
            except Exception:
                pass
            try:
                self.method_type_var.set("NONE")
                self.method_value.set("")
                self.method_value_entry.config(state="disabled")
            except Exception:
                pass
    def _setup_method_params(self, obj, method_idx):
        try:
            tname = self._type_name(obj.objectType) if obj else ""
            dtype = "NONE"
            require_value = False
            default_val = ""
            if tname == "CLOCK":
                if method_idx in (1,2,3,4):
                    dtype = "INT8"
                    require_value = False
                    default_val = "0"
                elif method_idx == 6:
                    dtype = "INT16"
                    require_value = True
                    default_val = ""
                else:
                    dtype = "NONE"
                    require_value = False
            elif tname in ("PROFILE_GENERIC","DISCONNECT_CONTROL","SCRIPT_TABLE"):
                dtype = "INT8"
                require_value = False
                default_val = "0"
            else:
                dtype = "NONE"
                require_value = False
            self.method_type_var.set(dtype)
            self.method_value.set(default_val)
            if require_value:
                self.method_value_entry.config(state="normal")
            else:
                self.method_value_entry.config(state="disabled")
        except Exception:
            pass
    def read_selected_attr(self):
        try:
            ln = self.sel_ln.get()
            obj = self._find_obj(ln)
            if not obj:
                messagebox.showerror("Error", "Object not found")
                return
            sel = self.attrs_tree.selection()
            if not sel:
                messagebox.showinfo("Info", "Select attribute in table")
                return
            idx = int(self.attrs_tree.item(sel[0], "values")[0])
            if not self._can_read(obj, idx):
                messagebox.showerror("Error", f"Access denied: Attr {idx} is not readable")
                return
            val = self.reader.read(obj, idx)
            self.obis_console.insert("end", f"Read {ln} [{idx}] = {val}\n")
            self.obis_console.see("end")
            # Update value column
            vals = list(self.attrs_tree.item(sel[0], "values"))
            # value column is last index (4)
            if len(vals) >= 5:
                vals[4] = str(val)
            self.attrs_tree.item(sel[0], values=vals)
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def write_selected_attr(self):
        try:
            ln = self.sel_ln.get()
            obj = self._find_obj(ln)
            if not obj:
                messagebox.showerror("Error", "Object not found")
                return
            sel = self.attrs_tree.selection()
            if not sel:
                messagebox.showinfo("Info", "Select attribute in table")
                return
            idx = int(self.attrs_tree.item(sel[0], "values")[0])
            if not self._can_write(obj, idx):
                messagebox.showerror("Error", f"Access denied: Attr {idx} is not writable")
                return
            dt = obj.getUIDataType(idx) if hasattr(obj, "getUIDataType") else obj.getDataType(idx)
            # Handle unknown dt by inferring from current value or heuristic.
            if hasattr(dt, "name") and dt.name == "NONE" or (not hasattr(dt, "name") and int(dt) == int(DataType.NONE)):
                s = str(self._editor_var.get()).strip()
                new_val = self._infer_value_for_none(obj, idx, s)
            else:
                new_val = self._get_editor_value(dt)
            if not self._apply_value(obj, idx, new_val):
                messagebox.showerror("Error", "Unsupported object write for this attribute")
                return
            self.reader.write(obj, idx)
            self.obis_console.insert("end", f"Wrote {ln} [{idx}] value {new_val}\n")
            self.obis_console.see("end")
            vals = list(self.attrs_tree.item(sel[0], "values"))
            if len(vals) >= 5:
                vals[4] = str(new_val)
            self.attrs_tree.item(sel[0], values=vals)
        except ValueError as ve:
            messagebox.showerror("Error", f"Type error: {ve}")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def _type_name(self, ot):
        try:
            if hasattr(ot, "name"):
                return ot.name
            v = int(ot)
            return self._type_map.get(v, str(v))
        except Exception:
            return str(ot)

    def _dtype_name(self, dt):
        try:
            if hasattr(dt, "name"):
                return dt.name
            v = int(dt)
            for k in ["ARRAY","BCD","BITSTRING","BOOLEAN","COMPACT_ARRAY","DATE","DATETIME","ENUM","FLOAT32","FLOAT64","INT16","INT32","INT64","INT8","NONE","OCTET_STRING","STRING","STRING_UTF8","STRUCTURE","TIME","UINT16","UINT32","UINT64","UINT8"]:
                try:
                    if v == int(getattr(DataType, k)):
                        return k
                except Exception:
                    continue
            return str(v)
        except Exception:
            return str(dt)
    def _get_attribute_names(self, obj):
        names = {}
        try:
            if hasattr(obj, "getNames"):
                arr = obj.getNames()
                for i, nm in enumerate(arr, start=1):
                    names[i] = str(nm)
        except Exception:
            pass
        if 1 not in names:
            names[1] = "Logical name"
        try:
            tname = self._type_name(obj.objectType)
            fallback = self._attr_name_map.get(tname, {})
            for k, v in fallback.items():
                names.setdefault(k, v)
        except Exception:
            pass
        return names

    def _get_method_names(self, obj):
        names = {}
        try:
            if hasattr(obj, "getMethodNames"):
                arr = obj.getMethodNames()
                for i, nm in enumerate(arr, start=1):
                    names[i] = str(nm)
        except Exception:
            pass
        try:
            tname = self._type_name(obj.objectType)
            fallback = self._method_name_map.get(tname, {})
            for k, v in fallback.items():
                names.setdefault(k, v)
        except Exception:
            pass
        return names

    def _example_for_type(self, dt):
        try:
            v = int(dt)
        except Exception:
            return ""
        if v == int(DataType.OCTET_STRING):
            return "010203 (hex)"
        if v == int(DataType.STRING) or v == int(DataType.STRING_UTF8):
            return "text"
        if v == int(DataType.BITSTRING):
            return "10101010"
        if v in (int(DataType.INT8), int(DataType.INT16), int(DataType.INT32), int(DataType.INT64),
                 int(DataType.UINT8), int(DataType.UINT16), int(DataType.UINT32), int(DataType.UINT64),
                 int(DataType.ENUM), int(DataType.BCD)):
            return "123"
        if v == int(DataType.BOOLEAN):
            return "true"
        if v == int(DataType.FLOAT32) or v == int(DataType.FLOAT64):
            return "12.34"
        if v == int(DataType.ARRAY) or v == int(DataType.STRUCTURE):
            return "[val1, val2]"
        if v == int(DataType.DATETIME):
            return "YYYY-MM-DD HH:MM:SS"
        if v == int(DataType.DATE):
            return "YYYY-MM-DD"
        if v == int(DataType.TIME):
            return "HH:MM:SS"
        return ""

    def _clear_editor(self):
        for w in self.edit_frame.winfo_children():
            w.destroy()
        self._editor_kind = None
        self._editor_var = None

    def _build_dynamic_editor_for(self, obj, idx):
        try:
            self._clear_editor()
            if not obj:
                return
            dt = obj.getUIDataType(idx) if hasattr(obj, "getUIDataType") else obj.getDataType(idx)
            # Current value
            cur = ""
            try:
                cur = str(self.reader.read(obj, idx))
            except Exception:
                cur = ""
            v = int(dt)
            if v == int(DataType.BOOLEAN):
                self._editor_kind = "bool"
                self._editor_var = tk.BooleanVar(value=str(cur).lower() in ("true","1","yes","on"))
                ttk.Checkbutton(self.edit_frame, text="Value", variable=self._editor_var).grid(row=0, column=0, sticky="w")
            elif v in (int(DataType.STRING), int(DataType.STRING_UTF8), int(DataType.BITSTRING)):
                self._editor_kind = "text"
                self._editor_var = tk.StringVar(value=cur)
                ttk.Entry(self.edit_frame, textvariable=self._editor_var, width=40).grid(row=0, column=0, sticky="w")
            elif v == int(DataType.OCTET_STRING):
                self._editor_kind = "hex"
                self._editor_var = tk.StringVar(value=cur if isinstance(cur, str) else "")
                ttk.Entry(self.edit_frame, textvariable=self._editor_var, width=40).grid(row=0, column=0, sticky="w")
                ttk.Label(self.edit_frame, text="hex").grid(row=0, column=1, sticky="w")
            elif v in (int(DataType.INT8), int(DataType.INT16), int(DataType.INT32), int(DataType.INT64),
                       int(DataType.UINT8), int(DataType.UINT16), int(DataType.UINT32), int(DataType.UINT64),
                       int(DataType.ENUM), int(DataType.BCD)):
                self._editor_kind = "int"
                self._editor_var = tk.StringVar(value=cur)
                ttk.Entry(self.edit_frame, textvariable=self._editor_var, width=20).grid(row=0, column=0, sticky="w")
            elif v in (int(DataType.DATETIME), int(DataType.DATE), int(DataType.TIME)):
                self._editor_kind = "dt"
                self._editor_var = tk.StringVar(value=cur)
                ttk.Entry(self.edit_frame, textvariable=self._editor_var, width=30).grid(row=0, column=0, sticky="w")
                ttk.Button(self.edit_frame, text="Current", command=lambda: self._fill_current_time(v)).grid(row=0, column=1, sticky="w")
            else:
                self._editor_kind = "raw"
                self._editor_var = tk.StringVar(value=cur)
                ttk.Entry(self.edit_frame, textvariable=self._editor_var, width=40).grid(row=0, column=0, sticky="w")
        except Exception:
            self._clear_editor()

    def _fill_current_time(self, v):
        try:
            now = time.localtime()
            if v == int(DataType.DATETIME):
                self._editor_var.set(time.strftime("%Y-%m-%d %H:%M:%S", now))
            elif v == int(DataType.DATE):
                self._editor_var.set(time.strftime("%Y-%m-%d", now))
            elif v == int(DataType.TIME):
                self._editor_var.set(time.strftime("%H:%M:%S", now))
        except Exception:
            pass

    def _get_editor_value(self, dt):
        if not self._editor_kind:
            raise ValueError("No editor for selected attribute")
        if self._editor_kind == "bool":
            return bool(self._editor_var.get())
        s = str(self._editor_var.get()).strip()
        if self._editor_kind == "dt":
            return self._normalize_datetime_input(s)
        return self._parse_value(s, dt)
    def _to_gx_datetime(self, text, kind):
        try:
            from gurux_dlms.GXDateTime import GXDateTime
        except Exception:
            raise ValueError("GXDateTime not available")
        text = self._normalize_datetime_input(text)
        patts = []
        if kind == "datetime":
            patts = ["%Y-%m-%d %H:%M:%S", "%m/%d/%Y %H:%M:%S", "%m/%d/%y %H:%M:%S"]
        elif kind == "date":
            patts = ["%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y"]
        elif kind == "time":
            patts = ["%H:%M:%S"]
        last_err = None
        for p in patts:
            try:
                return GXDateTime(text, p)
            except Exception as e:
                last_err = e
                continue
        if last_err:
            raise last_err
        raise ValueError("Unsupported date/time")
    def _normalize_datetime_input(self, s):
        try:
            t = s.strip()
            # Drop fractional part separated by ':' or '.'
            # e.g., "16:50:57:0000000" -> "16:50:57"
            if t.count(":") >= 3:
                parts = t.split(" ")
                if len(parts) == 2:
                    hms = parts[1]
                    h = hms.split(":")
                    if len(h) >= 3:
                        hms_clean = ":".join(h[:3])
                        t = parts[0] + " " + hms_clean
            if "." in t and t.split(" ")[-1].count(":") == 2:
                # "16:50:57.000000" -> "16:50:57"
                date_part, time_part = t.split(" ")
                time_part = time_part.split(".")[0]
                t = date_part + " " + time_part
            return t
        except Exception:
            return s
    def _infer_value_for_none(self, obj, idx, s):
        # Try to infer from current value first
        try:
            cur = self.reader.read(obj, idx)
            if isinstance(cur, (bytes, bytearray)):
                from gurux_dlms.GXByteBuffer import GXByteBuffer
                return GXByteBuffer.hexToBytes(s) if s else cur
            if isinstance(cur, bool):
                ls = s.lower()
                if ls in ("true","1","yes","on"):
                    return True
                if ls in ("false","0","no","off"):
                    return False
                return bool(cur)
            if isinstance(cur, int):
                return int(s)
            if isinstance(cur, float):
                return float(s)
            if isinstance(cur, str):
                return s
        except Exception:
            pass
        # Heuristics if read failed
        try:
            from gurux_dlms.GXByteBuffer import GXByteBuffer
            hs = s.replace(" ", "")
            if len(hs) >= 2 and all(c in "0123456789abcdefABCDEF" for c in hs):
                return GXByteBuffer.hexToBytes(hs)
        except Exception:
            pass
        try:
            return int(s)
        except Exception:
            pass
        try:
            return float(s)
        except Exception:
            pass
        ls = s.lower()
        if ls in ("true","1","yes","on"):
            return True
        if ls in ("false","0","no","off"):
            return False
        return s
    def open_advanced_editor(self):
        try:
            ln = self.sel_ln.get()
            obj = self._find_obj(ln)
            sel = self.attrs_tree.selection()
            if not obj or not sel:
                messagebox.showinfo("Info", "Select attribute in table")
                return
            idx = int(self.attrs_tree.item(sel[0], "values")[0])
            dt = obj.getUIDataType(idx) if hasattr(obj, "getUIDataType") else obj.getDataType(idx)
            win = tk.Toplevel(self.root)
            win.title(f"Advanced Editor - {ln} [{idx}]")
            nb = ttk.Notebook(win)
            nb.pack(fill="both", expand=True)
            # Basic tab shows current raw value
            tab_basic = ttk.Frame(nb)
            nb.add(tab_basic, text="Basic")
            cur_val = ""
            try:
                cur_val = str(self.reader.read(obj, idx))
            except Exception:
                cur_val = ""
            ttk.Label(tab_basic, text="Current value").pack(anchor="w")
            txt = tk.Text(tab_basic, height=6)
            txt.insert("end", cur_val)
            txt.pack(fill="both", expand=True)
            # Specialized tabs
            tname = self._type_name(obj.objectType)
            if tname == "PUSH_SETUP":
                self._adv_build_pushsetup_tabs(nb, obj, idx)
            elif tname == "DISCONNECT_CONTROL":
                self._adv_build_disconnect_tabs(nb, obj, idx)
            elif tname == "CLOCK":
                self._adv_build_clock_tabs(nb, obj, idx)
            ttk.Button(win, text="Close", command=win.destroy).pack(side="right", padx=8, pady=8)
        except Exception as e:
            messagebox.showerror("Error", str(e))
    def _adv_build_pushsetup_tabs(self, nb, obj, idx):
        try:
            # Objects tab (attribute 2)
            tab_objs = ttk.Frame(nb)
            nb.add(tab_objs, text="Objects")
            frm = ttk.Frame(tab_objs)
            frm.pack(fill="x")
            ttk.Label(frm, text="Object LN").grid(row=0, column=0, sticky="w")
            ln_var = tk.StringVar()
            ln_combo = ttk.Combobox(frm, textvariable=ln_var, width=24, values=[(it.logicalName or "").strip() for it in self.client.objects])
            ln_combo.grid(row=0, column=1, sticky="w")
            ttk.Label(frm, text="Attr idx").grid(row=0, column=2, sticky="w")
            ai_var = tk.StringVar(value="2")
            ttk.Entry(frm, textvariable=ai_var, width=6).grid(row=0, column=3, sticky="w")
            ttk.Label(frm, text="Data idx").grid(row=0, column=4, sticky="w")
            di_var = tk.StringVar(value="0")
            ttk.Entry(frm, textvariable=di_var, width=6).grid(row=0, column=5, sticky="w")
            listbox = tk.Listbox(tab_objs)
            listbox.pack(fill="both", expand=True)
            # Populate existing
            try:
                for k, v in getattr(obj, "pushObjectList", []):
                    listbox.insert("end", f"{(k.logicalName or '').strip()} | AI={v.attributeIndex} DI={v.dataIndex}")
            except Exception:
                pass
            btns = ttk.Frame(tab_objs)
            btns.pack(fill="x")
            def _add():
                ln = ln_var.get().strip()
                if not ln:
                    return
                listbox.insert("end", f"{ln} | AI={ai_var.get().strip()} DI={di_var.get().strip()}")
            def _remove():
                sel = list(listbox.curselection())
                for i in reversed(sel):
                    listbox.delete(i)
            def _apply():
                try:
                    from gurux_dlms.objects.GXDLMSCaptureObject import GXDLMSCaptureObject
                except Exception:
                    messagebox.showerror("Error", "GXDLMSCaptureObject not available")
                    return
                new_list = []
                for i in range(listbox.size()):
                    row = listbox.get(i)
                    try:
                        parts = row.split("|")
                        ln = parts[0].strip()
                        ai = int(parts[1].split("=")[1].split()[0])
                        di = int(parts[1].split("DI=")[1])
                        # find object by LN
                        ref = self._find_obj(ln)
                        if not ref:
                            continue
                        co = GXDLMSCaptureObject(ai, di)
                        new_list.append((ref, co))
                    except Exception:
                        continue
                try:
                    obj.pushObjectList = new_list
                    self.reader.write(obj, 2)
                    self.obis_console.insert("end", f"Applied PushSetup object list ({len(new_list)} items)\n")
                    self.obis_console.see("end")
                except Exception as e:
                    messagebox.showerror("Error", str(e))
            ttk.Button(btns, text="Add", command=_add).pack(side="left")
            ttk.Button(btns, text="Remove", command=_remove).pack(side="left")
            ttk.Button(btns, text="Apply", command=_apply).pack(side="right")
            # Communication window tab (attribute 4)
            tab_win = ttk.Frame(nb)
            nb.add(tab_win, text="Comm Window")
            wfrm = ttk.Frame(tab_win)
            wfrm.pack(fill="x")
            ttk.Label(wfrm, text="Start").grid(row=0, column=0, sticky="w")
            st = tk.StringVar()
            ttk.Entry(wfrm, textvariable=st, width=20).grid(row=0, column=1, sticky="w")
            ttk.Label(wfrm, text="End").grid(row=0, column=2, sticky="w")
            et = tk.StringVar()
            ttk.Entry(wfrm, textvariable=et, width=20).grid(row=0, column=3, sticky="w")
            lst = tk.Listbox(tab_win)
            lst.pack(fill="both", expand=True)
            try:
                for k, v in getattr(obj, "communicationWindow", []):
                    lst.insert("end", f"{k} -> {v}")
            except Exception:
                pass
            def _add_win():
                try:
                    from gurux_dlms.GXDateTime import GXDateTime
                    k = GXDateTime(st.get().strip())
                    v = GXDateTime(et.get().strip())
                    lst.insert("end", f"{k} -> {v}")
                except Exception:
                    messagebox.showerror("Error", "Use YYYY-MM-DD HH:MM:SS")
            def _apply_win():
                try:
                    from gurux_dlms.GXDateTime import GXDateTime
                    wins = []
                    for i in range(lst.size()):
                        row = lst.get(i)
                        parts = row.split("->")
                        k = GXDateTime(parts[0].strip())
                        v = GXDateTime(parts[1].strip())
                        wins.append((k, v))
                    obj.communicationWindow = wins
                    self.reader.write(obj, 4)
                    self.obis_console.insert("end", f"Applied PushSetup communication windows ({len(wins)})\n")
                    self.obis_console.see("end")
                except Exception as e:
                    messagebox.showerror("Error", str(e))
            wbtns = ttk.Frame(tab_win)
            wbtns.pack(fill="x")
            ttk.Button(wbtns, text="Add Window", command=_add_win).pack(side="left")
            ttk.Button(wbtns, text="Apply", command=_apply_win).pack(side="right")
        except Exception:
            pass
    def _adv_build_disconnect_tabs(self, nb, obj, idx):
        try:
            tab = ttk.Frame(nb)
            nb.add(tab, text="Control")
            ttk.Label(tab, text="Control mode").pack(anchor="w")
            mode = tk.StringVar(value="0")
            choice = ttk.Combobox(tab, textvariable=mode, values=["0","1","2"], width=10)
            choice.pack(anchor="w")
            def _apply():
                try:
                    val = int(mode.get())
                    if hasattr(obj, "controlMode"):
                        obj.controlMode = val
                    self.reader.write(obj, 3)
                    self.obis_console.insert("end", f"Applied Disconnect control mode {val}\n")
                    self.obis_console.see("end")
                except Exception as e:
                    messagebox.showerror("Error", str(e))
            ttk.Button(tab, text="Apply", command=_apply).pack(anchor="e")
        except Exception:
            pass
    def _adv_build_clock_tabs(self, nb, obj, idx):
        try:
            tab = ttk.Frame(nb)
            nb.add(tab, text="Date/Time")
            ttk.Label(tab, text="Set time").pack(anchor="w")
            tm = tk.StringVar()
            ttk.Entry(tab, textvariable=tm, width=24).pack(anchor="w")
            def _now():
                tm.set(time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()))
            ttk.Button(tab, text="Current", command=_now).pack(anchor="w")
            def _apply():
                try:
                    obj.time = self._to_gx_datetime(tm.get().strip(), "datetime")
                    self.reader.write(obj, 2)
                    self.obis_console.insert("end", f"Applied Clock time {tm.get().strip()}\n")
                    self.obis_console.see("end")
                except Exception as e:
                    messagebox.showerror("Error", str(e))
            ttk.Button(tab, text="Apply", command=_apply).pack(anchor="e")
        except Exception:
            pass

    def _obis_name(self, obj, ln, tname):
        try:
            if getattr(obj, "description", None):
                d = str(obj.description)
                if d:
                    return d
            if getattr(obj, "name", None):
                n = str(obj.name)
                if n and n != ln:
                    return n
        except Exception:
            pass
        try:
            if ln in self._ln_name_map:
                return self._ln_name_map[ln]
        except Exception:
            pass
        return tname

    def _parse_value(self, s, dt):
        if dt == DataType.NONE:
            raise ValueError("Unknown data type")
        t = int(dt)
        # Bracketed list handling, e.g. "[80, 120, 120]"
        if s.startswith("[") and s.endswith("]"):
            items = [x.strip() for x in s[1:-1].split(",") if x.strip()]
            ints = []
            is_ints = True
            for it in items:
                try:
                    ints.append(int(it))
                except Exception:
                    is_ints = False
                    break
            if is_ints:
                try:
                    return bytearray(ints) if t == int(DataType.OCTET_STRING) else ints
                except Exception:
                    return ints
            return items
        if t in (int(DataType.INT8), int(DataType.INT16), int(DataType.INT32), int(DataType.INT64),
                 int(DataType.UINT8), int(DataType.UINT16), int(DataType.UINT32), int(DataType.UINT64),
                 int(DataType.ENUM), int(DataType.BCD)):
            # Try integer
            return int(s)
        if t == int(DataType.BOOLEAN):
            ls = s.lower()
            if ls in ("true","1","yes","on"):
                return True
            if ls in ("false","0","no","off"):
                return False
            raise ValueError("Expect boolean (true/false)")
        if t == int(DataType.OCTET_STRING):
            try:
                return GXByteBuffer.hexToBytes(s)
            except Exception:
                raise ValueError("Expect hex string for OCTET_STRING")
        if t == int(DataType.STRING) or t == int(DataType.STRING_UTF8) or t == int(DataType.BITSTRING):
            return s
        # Fallback: return raw string
        return s

    def _apply_value(self, obj, idx, val):
        try:
            v = int(obj.getObjectType())
        except Exception:
            v = None
        try:
            # Detect data type for conversion
            dt = None
            try:
                dt = obj.getUIDataType(idx) if hasattr(obj, "getUIDataType") else obj.getDataType(idx)
            except Exception:
                dt = None
            # Common: DATA/REGISTER write value attribute 2
            if v in (int(ObjectType.DATA), int(ObjectType.REGISTER), int(ObjectType.EXTENDED_REGISTER)) and idx == 2:
                setattr(obj, "value", val)
                return True
            # CLOCK attributes: accept human-readable date/time strings
            if v == int(ObjectType.CLOCK):
                if idx == 2:
                    if isinstance(val, str):
                        setattr(obj, "time", self._to_gx_datetime(val, "datetime"))
                    else:
                        setattr(obj, "time", val)
                    return True
                if idx == 5:
                    if isinstance(val, str):
                        setattr(obj, "begin", self._to_gx_datetime(val, "datetime"))
                    else:
                        setattr(obj, "begin", val)
                    return True
                if idx == 6:
                    if isinstance(val, str):
                        setattr(obj, "end", self._to_gx_datetime(val, "datetime"))
                    else:
                        setattr(obj, "end", val)
                    return True
            # DISCONNECT_CONTROL: write control mode/state if supported
            if v == int(ObjectType.DISCONNECT_CONTROL) and idx in (2,3):
                # Some meters expose properties outputState/controlMode
                try:
                    if idx == 2 and hasattr(obj, "outputState"):
                        setattr(obj, "outputState", val)
                        return True
                    if idx == 3 and hasattr(obj, "controlMode"):
                        setattr(obj, "controlMode", val)
                        return True
                except Exception:
                    return False
            # Default: attempt to set 'value' for idx 2
            if idx == 2 and hasattr(obj, "value"):
                setattr(obj, "value", val)
                return True
        except Exception:
            return False
        return False

    def run_selected_method(self):
        try:
            ln = self.sel_ln.get()
            obj = self._find_obj(ln)
            if not obj:
                messagebox.showerror("Error", "Object not found")
                return
            sel = self.methods_tree.selection()
            if not sel:
                messagebox.showinfo("Info", "Select method in table")
                return
            idx = int(self.methods_tree.item(sel[0], "values")[0])
            right = str(self.methods_tree.item(sel[0], "values")[2])
            if right != "Access":
                messagebox.showerror("Error", f"Access denied: Method {idx}")
                return
            type_name = self.method_type_var.get().strip()
            if not type_name or type_name == "NONE":
                dt = DataType.INT8
                val = 0
            else:
                dt = getattr(DataType, type_name)
                val = self._parse_value(self.method_value.get().strip(), dt)
            data = self.client.method(obj, idx, val, dt)
            self.reader.readDLMSPacket(data)
            self.obis_console.insert("end", f"Method {ln} [{idx}] with {type_name}={val}\n")
            self.obis_console.see("end")
        except ValueError as ve:
            messagebox.showerror("Error", f"Type error: {ve}")
        except Exception as e:
            messagebox.showerror("Error", str(e))
    def run_selected_tests(self):
        try:
            sel = list(self.tests_list.curselection())
            if not sel:
                messagebox.showinfo("Info", "Select tests")
                return
            nodes = [self.tests_list.get(i) for i in sel]
            cmd = [sys.executable, "-m", "pytest", "-v", "-s"] + nodes
            res = subprocess.run(cmd, capture_output=True, text=True)
            self.bug_text.delete("1.0","end")
            self.bug_text.insert("end", res.stdout or res.stderr)
            self.console.insert("end", res.stdout or res.stderr)
            self.console.see("end")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def save_assoc_view(self):
        try:
            path = filedialog.asksaveasfilename(defaultextension=".txt", initialfile="association_view.txt")
            if not path:
                return
            with open(path, "w", encoding="utf-8") as f:
                f.write(f"Objects count: {len(self.client.objects)}\n")
                for obj in self.client.objects:
                    ln = obj.logicalName.strip() if obj.logicalName else ""
                    t = getattr(obj.objectType, "name", str(obj.objectType))
                    f.write(f"{ln}\t{t}\n")
            self._trace(f"Saved {path}")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def export_console(self):
        try:
            path = filedialog.asksaveasfilename(defaultextension=".txt", initialfile="console_output.txt")
            if not path:
                return
            data = self.console.get("1.0","end")
            with open(path, "w", encoding="utf-8") as f:
                f.write(data)
            self._trace(f"Saved {path}")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def _make_scrollable_tab(self, tab):
        canvas = tk.Canvas(tab, highlightthickness=0)
        vsb = ttk.Scrollbar(tab, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        inner = ttk.Frame(canvas)
        canvas.create_window((0, 0), window=inner, anchor="nw")
        try:
            inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        except Exception:
            pass
        def _on_mousewheel(event):
            try:
                delta = -1 if event.delta > 0 else 1
                canvas.yview_scroll(delta, "units")
            except Exception:
                pass
        canvas.bind_all("<MouseWheel>", _on_mousewheel)
        return canvas, inner
    def _build_logo_sidebar(self, canvas):
        try:
            self.sidebar_img = None
            logo_path = os.path.join(os.path.dirname(__file__), "assets", "azka_logo.png")
            if os.path.exists(logo_path):
                self.sidebar_img = tk.PhotoImage(file=logo_path)
                def _draw(event=None):
                    canvas.delete("all")
                    w = canvas.winfo_width()
                    h = canvas.winfo_height()
                    if self.sidebar_img:
                        canvas.create_image(w//2, h//2, image=self.sidebar_img)
                canvas.bind("<Configure>", _draw)
                _draw()
            else:
                def _draw_text(event=None):
                    canvas.delete("all")
                    w = canvas.winfo_width()
                    h = canvas.winfo_height()
                    canvas.create_text(w//2, h//2, text="AZKA TECHNOLOGY\nFREE ZONE S.A.E", fill="#0b4d79", font=("Arial", 16, "bold"))
                canvas.bind("<Configure>", _draw_text)
                _draw_text()
        except Exception:
            pass
    def _add_watermark(self, canvas):
        try:
            def _update_wm(event=None):
                w = canvas.winfo_width()
                h = canvas.winfo_height()
                size = max(18, min(48, int(min(w, h) * 0.08)))
                if not hasattr(self, "_wm_fonts"):
                    self._wm_fonts = {}
                if canvas not in self._wm_fonts:
                    self._wm_fonts[canvas] = tkfont.Font(family="Arial", size=size, weight="bold")
                else:
                    self._wm_fonts[canvas].config(size=size)
                if not hasattr(self, "_wm_text_ids"):
                    self._wm_text_ids = {}
                if canvas not in self._wm_text_ids:
                    tid = canvas.create_text(w//2, h//2, text="AZKA TECHNOLOGY FREE ZONE S.A.E", fill="#d0dee9", font=self._wm_fonts[canvas])
                    self._wm_text_ids[canvas] = tid
                    canvas.tag_lower(tid)
                else:
                    tid = self._wm_text_ids[canvas]
                    canvas.coords(tid, w//2, h//2)
            canvas.bind("<Configure>", _update_wm)
            _update_wm()
        except Exception:
            pass
    def _add_tab_watermark(self, tab):
        try:
            lbl = ttk.Label(tab, text="AZKA TECHNOLOGY FREE ZONE S.A.E", foreground="#d0dee9")
            lbl.place(relx=0.5, rely=0.5, anchor="center")
            try:
                lbl.lower()
            except Exception:
                pass
        except Exception:
            pass
    def create_bug(self):
        try:
            if not requests:
                messagebox.showerror("Error", "requests not installed")
                return
            full = self.azure_url.get().strip()
            base, proj = self._parse_azure_url(full)
            pat = self.azure_pat.get().strip()
            if not base or not proj or not pat:
                messagebox.showerror("Error", "Set Azure URL (full), PAT")
                return
            title = "Automated Test Failure"
            desc = self.bug_text.get("1.0","end")
            api = base.rstrip("/") + f"/{proj}/_apis/wit/workitems/$Bug?api-version=7.0"
            payload = [
                {"op":"add","path":"/fields/System.Title","value":title},
                {"op":"add","path":"/fields/System.Description","value":desc},
                {"op":"add","path":"/fields/Microsoft.VSTS.Common.Severity","value":"3 - Medium"}
            ]
            auth = ("" , pat)
            r = requests.patch(api, json=payload, headers={"Content-Type":"application/json-patch+json"}, auth=auth)
            if r.status_code >= 200 and r.status_code < 300:
                wi = r.json()
                self._trace(f"Bug created #{wi.get('id')}")
            else:
                messagebox.showerror("Error", f"{r.status_code}: {r.text}")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def fetch_bugs(self):
        try:
            if not requests:
                messagebox.showerror("Error", "requests not installed")
                return
            full = self.azure_url.get().strip()
            base, proj = self._parse_azure_url(full)
            pat = self.azure_pat.get().strip()
            if not base or not proj or not pat:
                messagebox.showerror("Error", "Set Azure URL (full), PAT")
                return
            wiql = {
                "query": "Select [System.Id], [System.Title], [System.State] From WorkItems Where [System.TeamProject] = @project And [System.WorkItemType] = 'Bug' Order By [System.ChangedDate] Desc"
            }
            wiql_api = base.rstrip("/") + f"/{proj}/_apis/wit/wiql?api-version=7.0"
            auth = ("" , pat)
            q = requests.post(wiql_api, json=wiql, auth=auth)
            ids = [it["id"] for it in q.json().get("workItems", [])]
            self.bugs_tree.delete(*self.bugs_tree.get_children())
            if not ids:
                self.stats_label.config(text="No bugs")
                return
            batch_api = base.rstrip("/") + f"/_apis/wit/workitemsbatch?api-version=7.0"
            b = requests.post(batch_api, json={"ids": ids, "fields":["System.Id","System.Title","System.State","Microsoft.VSTS.Common.Severity"]}, auth=auth)
            items = b.json().get("value", [])
            # Sort by severity
            order = {"1 - Critical":0, "2 - High":1, "3 - Medium":2, "4 - Low":3}
            items.sort(key=lambda it: order.get(it["fields"].get("Microsoft.VSTS.Common.Severity",""), 99))
            sev_counts = {}
            for it in items:
                fields = it["fields"]
                fid = fields.get("System.Id")
                ttl = fields.get("System.Title")
                st = fields.get("System.State")
                sv = fields.get("Microsoft.VSTS.Common.Severity","")
                self.bugs_tree.insert("", "end", values=(fid, ttl, st, sv))
                sev_counts[sv] = sev_counts.get(sv, 0) + 1
            total = len(items)
            stats = f"Total: {total} | " + " | ".join([f"{k}:{v}" for k,v in sev_counts.items()])
            self.stats_label.config(text=stats)
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def _parse_azure_url(self, url):
        try:
            # Example: https://dev.azure.com/{org}/{project}/_boards/...
            if not url:
                return "", ""
            u = url.strip()
            if not u.startswith("http"):
                return "", ""
            parts = u.split("/")
            # ['https:', '', 'dev.azure.com', '{org}', '{project}', '_boards', ...]
            if len(parts) >= 6 and parts[2] == "dev.azure.com":
                org = parts[3]
                proj_enc = parts[4]
                try:
                    proj = urllib.parse.unquote(proj_enc)
                except Exception:
                    proj = proj_enc
                base = f"https://dev.azure.com/{org}"
                return base, proj
        except Exception:
            pass
        return "", ""

def main():
    root = tk.Tk()
    app = DLMSGUI(root)
    root.protocol("WM_DELETE_WINDOW", lambda: (app.disconnect(), root.destroy()))
    root.mainloop()

if __name__ == "__main__":
    main()

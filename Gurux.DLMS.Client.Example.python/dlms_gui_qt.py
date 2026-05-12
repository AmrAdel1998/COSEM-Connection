"""
DLMS GUI — Qt version
Layout is defined in dlms_gui.ui (Qt Designer file).
This module contains only application logic.
"""

RECEIVE_TIMEOUT_MS = 600000

import os
import sys
import time
import json
import threading
import subprocess
import urllib.parse
from pathlib import Path

from PyQt5.QtWidgets import (
    QMainWindow, QApplication, QMessageBox, QFileDialog,
    QTreeWidgetItem, QDialog, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QPlainTextEdit,
    QTabWidget, QCheckBox, QComboBox, QProgressBar,
    QGroupBox, QRadioButton, QDialogButtonBox, QSizePolicy,
    QAbstractItemView,
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QObject, QTimer
from PyQt5.QtGui import QFont, QPixmap
from PyQt5 import uic

try:
    import serial.tools.list_ports
except ImportError:
    serial = None

try:
    import requests
except ImportError:
    requests = None

from gurux_common.enums import TraceLevel
from gurux_common import ReceiveParameters, IGXMediaListener
from gurux_common.io import Parity, StopBits, BaudRate
from gurux_dlms.enums import (
    InterfaceType, Authentication, Security, Standard, DataType, ObjectType,
)
from gurux_dlms import GXDLMSClient
from gurux_dlms.objects import GXDLMSObject
from gurux_dlms.GXByteBuffer import GXByteBuffer
from gurux_serial.GXSerial import GXSerial
from gurux_dlms.GXDLMSConverter import GXDLMSConverter
from gurux_dlms.GXDateTime import GXDateTime

from GXDLMSSecureClient2 import GXDLMSSecureClient2
from GXDLMSReader import GXDLMSReader


# ---------------------------------------------------------------------------
# Port listener (same logic as Tkinter version)
# ---------------------------------------------------------------------------

class _PortListener(IGXMediaListener):
    """Passive listener — logs HDLC frames and detects DM frames."""

    _DM_CONTROL_BYTES = {0x1F, 0x17}

    def __init__(self, gui):
        self._gui = gui
        self._buf = bytearray()

    def onReceived(self, sender, e):
        if e.data is None:
            return
        raw = bytearray(e.data) if not isinstance(e.data, bytearray) else e.data
        self._buf.extend(raw)
        while len(self._buf) >= 2:
            start = self._buf.find(0x7E)
            if start == -1:
                self._buf.clear()
                break
            if start > 0:
                self._buf = self._buf[start:]
            end = self._buf.find(0x7E, 1)
            if end == -1:
                break
            frame = bytes(self._buf[:end + 1])
            self._buf = self._buf[end + 1:]
            hex_str = GXByteBuffer.hex(frame)
            self._gui.append_terminal(f"RX (listener): {hex_str}")
            ctrl = self._extract_control_byte(frame)
            if ctrl in self._DM_CONTROL_BYTES:
                self._gui.on_meter_disconnect_signal.emit()

    @staticmethod
    def _extract_control_byte(frame):
        if len(frame) < 6:
            return None
        i = 3
        while i < len(frame) - 1:
            if frame[i] & 0x01:
                i += 1
                break
            i += 1
        while i < len(frame) - 1:
            if frame[i] & 0x01:
                i += 1
                break
            i += 1
        return frame[i] if i < len(frame) else None

    def onError(self, sender, ex):
        pass

    def onMediaStateChange(self, sender, e):
        pass

    def onTrace(self, sender, e):
        pass

    def onPropertyChanged(self, sender, e):
        pass


# ---------------------------------------------------------------------------
# Worker thread for long operations
# ---------------------------------------------------------------------------

class WorkerSignals(QObject):
    finished = pyqtSignal()
    error = pyqtSignal(str)
    message = pyqtSignal(str)


class ConnectWorker(QThread):
    finished = pyqtSignal()
    error = pyqtSignal(str)
    message = pyqtSignal(str)

    def __init__(self, fn):
        super().__init__()
        self._fn = fn

    def run(self):
        try:
            self._fn()
            self.finished.emit()
        except Exception as ex:
            self.error.emit(str(ex))


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------

class DLMSGUI(QMainWindow):
    on_meter_disconnect_signal = pyqtSignal()

    def __init__(self):
        super().__init__()
        script_dir = Path(__file__).parent
        ui_path = script_dir / "dlms_gui.ui"
        # Check if file exists
        if not ui_path.exists():
            raise FileNotFoundError(f"UI file not found: {ui_path}")
        
        # Load UI from .ui file
        uic.loadUi(str(ui_path), self)

        self.client = None
        self.reader = None
        self.media = None
        self._port_listener = None
        self.log_path = "logFile.txt"
        self.test_files = []

        # Association view cache
        self.association_cache_file = Path(__file__).parent / "association_cache.json"
        self.cached_objects = []

        # Keep-alive attributes
        self.keep_alive_enabled = False
        self.keep_alive_interval_seconds = 30
        self.last_communication_time = 0
        self.keep_alive_check_timer = None
        self.keep_alive_lock = threading.Lock()

        # Runtime helpers (same maps as Tkinter version)
        self._build_helpers()

        # Wire up signals
        self._connect_signals()

        # Setup keep-alive
        self._setup_keep_alive()

        # Populate COM ports
        self.refresh_ports()

        # Set initial combobox values to defaults
        self._set_defaults()

        # Load cached association view if available
        self.load_association_cache()

        # Status bar
        self.mainStatusBar.showMessage("Ready")

    # ------------------------------------------------------------------
    # Signal wiring
    # ------------------------------------------------------------------

    def _connect_signals(self):
        self.btnConnect.clicked.connect(self.connect_meter)
        self.btnDisconnect.clicked.connect(self.disconnect_meter)
        self.btnRefreshPorts.clicked.connect(self.refresh_ports)
        self.btnSaveAssocView.clicked.connect(self.save_assoc_view)
        self._connect_tasks_signals()

        # Keep-alive connections
        if hasattr(self, 'chkKeepAlive'):
            self.chkKeepAlive.toggled.connect(self.toggle_keep_alive)
        if hasattr(self, 'spinKeepAliveInterval'):
            self.spinKeepAliveInterval.valueChanged.connect(self.set_keep_alive_interval)

        self.btnRefreshOBIS.clicked.connect(self.refresh_obis)
        self.btnSelectObject.clicked.connect(self.select_obis_object)
        self.obisTree.itemDoubleClicked.connect(self._on_obis_double_click)
        self.attrsTree.itemSelectionChanged.connect(self._on_attr_select)
        self.attrsTree.itemDoubleClicked.connect(lambda: self.read_selected_attr())
        self.methodsTree.itemSelectionChanged.connect(self._on_method_select)

        self.btnReadSelected.clicked.connect(self.read_selected_attr)
        self.btnWriteSelected.clicked.connect(self.write_selected_attr)
        self.btnAdvancedEditor.clicked.connect(self.open_advanced_editor)
        self.btnRunMethod.clicked.connect(self.run_selected_method)

        self.btnSendRaw.clicked.connect(self.send_raw_frame)

        self.radioPDUHex.toggled.connect(self._on_pdu_mode_change)
        self.btnBuildFrame.clicked.connect(self._build_custom_frame_preview)
        self.btnSendPDU.clicked.connect(self._send_custom_pdu_frame)

        self.btnAddTestFile.clicked.connect(self.add_test_file)
        self.btnClearTestFiles.clicked.connect(self.clear_test_files)
        self.btnCollectTests.clicked.connect(self.collect_tests)
        self.btnRunSelected.clicked.connect(self.run_selected_tests)
        self.btnRunAll.clicked.connect(self.run_all_tests)

        self.btnCreateBug.clicked.connect(self.create_bug)
        self.btnFetchBugs.clicked.connect(self.fetch_bugs)

        self.btnClearTerminal.clicked.connect(self.terminal.clear)

        self.on_meter_disconnect_signal.connect(self._on_meter_disconnect)

    # ------------------------------------------------------------------
    # Defaults
    # ------------------------------------------------------------------

    def _set_defaults(self):
        self.cmbAuth.setCurrentText("HIGH_GMAC")
        self.cmbSecurity.setCurrentText("AUTHENTICATION_ENCRYPTION")
        self.cmbStandard.setCurrentText("ITALY")
        self.btnWriteSelected.setEnabled(False)
        self.btnRunMethod.setEnabled(False)

    # ------------------------------------------------------------------
    # Association View Caching
    # ------------------------------------------------------------------

    def save_association_cache(self):
        """Save the current association view to a JSON cache file"""
        if not self.client or not self.client.objects:
            self._trace("No objects to cache")
            return False
        
        try:
            cache_data = []
            for obj in self.client.objects:
                obj_data = {
                    "logical_name": (obj.logicalName or "").strip(),
                    "object_type": self._type_name(obj.objectType),
                    "object_type_code": int(obj.objectType),
                    "description": getattr(obj, "description", ""),
                    "attributes": []
                }
                
                # Save attribute information
                try:
                    count = obj.getAttributeCount()
                except Exception:
                    count = self._attr_count_map.get(obj_data["object_type"], 20)
                
                for i in range(1, count + 1):
                    try:
                        access_str = self._access_str(obj.getAccess3(i))
                        if access_str != "NO_ACCESS":
                            attr_data = {
                                "index": i,
                                "name": self._get_attribute_names(obj).get(i, f"Attribute {i}"),
                                "access": access_str,
                                "data_type": ""
                            }
                            try:
                                dt = obj.getUIDataType(i) if hasattr(obj, "getUIDataType") else obj.getDataType(i)
                                attr_data["data_type"] = self._dtype_name(dt)
                            except Exception:
                                pass
                            obj_data["attributes"].append(attr_data)
                    except Exception:
                        pass
                
                # Save method information
                obj_data["methods"] = []
                try:
                    mcount = obj.getMethodCount()
                except Exception:
                    mcount = 10
                
                for i in range(1, mcount + 1):
                    try:
                        method_access = obj.getMethodAccess3(i)
                        if method_access == 1:  # Access allowed
                            method_data = {
                                "index": i,
                                "name": self._get_method_names(obj).get(i, f"Method {i}"),
                                "access": "Access"
                            }
                            obj_data["methods"].append(method_data)
                    except Exception:
                        pass
                
                cache_data.append(obj_data)
            
            # Save to file
            with open(self.association_cache_file, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, indent=2, ensure_ascii=False)
            
            self._trace(f"Association view cached to {self.association_cache_file}")
            return True
        except Exception as e:
            self._trace(f"Failed to save association cache: {e}")
            return False

    def load_association_cache(self):
        """Load cached association view from JSON file"""
        if not self.association_cache_file.exists():
            return False
        
        try:
            with open(self.association_cache_file, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)
            
            self.cached_objects = cache_data
            self._trace(f"Loaded {len(cache_data)} objects from cached association view")
            
            # Display cached data in OBIS tree
            self._display_cached_association()
            return True
        except Exception as e:
            self._trace(f"Failed to load association cache: {e}")
            return False

    def _display_cached_association(self):
        """Display cached association data in the OBIS tree"""
        if not self.cached_objects:
            return
        
        self.obisTree.clear()
        parents = {}
        
        for obj in self.cached_objects:
            ln = obj["logical_name"]
            t = obj["object_type"]
            nm = obj.get("description", t)
            
            if t not in parents:
                parent_item = QTreeWidgetItem(self.obisTree, ["", t, ""])
                parents[t] = parent_item
            
            child = QTreeWidgetItem(parents[t], [ln, nm, t])
            child.setData(0, Qt.UserRole, ln)
            
            # Store cached attributes and methods for quick access
            child.setData(1, Qt.UserRole, obj.get("attributes", []))
            child.setData(2, Qt.UserRole, obj.get("methods", []))
        
        self.obisTree.expandAll()
        self._trace("Cached association view displayed (offline mode)")

    def _populate_from_cache(self, ln):
        """Populate attributes and methods from cache for a given logical name"""
        for obj in self.cached_objects:
            if obj["logical_name"] == ln:
                # Display type description
                tname = obj["object_type"]
                desc = self._type_desc_map.get(tname, "")
                self.lblTypeDescValue.setText(desc)
                
                # Populate attributes from cache
                self.attrsTree.clear()
                for attr in obj.get("attributes", []):
                    item = QTreeWidgetItem([
                        str(attr["index"]),
                        attr["name"],
                        attr["access"],
                        attr.get("data_type", ""),
                        ""  # Value will be empty in cached mode
                    ])
                    self.attrsTree.addTopLevelItem(item)
                
                # Populate methods from cache
                self.methodsTree.clear()
                for method in obj.get("methods", []):
                    QTreeWidgetItem(self.methodsTree, [
                        str(method["index"]),
                        method["name"],
                        method["access"]
                    ])
                
                return True
        return False

    # ------------------------------------------------------------------
    # Keep-alive methods
    # ------------------------------------------------------------------

    def _setup_keep_alive(self):
        """Initialize keep-alive mechanism"""
        self.keep_alive_check_timer = QTimer()
        self.keep_alive_check_timer.timeout.connect(self._check_keep_alive_needed)
        self.keep_alive_check_timer.start(5000)  # Check every 5 seconds

    def update_last_communication(self):
        """Update the timestamp of the last communication"""
        self.last_communication_time = time.time()

    def toggle_keep_alive(self, enabled):
        """Enable or disable keep-alive mechanism"""
        self.keep_alive_enabled = enabled
        if enabled:
            self._trace(f"Keep-alive enabled (interval: {self.keep_alive_interval_seconds} seconds)")
            if self.reader and self.client:
                self.update_last_communication()
        else:
            self._trace("Keep-alive disabled")

    def set_keep_alive_interval(self, seconds):
        """Change the keep-alive interval"""
        self.keep_alive_interval_seconds = seconds
        if self.keep_alive_enabled:
            self._trace(f"Keep-alive interval updated to {seconds} seconds")

    def _check_keep_alive_needed(self):
        """Check if keep-alive is needed based on last communication time"""
        if not self.keep_alive_enabled or not self.reader or not self.client:
            return

        if self.last_communication_time == 0:
            return

        time_since_last = time.time() - self.last_communication_time
        if time_since_last >= self.keep_alive_interval_seconds:
            self._send_keep_alive()

    def _send_keep_alive(self):
        """Send keep-alive request - read attribute 1 of OBIS 0.0.40.0.0.255 (Association LN)"""
        with self.keep_alive_lock:
            # Don't send if another keep-alive is in progress or recent activity
            if time.time() - self.last_communication_time < self.keep_alive_interval_seconds:
                return

            try:
                self._trace("[Keep-Alive] Sending keep-alive request (0.0.40.0.0.255 attr 1)...")
                
                # Find the association object
                assoc_obj = None
                for obj in self.client.objects:
                    if obj.logicalName and obj.logicalName.strip() == "0.0.40.0.0.255":
                        assoc_obj = obj
                        break
                
                if assoc_obj:
                    # Read attribute 1 (logical name) - lightweight keep-alive
                    self.reader.read(assoc_obj, 1)
                    self.update_last_communication()
                    self._trace("[Keep-Alive] Keep-alive sent successfully")
                else:
                    self._trace("[Keep-Alive] Association object 0.0.40.0.0.255 not found")
                    
            except Exception as e:
                self._trace(f"[Keep-Alive] Failed: {e}")

    # ------------------------------------------------------------------
    # Terminal helpers
    # ------------------------------------------------------------------

    def append_terminal(self, text: str):
        """Thread-safe terminal append."""
        QTimer.singleShot(0, lambda: self._do_append(text))

    def _do_append(self, text: str):
        self.terminal.appendPlainText(text)
        sb = self.terminal.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _trace(self, text: str):
        self.append_terminal(text)

    # ------------------------------------------------------------------
    # Port management
    # ------------------------------------------------------------------

    def refresh_ports(self):
        current = self.cmbPort.currentText()
        if serial:
            ports = sorted([p.device for p in serial.tools.list_ports.comports()])
        else:
            ports = []
        self.cmbPort.clear()
        self.cmbPort.addItems(ports)
        if current in ports:
            self.cmbPort.setCurrentText(current)
        elif "COM6" in ports:
            self.cmbPort.setCurrentText("COM6")

    # ------------------------------------------------------------------
    # Connect / disconnect
    # ------------------------------------------------------------------

    def connect_meter(self):
        try:
            self.disconnect_meter()
            client = GXDLMSSecureClient2(True)
            client.interfaceType = InterfaceType.HDLC_WITH_MODE_E
            client.useLogicalNameReferencing = True
            client.clientAddress = self.spinClient.value()
            server = GXDLMSClient.getServerAddress(
                self.spinLogical.value(), self.spinPhysical.value()
            )
            client.serverAddress = server
            client.authentication = getattr(Authentication, self.cmbAuth.currentText())
            client.ciphering.security = getattr(Security, self.cmbSecurity.currentText())

            st_val = self.editSysTitle.text().strip()
            try:
                client.ciphering.systemTitle = GXByteBuffer.hexToBytes(st_val)
            except Exception:
                client.ciphering.systemTitle = st_val.encode()

            client.ciphering.blockCipherKey = GXByteBuffer.hexToBytes(
                self.editBlockKey.text().strip()
            )
            client.ciphering.authenticationKey = GXByteBuffer.hexToBytes(
                self.editAuthKey.text().strip()
            )
            client.standard = getattr(Standard, self.cmbStandard.currentText())
            client.useUtc2NormalTime = True

            media = GXSerial(None)
            media.port = self.cmbPort.currentText()
            media.baudRate = BaudRate.BAUD_RATE_300
            media.dataBits = 7
            media.parity = Parity.EVEN
            media.stopBits = StopBits.ONE

            reader = GXDLMSReader(
                client, media, TraceLevel.VERBOSE,
                "0.0.43.1.0.255", trace_callback=self._trace,
            )

            self.client = client
            self.reader = reader
            self.media = media
            self.media.open()
            self._port_listener = _PortListener(self)
            self.media.addListener(self._port_listener)

            # Run in a thread so the UI doesn't freeze
            self._worker = ConnectWorker(self.reader.initializeConnection)
            self._worker.finished.connect(self._on_connect_success)
            self._worker.error.connect(self._on_connect_error)
            self._worker.start()

        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def _on_connect_success(self):
        """Handle successful connection"""
        self._trace("Connected")
        self.mainStatusBar.showMessage("Connected")
        self.update_last_communication()
        
        # Save association view to cache after successful connection
        self.save_association_cache()

    def _on_connect_error(self, msg: str):
        QMessageBox.critical(self, "Connection Error", msg)
        self.disconnect_meter()

    def disconnect_meter(self):
        try:
            if self._port_listener and self.media:
                try:
                    self.media.removeListener(self._port_listener)
                except Exception:
                    pass
            self._port_listener = None
            if self.reader:
                self.reader.close()
            if self.media and self.media.isOpen():
                self.media.close()
        except Exception:
            pass
        self.reader = None
        self.client = None
        self.media = None
        self.terminal.clear()
        self.attrsTree.clear()
        self.methodsTree.clear()
        self.mainStatusBar.showMessage("Disconnected")

    def _on_meter_disconnect(self):
        self._trace("Meter sent Disconnected Mode (DM) frame — ending session.")
        self.disconnect_meter()

    # ------------------------------------------------------------------
    # OBIS
    # ------------------------------------------------------------------

    def refresh_obis(self):
        if not self.reader:
            QMessageBox.warning(self, "Error", "Not connected")
            return
        try:
            self.reader.getAssociationView()
            conv = GXDLMSConverter(self.client.standard)
            for it in self.client.objects:
                try:
                    conv.updateOBISCodeInformation(it)
                except Exception:
                    pass
            self.obisTree.clear()
            parents = {}
            for obj in self.client.objects:
                ln = (obj.logicalName or "").strip()
                t = self._type_name(obj.objectType)
                nm = self._obis_name(obj, ln, t)
                if t not in parents:
                    parent_item = QTreeWidgetItem(self.obisTree, ["", t, ""])
                    parents[t] = parent_item
                child = QTreeWidgetItem(parents[t], [ln, nm, t])
                child.setData(0, Qt.UserRole, ln)
            self.obisTree.expandAll()
            
            # Save to cache after successful refresh
            self.save_association_cache()
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def select_obis_object(self):
        sel = self.obisTree.selectedItems()
        if not sel:
            return
        ln = sel[0].data(0, Qt.UserRole) or sel[0].text(0)
        if ln:
            self.editSelOBIS.setText(ln)
            self._populate_rights(ln)

    def _on_obis_double_click(self, item, col):
        ln = item.data(0, Qt.UserRole) or item.text(0)
        if ln:
            self.editSelOBIS.setText(ln)
            self._populate_rights(ln)

    def _find_obj(self, ln):
        target = ln.strip()
        if not self.client:
            return None
        for obj in self.client.objects:
            if (obj.logicalName or "").strip() == target:
                return obj
        return None

    def _populate_rights(self, ln):
        try:
            # Try to get from live connection first
            obj = self._find_obj(ln)
            
            if obj:
                # Live mode - use actual object
                tname = self._type_name(obj.objectType)
                desc = self._type_desc_map.get(tname, "")
                self.lblTypeDescValue.setText(desc)

                self.attrsTree.clear()
                names = self._get_attribute_names(obj)
                try:
                    count = obj.getAttributeCount()
                except Exception:
                    count = self._attr_count_map.get(tname, 20)

                for i in range(1, count + 1):
                    try:
                        s = self._access_str(obj.getAccess3(i))
                        nm = names.get(i, f"Attribute {i}")
                        val = ""
                        dtname = ""
                        try:
                            dt = (
                                obj.getUIDataType(i)
                                if hasattr(obj, "getUIDataType")
                                else obj.getDataType(i)
                            )
                            dtname = self._dtype_name(dt)
                        except Exception:
                            pass
                        if s in ("GET", "GET/SET") and self.reader:
                            try:
                                v = self.reader.read(obj, i)
                                val = str(v)
                            except Exception:
                                val = ""
                        if s != "NO_ACCESS":
                            item = QTreeWidgetItem([str(i), nm, s, dtname, val])
                            self.attrsTree.addTopLevelItem(item)
                    except Exception:
                        pass

                self.methodsTree.clear()
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
                            QTreeWidgetItem(self.methodsTree, [str(i), n, s])
                    except Exception:
                        pass
            else:
                # No live connection - try to use cache
                self._trace(f"No live connection, using cached data for {ln}")
                if self._populate_from_cache(ln):
                    self._trace("Using cached data (offline mode)")
                else:
                    self._trace(f"No cached data found for {ln}")
                    
        except Exception as e:
            self._trace(f"Error populating rights: {e}")

    def _on_attr_select(self):
        sel = self.attrsTree.selectedItems()
        if not sel:
            self.btnWriteSelected.setEnabled(False)
            return
        vals = [sel[0].text(c) for c in range(self.attrsTree.columnCount())]
        right = vals[2] if len(vals) > 2 else ""
        self.btnWriteSelected.setEnabled(right in ("SET", "GET/SET"))
        self.editAttrValue.setText(vals[4] if len(vals) > 4 else "")

    def _on_method_select(self):
        sel = self.methodsTree.selectedItems()
        if not sel:
            self.btnRunMethod.setEnabled(False)
            return
        right = sel[0].text(2)
        self.btnRunMethod.setEnabled(right == "Access")

    def read_selected_attr(self):
        try:
            ln = self.editSelOBIS.text()
            obj = self._find_obj(ln)
            if not obj:
                QMessageBox.warning(self, "Error", "Object not found (connect to meter first)")
                return
            sel = self.attrsTree.selectedItems()
            if not sel:
                QMessageBox.information(self, "Info", "Select attribute in table")
                return
            idx = int(sel[0].text(0))
            val = self.reader.read(obj, idx)
            self._trace(f"Read {ln} [{idx}] = {val}")
            sel[0].setText(4, str(val))
            self.editAttrValue.setText(str(val))
            self.update_last_communication()
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def write_selected_attr(self):
        try:
            ln = self.editSelOBIS.text()
            self._trace(f"write_selected_attr: ln={ln}")
            obj = self._find_obj(ln)
            if not obj:
                QMessageBox.warning(self, "Error", "Object not found")
                return
            self._trace(f"write_selected_attr: found obj type {obj.objectType}")
            sel = self.attrsTree.selectedItems()
            if not sel:
                QMessageBox.information(self, "Info", "Select attribute in table")
                return
            idx = int(sel[0].text(0))
            self._trace(f"write_selected_attr: idx={idx}")
            if not self._can_write(obj, idx):
                QMessageBox.critical(
                    self, "Error",
                    f"Access denied: Attr {idx} is not writable (check terminal for details)",
                )
                return
            self._trace(f"write_selected_attr: access check passed")
            
            dt = (
                obj.getUIDataType(idx)
                if hasattr(obj, "getUIDataType")
                else obj.getDataType(idx)
            )
            self._trace(f"write_selected_attr: data type={dt}, int(dt)={int(dt)}")
            s = self.editAttrValue.text().strip()
            self._trace(f"write_selected_attr: input value='{s}'")
            
            # Special handling: if object type is DATA (1) and data type is number type, don't convert to GXDateTime!
            v = None
            try:
                v = int(obj.getObjectType())
            except Exception:
                pass
            
            if v == int(ObjectType.DATA) and idx == 2:
                # For DATA obj idx=2, try to parse as integer/float first!
                try:
                    new_val = int(s)
                    self._trace(f"write_selected_attr: DATA obj, parsed as integer: {new_val}")
                except:
                    try:
                        new_val = float(s)
                        self._trace(f"write_selected_attr: DATA obj, parsed as float: {new_val}")
                    except:
                        # If not number, fall back to normal parsing!
                        if hasattr(dt, "name") and dt.name == "NONE":
                            new_val = self._infer_value_for_none(obj, idx, s)
                        else:
                            new_val = self._parse_value(s, dt)
            else:
                # Normal handling for other object types!
                if hasattr(dt, "name") and dt.name == "NONE":
                    new_val = self._infer_value_for_none(obj, idx, s)
                else:
                    new_val = self._parse_value(s, dt)
            
            self._trace(f"write_selected_attr: parsed value={new_val}, type={type(new_val)}")
            if not self._apply_value(obj, idx, new_val):
                QMessageBox.critical(
                    self, "Error",
                    f"Failed to prepare value for {ln} Attribute {idx}.",
                )
                return
            self._trace(f"write_selected_attr: calling reader.write()...")
            self.reader.write(obj, idx)
            self._trace(f"Wrote {ln} [{idx}] = {new_val}")
            sel[0].setText(4, str(new_val))
            self.update_last_communication()
            QMessageBox.information(self, "Success", f"Attribute {idx} written successfully!")
        except Exception as e:
            self._trace(f"write_selected_attr ERROR: {e}")
            import traceback
            self._trace(traceback.format_exc())
            QMessageBox.critical(self, "Write Error", f"{str(e)}\nCheck terminal for more details!")

    def run_selected_method(self):
        try:
            ln = self.editSelOBIS.text()
            obj = self._find_obj(ln)
            if not obj:
                QMessageBox.warning(self, "Error", "Object not found")
                return
            sel = self.methodsTree.selectedItems()
            if not sel:
                QMessageBox.information(self, "Info", "Select method in table")
                return
            idx = int(sel[0].text(0))
            right = sel[0].text(2)
            if right != "Access":
                QMessageBox.critical(self, "Error", f"Access denied: Method {idx}")
                return
            type_name = self.cmbMethodType.currentText()
            if not type_name or type_name == "NONE":
                dt = DataType.INT8
                val = 0
            else:
                dt = getattr(DataType, type_name)
                val = self._parse_value(self.editMethodValue.text().strip(), dt)
            data = self.client.method(obj, idx, val, dt)
            reply = self.reader.readDLMSPacket(data)
            self._trace(f"Method {ln} [{idx}] executed. Reply: {reply}")
            QMessageBox.information(self, "Success", f"Method executed.\nReply: {reply}")
            self.update_last_communication()
        except Exception as e:
            QMessageBox.critical(self, "Method Error", str(e))

    # ------------------------------------------------------------------
    # Tasks Tab
    # ------------------------------------------------------------------

    def _connect_tasks_signals(self):
        """Connect signals for tasks tab"""
        self.btnAddTask.clicked.connect(self.add_task)
        self.btnEditTask.clicked.connect(self.edit_task)
        self.btnRemoveTask.clicked.connect(self.remove_task)
        self.btnRunTasks.clicked.connect(self.run_tasks)

    def add_task(self):
        """Open dialog to add a new task"""
        dialog = TaskDialog(self, self.client, self.cached_objects)
        if dialog.exec_() == QDialog.Accepted:
            task = dialog.get_task()
            if task:
                self._add_task_to_tree(task)
                self._trace(f"Task added: {task['type']} {task['obis']}")

    def edit_task(self):
        """Edit selected task"""
        selected = self.tasksTree.selectedItems()
        if not selected:
            QMessageBox.information(self, "Info", "Select a task to edit")
            return

        # Get existing task data
        task = {
            'type': selected[0].text(1),
            'obis': selected[0].text(2),
            'index': int(selected[0].text(3)) if selected[0].text(3).isdigit() else 0,
            'data': selected[0].text(4),
            'run': selected[0].checkState(0) == Qt.Checked
        }

        dialog = TaskDialog(self, self.client, self.cached_objects, task)
        if dialog.exec_() == QDialog.Accepted:
            updated_task = dialog.get_task()
            if updated_task:
                self._update_task_in_tree(selected[0], updated_task)
                self._trace(f"Task edited: {updated_task['type']} {updated_task['obis']}")

    def remove_task(self):
        """Remove selected task(s)"""
        selected = self.tasksTree.selectedItems()
        if not selected:
            QMessageBox.information(self, "Info", "Select task(s) to remove")
            return

        reply = QMessageBox.question(self, "Confirm Remove",
                                     f"Remove {len(selected)} task(s)?",
                                     QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            for item in selected:
                self.tasksTree.takeTopLevelItem(self.tasksTree.indexOfTopLevelItem(item))
            self._trace(f"Removed {len(selected)} task(s)")

    def _add_task_to_tree(self, task):
        """Add task to the tree widget"""
        item = QTreeWidgetItem(self.tasksTree)
        # Checkbox column
        item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
        item.setCheckState(0, Qt.Checked if task.get('run', True) else Qt.Unchecked)
        # Other columns
        item.setText(1, task['type'])
        item.setText(2, task['obis'])
        item.setText(3, str(task['index']))
        item.setText(4, task.get('data', ''))
        item.setText(5, '')  # Response - will be filled later
        item.setText(6, 'Pending')  # Status

        # Store full task data as user data
        item.setData(0, Qt.UserRole, task)

    def _update_task_in_tree(self, item, task):
        """Update existing tree item with new task data"""
        item.setCheckState(0, Qt.Checked if task.get('run', True) else Qt.Unchecked)
        item.setText(1, task['type'])
        item.setText(2, task['obis'])
        item.setText(3, str(task['index']))
        item.setText(4, task.get('data', ''))
        item.setData(0, Qt.UserRole, task)

    def run_tasks(self):
        """Execute all checked tasks"""
        if not self.reader:
            QMessageBox.warning(self, "Error", "Not connected to meter")
            return

        # Collect checked tasks
        tasks = []
        for i in range(self.tasksTree.topLevelItemCount()):
            item = self.tasksTree.topLevelItem(i)
            if item.checkState(0) == Qt.Checked:
                task = item.data(0, Qt.UserRole)
                if task:
                    tasks.append((item, task))

        if not tasks:
            QMessageBox.information(self, "Info", "No tasks selected to run")
            return

        self._trace(f"Running {len(tasks)} task(s)...")

        # Check if using WithList mode
        if self.chkListMode.isChecked():
            self._run_tasks_with_list(tasks)
        else:
            self._run_tasks_individual(tasks)

    def _run_tasks_individual(self, tasks):
        """Run tasks individually (one by one)"""
        for item, task in tasks:
            try:
                item.setText(6, "Running...")
                self._trace(f"Executing: {task['type']} {task['obis']} [{task['index']}]")

                # Find the object
                obj = self._find_obj(task['obis'])
                if not obj:
                    raise Exception(f"Object {task['obis']} not found")

                if task['type'] == "GET":
                    val = self.reader.read(obj, task['index'])
                    item.setText(5, str(val))
                    item.setText(6, "Success")
                    self._trace(f"GET result: {val}")

                elif task['type'] == "SET":
                    # Parse data value
                    dt = obj.getDataType(task['index']) if hasattr(obj, 'getDataType') else DataType.OCTET_STRING
                    val = self._parse_value(task.get('data', ''), dt)
                    self._apply_value(obj, task['index'], val)
                    self.reader.write(obj, task['index'])
                    item.setText(5, "OK")
                    item.setText(6, "Success")
                    self._trace(f"SET completed")

                elif task['type'] == "ACTION":
                    # Parse method parameters
                    dt = DataType.INT8
                    val = 0
                    if task.get('data'):
                        val = self._parse_value(task['data'], DataType.INT32)
                    data = self.client.method(obj, task['index'], val, dt)
                    reply = self.reader.readDLMSPacket(data)
                    item.setText(5, str(reply))
                    item.setText(6, "Success")
                    self._trace(f"ACTION result: {reply}")

                self.update_last_communication()

            except Exception as e:
                item.setText(6, f"Error: {str(e)[:50]}")
                self._trace(f"Task failed: {e}")

            # Process UI events
            QApplication.processEvents()

        self._trace("All tasks completed")
        QMessageBox.information(self, "Success", "Task execution completed")

    def _run_tasks_with_list(self, tasks):
        """Run tasks grouped by type using WithList commands"""
        # Group tasks by type
        get_tasks = [(task, item) for item, task in tasks if task['type'] == "GET"]
        set_tasks = [(task, item) for item, task in tasks if task['type'] == "SET"]
        action_tasks = [(task, item) for item, task in tasks if task['type'] == "ACTION"]

        # Process each group in batches of 10 (meter limit)
        if get_tasks:
            self._process_get_with_list(get_tasks)
        if set_tasks:
            self._process_set_with_list(set_tasks)
        if action_tasks:
            self._process_action_with_list(action_tasks)

        self._trace("All batch tasks completed")
        QMessageBox.information(self, "Success", "Batch task execution completed")

    def _process_get_with_list(self, tasks):
        """Process GET tasks using getWithList"""
        batch_size = 10
        for i in range(0, len(tasks), batch_size):
            batch = tasks[i:i+batch_size]
            items = []
            objs = []

            for task, item in batch:
                obj = self._find_obj(task['obis'])
                if obj:
                    items.append((obj, task['index']))
                    objs.append((task, item))
                else:
                    self._trace(f"Object not found: {task['obis']}")
                    item.setText(6, "Error: Object not found")

            if not items:
                continue

            try:
                with self.keep_alive_lock:
                    self._trace(f"Sending getWithList for {len(items)} items...")
                    data = self.client.getWithList(items)
                    reply = self.reader.readDLMSPacket(data)

                    # Parse response - each item gets a corresponding result
                    results = self._parse_get_with_list_response(reply, len(items))

                    for idx, (task, item) in enumerate(objs):
                        if idx < len(results):
                            item.setText(5, str(results[idx]))
                            item.setText(6, "Success")
                        else:
                            item.setText(6, "Error: No response")

                    self.update_last_communication()
            except Exception as e:
                self._trace(f"getWithList failed: {e}")
                for task, item in objs:
                    item.setText(6, f"Error: {str(e)[:50]}")

    def _process_set_with_list(self, tasks):
        """Process SET tasks using setWithList"""
        batch_size = 10
        for i in range(0, len(tasks), batch_size):
            batch = tasks[i:i+batch_size]
            items = []
            objs = []

            for task, item in batch:
                obj = self._find_obj(task['obis'])
                if obj:
                    dt = obj.getDataType(task['index']) if hasattr(obj, 'getDataType') else DataType.OCTET_STRING
                    val = self._parse_value(task.get('data', ''), dt)
                    self._apply_value(obj, task['index'], val)
                    items.append((obj, task['index'], val))
                    objs.append((task, item))
                else:
                    self._trace(f"Object not found: {task['obis']}")
                    item.setText(6, "Error: Object not found")

            if not items:
                continue

            try:
                with self.keep_alive_lock:
                    self._trace(f"Sending setWithList for {len(items)} items...")
                    data = self.client.setWithList(items)
                    self.reader.readDLMSPacket(data)
                    self.update_last_communication()

                    for task, item in objs:
                        item.setText(5, "OK")
                        item.setText(6, "Success")
            except Exception as e:
                self._trace(f"setWithList failed: {e}")
                for task, item in objs:
                    item.setText(6, f"Error: {str(e)[:50]}")

    def _process_action_with_list(self, tasks):
        """Process ACTION tasks using actionWithList"""
        batch_size = 10
        for i in range(0, len(tasks), batch_size):
            batch = tasks[i:i+batch_size]
            items = []
            objs = []

            for task, item in batch:
                obj = self._find_obj(task['obis'])
                if obj:
                    # Parse method parameters
                    val = 0
                    if task.get('data'):
                        try:
                            val = self._parse_value(task['data'], DataType.INT32)
                        except:
                            val = task['data']
                    items.append((obj, task['index'], val))
                    objs.append((task, item))
                else:
                    self._trace(f"Object not found: {task['obis']}")
                    item.setText(6, "Error: Object not found")

            if not items:
                continue

            try:
                with self.keep_alive_lock:
                    self._trace(f"Sending actionWithList for {len(items)} items...")
                    data = self.client.actionWithList(items)
                    reply = self.reader.readDLMSPacket(data)
                    self.update_last_communication()

                    # Parse response
                    results = self._parse_action_with_list_response(reply, len(items))

                    for idx, (task, item) in enumerate(objs):
                        if idx < len(results):
                            item.setText(5, str(results[idx]))
                            item.setText(6, "Success")
                        else:
                            item.setText(6, "Success")
            except Exception as e:
                self._trace(f"actionWithList failed: {e}")
                for task, item in objs:
                    item.setText(6, f"Error: {str(e)[:50]}")

    def _parse_get_with_list_response(self, reply, expected_count):
        """Parse getWithList response into individual results"""
        results = []
        try:
            # This depends on how your GXDLMSReader returns data
            if hasattr(reply, 'value'):
                reply_data = reply.value
            else:
                reply_data = reply

            if isinstance(reply_data, (list, tuple)):
                results = list(reply_data)
            else:
                results = [reply_data]
        except Exception as e:
            self._trace(f"Failed to parse getWithList response: {e}")
            results = [None] * expected_count

        # Ensure we have expected number of results
        while len(results) < expected_count:
            results.append(None)
        return results[:expected_count]

    def _parse_action_with_list_response(self, reply, expected_count):
        """Parse actionWithList response into individual results"""
        return self._parse_get_with_list_response(reply, expected_count)


# ---------------------------------------------------------------------------
# Task Dialog for adding/editing tasks
# ---------------------------------------------------------------------------

    def save_assoc_view(self):
        """Save association view to JSON file"""
        if self.client and self.client.objects:
            if self.save_association_cache():
                QMessageBox.information(self, "Success", f"Association view saved to:\n{self.association_cache_file}")
            else:
                QMessageBox.warning(self, "Error", "Failed to save association view")
        else:
            # Try to save cached data instead
            if self.cached_objects:
                try:
                    with open(self.association_cache_file, 'w', encoding='utf-8') as f:
                        json.dump(self.cached_objects, f, indent=2, ensure_ascii=False)
                    QMessageBox.information(self, "Success", f"Cached association view saved to:\n{self.association_cache_file}")
                except Exception as e:
                    QMessageBox.critical(self, "Error", str(e))
            else:
                QMessageBox.warning(self, "Error", "No association view available to save")

    # ------------------------------------------------------------------
    # Advanced Editor dialog
    # ------------------------------------------------------------------

    def open_advanced_editor(self):
        try:
            ln = self.editSelOBIS.text()
            obj = self._find_obj(ln)
            sel = self.attrsTree.selectedItems()
            if not obj or not sel:
                QMessageBox.information(self, "Info", "Select attribute in table")
                return
            idx = int(sel[0].text(0))
            dlg = AdvancedEditorDialog(self, obj, idx, ln)
            dlg.exec_()
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    # ------------------------------------------------------------------
    # Manual HDLC tab
    # ------------------------------------------------------------------

    def send_raw_frame(self):
        if not self.media or not self.media.isOpen():
            QMessageBox.warning(self, "Error", "Not connected")
            return
        content = self.txText.toPlainText().strip()
        if not content:
            return
        try:
            clean_hex = "".join(content.split())
            data = GXByteBuffer.hexToBytes(clean_hex)
            p = ReceiveParameters()
            p.waitTime = RECEIVE_TIMEOUT_MS
            if self.client and self.client.interfaceType == InterfaceType.WRAPPER:
                p.eop = None
                p.count = 8
            else:
                p.eop = 0x7E
            with self.media.getSynchronous():
                self.media.send(data)
                self.rxText.setPlainText("Sending…")
                full_reply = bytearray()
                while True:
                    if not self.media.receive(p):
                        break
                    full_reply.extend(p.reply)
                    if len(full_reply) > 1 and full_reply[-1] == 0x7E:
                        break
                self.rxText.setPlainText(
                    GXByteBuffer.hex(full_reply)
                    if full_reply
                    else "Timeout: No response received."
                )
                self.update_last_communication()
        except Exception as e:
            self.rxText.setPlainText(f"Error: {e}")

    # ------------------------------------------------------------------
    # Custom PDU tab
    # ------------------------------------------------------------------

    def _on_pdu_mode_change(self):
        from gurux_dlms.GXDLMSTranslator import GXDLMSTranslator
        content = self.pduInput.toPlainText().strip()
        if not content:
            return
        t = GXDLMSTranslator()
        try:
            if self.radioPDUXml.isChecked():
                pdu_bytes = bytearray(
                    GXByteBuffer.hexToBytes("".join(content.split()))
                )
                result = t.pduToXml(pdu_bytes)
                self.grpPDUInput.setTitle("PDU Input (XML)")
            else:
                result = t.xmlToHexPdu(content, addSpace=True)
                self.grpPDUInput.setTitle("PDU Input (Hex)")
            self.pduInput.setPlainText(result)
        except Exception as e:
            QMessageBox.critical(self, "Translation Error", str(e))

    def _assemble_custom_frame(self):
        from gurux_dlms.GXDLMS import GXDLMS
        from gurux_dlms.AesGcmParameter import AesGcmParameter
        from gurux_dlms.GXCiphering import GXCiphering
        from gurux_dlms.enums.Command import Command
        from gurux_dlms.enums.Standard import Standard as Std
        from gurux_dlms.GXDLMSTranslator import GXDLMSTranslator

        content = self.pduInput.toPlainText().strip()
        if not content:
            raise ValueError("PDU input is empty")

        if self.radioPDUXml.isChecked():
            t = GXDLMSTranslator()
            pdu_bytes = bytearray(t.xmlToPdu(content))
        else:
            pdu_bytes = bytearray(
                GXByteBuffer.hexToBytes("".join(content.split()))
            )

        apply_cipher = self.chkApplyCipher.isChecked()
        add_llc = self.chkAddLLC.isChecked()

        if apply_cipher:
            if not self.client:
                raise RuntimeError("Not connected – ciphering requires an active connection")
            cipher = self.client.ciphering
            tag_str = self.cmbCipherTag.currentText()
            if tag_str.startswith("AUTO"):
                glo_tag = GXDLMS.getGloMessage(pdu_bytes[0])
                if glo_tag == 0:
                    glo_tag = Command.GENERAL_GLO_CIPHERING
            else:
                glo_tag = int(tag_str.split()[0], 16)
            ic_str = self.editInvCounter.text().strip()
            ic = cipher.invocationCounter if ic_str.upper() == "AUTO" else int(ic_str, 0)
            s = AesGcmParameter(
                glo_tag,
                cipher.systemTitle,
                cipher.blockCipherKey,
                cipher.authenticationKey,
            )
            s.security = cipher.security
            s.securitySuite = cipher.securitySuite
            s.invocationCounter = ic
            s.ignoreSystemTitle = (self.client.standard == Std.ITALY)
            pdu_bytes = GXCiphering.encrypt(s, pdu_bytes)
            if ic_str.upper() == "AUTO":
                cipher.invocationCounter += 1

        data_buf = GXByteBuffer()
        data_buf.set(pdu_bytes)
        if add_llc and self.client:
            GXDLMS.addLLCBytes(self.client.settings, data_buf)

        ft_str = self.editFrameType.text().strip()
        frame_id = 0 if ft_str.upper() == "AUTO" else int(ft_str, 16)

        frames = []
        if self.client and self.client.interfaceType in (
            InterfaceType.HDLC, InterfaceType.HDLC_WITH_MODE_E
        ):
            first = True
            while data_buf.position < len(data_buf):
                hdlc = GXDLMS.getHdlcFrame(self.client.settings, frame_id, data_buf)
                frames.append(hdlc)
                if first and ft_str.upper() == "AUTO":
                    first = False
                frame_id = self.client.settings.getNextSend(False)
        else:
            frames.append(bytes(data_buf.array()))
        return frames

    def _build_custom_frame_preview(self):
        try:
            frames = self._assemble_custom_frame()
            combined = b"".join(frames)
            self.pduBuiltText.setPlainText(GXByteBuffer.hex(combined))
        except Exception as e:
            QMessageBox.critical(self, "Build Error", str(e))

    def _send_custom_pdu_frame(self):
        if not self.reader:
            QMessageBox.warning(self, "Error", "Not connected")
            return
        try:
            frames = self._assemble_custom_frame()
        except Exception as e:
            QMessageBox.critical(self, "Build Error", str(e))
            return
        combined = b"".join(frames)
        self.pduBuiltText.setPlainText(GXByteBuffer.hex(combined))
        self.pduRxText.setPlainText("Sending…")
        self.btnSendPDU.setEnabled(False)

        def worker():
            try:
                from gurux_dlms import GXReplyData
                p = ReceiveParameters()
                p.eop = 0x7E
                p.allData = True
                p.waitTime = RECEIVE_TIMEOUT_MS
                p.count = 5
                all_rx = bytearray()
                reply = GXReplyData()
                rd = GXByteBuffer()
                for frame in frames:
                    self.media.send(bytearray(frame))
                while not self.client.getData(rd, reply):
                    if not self.media.receive(p):
                        break
                    chunk = bytearray(p.reply) if p.reply else bytearray()
                    all_rx.extend(chunk)
                    rd.set(chunk)
                    p.reply = None
                while reply.isMoreData():
                    rr = self.client.receiverReady(reply)
                    for f in (rr if isinstance(rr, list) else [rr]):
                        self.media.send(bytearray(f))
                    rd.clear()
                    while not self.client.getData(rd, reply):
                        if not self.media.receive(p):
                            break
                        chunk = bytearray(p.reply) if p.reply else bytearray()
                        all_rx.extend(chunk)
                        rd.set(chunk)
                        p.reply = None
                result = GXByteBuffer.hex(all_rx) if all_rx else "Timeout: No response received."
                QTimer.singleShot(0, lambda: self.pduRxText.setPlainText(result))
                QTimer.singleShot(0, lambda: self.update_last_communication())
            except Exception as ex:
                QTimer.singleShot(0, lambda: self.pduRxText.setPlainText(f"Error: {ex}"))
            finally:
                QTimer.singleShot(0, lambda: self.btnSendPDU.setEnabled(True))

        threading.Thread(target=worker, daemon=True).start()

    # ------------------------------------------------------------------
    # Tests tab
    # ------------------------------------------------------------------

    def add_test_file(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Select Test Files", "", "Python (*.py)"
        )
        if not paths:
            return
        self.test_files.extend(paths)
        self._trace(f"Added {len(paths)} file(s)")

    def clear_test_files(self):
        self.test_files = []
        self.testsList.clear()

    def collect_tests(self):
        try:
            self.testsList.clear()
            for p in self.test_files:
                cmd = [sys.executable, "-m", "pytest", "--collect-only", "-q", p]
                res = subprocess.run(cmd, capture_output=True, text=True)
                for line in res.stdout.splitlines():
                    if line and "::" in line and not line.startswith("<"):
                        self.testsList.addItem(line.strip())
            self._trace("Tests collected")
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def _run_pytest(self, nodes):
        try:
            cmd = [sys.executable, "-m", "pytest", "-v", "-s"] + nodes
            res = subprocess.run(cmd, capture_output=True, text=True)
            output = res.stdout or res.stderr
            self.bugText.setPlainText(output)
            self._trace(output)
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def run_selected_tests(self):
        items = self.testsList.selectedItems()
        if not items:
            QMessageBox.information(self, "Info", "Select tests first")
            return
        self._run_pytest([it.text() for it in items])

    def run_all_tests(self):
        nodes = [self.testsList.item(i).text() for i in range(self.testsList.count())]
        if not nodes:
            QMessageBox.information(self, "Info", "No tests collected")
            return
        self._run_pytest(nodes)

    # ------------------------------------------------------------------
    # Bugs tab
    # ------------------------------------------------------------------

    def _parse_azure_url(self, url):
        try:
            u = url.strip()
            if not u.startswith("http"):
                return "", ""
            parts = u.split("/")
            if len(parts) >= 6 and parts[2] == "dev.azure.com":
                org = parts[3]
                proj = urllib.parse.unquote(parts[4])
                base = f"https://dev.azure.com/{org}"
                return base, proj
        except Exception:
            pass
        return "", ""

    def create_bug(self):
        if not requests:
            QMessageBox.critical(self, "Error", "requests not installed")
            return
        full = self.editAzureUrl.text().strip()
        base, proj = self._parse_azure_url(full)
        pat = self.editPAT.text().strip()
        if not base or not proj or not pat:
            QMessageBox.warning(self, "Error", "Set Azure URL and PAT")
            return
        title = "Automated Test Failure"
        desc = self.bugText.toPlainText()
        api = base.rstrip("/") + f"/{proj}/_apis/wit/workitems/$Bug?api-version=7.0"
        payload = [
            {"op": "add", "path": "/fields/System.Title", "value": title},
            {"op": "add", "path": "/fields/System.Description", "value": desc},
            {"op": "add", "path": "/fields/Microsoft.VSTS.Common.Severity", "value": "3 - Medium"},
        ]
        try:
            r = requests.patch(
                api, json=payload,
                headers={"Content-Type": "application/json-patch+json"},
                auth=("", pat),
            )
            if 200 <= r.status_code < 300:
                wi = r.json()
                self._trace(f"Bug created #{wi.get('id')}")
            else:
                QMessageBox.critical(self, "Error", f"{r.status_code}: {r.text}")
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def fetch_bugs(self):
        if not requests:
            QMessageBox.critical(self, "Error", "requests not installed")
            return
        full = self.editAzureUrlMgr.text().strip()
        base, proj = self._parse_azure_url(full)
        pat = self.editPATMgr.text().strip()
        if not base or not proj or not pat:
            QMessageBox.warning(self, "Error", "Set Azure URL and PAT")
            return
        try:
            wiql = {
                "query": (
                    "Select [System.Id], [System.Title], [System.State] "
                    "From WorkItems Where [System.TeamProject] = @project "
                    "And [System.WorkItemType] = 'Bug' "
                    "Order By [System.ChangedDate] Desc"
                )
            }
            wiql_api = base.rstrip("/") + f"/{proj}/_apis/wit/wiql?api-version=7.0"
            auth = ("", pat)
            q = requests.post(wiql_api, json=wiql, auth=auth)
            ids = [it["id"] for it in q.json().get("workItems", [])]
            self.bugsTree.clear()
            if not ids:
                self.statsLabel.setText("No bugs")
                return
            batch_api = base.rstrip("/") + "/_apis/wit/workitemsbatch?api-version=7.0"
            b = requests.post(
                batch_api,
                json={
                    "ids": ids,
                    "fields": [
                        "System.Id", "System.Title", "System.State",
                        "Microsoft.VSTS.Common.Severity",
                    ],
                },
                auth=auth,
            )
            items = b.json().get("value", [])
            order = {"1 - Critical": 0, "2 - High": 1, "3 - Medium": 2, "4 - Low": 3}
            items.sort(key=lambda it: order.get(
                it["fields"].get("Microsoft.VSTS.Common.Severity", ""), 99
            ))
            sev_counts = {}
            for it in items:
                fields = it["fields"]
                sv = fields.get("Microsoft.VSTS.Common.Severity", "")
                QTreeWidgetItem(self.bugsTree, [
                    str(fields.get("System.Id", "")),
                    str(fields.get("System.Title", "")),
                    str(fields.get("System.State", "")),
                    sv,
                ])
                sev_counts[sv] = sev_counts.get(sv, 0) + 1
            stats = f"Total: {len(items)} | " + " | ".join(
                f"{k}:{v}" for k, v in sev_counts.items()
            )
            self.statsLabel.setText(stats)
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    # ------------------------------------------------------------------
    # Helper maps (same as Tkinter version)
    # ------------------------------------------------------------------

    def _build_helpers(self):
        self._access_map = {0: "NO_ACCESS", 1: "GET", 2: "SET", 3: "GET/SET"}
        self._type_map = {
            1: "DATA", 3: "REGISTER", 4: "EXTENDED_REGISTER",
            5: "DEMAND_REGISTER", 7: "PROFILE_GENERIC", 8: "CLOCK",
            9: "SCRIPT_TABLE", 10: "SCHEDULE", 11: "SPECIAL_DAYS_TABLE",
            12: "ASSOCIATION_SHORT_NAME", 15: "ASSOCIATION_LOGICAL_NAME",
            17: "SAP_ASSIGNMENT", 18: "IMAGE_TRANSFER", 20: "ACTIVITY_CALENDAR",
            22: "ACTION_SCHEDULE", 23: "IEC_HDLC_SETUP", 40: "PUSH_SETUP",
            41: "TCP_UDP_SETUP", 42: "IP4_SETUP", 43: "MAC_ADDRESS_SETUP",
            64: "SECURITY_SETUP", 70: "DISCONNECT_CONTROL", 8192: "TARIFF_PLAN",
        }
        self._method_access_map = {0: "NoAccess", 1: "Access"}
        self._attr_count_map = {
            "DATA": 2, "REGISTER": 4, "EXTENDED_REGISTER": 5,
            "DEMAND_REGISTER": 8, "PROFILE_GENERIC": 8, "CLOCK": 9,
            "ASSOCIATION_LOGICAL_NAME": 11, "SECURITY_SETUP": 6,
            "DISCONNECT_CONTROL": 4, "TARIFF_PLAN": 3, "SAP_ASSIGNMENT": 2,
            "IMAGE_TRANSFER": 7, "ACTION_SCHEDULE": 6, "ACTIVITY_CALENDAR": 9,
            "SPECIAL_DAYS_TABLE": 3, "SCRIPT_TABLE": 4, "IEC_HDLC_SETUP": 9,
            "PUSH_SETUP": 7, "TCP_UDP_SETUP": 10, "IP4_SETUP": 8,
            "MAC_ADDRESS_SETUP": 2,
        }
        self._type_desc_map = {
            "DATA": "Generic data holder with single Value",
            "REGISTER": "Scalar/unit numeric value",
            "EXTENDED_REGISTER": "Register with capture time",
            "DEMAND_REGISTER": "Average demand over period",
            "PROFILE_GENERIC": "Cyclic buffer of captured values",
            "CLOCK": "Date/time and DST settings",
            "SCRIPT_TABLE": "Script entries for actions",
            "SCHEDULE": "Time-based script triggers",
            "SPECIAL_DAYS_TABLE": "Overrides for specific dates",
            "ASSOCIATION_LOGICAL_NAME": "Association and user/security context",
            "SAP_ASSIGNMENT": "Service access points list",
            "IMAGE_TRANSFER": "Firmware image transfer",
            "ACTIVITY_CALENDAR": "Season and tariff switching",
            "ACTION_SCHEDULE": "Method invocation schedule",
            "IEC_HDLC_SETUP": "HDLC link layer parameters",
            "PUSH_SETUP": "Automatic push configuration",
            "TCP_UDP_SETUP": "Transport parameters",
            "IP4_SETUP": "IPv4 network configuration",
            "MAC_ADDRESS_SETUP": "MAC address",
            "SECURITY_SETUP": "Security policy and keys",
            "DISCONNECT_CONTROL": "Remote connect/disconnect",
            "TARIFF_PLAN": "Tariff plan definitions",
        }
        self._attr_name_map = {
            "CLOCK": {
                1: "Logical name", 2: "Time", 3: "Time zone", 4: "Status",
                5: "DST begin", 6: "DST end", 7: "DST deviation",
                8: "DST enabled", 9: "Clock base",
            },
            "DATA": {1: "Logical name", 2: "Value"},
            "REGISTER": {1: "Logical name", 2: "Value", 3: "Scaler unit", 4: "Status"},
            "EXTENDED_REGISTER": {
                1: "Logical name", 2: "Value", 3: "Scaler unit",
                4: "Status", 5: "Capture time",
            },
            "DEMAND_REGISTER": {
                1: "Logical name", 2: "Current average value",
                3: "Last average value", 4: "Scaler unit",
                5: "Period", 6: "Number of periods",
                7: "Max demand", 8: "Max demand time",
            },
            "PROFILE_GENERIC": {
                1: "Logical name", 2: "Buffer", 3: "Capture objects",
                4: "Capture period", 5: "Sort method",
                6: "Sort object", 7: "Entries in use", 8: "Profile entries",
            },
            "SECURITY_SETUP": {
                1: "Logical name", 2: "Security policy", 3: "Security suite",
                4: "Client system title", 5: "Server system title", 6: "Certificates",
            },
            "DISCONNECT_CONTROL": {
                1: "Logical name", 2: "Output state",
                3: "Control mode", 4: "Default mode",
            },
            "TARIFF_PLAN": {1: "Logical name", 2: "Active plan", 3: "Passive plan"},
            "ASSOCIATION_LOGICAL_NAME": {
                1: "Logical name", 2: "Object list",
                3: "Associated partners ID", 4: "Application context name",
                5: "xDLMS context info", 6: "Authentication mechanism name",
                7: "User name", 8: "Association status",
                9: "Security setup reference", 10: "User list", 11: "Current user",
            },
        }
        self._method_name_map = {
            "CLOCK": {
                1: "Adjust to quarter", 2: "Adjust to measure unit",
                3: "Adjust to minute", 4: "Adjust to preset time",
                5: "Preset adjusting time", 6: "Shift time",
            },
            "PROFILE_GENERIC": {1: "Capture", 2: "Clear"},
            "DISCONNECT_CONTROL": {1: "Remote disconnect", 2: "Remote reconnect"},
            "SECURITY_SETUP": {1: "Update key", 2: "Activate key"},
            "DEMAND_REGISTER": {1: "Reset"},
            "TARIFF_PLAN": {1: "Activate", 2: "Deactivate"},
        }

    # ------------------------------------------------------------------
    # Utility helpers (same logic as Tkinter version)
    # ------------------------------------------------------------------

    def _type_name(self, ot):
        try:
            if hasattr(ot, "name"):
                return ot.name
            return self._type_map.get(int(ot), str(ot))
        except Exception:
            return str(ot)

    def _dtype_name(self, dt):
        try:
            if hasattr(dt, "name"):
                return dt.name
            v = int(dt)
            for k in ["ARRAY", "BCD", "BITSTRING", "BOOLEAN", "COMPACT_ARRAY",
                       "DATE", "DATETIME", "ENUM", "FLOAT32", "FLOAT64",
                       "INT16", "INT32", "INT64", "INT8", "NONE",
                       "OCTET_STRING", "STRING", "STRING_UTF8", "STRUCTURE",
                       "TIME", "UINT16", "UINT32", "UINT64", "UINT8"]:
                try:
                    if v == int(getattr(DataType, k)):
                        return k
                except Exception:
                    continue
            return str(v)
        except Exception:
            return str(dt)

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

    def _can_read(self, obj, idx):
        try:
            s = self._access_str(obj.getAccess3(idx))
            tname = self._type_name(obj.objectType)
            count = self._attr_count_map.get(tname, 20)
            if idx < 1 or idx > count:
                return False
            return s in ("GET", "GET/SET")
        except Exception:
            return True

    def _can_write(self, obj, idx):
        try:
            s = None
            try:
                access_val = obj.getAccess(idx)
                s = self._access_str(access_val)
                self._trace(f"_can_write getAccess({idx}) returned {access_val} -> {s}")
            except:
                try:
                    access_val = obj.getAccess3(idx)
                    s = self._access_str(access_val)
                    self._trace(f"_can_write getAccess3({idx}) returned {access_val} -> {s}")
                except Exception as e2:
                    self._trace(f"_can_write both getAccess/getAccess3 failed for idx {idx}: {e2}")
                    # Fallback to check attributes collection
                    att = obj.attributes.find(idx)
                    if att:
                        s = self._access_str(att.access)
                        self._trace(f"_can_write using attributes.find({idx}) -> {s}")
            if not s:
                self._trace(f"_can_write could not determine access mode for idx {idx}, defaulting to allow")
                return True
            
            tname = self._type_name(obj.objectType)
            count = self._attr_count_map.get(tname, 20)
            if idx < 1 or idx > count:
                self._trace(f"_can_write idx {idx} out of range (1-{count}) for {tname}")
                return False
            
            result = s in ("SET", "GET/SET")
            self._trace(f"_can_write idx {idx} access {s} -> {result}")
            return result
        except Exception as e:
            self._trace(f"_can_write exception: {e}")
            # Don't block write if access check fails
            return True

    def _get_attribute_names(self, obj):
        names = {}
        try:
            if hasattr(obj, "getNames"):
                for i, nm in enumerate(obj.getNames(), start=1):
                    names[i] = str(nm)
        except Exception:
            pass
        names.setdefault(1, "Logical name")
        try:
            tname = self._type_name(obj.objectType)
            for k, v in self._attr_name_map.get(tname, {}).items():
                names.setdefault(k, v)
        except Exception:
            pass
        return names

    def _get_method_names(self, obj):
        names = {}
        try:
            if hasattr(obj, "getMethodNames"):
                for i, nm in enumerate(obj.getMethodNames(), start=1):
                    names[i] = str(nm)
        except Exception:
            pass
        try:
            tname = self._type_name(obj.objectType)
            for k, v in self._method_name_map.get(tname, {}).items():
                names.setdefault(k, v)
        except Exception:
            pass
        return names

    def _obis_name(self, obj, ln, tname):
        try:
            d = str(getattr(obj, "description", None) or "")
            if d:
                return d
            n = str(getattr(obj, "name", None) or "")
            if n and n != ln:
                return n
        except Exception:
            pass
        return tname

    def _parse_value(self, s, dt):
        self._trace(f"_parse_value called for s='{s}', dt={dt}, int(dt)={int(dt)}")
        if dt == DataType.NONE:
            raise ValueError("Unknown data type")
        t = int(dt)
        if s.startswith("[") and s.endswith("]"):
            items = [x.strip() for x in s[1:-1].split(",") if x.strip()]
            try:
                ints = [int(x) for x in items]
                result = bytearray(ints) if t == int(DataType.OCTET_STRING) else ints
                self._trace(f"_parse_value: parsed list/bytes: {result}")
                return result
            except Exception:
                self._trace(f"_parse_value: parsed string list: {items}")
                return items
        if t in (int(DataType.INT8), int(DataType.INT16), int(DataType.INT32),
                 int(DataType.INT64), int(DataType.UINT8), int(DataType.UINT16),
                 int(DataType.UINT32), int(DataType.UINT64),
                 int(DataType.ENUM), int(DataType.BCD)):
            s = s.strip()
            result = int(s, 16) if s.lower().startswith("0x") else int(s)
            self._trace(f"_parse_value: parsed integer: {result}")
            return result
        if t in (int(DataType.DATETIME), int(DataType.DATE), int(DataType.TIME)):
            kind = {
                int(DataType.DATE): "date",
                int(DataType.TIME): "time",
            }.get(t, "datetime")
            result = self._to_gx_datetime(s, kind)
            self._trace(f"_parse_value: parsed datetime: {result}")
            return result
        if t == int(DataType.BOOLEAN):
            if s.lower() in ("true", "1", "yes", "on"):
                self._trace(f"_parse_value: parsed boolean: True")
                return True
            if s.lower() in ("false", "0", "no", "off"):
                self._trace(f"_parse_value: parsed boolean: False")
                return False
            raise ValueError("Expected boolean (true/false)")
        if t == int(DataType.OCTET_STRING):
            result = GXByteBuffer.hexToBytes(s)
            self._trace(f"_parse_value: parsed octet string: {result}")
            return result
        self._trace(f"_parse_value: returning string: {s}")
        return s

    def _to_gx_datetime(self, text, kind):
        text = text.strip()
        self._trace(f"_to_gx_datetime called with text='{text}', kind={kind}")
        if not text:
            raise ValueError("Empty date/time")
        
        # Try parsing as Unix timestamp first (integer or float)
        try:
            ts = float(text)
            import datetime
            dt_obj = datetime.datetime.fromtimestamp(ts, datetime.timezone.utc)
            formatted = dt_obj.strftime("%Y-%m-%d %H:%M:%S")
            self._trace(f"_to_gx_datetime: parsed as Unix timestamp {ts} -> {formatted}")
            return GXDateTime(formatted, "%Y-%m-%d %H:%M:%S")
        except Exception as e:
            self._trace(f"_to_gx_datetime: unix timestamp parse failed: {e}")
        
        patterns = {
            "datetime": ["%Y-%m-%d %H:%M:%S", "%m/%d/%Y %H:%M:%S", "%Y%m%d%H%M%S"],
            "date": ["%Y-%m-%d", "%m/%d/%Y", "%Y%m%d"],
            "time": ["%H:%M:%S", "%H%M%S"],
        }.get(kind, ["%Y-%m-%d %H:%M:%S", "%m/%d/%Y %H:%M:%S", "%Y%m%d%H%M%S"])
        self._trace(f"_to_gx_datetime: trying patterns: {patterns}")
        for p in patterns:
            try:
                result = GXDateTime(text, p)
                self._trace(f"_to_gx_datetime: succeeded with pattern '{p}'")
                return result
            except Exception as e:
                self._trace(f"_to_gx_datetime: pattern '{p}' failed: {e}")
                continue
        raise ValueError(f"Unsupported {kind} format: {text}")

    def _infer_value_for_none(self, obj, idx, s):
        self._trace(f"_infer_value_for_none called for idx={idx}, s='{s}'")
        # Try to get current value from obj's value property first
        cur = None
        try:
            if idx == 2 and hasattr(obj, "value"):
                cur = obj.value
                self._trace(f"_infer_value_for_none: found existing value from value property: {cur}, type: {type(cur)}")
        except Exception as e:
            self._trace(f"_infer_value_for_none: value property failed: {e}")
        
        # If we have current value, infer type from that
        if cur is not None:
            try:
                if isinstance(cur, (bytes, bytearray)):
                    return GXByteBuffer.hexToBytes(s) if s else cur
                if isinstance(cur, bool):
                    return s.lower() in ("true", "1", "yes", "on")
                if isinstance(cur, int):
                    return int(s)
                if isinstance(cur, float):
                    return float(s)
                if isinstance(cur, GXDateTime):
                    return self._to_gx_datetime(s, "datetime")
                return s
            except Exception as e:
                self._trace(f"_infer_value_for_none: infer from existing failed: {e}")
        
        # Fallback to previous heuristics if no cur
        try:
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
        return s

    def _apply_value(self, obj, idx, val):
        self._trace(f"_apply_value called for obj type={obj.objectType}, idx={idx}, val={val}, type(val)={type(val)}")
        try:
            v = None
            try:
                v = int(obj.getObjectType())
            except Exception:
                pass
            
            # First, check for specific object types that have known properties!
            # ------------------------------
            # ObjectType.PUSH_SETUP (40)
            if v == int(ObjectType.PUSH_SETUP):
                self._trace(f"_apply_value: handling Push Setup (type 40)")
                if idx == 2:
                    if hasattr(obj, "pushObjectList"):
                        obj.pushObjectList = val
                        return True
                elif idx == 3:
                    if hasattr(obj, "sendDestinationAndMethod"):
                        obj.sendDestinationAndMethod = val
                        return True
                elif idx == 4:
                    if hasattr(obj, "communicationWindow"):
                        obj.communicationWindow = val
                        return True
                elif idx == 5:
                    if hasattr(obj, "randomisationStartInterval"):
                        obj.randomisationStartInterval = val
                        self._trace(f"_apply_value: set randomisationStartInterval to {val}")
                        return True
                elif idx == 6:
                    if hasattr(obj, "numberOfRetries"):
                        obj.numberOfRetries = val
                        return True
                elif idx == 7:
                    if hasattr(obj, "repetitionDelay"):
                        obj.repetitionDelay = val
                        return True
            # ------------------------------
            # Common: DATA/REGISTER write value attribute 2
            if v in (int(ObjectType.DATA), int(ObjectType.REGISTER), int(ObjectType.EXTENDED_REGISTER)) and idx == 2:
                self._trace(f"_apply_value: setting value via value property")
                setattr(obj, "value", val)
                return True
            # ------------------------------
            # CLOCK attributes: accept human-readable date/time strings
            if v == int(ObjectType.CLOCK):
                if idx == 2:
                    self._trace(f"_apply_value: setting clock time")
                    if isinstance(val, str):
                        setattr(obj, "time", self._to_gx_datetime(val, "datetime"))
                    elif isinstance(val, (int, float)):
                        setattr(obj, "time", self._to_gx_datetime(str(val), "datetime"))
                    else:
                        setattr(obj, "time", val)
                    return True
                if idx == 5:
                    self._trace(f"_apply_value: setting clock begin")
                    if isinstance(val, str):
                        setattr(obj, "begin", self._to_gx_datetime(val, "datetime"))
                    elif isinstance(val, (int, float)):
                        setattr(obj, "begin", self._to_gx_datetime(str(val), "datetime"))
                    else:
                        setattr(obj, "begin", val)
                    return True
                if idx == 6:
                    self._trace(f"_apply_value: setting clock end")
                    if isinstance(val, str):
                        setattr(obj, "end", self._to_gx_datetime(val, "datetime"))
                    elif isinstance(val, (int, float)):
                        setattr(obj, "end", self._to_gx_datetime(str(val), "datetime"))
                    else:
                        setattr(obj, "end", val)
                    return True
            # ------------------------------
            # DISCONNECT_CONTROL: write control mode/state if supported
            if v == int(ObjectType.DISCONNECT_CONTROL) and idx in (2, 3):
                # Some meters expose properties outputState/controlMode
                try:
                    if idx == 2 and hasattr(obj, "outputState"):
                        self._trace(f"_apply_value: setting outputState")
                        setattr(obj, "outputState", val)
                        return True
                    if idx == 3 and hasattr(obj, "controlMode"):
                        self._trace(f"_apply_value: setting controlMode")
                        setattr(obj, "controlMode", val)
                        return True
                except Exception:
                    pass
            # ------------------------------
            # Default: attempt to set 'value' for idx 2
            if idx == 2 and hasattr(obj, "value"):
                self._trace(f"_apply_value: setting default value property")
                setattr(obj, "value", val)
                return True
            # ------------------------------
            # LAST resort: try obj.setValue!
            self._trace(f"_apply_value: trying obj.setValue({idx}, {val}) as last resort!")
            obj.setValue(idx, val)
            self._trace(f"_apply_value: setValue succeeded!")
            return True
        except Exception as e:
            self._trace(f"_apply_value exception: {e}")
            import traceback
            self._trace(traceback.format_exc())
            return False
        return False

    def closeEvent(self, event):
        self.disconnect_meter()
        event.accept()


# ---------------------------------------------------------------------------
# Advanced Editor dialog (popup)
# ---------------------------------------------------------------------------

class AdvancedEditorDialog(QDialog):
    def __init__(self, parent: DLMSGUI, obj, idx: int, ln: str):
        super().__init__(parent)
        self.setWindowTitle(f"Edit {ln}  Attribute {idx}")
        self.resize(640, 520)
        self._parent = parent
        self._obj = obj
        self._idx = idx

        layout = QVBoxLayout(self)
        tabs = QTabWidget()
        layout.addWidget(tabs)

        # Basic tab
        basic = QWidget()
        bl = QVBoxLayout(basic)
        self._txt = QPlainTextEdit()
        bl.addWidget(QLabel("Value (raw):"))
        bl.addWidget(self._txt)
        btn_read = QPushButton("Read from meter")
        btn_read.clicked.connect(self._read_val)
        bl.addWidget(btn_read)
        tabs.addTab(basic, "Basic")

        # Pre-populate
        try:
            val = parent.reader.read(obj, idx)
            self._txt.setPlainText(str(val))
        except Exception:
            pass

        # Specialised tabs
        tname = parent._type_name(obj.objectType)
        if tname == "CLOCK" and idx == 2:
            self._add_clock_tab(tabs, obj)
        elif tname == "DISCONNECT_CONTROL":
            self._add_disconnect_tab(tabs, obj)
        elif tname == "IMAGE_TRANSFER":
            self._add_image_tab(tabs, obj)

        # Close button
        bbox = QDialogButtonBox(QDialogButtonBox.Close)
        bbox.rejected.connect(self.reject)
        layout.addWidget(bbox)

    def _read_val(self):
        try:
            val = self._parent.reader.read(self._obj, self._idx)
            self._txt.setPlainText(str(val))
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def _add_clock_tab(self, tabs, obj):
        tab = QWidget()
        l = QVBoxLayout(tab)
        l.addWidget(QLabel("Set Date/Time (YYYY-MM-DD HH:MM:SS):"))
        self._dt_edit = QLineEdit()
        l.addWidget(self._dt_edit)
        btn_now = QPushButton("Current time")
        btn_now.clicked.connect(
            lambda: self._dt_edit.setText(
                time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
            )
        )
        l.addWidget(btn_now)
        btn_apply = QPushButton("Apply")

        def _apply():
            try:
                obj.time = self._parent._to_gx_datetime(
                    self._dt_edit.text().strip(), "datetime"
                )
                self._parent.reader.write(obj, 2)
                self._parent._trace(f"Applied Clock time {self._dt_edit.text().strip()}")
            except Exception as e:
                QMessageBox.critical(self, "Error", str(e))

        btn_apply.clicked.connect(_apply)
        l.addWidget(btn_apply)
        l.addStretch()
        tabs.addTab(tab, "Date/Time")

    def _add_disconnect_tab(self, tabs, obj):
        tab = QWidget()
        l = QVBoxLayout(tab)
        l.addWidget(QLabel("Control mode:"))
        self._ctrl_cmb = QComboBox()
        self._ctrl_cmb.addItems(["0", "1", "2"])
        l.addWidget(self._ctrl_cmb)
        btn_apply = QPushButton("Apply")

        def _apply():
            try:
                val = int(self._ctrl_cmb.currentText())
                if hasattr(obj, "controlMode"):
                    obj.controlMode = val
                self._parent.reader.write(obj, 3)
                self._parent._trace(f"Applied Disconnect control mode {val}")
            except Exception as e:
                QMessageBox.critical(self, "Error", str(e))

        btn_apply.clicked.connect(_apply)
        l.addWidget(btn_apply)
        l.addStretch()
        tabs.addTab(tab, "Control")

    def _add_image_tab(self, tabs, obj):
        tab = QWidget()
        l = QVBoxLayout(tab)

        file_grp = QGroupBox("Image File")
        fl = QHBoxLayout(file_grp)
        self._img_path = QLineEdit()
        fl.addWidget(self._img_path)
        btn_browse = QPushButton("Browse…")
        btn_browse.clicked.connect(self._browse_image)
        fl.addWidget(btn_browse)
        l.addWidget(file_grp)

        ctrl_grp = QGroupBox("Transfer Control")
        cl = QVBoxLayout(ctrl_grp)
        hl = QHBoxLayout()
        hl.addWidget(QLabel("Block Size:"))
        from PyQt5.QtWidgets import QSpinBox
        self._blk_spin = QSpinBox()
        self._blk_spin.setRange(1, 10000)
        self._blk_spin.setValue(getattr(obj, "imageBlockSize", 100))
        hl.addWidget(self._blk_spin)
        hl.addStretch()
        cl.addLayout(hl)
        self._progress = QProgressBar()
        cl.addWidget(self._progress)
        self._status_lbl = QLabel("Ready")
        cl.addWidget(self._status_lbl)
        self._start_btn = QPushButton("Start Transfer")
        self._start_btn.clicked.connect(self._start_transfer)
        cl.addWidget(self._start_btn)
        l.addWidget(ctrl_grp)
        l.addStretch()
        tabs.addTab(tab, "Firmware Update")

    def _browse_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Firmware", "",
            "Binary Files (*.bin);;All Files (*.*)",
        )
        if path:
            self._img_path.setText(path)

    def _start_transfer(self):
        path = self._img_path.text()
        if not path or not os.path.exists(path):
            QMessageBox.warning(self, "Error", "Select valid file")
            return
        self._obj.imageBlockSize = self._blk_spin.value()
        self._start_btn.setEnabled(False)
        self._progress.setValue(0)
        self._status_lbl.setText("Starting…")
        threading.Thread(
            target=self._run_transfer, args=(path,), daemon=True
        ).start()

    def _run_transfer(self, path):
        try:
            with open(path, "rb") as f:
                content = f.read()
            total = len(content)
            blk = self._obj.imageBlockSize
            ident = os.path.basename(path)[:10]

            QTimer.singleShot(0, lambda: self._status_lbl.setText("Initiating…"))
            reqs = self._obj.imageTransferInitiate(self._parent.client, ident, total)
            self._send_reqs(reqs, "Initiate")

            blocks = [content[i:i + blk] for i in range(0, total, blk)]
            for i, chunk in enumerate(blocks):
                pct = int((i / len(blocks)) * 100)
                QTimer.singleShot(0, lambda p=pct: self._progress.setValue(p))
                QTimer.singleShot(
                    0,
                    lambda i=i: self._status_lbl.setText(
                        f"Block {i + 1}/{len(blocks)}"
                    ),
                )
                from gurux_dlms.GXByteBuffer import GXByteBuffer as _BB
                from gurux_dlms.internal._GXCommon import _GXCommon
                req_data = _BB()
                req_data.setUInt8(DataType.STRUCTURE)
                req_data.setUInt8(2)
                _GXCommon.setData(None, req_data, DataType.UINT32, i)
                _GXCommon.setData(None, req_data, DataType.OCTET_STRING, chunk)
                reqs = self._parent.client.method(self._obj, 2, req_data, DataType.ARRAY)
                self._send_reqs(reqs, f"Block {i}")

            QTimer.singleShot(0, lambda: self._status_lbl.setText("Verifying…"))
            self._send_reqs(self._obj.imageVerify(self._parent.client), "Verify")
            QTimer.singleShot(0, lambda: self._status_lbl.setText("Activating…"))
            self._send_reqs(self._obj.imageActivate(self._parent.client), "Activate")
            QTimer.singleShot(0, lambda: self._status_lbl.setText("Complete!"))
            QTimer.singleShot(
                0, lambda: QMessageBox.information(self, "Success", "Transfer complete!")
            )
        except Exception as ex:
            QTimer.singleShot(
                0, lambda: QMessageBox.critical(self, "Transfer Error", str(ex))
            )
            QTimer.singleShot(0, lambda: self._status_lbl.setText("Error"))
        finally:
            QTimer.singleShot(0, lambda: self._start_btn.setEnabled(True))

    def _send_reqs(self, reqs, desc):
        from gurux_dlms.GXReplyData import GXReplyData
        if isinstance(reqs, (bytes, bytearray)):
            reqs = [reqs]
        reply = GXReplyData()
        for req in reqs:
            reply.clear()
            self._parent.reader.readDLMSPacket(req, reply)
            if reply.error:
                raise Exception(f"DLMS Error {reply.error} in {desc}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    win = DLMSGUI()
    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()

class TaskDialog(QDialog):
    def __init__(self, parent, client, cached_objects, existing_task=None):
        super().__init__(parent)
        self.parent = parent
        self.client = client
        self.cached_objects = cached_objects
        self.existing_task = existing_task

        self.setWindowTitle("Add Task" if not existing_task else "Edit Task")
        self.setModal(True)
        self.resize(500, 400)

        self._init_ui()
        if existing_task:
            self._load_existing_task()

    def _init_ui(self):
        layout = QVBoxLayout(self)

        # Operation Type
        type_layout = QHBoxLayout()
        type_layout.addWidget(QLabel("Operation Type:"))
        self.type_combo = QComboBox()
        self.type_combo.addItems(["GET", "SET", "ACTION"])
        self.type_combo.currentTextChanged.connect(self._on_type_changed)
        type_layout.addWidget(self.type_combo)
        type_layout.addStretch()
        layout.addLayout(type_layout)

        # OBIS Selection
        obis_layout = QHBoxLayout()
        obis_layout.addWidget(QLabel("OBIS:"))
        self.obis_combo = QComboBox()
        self.obis_combo.setEditable(True)
        self._populate_obis_list()
        obis_layout.addWidget(self.obis_combo)
        obis_layout.addWidget(QPushButton("Browse..."))
        layout.addLayout(obis_layout)

        # Attribute/Method Index
        idx_layout = QHBoxLayout()
        idx_layout.addWidget(QLabel("Attribute/Method Index:"))
        self.index_spin = QSpinBox()
        self.index_spin.setRange(1, 255)
        idx_layout.addWidget(self.index_spin)
        idx_layout.addStretch()
        layout.addLayout(idx_layout)

        # Data/Parameters (for SET and ACTION)
        self.data_group = QGroupBox("Data/Parameters (XDR Format)")
        data_layout = QVBoxLayout(self.data_group)
        self.data_text = QPlainTextEdit()
        self.data_text.setPlaceholderText("Enter value in XDR format (e.g., 0x0A, 123, \"text\", [0x01, 0x02])")
        data_layout.addWidget(self.data_text)
        layout.addWidget(self.data_group)

        # Selective Access
        self.sel_group = QGroupBox("Selective Access")
        sel_layout = QVBoxLayout(self.sel_group)

        self.sel_none = QRadioButton("None")
        self.sel_entry = QRadioButton("By Entry")
        self.sel_range = QRadioButton("By Range")
        self.sel_none.setChecked(True)

        sel_type_layout = QHBoxLayout()
        sel_type_layout.addWidget(self.sel_none)
        sel_type_layout.addWidget(self.sel_entry)
        sel_type_layout.addWidget(self.sel_range)
        sel_layout.addLayout(sel_type_layout)

        # Entry/Range parameters
        self.entry_frame = QWidget()
        entry_layout = QHBoxLayout(self.entry_frame)
        entry_layout.addWidget(QLabel("Entry Index:"))
        self.entry_spin = QSpinBox()
        self.entry_spin.setRange(1, 999999)
        entry_layout.addWidget(self.entry_spin)
        entry_layout.addStretch()
        sel_layout.addWidget(self.entry_frame)
        self.entry_frame.hide()

        self.range_frame = QWidget()
        range_layout = QGridLayout(self.range_frame)
        range_layout.addWidget(QLabel("From (OBIS):"), 0, 0)
        self.range_from = QLineEdit()
        range_layout.addWidget(self.range_from, 0, 1)
        range_layout.addWidget(QLabel("To (OBIS):"), 1, 0)
        self.range_to = QLineEdit()
        range_layout.addWidget(self.range_to, 1, 1)
        sel_layout.addWidget(self.range_frame)
        self.range_frame.hide()

        self.sel_none.toggled.connect(lambda: self._on_sel_type_changed())
        self.sel_entry.toggled.connect(lambda: self._on_sel_type_changed())
        self.sel_range.toggled.connect(lambda: self._on_sel_type_changed())

        layout.addWidget(self.sel_group)

        # Dialog buttons
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._on_type_changed()

    def _populate_obis_list(self):
        """Populate OBIS combo box from cached objects"""
        self.obis_combo.clear()
        if self.cached_objects:
            for obj in self.cached_objects:
                ln = obj.get('logical_name', '')
                if ln:
                    self.obis_combo.addItem(ln)

    def _on_type_changed(self):
        """Handle operation type change"""
        is_set_or_action = self.type_combo.currentText() in ["SET", "ACTION"]
        self.data_group.setVisible(is_set_or_action)

    def _on_sel_type_changed(self):
        """Handle selective access type change"""
        self.entry_frame.setVisible(self.sel_entry.isChecked())
        self.range_frame.setVisible(self.sel_range.isChecked())

    def _load_existing_task(self):
        """Load existing task data into dialog"""
        self.type_combo.setCurrentText(self.existing_task['type'])
        self.obis_combo.setCurrentText(self.existing_task['obis'])
        self.index_spin.setValue(self.existing_task['index'])
        if 'data' in self.existing_task and self.existing_task['data']:
            self.data_text.setPlainText(self.existing_task['data'])

    def get_task(self):
        """Return task data dictionary"""
        task = {
            'type': self.type_combo.currentText(),
            'obis': self.obis_combo.currentText(),
            'index': self.index_spin.value(),
            'run': True,
        }

        if self.type_combo.currentText() in ["SET", "ACTION"]:
            task['data'] = self.data_text.toPlainText().strip()

        # Add selective access if configured
        if self.sel_entry.isChecked():
            task['selective_access'] = {
                'type': 'entry',
                'entry': self.entry_spin.value()
            }
        elif self.sel_range.isChecked():
            task['selective_access'] = {
                'type': 'range',
                'from': self.range_from.text().strip(),
                'to': self.range_to.text().strip()
            }

        return task

    # ------------------------------------------------------------------
    # Save association view
    # ------------------------------------------------------------------


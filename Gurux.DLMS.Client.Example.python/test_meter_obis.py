import pytest
import sys
import time
from connect_meter import initialize_client

# Access meaning:
# "GET"     -> Attribute must be readable.
# "GET/SET" -> Attribute must be readable and writable (write back same value).
# =========================
# Console output to file
# =========================
class TeeOutput:
    def __init__(self, filename):
        self.terminal = sys.stdout
        self.log = open(filename, "w", encoding="utf-8")

    def write(self, message):
        self.terminal.write(message)
        self.log.write(message)

    def flush(self):
        self.terminal.flush()
        self.log.flush()

# Redirect stdout & stderr
sys.stdout = TeeOutput("output_console.txt")
sys.stderr = sys.stdout
# Per‑object attribute specifications.
# Attribute index is implied by order: 1 = logical_name, 2 = next attribute, etc.
OBJECT_SPECS = {
    # Reference to UNI/TS 11291-12-2
    # =========================
# IDENTIFICATION OBJECTS
# =========================

"0.0.96.1.0.255": [
    ("Manufacturing Number - logical_name", 1, "GET"),
    ("Manufacturing Number - value", 2, "GET"),
],

"0.0.96.1.10.255": [
    ("Metering Point Identifier - logical_name", 1, "GET"),
    ("Metering Point Identifier - value", 2, "GET/SET"),
],

"0.0.96.1.3.255": [
    ("Equipment Class Identifier - logical_name", 1, "GET"),
    ("Equipment Class Identifier - value", 2, "GET"),
],

"0.0.96.1.5.255": [
    ("Reference UNI/TS 11291-12-2 - logical_name", 1, "GET"),
    ("Reference UNI/TS 11291-12-2 - value", 2, "GET"),
],

"0.0.41.0.0.255": [
    ("SAP Assignment - logical_name", 1, "GET"),
    ("SAP Assignment - SAP_assignment_list", 2, "GET"),
],

"0.0.42.0.0.255": [
    ("COSEM Logical Device Name - logical_name", 1, "GET"),
    ("COSEM Logical Device Name - value", 2, "GET"),
],

# =========================
# ASSOCIATIONS
# =========================

"0.0.40.0.1.255": [
    ("Management Association - logical_name", 1, "GET"),
    ("Management Association - object_list", 2, "GET"),
    ("Management Association - associated_partners_id", 3, "GET"),
    ("Management Association - application_context_name", 4, "GET"),
    ("Management Association - authentication_mechanism_name", 6, "GET"),
    ("Management Association - association_status", 8, "GET"),
    ("Management Association - security_setup_reference", 9, "GET"),
    ("Management Association - user_list", 10, "GET"),
    ("Management Association - current_user", 11, "GET"),
],

"0.0.40.0.16.255": [
    ("Public Association - logical_name", 1, "GET"),
    ("Public Association - object_list", 2, "GET"),
    ("Public Association - associated_partners_id", 3, "GET"),
    ("Public Association - application_context_name", 4, "GET"),
    ("Public Association - authentication_mechanism_name", 6, "GET"),
    ("Public Association - association_status", 8, "GET"),
    ("Public Association - security_setup_reference", 9, "GET"),
    ("Public Association - user_list", 10, "GET"),
    ("Public Association - current_user", 11, "GET"),
],

"0.0.40.0.3.255": [
    ("Installer/Maintainer Association - logical_name", 1, "GET"),
    ("Installer/Maintainer Association - object_list", 2, "GET"),
    ("Installer/Maintainer Association - associated_partners_id", 3, "GET"),
    ("Installer/Maintainer Association - application_context_name", 4, "GET"),
    ("Installer/Maintainer Association - authentication_mechanism_name", 6, "GET"),
    ("Installer/Maintainer Association - association_status", 8, "GET"),
    ("Installer/Maintainer Association - security_setup_reference", 9, "GET"),
    ("Installer/Maintainer Association - user_list", 10, "GET/SET"),
    ("Installer/Maintainer Association - current_user", 11, "GET"),
],

"0.0.40.0.32.255": [
    ("Broadcasting Association - logical_name", 1, "GET"),
    ("Broadcasting Association - object_list", 2, "GET"),
    ("Broadcasting Association - associated_partners_id", 3, "GET"),
    ("Broadcasting Association - application_context_name", 4, "GET"),
    ("Broadcasting Association - xDLMS_context_info", 5, "GET"),
    ("Broadcasting Association - authentication_mechanism_name", 6, "GET"),
    ("Broadcasting Association - association_status", 8, "GET"),
    ("Broadcasting Association - security_setup_reference", 9, "GET"),
    ("Broadcasting Association - user_list", 10, "GET"),
    ("Broadcasting Association - current_user", 11, "GET"),
],

# =========================
# FRAME COUNTERS
# =========================

"0.0.94.39.33.255": [
    ("Global Frame Counter Thresholds - logical_name", 1, "GET"),
    ("Global Frame Counter Thresholds - value", 2, "GET/SET"),
],

"0.0.43.1.1.255": [
    ("Management Frame Counter Online - logical_name", 1, "GET"),
    ("Management Frame Counter Online - value", 2, "GET"),
],

"0.1.43.1.1.255": [
    ("Off-line Management Frame Counter - logical_name", 1, "GET"),
    ("Off-line Management Frame Counter - value", 2, "GET"),
],

''' "0.0.43.1.48.255": [
    ("Guarantor Authority Frame Counter - logical_name", 1, "GET"),
    ("Guarantor Authority Frame Counter - value", 2, "GET"),
],

"0.0.43.1.3.255": [
    ("Installer/Maintainer Frame Counter - logical_name", 1, "GET"),
    ("Installer/Maintainer Frame Counter - value", 2, "GET"),
], '''

"0.0.43.1.32.255": [
    ("Broadcast Frame Counter - logical_name", 1, "GET"),
    ("Broadcast Frame Counter - value", 2, "GET"),
],

# =========================
# CLOCK & TIME
# =========================

"0.0.1.0.0.255": [
    ("Clock - logical_name", 1, "GET"),
    ("Clock - time", 2, "GET/SET"),
    ("Clock - time_zone", 3, "GET/SET"),
    ("Clock - status", 4, "GET"),
    ("Clock - daylight_savings_begin", 5, "GET/SET"),
    ("Clock - daylight_savings_end", 6, "GET/SET"),
    ("Clock - daylight_savings_deviation", 7, "GET/SET"),
    ("Clock - daylight_savings_enabled", 8, "GET/SET"),
    ("Clock - clock_base", 9, "GET"),
],

"0.0.1.1.0.255": [
    ("UNIX Time - logical_name", 1, "GET"),
    ("UNIX Time - value", 2, "GET/SET"),
],

"0.0.94.39.44.255": [
    ("Synchronization Algorithm - logical_name", 1, "GET"),
    ("Synchronization Algorithm - value", 2, "GET/SET"),
],

"0.0.94.39.20.255": [
    ("Synchronization Registers - logical_name", 1, "GET"),
    ("Synchronization Registers - value", 2, "GET"),
],

"0.0.96.14.0.255": [
    ("Current Active Tariff - logical_name", 1, "GET"),
    ("Current Active Tariff - value", 2, "GET"),
],


"0.0.94.39.21.255": [
    ("Active UNI/TS 11291 Tariff Plan - logical_name", 1, "GET"),
    ("Active UNI/TS 11291 Tariff Plan - calendar_name", 2, "GET"),
    ("Active UNI/TS 11291 Tariff Plan - enabled", 3, "GET"),
    ("Active UNI/TS 11291 Tariff Plan - plan", 4, "GET"),
    ("Active UNI/TS 11291 Tariff Plan - activation_date_time", 5, "GET"),
],

"0.0.94.39.22.255": [
    ("Passive UNI/TS 11291 Tariff Plan - logical_name", 1, "GET"),
    ("Passive UNI/TS 11291 Tariff Plan - calendar_name", 2, "GET/SET"),
    ("Passive UNI/TS 11291 Tariff Plan - enabled", 3, "GET/SET"),
    ("Passive UNI/TS 11291 Tariff Plan - plan", 4, "GET/SET"),
    ("Passive UNI/TS 11291 Tariff Plan - activation_date_time", 5, "GET/SET"),
],

# =========================
# DIAGNOSTICS
# =========================

"7.0.96.5.0.255": [
    ("UNI/TS Device Status - logical_name", 1, "GET"),
    ("UNI/TS Device Status - value", 2, "GET"),
],

"7.0.96.5.1.255": [
    ("Current Diagnostic - logical_name", 1, "GET"),
    ("Current Diagnostic - value", 2, "GET"),
],

"7.1.96.5.1.255": [
    ("Daily Diagnostic - logical_name", 1, "GET"),
    ("Daily Diagnostic - value", 2, "GET"),
],

# =========================
# VALVE
# =========================

"0.0.96.3.10.255": [
    ("Valve Management - logical_name", 1, "GET"),
    ("Valve Management - output_state", 2, "GET"),
    ("Valve Management - control_state", 3, "GET"),
    ("Valve Management - control_mode", 4, "GET"),
],

"0.0.10.0.106.255": [
    ("Valve Script Table - logical_name", 1, "GET"),
    ("Valve Script Table - scripts", 2, "GET"),
],

"0.0.15.0.1.255": [
    ("Valve Scheduler - logical_name", 1, "GET"),
    ("Valve Scheduler - executed_script", 2, "GET/SET"),
    ("Valve Scheduler - type", 3, "GET"),
    ("Valve Scheduler - execution_time", 4, "GET/SET"),
],

# =========================
# THRESHOLDS / MONITORS
# =========================

"0.0.94.39.25.255": [
    ("Tampering Attempts Threshold - logical_name", 1, "GET"),
    ("Tampering Attempts Threshold - thresholds", 2, "GET/SET"),
    ("Tampering Attempts Threshold - monitored_value", 3, "GET"),
    ("Tampering Attempts Threshold - actions", 4, "GET"),
],

"0.0.94.39.26.255": [
    ("Leakage Test Parameters - logical_name", 1, "GET"),
    ("Leakage Test Parameters - value", 2, "GET/SET"),
],

"0.0.94.39.7.255": [
    ("Valve Closure Cause - logical_name", 1, "GET"),
    ("Valve Closure Cause - value", 2, "GET"),
],

"0.0.94.39.46.255": [
    ("Message to the user - logical_name", 1, "GET"),
    ("Message to the user - value", 2, "GET/SET"),
],
# =========================
# EVENT & LOGBOOKS
# =========================

"7.0.99.98.0.255": [
    ("Event Logbook - logical_name", 1, "GET"),
    ("Event Logbook - buffer", 2, "GET"),
    ("Event Logbook - capture_objects", 3, "GET"),
    ("Event Logbook - capture_period", 4, "GET"),
    ("Event Logbook - sort_method", 5, "GET"),
    ("Event Logbook - sort_object", 6, "GET"),
    ("Event Logbook - entries_in_use", 7, "GET"),
    ("Event Logbook - profile_entries", 8, "GET"),
],

"7.0.99.98.1.255": [
    ("Metrological Logbook - logical_name", 1, "GET"),
    ("Metrological Logbook - buffer", 2, "GET"),
    ("Metrological Logbook - capture_objects", 3, "GET"),
    ("Metrological Logbook - capture_period", 4, "GET"),
    ("Metrological Logbook - sort_method", 5, "GET"),
    ("Metrological Logbook - sort_object", 6, "GET"),
    ("Metrological Logbook - entries_in_use", 7, "GET"),
    ("Metrological Logbook - profile_entries", 8, "GET"),
],

"7.0.99.16.0.255": [
    ("Metrological Parameter Change Log - logical_name", 1, "GET"),
    ("Metrological Parameter Change Log - buffer", 2, "GET"),
    ("Metrological Parameter Change Log - capture_objects", 3, "GET"),
    ("Metrological Parameter Change Log - capture_period", 4, "GET"),
    ("Metrological Parameter Change Log - sort_method", 5, "GET"),
    ("Metrological Parameter Change Log - sort_object", 6, "GET"),
    ("Metrological Parameter Change Log - entries_in_use", 7, "GET"),
    ("Metrological Parameter Change Log - profile_entries", 8, "GET"),
],
# =========================
# PROFILES
# =========================

"7.0.99.99.3.255": [
    ("Daily Load Profile - logical_name", 1, "GET"),
    ("Daily Load Profile - buffer", 2, "GET"),
    ("Daily Load Profile - capture_objects", 3, "GET"),
    ("Daily Load Profile - capture_period", 4, "GET"),
    ("Daily Load Profile - sort_method", 5, "GET"),
    ("Daily Load Profile - sort_object", 6, "GET"),
    ("Daily Load Profile - entries_in_use", 7, "GET"),
    ("Daily Load Profile - profile_entries", 8, "GET"),
],

"7.0.98.11.0.255": [
    ("Snapshot Period Data - logical_name", 1, "GET"),
    ("Snapshot Period Data - buffer", 2, "GET"),
    ("Snapshot Period Data - capture_objects", 3, "GET"),
    ("Snapshot Period Data - capture_period", 4, "GET/SET"),
    ("Snapshot Period Data - sort_method", 5, "GET"),
    ("Snapshot Period Data - sort_object", 6, "GET"),
    ("Snapshot Period Data - entries_in_use", 7, "GET"),
    ("Snapshot Period Data - profile_entries", 8, "GET"),
],
# =========================
# PUSH
# =========================

"0.1.15.0.4.255": [
    ("Push Scheduler 1 - logical_name", 1, "GET"),
    ("Push Scheduler 1 - executed_script", 2, "GET"),
    ("Push Scheduler 1 - type", 3, "GET"),
    ("Push Scheduler 1 - execution_time", 4, "GET/SET"),
],

"0.1.25.9.0.255": [
    ("Push Setup 1 - logical_name", 1, "GET"),
    ("Push Setup 1 - push_object_list", 2, "GET/SET"),
    ("Push Setup 1 - send_destination_and_method", 3, "GET/SET"),
    ("Push Setup 1 - communication_window", 4, "GET/SET"),
    ("Push Setup 1 - randomisation_start_interval", 5, "GET/SET"),
    ("Push Setup 1 - number_of_retries", 6, "GET/SET"),
    ("Push Setup 1 - repetition_delay", 7, "GET/SET"),
],

"0.2.15.0.4.255": [
    ("Push Scheduler 2 - logical_name", 1, "GET"),
    ("Push Scheduler 2 - executed_script", 2, "GET"),
    ("Push Scheduler 2 - type", 3, "GET"),
    ("Push Scheduler 2 - execution_time", 4, "GET/SET"),
],

"0.2.25.9.0.255": [
    ("Push Setup 2 - logical_name", 1, "GET"),
    ("Push Setup 2 - push_object_list", 2, "GET/SET"),
    ("Push Setup 2 - send_destination_and_method", 3, "GET/SET"),
    ("Push Setup 2 - communication_window", 4, "GET/SET"),
    ("Push Setup 2 - randomisation_start_interval", 5, "GET/SET"),
    ("Push Setup 2 - number_of_retries", 6, "GET/SET"),
    ("Push Setup 2 - repetition_delay", 7, "GET/SET"),
],
# =========================
# NETWORK & COMMUNICATION
# =========================

"0.0.25.4.0.255": [
    ("SIM Setup GPRS - logical_name", 1, "GET"),
    ("SIM Setup GPRS - APN", 2, "GET/SET"),
    ("SIM Setup GPRS - PIN_code", 3, "GET/SET"),
    ("SIM Setup GPRS - quality_of_service", 4, "GET/SET"),
],

"0.1.25.4.0.255": [
    ("SIM Setup NB-IoT - logical_name", 1, "GET"),
    ("SIM Setup NB-IoT - APN", 2, "GET/SET"),
    ("SIM Setup NB-IoT - PIN_code", 3, "GET/SET"),
    ("SIM Setup NB-IoT - quality_of_service", 4, "GET/SET"),
],

"0.0.25.1.0.255": [
    ("IPv4 Setup - logical_name", 1, "GET"),
    ("IPv4 Setup - DL_reference", 2, "GET"),
    ("IPv4 Setup - IP_address", 3, "GET/SET"),
    ("IPv4 Setup - subnet_mask", 4, "GET/SET"),
    ("IPv4 Setup - gateway_IP_address", 5, "GET/SET"),
    ("IPv4 Setup - use_DHCP_flag", 6, "GET/SET"),
],

"0.0.25.7.0.255": [
    ("IPv6 Setup - logical_name", 1, "GET"),
    ("IPv6 Setup - DL_reference", 2, "GET"),
    ("IPv6 Setup - IP_address", 3, "GET/SET"),
    ("IPv6 Setup - use_DHCP_flag", 6, "GET/SET"),
],

"0.0.25.0.0.255": [
    ("TCP-UDP Setup - logical_name", 1, "GET"),
    ("TCP-UDP Setup - TCP-UDP_port", 2, "GET/SET"),
    ("TCP-UDP Setup - IP_reference", 3, "GET"),
    ("TCP-UDP Setup - MSS", 4, "GET/SET"),
    ("TCP-UDP Setup - nb_of_sim_conn", 5, "GET/SET"),
],
# =========================
# IMAGE TRANSFER
# =========================

"0.0.44.0.0.255": [
    ("Image Transfer - logical_name", 1, "GET"),
    ("Image Transfer - image_block_size", 2, "GET"),
    ("Image Transfer - image_transferred_blocks_status", 3, "GET"),
    ("Image Transfer - image_first_not_transferred_block_number", 4, "GET"),
    ("Image Transfer - image_transfer_enabled", 5, "GET/SET"),
    ("Image Transfer - image_transfer_status", 6, "GET"),
    ("Image Transfer - image_to_activate_info", 7, "GET"),
],

}

# Flatten OBJECT_SPECS into a simple list for parametrization.
TEST_DATA = []
for ln, attrs in OBJECT_SPECS.items():
    for name, index, access in attrs:
        TEST_DATA.append((name, ln, index, access))

@pytest.fixture(scope="module")
def meter_connection():
    """
    Fixture to establish connection once for the entire test module.
    Includes retry logic to handle optical probe flakiness.
    """
    client, reader, media = initialize_client()
    
    max_retries = 3
    connected = False
    
    for attempt in range(max_retries):
        try:
            print(f"\n[Setup] Connecting to meter (Attempt {attempt+1}/{max_retries})...")
            if media.isOpen():
                media.close()
            
            # Wait a bit to ensure port is released by OS
            time.sleep(2)
            
            media.open()
            # Initialize connection (Mode E + SNRM + AARQ)
            reader.initializeConnection()
            
            print("[Setup] Connection initialized. Reading Association View...")
            # Retrieve list of available objects
            reader.getAssociationView()
            
            print("[Setup] Connected successfully.")
            connected = True
            break
        except Exception as e:
            print(f"[Setup] Connection failed on attempt {attempt+1}: {e}")
            try:
                if media.isOpen():
                    media.close()
            except:
                pass
            time.sleep(3) # Wait before retry

    if not connected:
        pytest.fail("Fatal: Could not establish connection to meter after multiple attempts. Check optical probe alignment.")

    yield client, reader
    
    # Teardown
    print("\n[Teardown] Closing connection...")
    try:
        reader.close()
    except:
        pass
    try:
        if media.isOpen():
            media.close()
    except:
        pass

def find_object_by_ln(client, logical_name):
    target = logical_name.strip()
    for obj in client.objects:
        if obj.logicalName.strip() == target:
            return obj
    return None


@pytest.mark.parametrize("name, logical_name, attr_index, access", TEST_DATA)
def test_obis_read(meter_connection, name, logical_name, attr_index, access):
    """
    Test case for each OBIS code.
    Verifies that the object exists and access rights (Read) work as expected.
    """
    client, reader = meter_connection

    print(f"\nTesting: {name} (OBIS: {logical_name}, Attr: {attr_index})")

    # 1. Find the object in the Association View (by logical name only).
    obj = find_object_by_ln(client, logical_name)

    if not obj:
        # Debugging: Print all available objects to help user verify
        print(f"\n[DEBUG] Object {logical_name} NOT found in Association View. Printing first 10 available objects...")
        
        try:
            val = reader.readByLogicalName(logical_name, attr_index)
            print(f" -> Direct Read Value: {val}")
            return
        except Exception as e:
            pytest.fail(f"Direct read failed for {logical_name}: {e}")

    # 2. Check Access Rights
    if "GET" in access:
        try:
            val = reader.read(obj, attr_index)
            print(f" -> Read Value: {val}")

            if val is None:
                pytest.fail(f"Read returned None for {name}")

            # 3. Check SET Access (write back same value when allowed)
            if "SET" in access:
                print(f" -> Testing SET access (Writing back same value: {val})...")
                try:
                    reader.write(obj, attr_index)
                    print(" -> Write successful.")
                except Exception as e:
                    pytest.fail(f"Failed to WRITE (SET) {name}: {e}")

        except Exception as e:
            pytest.fail(f"Failed to read {name}: {e}")
    else:
        # Negative test: Ensure we CANNOT read
        try:
            reader.read(obj, attr_index)
            pytest.fail(f"Read succeeded but expected failure (Access: {access})")
        except Exception:
            print(f" -> Read failed as expected (Access: {access})")

if __name__ == "__main__":
    # Allow running this script directly
    sys.exit(pytest.main(["-v", "-s", __file__]))

import pytest
import datetime
import traceback
import time
from gurux_dlms.enums import InterfaceType, Authentication, Security, Standard, ObjectType, AccessMode, DataType, MethodAccessMode
from gurux_dlms.objects.enums import SecuritySuite
from gurux_serial.GXSerial import GXSerial
from gurux_dlms.GXByteBuffer import GXByteBuffer
from gurux_common.io import Parity, StopBits, BaudRate
from gurux_dlms import GXDLMSClient, GXDateTime
from gurux_common.enums import TraceLevel
from gurux_dlms.objects import GXDLMSActionSchedule, GXDLMSDisconnectControl

# Import local classes
from GXDLMSSecureClient2 import GXDLMSSecureClient2
from GXDLMSReader import GXDLMSReader

# --- Configuration copied from connect_meter.py ---
SERIAL_PORT = "COM6"
WAIT_TIME = 15000
CLIENT_ADDRESS = 1
LOGICAL_SERVER = 1
PHYSICAL_SERVER = 18 
AUTHENTICATION = Authentication.HIGH_GMAC
SECURITY = Security.AUTHENTICATION_ENCRYPTION
SECURITY_SUITE = SecuritySuite.SUITE_0
INVOCATION_COUNTER_LN = "0.0.43.1.0.255"
SYSTEM_TITLE_HEX = "5341435341435341"
BLOCK_CIPHER_KEY_HEX = "7ADF639CA79632FCA3D7810BE6416ABE"
AUTHENTICATION_KEY_HEX = "7ADF639CA79632FCA3D7810BE6416ABE"
DLMS_STANDARD = Standard.ITALY
MAX_INFO_SIZE = 128

@pytest.fixture(scope="module")
def dlms_connection():
    """Pytest fixture to initialize and close the DLMS connection."""
    client = GXDLMSSecureClient2(True)
    client.interfaceType = InterfaceType.HDLC_WITH_MODE_E
    client.useLogicalNameReferencing = True
    client.clientAddress = CLIENT_ADDRESS
    client.serverAddress = GXDLMSClient.getServerAddress(LOGICAL_SERVER, PHYSICAL_SERVER)
    client.authentication = AUTHENTICATION
    client.ciphering.security = SECURITY
    client.ciphering.securitySuite = SECURITY_SUITE
    client.ciphering.systemTitle = GXByteBuffer.hexToBytes(SYSTEM_TITLE_HEX)
    client.ciphering.blockCipherKey = GXByteBuffer.hexToBytes(BLOCK_CIPHER_KEY_HEX)
    client.ciphering.authenticationKey = GXByteBuffer.hexToBytes(AUTHENTICATION_KEY_HEX)
    client.standard = DLMS_STANDARD
    client.useUtc2NormalTime = True
    client.hdlcSettings.maxInfoRX = MAX_INFO_SIZE
    client.hdlcSettings.maxInfoTX = MAX_INFO_SIZE

    media = GXSerial(None)
    media.port = SERIAL_PORT
    media.baudRate = BaudRate.BAUD_RATE_300
    media.dataBits = 7
    media.parity = Parity.EVEN
    media.stopBits = StopBits.ONE
    
    reader = GXDLMSReader(client, media, TraceLevel.VERBOSE, INVOCATION_COUNTER_LN)
    reader.waitTime = WAIT_TIME

    print(f"\nOpening {SERIAL_PORT}...")
    media.open()
    try:
        print("Initializing connection...")
        reader.initializeConnection()
        print("Reading Association View...")
        reader.getAssociationView()
        yield client, reader, media
    finally:
        print("\nClosing connection...")
        try:
            reader.close()
        except:
            pass
        if media.isOpen():
            media.close()

def schedule_action(client, reader, selector, delay_minutes=1):
    """Helper to schedule an action on 0.0.15.0.1.255."""
    schedule_obis = "0.0.15.0.1.255"
    schedule = client.objects.findByLN(ObjectType.ACTION_SCHEDULE, schedule_obis)
    
    if not schedule:
        print(f"Schedule {schedule_obis} not found in objects. Creating manually...")
        schedule = GXDLMSActionSchedule(schedule_obis)
        client.objects.append(schedule)
    
    # 1. Read Meter Clock to sync time
    clock_obis = "0.0.1.0.0.255"
    clock = client.objects.findByLN(ObjectType.CLOCK, clock_obis)
    meter_time = datetime.datetime.now() # Fallback
    if clock:
        try:
            val = reader.read(clock, 2)
            if isinstance(val, GXDateTime):
                meter_time = val.value
                print(f"Meter Time: {meter_time}")
            else:
                print(f"Meter Time (Raw): {val}")
        except Exception as e:
            print(f"Could not read meter clock: {e}")
    
    # 2. Read current schedule config (Attribute 2: Executed Script)
    try:
        print(f"Reading current config for {schedule_obis} (Attr 2)...")
        reader.read(schedule, 2)
        if schedule.target:
            print(f"Target Script Table: {schedule.target.logicalName}")
        else:
            print("No target script table currently set.")
            # Fallback to common valve script table if None
            # In UNI TS 11291 (Italy), it's often 0.0.10.0.106.255
            from gurux_dlms.objects import GXDLMSScriptTable
            schedule.target = GXDLMSScriptTable("0.0.10.0.106.255")
            print(f"Using default target: {schedule.target.logicalName}")
    except Exception as e:
        print(f"Error reading schedule target: {e}")
    
    schedule.executedScriptSelector = selector
    
    # 3. Calculate execution time based on METER clock
    exec_time = meter_time + datetime.timedelta(minutes=delay_minutes)
    gx_exec_time = GXDateTime(exec_time)
    schedule.executionTime = [gx_exec_time]
    
    print(f"Scheduling selector {selector} at {exec_time} (Meter Time + {delay_minutes}m)...")
    print(f"System Local Time: {datetime.datetime.now()}")
    
    # 4. Write configuration
    try:
        # Write Attribute 2 (Script LN + Selector)
        reader.write(schedule, 2)
        # Write Attribute 4 (Execution Time)
        reader.write(schedule, 4)
        print("Schedule updated successfully on the meter.")
    except Exception as e:
        print(f"Failed to write schedule: {e}")
        raise e
    
    return exec_time, meter_time

def get_valve_status(client, reader):
    """Reads and returns the current status of the valve (Disconnect Control)."""
    valve_obis = "0.0.96.3.10.255"
    valve = client.objects.findByLN(ObjectType.DISCONNECT_CONTROL, valve_obis)
    if not valve:
        valve = GXDLMSDisconnectControl(valve_obis)
        client.objects.append(valve)
    
    try:
        # Attribute 2 is Output State (True=Connected/Open, False=Disconnected/Closed)
        reader.read(valve, 2)
        status_str = 'OPEN' if valve.outputState else 'CLOSED'
        print(f"  Current Valve Output State: {status_str}")
        return valve.outputState
    except Exception as e:
        print(f"Could not read valve status: {e}")
        return None

def wait_for_valve_action(client, reader, target_state, timeout_seconds=90):
    """
    Polls the valve status until it matches target_state or timeout occurs.
    target_state: True for OPEN, False for CLOSED
    """
    print(f"\nWaiting for valve to become {'OPEN' if target_state else 'CLOSED'}...")
    start_time = time.time()
    while (time.time() - start_time) < timeout_seconds:
        current_state = get_valve_status(client, reader)
        if current_state == target_state:
            print(f"SUCCESS: Valve reached target state!")
            return True
        print(f"  Still waiting... ({int(time.time() - start_time)}s elapsed)")
        time.sleep(10) # Poll every 10 seconds
    
    print("TIMEOUT: Valve did not change state in time.")
    return False

def test_close_valve_schedule(dlms_connection):
    """Test case to schedule valve CLOSE (Selector 1) and verify it happens."""
    client, reader, _ = dlms_connection
    print("\n--- TEST: CLOSE VALVE ---")
    
    # Ensure it's open first (optional but good for testing)
    initial_state = get_valve_status(client, reader)
    
    # Selector 1 to Close
    exec_time, meter_time = schedule_action(client, reader, selector=1, delay_minutes=1)
    
    # Verify based on meter clock synchronization
    assert exec_time > meter_time
    
    # Now wait and verify
    # We scheduled for 1 minute (60s), so we wait up to 90s to be sure
    success = wait_for_valve_action(client, reader, target_state=False, timeout_seconds=100)
    assert success, "Valve should have CLOSED after 1 minute schedule"
    print("Verification: Valve CLOSE confirmed via OBIS 0.0.96.3.10.255")

def test_open_valve_schedule(dlms_connection):
    """Test case to schedule valve OPEN (Selector 2) and verify it happens."""
    client, reader, _ = dlms_connection
    print("\n--- TEST: OPEN VALVE ---")
    
    # Selector 2 to Open
    exec_time, meter_time = schedule_action(client, reader, selector=2, delay_minutes=1)
    
    assert exec_time > meter_time
    
    # Wait and verify
    success = wait_for_valve_action(client, reader, target_state=True, timeout_seconds=100)
    assert success, "Valve should have OPENED after 1 minute schedule"
    print("Verification: Valve OPEN confirmed via OBIS 0.0.96.3.10.255")

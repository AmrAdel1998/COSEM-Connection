import sys
import traceback
from gurux_dlms.enums import InterfaceType, Authentication, Security, Standard, ObjectType, AccessMode, DataType, MethodAccessMode
from gurux_dlms.objects.enums import SecuritySuite
from gurux_serial.GXSerial import GXSerial
from gurux_dlms.GXByteBuffer import GXByteBuffer
from gurux_common.io import Parity, StopBits, BaudRate
from gurux_dlms import GXDLMSClient
from gurux_common.enums import TraceLevel

# Import local classes
from GXDLMSSecureClient2 import GXDLMSSecureClient2
from GXDLMSReader import GXDLMSReader

# --- Configuration based on user screenshots ---

# Connection
SERIAL_PORT = "COM6"
WAIT_TIME = 15000  # 5 seconds

# Addressing
CLIENT_ADDRESS = 1
LOGICAL_SERVER = 1
# Physical Server 18 (0x12) - Matches user's successful manual log (02 25 -> 25 hex = 37 dec -> 37 >> 1 = 18)
PHYSICAL_SERVER = 18 

# Interface Settings (Optical Mode E)
# Initial baud rate is 300, then it negotiates (usually to 9600)
# Data bits: 7, Parity: Even, Stop bits: 1 (Standard for Mode E)

# HDLC Settings
MAX_PDU_SIZE = 65535
GBT_WINDOW_SIZE = 1
HDLC_WINDOW_SIZE = 1
MAX_INFO_SIZE = 128 # Frame size

# Security
AUTHENTICATION = Authentication.HIGH_GMAC
SECURITY = Security.AUTHENTICATION_ENCRYPTION
SECURITY_SUITE = SecuritySuite.SUITE_0
INVOCATION_COUNTER_LN = "0.0.43.1.0.255" # Standard LN for invocation counter

# Keys (Hex strings)
# System Title: SACSACSA -> Hex: 5341435341435341
SYSTEM_TITLE_HEX = "5341435341435341"
BLOCK_CIPHER_KEY_HEX = "7ADF639CA79632FCA3D7810BE6416ABE"
AUTHENTICATION_KEY_HEX = "7ADF639CA79632FCA3D7810BE6416ABE"
# Dedicated Key is empty in screenshot

# Standard
DLMS_STANDARD = Standard.ITALY

def initialize_client():
    """Initializes and returns the DLMS client, reader, and media."""
    print("Initializing DLMS Client...")
    
    # Initialize Secure Client
    client = GXDLMSSecureClient2(True)
    
    # 1. Interface Setup
    client.interfaceType = InterfaceType.HDLC_WITH_MODE_E
    client.useLogicalNameReferencing = True
    
    # 2. Addressing
    client.clientAddress = CLIENT_ADDRESS
    # Calculate Server Address: (Logical << 14) | Physical
    client.serverAddress = GXDLMSClient.getServerAddress(LOGICAL_SERVER, PHYSICAL_SERVER)
    print(f"Server Address calculated: {client.serverAddress} (Logical: {LOGICAL_SERVER}, Physical: {PHYSICAL_SERVER})")
    
    # 3. Security Setup
    client.authentication = AUTHENTICATION
    client.ciphering.security = SECURITY
    client.ciphering.securitySuite = SECURITY_SUITE
    
    # Set Keys
    client.ciphering.systemTitle = GXByteBuffer.hexToBytes(SYSTEM_TITLE_HEX)
    client.ciphering.blockCipherKey = GXByteBuffer.hexToBytes(BLOCK_CIPHER_KEY_HEX)
    client.ciphering.authenticationKey = GXByteBuffer.hexToBytes(AUTHENTICATION_KEY_HEX)
    
    # 4. Standard and Time
    client.standard = DLMS_STANDARD
    client.useUtc2NormalTime = True
    
    # 5. HDLC & PDU Settings
    # client.maxPduSize = MAX_PDU_SIZE # Note: maxPduSize is often negotiated/read only in some implementations
    client.gbtWindowSize = GBT_WINDOW_SIZE
    client.hdlcSettings.windowSizeRX = HDLC_WINDOW_SIZE
    client.hdlcSettings.windowSizeTX = HDLC_WINDOW_SIZE
    client.hdlcSettings.maxInfoRX = MAX_INFO_SIZE
    client.hdlcSettings.maxInfoTX = MAX_INFO_SIZE
    
    # 6. Media (Serial) Setup
    media = GXSerial(None)
    media.port = SERIAL_PORT
    # Mode E starts at 300 baud, 7 data bits, Even parity, 1 stop bit
    media.baudRate = BaudRate.BAUD_RATE_300
    media.dataBits = 7
    media.parity = Parity.EVEN
    media.stopBits = StopBits.ONE
    
    # 7. Reader Setup
    # TraceLevel.VERBOSE will show all TX/RX frames
    reader = GXDLMSReader(client, media, TraceLevel.VERBOSE, INVOCATION_COUNTER_LN)
    reader.waitTime = WAIT_TIME
    
    return client, reader, media

def main():
    client, reader, media = initialize_client()
    
    try:
        print(f"Opening {SERIAL_PORT}...")
        media.open()
        
        print("Initializing connection (Mode E handshake + SNRM + AARQ)...")
        # initializeConnection handles the Mode E readout, invocation counter update (if needed), and Association
        reader.initializeConnection()
        
        print("Connection established successfully!")
        
        # Read Association View to see what objects are available
        print("Reading Association View...")
        reader.getAssociationView()
        
        # Print list of objects found
        print(f"Found {len(client.objects)} objects.")
        
        # Helper maps for attribute/method names (fallbacks)
        attr_name_map = {
            "CLOCK": {
                1:"Logical name", 2:"Time", 3:"Time zone", 4:"Status",
                5:"DST begin", 6:"DST end", 7:"DST deviation", 8:"DST enabled", 9:"Clock base"
            },
            "DATA": {1:"Logical name", 2:"Value"},
            "REGISTER": {1:"Logical name", 2:"Value", 3:"Scaler unit", 4:"Status"},
            "EXTENDED_REGISTER": {1:"Logical name", 2:"Value", 3:"Scaler unit", 4:"Status", 5:"Capture time"},
            "DEMAND_REGISTER": {
                1:"Logical name", 2:"Current average value", 3:"Last average value", 4:"Scaler unit",
                5:"Period", 6:"Number of periods", 7:"Max demand", 8:"Max demand time"
            },
            "PROFILE_GENERIC": {
                1:"Logical name", 2:"Buffer", 3:"Capture objects", 4:"Capture period",
                5:"Sort method", 6:"Sort object", 7:"Entries in use", 8:"Profile entries"
            },
            "SECURITY_SETUP": {
                1:"Logical name", 2:"Security policy", 3:"Security suite",
                4:"Client system title", 5:"Server system title", 6:"Certificates"
            },
            "DISCONNECT_CONTROL": {
                1:"Logical name", 2:"Output state", 3:"Control mode", 4:"Default mode"
            },
            "ASSOCIATION_LOGICAL_NAME": {
                1:"Logical name", 2:"Object list", 3:"Associated partners ID", 4:"Application context name",
                5:"xDLMS context info", 6:"Authentication mechanism name", 7:"Secret", 8:"Association status",
                9:"Security setup reference", 10:"User list", 11:"Current user"
            }
        }
        method_name_map = {
            "CLOCK": {
                1:"Adjust to quarter", 2:"Adjust to measure unit", 3:"Adjust to minute",
                4:"Adjust to preset time", 5:"Preset adjusting time", 6:"Shift time"
            },
            "PROFILE_GENERIC": {1:"Capture", 2:"Clear"},
            "DISCONNECT_CONTROL": {1:"Remote disconnect", 2:"Remote reconnect"},
            "SECURITY_SETUP": {1:"Update key", 2:"Activate key"},
            "DEMAND_REGISTER": {1:"Reset"},
            "ASSOCIATION_LOGICAL_NAME": {
                1:"Reply to hls authentication", 2:"Change hls secret", 3:"Add object",
                4:"Remove object", 5:"Add user", 6:"Remove user"
            }
        }

        with open("OBSIS_Detailed.txt", "w") as f:
            for obj in client.objects:
                obj_type_name = "Unknown"
                try:
                    if hasattr(obj.objectType, 'name'):
                        obj_type_name = obj.objectType.name
                    else:
                        obj_type_name = str(obj.objectType)
                except:
                    obj_type_name = str(obj.objectType)
                
                header = f"OBIS: {obj.logicalName} ({obj_type_name})"
                print(header)
                f.write(header + "\n")
                
                # Get Attribute Names
                attr_names = {}
                if hasattr(obj, "getNames"):
                    try:
                        names_arr = obj.getNames()
                        for i, nm in enumerate(names_arr, start=1):
                            attr_names[i] = str(nm)
                    except:
                        pass
                # Merge with fallback map
                fallback = attr_name_map.get(obj_type_name, {})
                for k, v in fallback.items():
                    attr_names.setdefault(k, v)
                
                # Determine number of attributes
                attr_count = 0
                if hasattr(obj, "getAttributeCount"):
                    try:
                        attr_count = obj.getAttributeCount()
                    except:
                        pass
                
                if attr_count > 0:
                    f.write("  Attributes:\n")
                    # Iterate all standard attributes
                    for i in range(1, attr_count + 1):
                        # Access
                        access = obj.getAccess(i)
                        access_str = str(access)
                        try:
                            access_str = AccessMode(access).name
                        except:
                            pass
                        
                        # Data Type
                        dtype = DataType.NONE
                        att_setting = obj.attributes.find(i)
                        if att_setting:
                            dtype = att_setting.type_
                        
                        if dtype == DataType.NONE:
                            try:
                                dtype = obj.getUIDataType(i)
                            except:
                                pass
                        
                        dtype_str = str(dtype)
                        try:
                            dtype_str = DataType(dtype).name
                        except:
                            pass
                        
                        attr_name = attr_names.get(i, f"Attribute {i}")
                        attr_info = f"    {i}. {attr_name}: Access={access_str}, Type={dtype_str}"
                        print(attr_info)
                        f.write(attr_info + "\n")
                
                # Methods
                method_names = {}
                if hasattr(obj, "getMethodNames"):
                    try:
                        m_names_arr = obj.getMethodNames()
                        for i, nm in enumerate(m_names_arr, start=1):
                            method_names[i] = str(nm)
                    except:
                        pass
                # Merge with fallback map
                m_fallback = method_name_map.get(obj_type_name, {})
                for k, v in m_fallback.items():
                    method_names.setdefault(k, v)
                
                method_count = 0
                if hasattr(obj, "getMethodCount"):
                    try:
                        method_count = obj.getMethodCount()
                    except:
                        pass
                
                if method_count > 0:
                    f.write("  Methods:\n")
                    for i in range(1, method_count + 1):
                        m_access = obj.getMethodAccess(i)
                        m_access_str = str(m_access)
                        try:
                            m_access_str = MethodAccessMode(m_access).name
                        except:
                            pass
                        
                        method_name = method_names.get(i, f"Method {i}")
                        method_info = f"    {i}. {method_name}: Access={m_access_str}"
                        print(method_info)
                        f.write(method_info + "\n")
                
                f.write("-" * 40 + "\n")
            
        # Example: Read Clock
        # clock = client.objects.findByLN(ObjectType.CLOCK, "0.0.1.0.0.255")
        # if clock:
        #     val = reader.read(clock, 2)
        #     print(f"Meter Time: {val}")

    except Exception as ex:
        print("An error occurred during connection:")
        print(ex)
        traceback.print_exc()
    finally:
        print("Closing connection...")
        try:
            reader.close()
        except:
            pass
        if media.isOpen():
            media.close()
        print("Done.")

if __name__ == "__main__":
    main()

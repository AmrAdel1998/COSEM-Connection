import sys
import traceback
from gurux_dlms.enums import InterfaceType, Authentication, Security, Standard, ObjectType
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
AUTHENTICATION_KEY_HEX = "245D0F1DF31C4380135AC91D4A22023D"
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
        for obj in client.objects:
            obj_type_name = "Unknown"
            try:
                if hasattr(obj.objectType, 'name'):
                    obj_type_name = obj.objectType.name
                else:
                    obj_type_name = str(obj.objectType)
            except:
                obj_type_name = str(obj.objectType)
                
            print(f" - {obj.logicalName} ({obj_type_name})")
            
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

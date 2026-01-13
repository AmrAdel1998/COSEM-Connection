import pytest
import sys
import time
from gurux_dlms.enums import ObjectType
from connect_meter import initialize_client

# Define the expected data structure
# (Test Name, Logical Name, Object Type, Attribute Index, Expected Value, Expected Access)
# Access: "GET" = Expect Success, "NONE" = Expect Failure/Access Denied
TEST_DATA = [
    # 1. Manufacturing Number
    ("Manufacturing Number - Value", "0.0.96.1.0.255", ObjectType.DATA, 2, None, "GET"),
    
    # 2. Metering Point Identifier
    ("Metering Point Identifier - Value", "0.0.96.1.10.255", ObjectType.DATA, 2, None, "GET"),
    
    # 3. Equipment Class Identifier
    ("Equipment Class Identifier - Value", "0.0.96.1.3.255", ObjectType.DATA, 2, None, "GET"),

    # 4. Timeout GPRS
    ("Timeout GPRS - Value", "0.0.94.39.52.255", ObjectType.DATA, 2, None, "GET/SET"),
]

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

@pytest.mark.parametrize("name, logical_name, obj_type, attr_index, expected_value, access", TEST_DATA)
def test_obis_read(meter_connection, name, logical_name, obj_type, attr_index, expected_value, access):
    """
    Test case for each OBIS code.
    Verifies that the object exists and access rights (Read) work as expected.
    """
    client, reader = meter_connection
    
    print(f"\nTesting: {name} (OBIS: {logical_name}, Attr: {attr_index})")
    
    # 1. Find the object in the Association View
    obj = client.objects.findByLN(obj_type, logical_name)
    
    if not obj:
        # If object is not in association view
        if "GET" in access:
            pytest.fail(f"Object {logical_name} not found in Association View (Cannot Read).")
        else:
            print(f" -> Object not found, as expected (Access: {access})")
            return

    # 2. Check Access Rights
    if "GET" in access:
        try:
            val = reader.read(obj, attr_index)
            print(f" -> Read Value: {val}")
            
            if val is None:
                pytest.fail(f"Read returned None for {name}")
                
            # 3. Verify Value (if expected value is provided)
            if expected_value is not None:
                # Convert to string for comparison to handle bytearrays/strings diffs
                val_str = str(val)
                exp_str = str(expected_value)
                
                assert val_str == exp_str, f"Value mismatch! Expected: {exp_str}, Got: {val_str}"
                print(" -> Value matches expected.")
            else:
                print(" -> Value read successfully (No specific value expected).")
            
            # 4. Check SET Access (Write back same value)
            if "SET" in access:
                print(f" -> Testing SET access (Writing back same value: {val})...")
                try:
                    # For Data objects, the value is already updated in 'obj' by the read() call
                    # reader.write uses the value currently stored in the object
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

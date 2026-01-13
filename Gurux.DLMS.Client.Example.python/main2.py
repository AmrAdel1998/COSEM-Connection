import sys
import traceback
from GXSettings import GXSettings
from GXDLMSReader import GXDLMSReader

def main():
    args = sys.argv
    settings = GXSettings()
    
    try:
        # Parse CLI args
        ret = settings.getParameters(args)
        if ret != 0:
            return
        
        # Ensure verbose logging
        if settings.trace == settings.trace.VERBOSE:
            print("Trace level: VERBOSE")

        # Open media (serial / TCP)
        settings.media.open()
        print(f"Media opened: {settings.media}")

        # Initialize reader
        reader = GXDLMSReader(settings.client, settings.media, settings.trace, settings.invocationCounter)
        
        # Perform connection / association
        reader.initializeConnection()
        print("Association established successfully ✅")
        
        # Optionally read all objects or specific ones
        if settings.readObjects:
            for ln, idx in settings.readObjects:
                val = reader.read(settings.client.objects.findByLN(None, ln), idx)
                reader.showValue(idx, val)
        else:
            reader.readAll(settings.outputFile)

    except Exception as ex:
        print("Error during connection:", ex)
        traceback.print_exc()
    finally:
        try:
            if settings.media:
                settings.media.close()
        except Exception:
            pass
        print("Ended.")

if __name__ == "__main__":
    main()

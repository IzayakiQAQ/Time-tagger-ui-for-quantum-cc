import time
import sys

try:
    import Swabian.TimeTagger as TimeTagger
except ImportError:
    print("Error: TimeTagger library not found. Please install the Swabian Instruments API.")
    sys.exit(1)

def main():
    # User Input: Replace with the actual IP of Node A
    remote_ip = "192.168.1.100" 
    remote_port = 4444
    address = f"{remote_ip}:{remote_port}"

    print(f"--- Swabian Network Data Debugger ---")
    print(f"Connecting to: {address}")

    try:
        # 1. Connect to the Network TimeTagger
        tagger = TimeTagger.createTimeTaggerNetwork(address)
        print(f"Successfully connected! Remote Serial: {tagger.getSerial()}")
    except Exception as e:
        print(f"FAILED to connect: {e}")
        print("Suggestion: Check WLAN connectivity and firewall on Node A.")
        return

    # 2. Setup a simple Counter to check if raw data is arriving
    channels = [1, 2, 3, 4]
    integration_time_ms = 500
    counter = TimeTagger.Counter(tagger, channels, int(integration_time_ms * 1e9), 1)

    print("\nAttempting to read counts from Node A (Channels 1-4)...")
    print("If counts remain 0.0 despite physical signals, the Data Plane (Firewall) is likely blocked.")
    print("Press Ctrl+C to stop.\n")

    try:
        while True:
            time.sleep(integration_time_ms / 1000.0)
            data = counter.getData()
            rates = [d[0] / (integration_time_ms / 1000.0) / 1000.0 for d in data]
            print(f"Rates (kHz): CH1={rates[0]:.2f}, CH2={rates[1]:.2f}, CH3={rates[2]:.2f}, CH4={rates[3]:.2f}", end="\r")
    except KeyboardInterrupt:
        print("\n\nStopped by user.")
    finally:
        TimeTagger.freeTimeTagger(tagger)

if __name__ == "__main__":
    main()

import requests
import time
import logging
import os
import sys

# Configuration
M2000_IP = os.environ.get("M2000_IP", "192.168.0.1")
M2000_URL = f"http://{M2000_IP}/webapi/"
ADMIN_PASSWORD = os.environ.get("M2000_PASSWORD", "password_here")
CHECK_INTERVAL = 300  # 5 minutes
FAILURE_THRESHOLD = 12 # 12 * 5 minutes = 1 hour
REBOOT_WAIT_TIME = 300  # 5 minutes
CHECK_HOST = "8.8.8.8"

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

def check_connectivity():
    try:
        # Use a short timeout for the check
        response = requests.head(f"http://{CHECK_HOST}", timeout=5)
        return response.status_code < 400
    except (requests.ConnectionError, requests.Timeout):
        # Also try a simple socket check if HTTP fails
        try:
            import socket
            socket.create_connection((CHECK_HOST, 53), timeout=5)
            return True
        except (socket.error, socket.timeout):
            return False

def login():
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "user_login",
        "params": {
            "user": "admin",
            "pwd": ADMIN_PASSWORD
        }
    }
    try:
        response = requests.post(M2000_URL, json=payload, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if "result" in data and "token" in data["result"]:
                logging.info("Successfully logged into M2000")
                return data["result"]["token"]
            else:
                logging.error(f"Login response missing token: {data}")
    except Exception as e:
        logging.error(f"Login request failed: {e}")
    return None

def reboot(token):
    if not token:
        return False
    
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "system_reboot",
        "params": {}
    }
    headers = {
        "token": token
    }
    
    try:
        response = requests.post(M2000_URL, json=payload, headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if "result" in data:
                logging.info("Reboot command sent successfully")
                return True
            else:
                logging.error(f"Reboot response error: {data}")
    except Exception as e:
        logging.error(f"Reboot request failed: {e}")
    return False

def main():
    consecutive_failures = 0
    logging.info(f"Starting M2000 monitor. Target IP: {M2000_IP}, Check Host: {CHECK_HOST}")
    
    # Check if we can reach the M2000 at all
    try:
        requests.get(f"http://{M2000_IP}/", timeout=5)
    except Exception:
        logging.error(f"Warning: Cannot reach M2000 at {M2000_IP}. Check connection and IP.")

    while True:
        if check_connectivity():
            if consecutive_failures > 0:
                logging.info("Connection restored")
            consecutive_failures = 0
        else:
            consecutive_failures += 1
            logging.warning(f"Connectivity check failed ({consecutive_failures}/{FAILURE_THRESHOLD})")
            
            if consecutive_failures >= FAILURE_THRESHOLD:
                logging.error("Failure threshold reached. Initiating M2000 reboot...")
                token = login()
                if token:
                    if reboot(token):
                        logging.info(f"Waiting {REBOOT_WAIT_TIME}s for reboot...")
                        time.sleep(REBOOT_WAIT_TIME)
                        consecutive_failures = 0
                        continue
                
                logging.error("Reboot process failed. Retrying in next interval.")
        
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()

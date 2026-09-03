import requests
import time
import logging
import os
import sys
import socket

# Configuration
M2000_IP = os.environ.get("M2000_IP", "192.168.0.1")
M2000_URL = f"http://{M2000_IP}/webapi/"
ADMIN_PASSWORD = os.environ.get("M2000_PASSWORD", "password_here")
CHECK_INTERVAL = int(os.environ.get("CHECK_INTERVAL", 300))      # 5 minutes
FAILURE_THRESHOLD = int(os.environ.get("FAILURE_THRESHOLD", 12))  # 12 * 5 minutes = 1 hour
REBOOT_WAIT_TIME = int(os.environ.get("REBOOT_WAIT_TIME", 300))   # 5 minutes

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

def is_router_reachable():
    """Check if the local M2000 router at M2000_IP is reachable via TCP port 80."""
    try:
        s = socket.create_connection((M2000_IP, 80), timeout=3)
        s.close()
        return True
    except Exception:
        return False

def check_wan_connectivity():
    """Verify internet connectivity using minimal bandwidth HTTP HEAD requests.
    
    Uses Cloudflare (1.1.1.1, 1.0.0.1) which explicitly serve HTTP on port 80.
    A HEAD request only fetches response headers (no body), consuming ~300 bytes per check.
    """
    for host in ["1.1.1.1", "1.0.0.1"]:
        try:
            response = requests.head(f"http://{host}", timeout=3)
            if response.status_code in [200, 301, 302]:
                return True
        except (requests.ConnectionError, requests.Timeout):
            pass

    return False

def login(max_retries=3):
    """Log in to M2000 and return session token with retries."""
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "user_login",
        "params": {
            "user": "admin",
            "pwd": ADMIN_PASSWORD
        }
    }
    for attempt in range(1, max_retries + 1):
        try:
            response = requests.post(M2000_URL, json=payload, timeout=8)
            if response.status_code == 200:
                data = response.json()
                if "result" in data and "token" in data["result"]:
                    logging.info("Successfully logged into M2000")
                    return data["result"]["token"]
                else:
                    logging.error(f"Login response missing token: {data}")
        except Exception as e:
            logging.warning(f"Login attempt {attempt}/{max_retries} failed: {e}")
        
        if attempt < max_retries:
            time.sleep(3)
    return None

def reboot(token):
    """Trigger system reboot on M2000 using a valid session token."""
    if not token:
        return False
    
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "system_reboot",
        "params": {
            "token": token
        }
    }
    
    try:
        response = requests.post(M2000_URL, json=payload, timeout=8)
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
    consecutive_wan_failures = 0
    logging.info(f"Starting M2000 monitor. Target IP: {M2000_IP}, Check Endpoints: 1.1.1.1 / 1.0.0.1 (port 80 HEAD)")
    
    if is_router_reachable():
        logging.info(f"Local connection to router at {M2000_IP} is active.")
    else:
        logging.warning(f"Warning: Cannot reach M2000 at {M2000_IP}. Check Wi-Fi/Ethernet connection and IP.")

    while True:
        wan_ok = check_wan_connectivity()
        router_ok = is_router_reachable()

        if wan_ok:
            if consecutive_wan_failures > 0:
                logging.info("Internet connection restored.")
            consecutive_wan_failures = 0
        else:
            consecutive_wan_failures += 1
            
            if not router_ok:
                logging.warning(
                    f"Internet check failed ({consecutive_wan_failures}/{FAILURE_THRESHOLD}) "
                    f"AND router at {M2000_IP} is unreachable (local Wi-Fi down or router off)."
                )
            else:
                logging.warning(
                    f"Router reachable, but Internet check failed ({consecutive_wan_failures}/{FAILURE_THRESHOLD})"
                )
            
            if consecutive_wan_failures >= FAILURE_THRESHOLD:
                if not router_ok:
                    logging.error(
                        f"Failure threshold reached, but router at {M2000_IP} is unreachable over local network. "
                        "Cannot send reboot command. Check Wi-Fi or physical connection."
                    )
                    consecutive_wan_failures = 0
                else:
                    logging.error("Failure threshold reached and router is reachable. Initiating M2000 reboot...")
                    consecutive_wan_failures = 0
                    token = login()
                    if token:
                        if reboot(token):
                            logging.info(f"Waiting {REBOOT_WAIT_TIME}s for reboot...")
                            time.sleep(REBOOT_WAIT_TIME)
                            continue
                    
                    logging.error("Reboot process failed. Retrying in next interval.")
        
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()

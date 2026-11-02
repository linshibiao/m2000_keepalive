import requests
import time
import logging
import os
import sys
import socket

# Configuration
# Env var names are historical (this project was started for an Inseego M2000).
# The device in use is a T-Mobile B321MH hotspot at the same API.
M2000_IP = os.environ.get("M2000_IP", "192.168.0.1")
M2000_URL = f"http://{M2000_IP}/webapi/"
ADMIN_PASSWORD = os.environ.get("M2000_PASSWORD", "password_here")
CHECK_INTERVAL = int(os.environ.get("CHECK_INTERVAL", 300))      # 5 minutes
FAILURE_THRESHOLD = int(os.environ.get("FAILURE_THRESHOLD", 12))  # 12 * 5 minutes = 1 hour
REBOOT_WAIT_TIME = int(os.environ.get("REBOOT_WAIT_TIME", 300))   # 5 minutes
DEVICE_NAME = "B321MH"
# Wi-Fi-only devices to mention in logs (USB cannot reach these). Comma-separated.
WIFI_CHECK_IPS = [
    ip.strip()
    for ip in os.environ.get("WIFI_CHECK_IPS", "192.168.0.128").split(",")
    if ip.strip()
]

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

def is_router_reachable():
    """Check if the local B321MH router at M2000_IP is reachable via TCP port 80."""
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

def login(max_retries=3, quiet=False):
    """Log in to the B321MH and return session token with retries."""
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
                    if not quiet:
                        logging.info(f"Successfully logged into {DEVICE_NAME}")
                    return data["result"]["token"]
                else:
                    logging.error(f"Login response missing token: {data}")
        except Exception as e:
            logging.warning(f"Login attempt {attempt}/{max_retries} failed: {e}")
        
        if attempt < max_retries:
            time.sleep(3)
    return None

def reboot(token):
    """Trigger system reboot on the B321MH using a valid session token."""
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

def api_call(token, method, extra_params=None):
    params = {"token": token}
    if extra_params:
        params.update(extra_params)
    response = requests.post(
        M2000_URL,
        json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
        timeout=8,
    )
    response.raise_for_status()
    data = response.json()
    if "error" in data:
        raise RuntimeError(data["error"])
    return data.get("result") or {}

def get_wifi_status():
    """Read hotspot Wi-Fi AP state via JSON-RPC (works over USB). Ping is not used:
    USB clients cannot reach Wi-Fi clients on this hotspot.
    """
    token = login(quiet=True)
    if not token:
        return None
    statusbar = api_call(token, "status_get_statusbar_info").get("statusbar_info") or {}
    devices = api_call(token, "connectivity_get_connected_devices").get("connected_devices") or []
    wifi_clients = []
    for dev in devices:
        if dev.get("tethering_type") == 1:
            continue
        ip = (dev.get("ipAddr") or "").split("/")[0]
        wifi_clients.append({"ip": ip, "name": dev.get("name") or "*"})
    missing = []
    present_ips = {c["ip"] for c in wifi_clients}
    for ip in WIFI_CHECK_IPS:
        if ip not in present_ips:
            missing.append(ip)
    enabled = bool(statusbar.get("wifi_enabled", 1))
    ap_down = (not enabled) or (len(wifi_clients) == 0)
    return {
        "enabled": enabled,
        "wifi_clients": wifi_clients,
        "missing_check_ips": missing,
        "ap_down": ap_down,
    }

def main():
    consecutive_wan_failures = 0
    wifi_was_down = False
    wifi_missing_was = set()
    logging.info(
        f"Starting {DEVICE_NAME} monitor. Target IP: {M2000_IP}, "
        "Check Endpoints: 1.1.1.1 / 1.0.0.1 (port 80 HEAD), "
        f"Wi-Fi watch IPs: {WIFI_CHECK_IPS or 'none'}"
    )
    
    if is_router_reachable():
        logging.info(f"Local connection to router at {M2000_IP} is active.")
    else:
        logging.warning(
            f"Warning: Cannot reach {DEVICE_NAME} at {M2000_IP}. "
            "Check Wi-Fi/Ethernet connection and IP."
        )

    while True:
        wan_ok = check_wan_connectivity()
        router_ok = is_router_reachable()

        if router_ok:
            try:
                wifi = get_wifi_status()
            except Exception as e:
                logging.warning(f"Wi-Fi status check failed: {e}")
                wifi = None
            if wifi is not None:
                if wifi["ap_down"]:
                    if not wifi_was_down:
                        reasons = []
                        if not wifi["enabled"]:
                            reasons.append("hotspot Wi-Fi is disabled")
                        if len(wifi["wifi_clients"]) == 0:
                            reasons.append("no Wi-Fi clients")
                        logging.warning(
                            "Wi-Fi appears down (" + "; ".join(reasons) + "). "
                            "Internet/USB may still be up; not rebooting for this."
                        )
                    wifi_was_down = True
                elif wifi_was_down:
                    names = [
                        f"{c['ip']}" + (f" ({c['name']})" if c["name"] not in ("", "*") else "")
                        for c in wifi["wifi_clients"]
                    ]
                    logging.info(
                        f"Wi-Fi restored. {len(wifi['wifi_clients'])} Wi-Fi client(s): "
                        + (", ".join(names) if names else "none")
                    )
                    wifi_was_down = False

                missing = set(wifi["missing_check_ips"])
                newly_missing = missing - wifi_missing_was
                if newly_missing:
                    logging.warning(
                        "Wi-Fi device(s) not associated: " + ", ".join(sorted(newly_missing))
                        + ". Not rebooting for this."
                    )
                returned = wifi_missing_was - missing
                if returned:
                    logging.info("Wi-Fi device(s) back: " + ", ".join(sorted(returned)))
                wifi_missing_was = missing

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
                    logging.error(
                        f"Failure threshold reached and router is reachable. "
                        f"Initiating {DEVICE_NAME} reboot..."
                    )
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

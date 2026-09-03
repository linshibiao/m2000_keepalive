# m2000_keepalive

Automated monitor and keepalive service for the Inseego MiFi M2000 hotspot. It detects internet outages, verifies local router reachability, and automatically reboots the hotspot via its web JSON-RPC API when connectivity is lost for over an hour.

Manual test reboot:
```bash
M2000_PASSWORD='kxPhTH6eJj!96hY' python3 -c "import sys; sys.path.append('/home/shibiao/m2000_keepalive'); import m2000_monitor; t=m2000_monitor.login(); m2000_monitor.reboot(t)"
```

---

## USB Connection / Tethering (Recommended)

Connecting the Inseego M2000 to the host Chromebook via a **USB-C cable** instead of relying purely on Wi-Fi is strongly recommended:

* **Why:** If the hotspot's Wi-Fi radio crashes, disconnects, or powers down, a Wi-Fi client cannot reach `http://192.168.0.1/` to issue the reboot command. A direct USB tethering connection keeps the network link to the router alive regardless of Wi-Fi state.
* **No Code Changes Required:** The M2000 uses the same IP (`192.168.0.1`), subnet (`192.168.0.0/24`), and Web API endpoint (`/webapi/`) for both USB tethering and Wi-Fi. ChromeOS automatically detects the USB connection as an Ethernet interface and routes Crostini/Tailscale traffic through it.
* **Setup on M2000:**
  1. Connect a USB-C cable between the M2000 and the Chromebook.
  2. When prompted on the M2000 touch screen, select **"Charge & Tether"** (or in M2000 menu: **Settings** &rarr; **Preferences** &rarr; **USB Mode** &rarr; set to *"Charge & Tether"* / *"Internet access"*).
  3. ChromeOS will display an **Ethernet** icon in the system status tray.

---

## Service Management

Manage the systemd user service:

```bash
# Check status
systemctl --user status m2000-monitor.service

# View live logs
journalctl --user -u m2000-monitor.service -f

# Start / Stop / Restart
systemctl --user start m2000-monitor.service
systemctl --user stop m2000-monitor.service
systemctl --user restart m2000-monitor.service

# Enable auto-start on boot
systemctl --user enable m2000-monitor.service
```

---

## How to See the Logs

You can see all these events in real-time or by looking at the history using `journalctl`.

### 1. See logs in real-time (Follow mode)
```bash
journalctl --user -u m2000-monitor.service -f
```

### 2. Search for specific events (History)
```bash
journalctl --user -u m2000-monitor.service | grep -E "failed|reboot|Successfully|restored"
```

### What to look for in the logs:

* **Startup & LAN Status:**  
  `INFO - Starting M2000 monitor. Target IP: 192.168.0.1, Check Endpoints: 1.1.1.1 / 1.0.0.1 (port 80 HEAD)`  
  `INFO - Local connection to router at 192.168.0.1 is active.`

* **True WAN Outage (Router UP, Internet DOWN):**  
  `WARNING - Router reachable, but Internet check failed (1/12)`  
  *(Counts up to 12 checks = 1 hour before initiating reboot)*

* **Wi-Fi / Physical Link Down (Both DOWN):**  
  `WARNING - Internet check failed (1/12) AND router at 192.168.0.1 is unreachable (local Wi-Fi down or router off).`

* **Reboot Sequence:**  
  `ERROR - Failure threshold reached and router is reachable. Initiating M2000 reboot...`  
  `INFO - Successfully logged into M2000`  
  `INFO - Reboot command sent successfully`  
  `INFO - Waiting 300s for reboot...`

* **Recovery:**  
  `INFO - Internet connection restored.`

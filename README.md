# B321MH keepalive

Simply leave the ChromeOS Linux Terminal window open (you can minimize it or move it to a secondary Virtual Desk). As long as a Crostini window or tab remains open, cros-garcon reports to ChromeOS that Linux is actively in use, preventing the idle shutdown.

Automated monitor and keepalive service for the **T-Mobile B321MH** hotspot (Tinno “Weymouth”). This repo was originally named for the Inseego MiFi M2000; the B321MH uses the same WebUI JSON-RPC API at `http://192.168.0.1/webapi/`. The service detects internet outages, verifies local router reachability, and automatically reboots the hotspot when connectivity is lost for over an hour.

Environment variables `M2000_IP` and `M2000_PASSWORD` are historical names; they still point at the B321MH.

Manual test reboot (uses the password already set in the systemd unit environment):

```bash
python3 -c "import sys; sys.path.append('/home/shibiao/m2000_keepalive'); import m2000_monitor; t=m2000_monitor.login(); m2000_monitor.reboot(t)"
```

---

## USB Connection / Tethering (Recommended)

Connecting the B321MH to the host Chromebook over USB instead of relying purely on Wi-Fi is strongly recommended:

* **Why:** If the hotspot's Wi-Fi radio crashes, disconnects, or powers down, a Wi-Fi client cannot reach `http://192.168.0.1/` to issue the reboot command. A direct USB tethering connection keeps the network link to the router alive regardless of Wi-Fi state.
* **No Code Changes Required:** The B321MH uses the same IP (`192.168.0.1`), subnet (`192.168.0.0/24`), and Web API endpoint (`/webapi/`) for both USB tethering and Wi-Fi. ChromeOS automatically detects the USB connection as an Ethernet interface and routes Crostini/Tailscale traffic through it.
* **Setup on B321MH:**
  1. Connect a data-capable USB cable between the B321MH USB-C port and the Chromebook (USB-A is fine; USB-C on the Chromebook is usually occupied by the Chromebook charger).
  2. In the B321MH WebUI (**System → Device**) or on the USB prompt, set **USB mode when connected to a computer** to **Access internet (USB & Wi-Fi)** (not “Charge the B321MH”). Click **Save**.
  3. ChromeOS will display an **Ethernet** icon in the system status tray.
* USB-A from the Chromebook may trickle-charge the B321MH while tethered, but it is usually not enough to keep a 5G hotspot up 24/7. Prefer a USB-C hub with power passthrough, or a charge+data splitter, if the battery still drops.

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
  `INFO - Starting B321MH monitor. Target IP: 192.168.0.1, Check Endpoints: 1.1.1.1 / 1.0.0.1 (port 80 HEAD)`  
  `INFO - Local connection to router at 192.168.0.1 is active.`

* **True WAN Outage (Router UP, Internet DOWN):**  
  `WARNING - Router reachable, but Internet check failed (1/12)`  
  *(Counts up to 12 checks = 1 hour before initiating reboot)*

* **Wi-Fi / Physical Link Down (Both DOWN):**  
  `WARNING - Internet check failed (1/12) AND router at 192.168.0.1 is unreachable (local Wi-Fi down or router off).`

* **Reboot Sequence:**  
  `ERROR - Failure threshold reached and router is reachable. Initiating B321MH reboot...`  
  `INFO - Successfully logged into B321MH`  
  `INFO - Reboot command sent successfully`  
  `INFO - Waiting 300s for reboot...`

* **Recovery:**  
  `INFO - Internet connection restored.`

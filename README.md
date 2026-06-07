# m2000_keepalive
[How to see the logs]

You can see all these events in real-time or by looking at the history using journalctl. The script is designed to log every failure, every login attempt, and every
  reboot command.

  1. See logs in real-time (Follow mode)
  Run this command to watch the service as it works. It will update automatically whenever a check happens:

   1 journalctl --user -u m2000-monitor.service -f

  2. Search for specific events (History)
  If you want to see a summary of just the important events (failures and reboots) from the past, use this:

   1 journalctl --user -u m2000-monitor.service | grep -E "failed|reboot|Successfully"

  What to look for in the logs:

   * Internet Hiccup: You will see a warning like:  
      WARNING - Connectivity check failed (1/12)  
      (It will count up to 12 before taking action).
   * Reboot Triggered: You will see:  
      ERROR - Failure threshold reached. Initiating M2000 reboot...
   * Login Status:  
      INFO - Successfully logged into M2000
   * Reboot Result:  
      INFO - Reboot command sent successfully  
      INFO - Waiting 300s for reboot...
   * Recovery: When the internet comes back, it logs:  
      INFO - Connection restored

  Example of a "Successful Recovery" log sequence:

   1 02:00:00 - WARNING - Connectivity check failed (1/12)
   2 ... (one hour later) ...
   3 03:00:00 - ERROR - Failure threshold reached. Initiating M2000 reboot...
   4 03:00:01 - INFO - Successfully logged into M2000
   5 03:00:01 - INFO - Reboot command sent successfully
   6 03:00:01 - INFO - Waiting 300s for reboot...
   7 03:05:01 - INFO - Connection restored


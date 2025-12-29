# Debug Steps - No Devices Found Issue

**Date:** 2025-12-29 19:45
**Issue:** Integration loads but reports "No light/cover entities found"

## Added Debug Logging

I've added comprehensive debug logging to help diagnose the issue. Here's what to do:

### Step 1: Enable Debug Logging

Add this to your `configuration.yaml`:

```yaml
logger:
  default: info
  logs:
    custom_components.ipcom: debug
    custom_components.ipcom.coordinator: debug
    custom_components.ipcom.light: debug
    custom_components.ipcom.cover: debug
```

### Step 2: Restart Home Assistant

```
Settings → System → Restart Home Assistant
```

### Step 3: Watch the Logs

After restart, look for these specific log messages in order:

#### ✅ Expected Success Sequence

1. **Integration Setup:**
   ```
   INFO Setting up IPCom integration: megane-david.dyndns.info:5000
   ```

2. **Persistent Connection Start:**
   ```
   INFO Persistent connection started: megane-david.dyndns.info:5000 (updates every 350ms)
   ```

3. **First Update Attempt:**
   ```
   DEBUG No cached data available. Client connected: True
   DEBUG Waiting for first snapshot from persistent connection...
   ```

4. **Snapshot Callback (THIS IS CRITICAL):**
   ```
   DEBUG Received snapshot callback (timestamp: XXXXX)
   DEBUG Converted snapshot to XX devices
   DEBUG Scheduling coordinator update via call_soon_threadsafe
   DEBUG Coordinator update scheduled successfully
   ```

5. **Data Available:**
   ```
   DEBUG Received first snapshot after X.Xs
   DEBUG Returning cached data with XX devices
   ```

6. **Entities Created:**
   ```
   INFO Adding XX light entities
   INFO Adding XX cover entities
   ```

### Step 4: Identify Where It's Failing

Compare the actual logs to the expected sequence above. The failure point will tell us what's wrong:

#### Scenario A: No "Received snapshot callback" message
**Problem:** Snapshots aren't being received from the device
**Possible causes:**
- Background status poll loop not running
- TCP connection not authenticated
- Device not responding to snapshot requests

**Next step:** Check if the device is reachable and authenticated

#### Scenario B: "Received snapshot callback" but "Converted snapshot to 0 devices"
**Problem:** Snapshot is received but contains no data or mapper is empty
**Possible causes:**
- devices.yaml not loaded
- Device mapper not initialized
- Snapshot data is empty

**Next step:** Check devices.yaml file exists and is loaded

#### Scenario C: "Converted snapshot to XX devices" but no entities created
**Problem:** Data conversion works but entities aren't being created
**Possible causes:**
- Data format mismatch
- Category filtering issue
- Platform setup timing issue

**Next step:** Check device categories in the data

#### Scenario D: "Client connected: False"
**Problem:** TCP client never connected
**Possible causes:**
- Network issue
- Authentication failed
- Connection timeout

**Next step:** Check network connectivity and credentials

### Step 5: Additional Diagnostic Commands

If you still have access to the CLI, run these commands:

```bash
# Test connection
python ipcom/ipcom_cli.py status --host megane-david.dyndns.info --port 5000

# List devices
python ipcom/ipcom_cli.py list

# Check devices.yaml exists
ls -la ipcom/devices.yaml
```

### Step 6: Check Full Coordinator Data

Add this temporary debug code to see what coordinator.data contains:

In `custom_components/ipcom/light.py`, change line 38-39 to:

```python
    _LOGGER.debug(f"Coordinator data: {coordinator.data}")
    if coordinator.data and "devices" in coordinator.data:
```

This will show you exactly what the coordinator has when the light platform tries to set up.

## What I Suspect

Based on the symptoms, I suspect one of these issues:

### Most Likely: Callback Not Firing
The persistent connection starts, but the snapshot callback never fires, so `self._latest_data` remains `None`.

This could happen if:
1. The status poll loop isn't running (thread didn't start)
2. The device isn't responding to snapshot requests
3. The receive loop isn't processing responses

### Less Likely: Timing Issue
The callback fires but too late - after the platforms have already tried to set up.

This could happen if:
1. The `async_config_entry_first_refresh()` timeout is too short
2. The callback scheduling isn't working correctly

### Least Likely: Data Format Issue
The callback fires and data is received, but the format doesn't match what the platforms expect.

## Quick Fix to Try

If you want to try a quick fix before checking logs, add this to `coordinator.py` around line 119:

```python
            if success:
                _LOGGER.info(
                    "Persistent connection started: %s:%d (updates every 350ms)",
                    self.host,
                    self.port
                )

                # TEMPORARY: Wait a bit longer for first snapshot
                import asyncio
                await asyncio.sleep(1.0)

            else:
```

This adds a 1-second delay after connection to give the first snapshot time to arrive.

## Next Steps

1. Enable debug logging
2. Restart HA
3. Copy the full log output
4. Share the logs so we can see exactly where it's failing

The debug messages I added will tell us exactly what's happening (or not happening) with the snapshot callbacks.

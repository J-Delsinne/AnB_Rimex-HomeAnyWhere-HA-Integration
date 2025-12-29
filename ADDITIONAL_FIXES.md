# Additional Fixes Applied - 2025-12-29 19:50

## Issue
Integration still reporting "No light/cover entities found" after initial fixes.

## Root Cause Analysis

The problem is a **timing issue**:

1. `start_persistent_connection()` returns `True` when connection is established
2. But the first snapshot hasn't been received yet (takes 350ms for first poll)
3. `async_config_entry_first_refresh()` is called immediately
4. It finds `self._latest_data` is still `None`
5. It waits up to 2 seconds for data
6. **BUT** the callback might not have fired yet or data isn't being received

## Fixes Applied

### Fix 1: Explicit Wait in async_start()

**File:** `custom_components/ipcom/coordinator.py:132-142`

**Change:**
After `start_persistent_connection()` succeeds, explicitly wait up to 1 second for the first snapshot:

```python
if success:
    _LOGGER.info(
        "Persistent connection started: %s:%d (updates every 350ms)",
        self.host,
        self.port
    )

    # Give the persistent connection a moment to receive first snapshot
    # The status poll loop runs every 350ms, so wait up to 1 second
    _LOGGER.debug("Waiting for first snapshot to arrive...")
    for i in range(10):  # Wait up to 1 second (10 * 0.1s)
        if self._latest_data:
            _LOGGER.info(f"First snapshot received after {(i+1)*0.1:.1f}s with {len(self._latest_data.get('devices', {}))} devices")
            break
        await asyncio.sleep(0.1)

    if not self._latest_data:
        _LOGGER.warning("No snapshot received after 1 second - will continue waiting in background")
```

**Why:** This ensures we give the background loops time to:
1. Start the status poll loop (runs every 350ms)
2. Send the first snapshot request
3. Receive the response
4. Trigger the callback
5. Update `self._latest_data`

### Fix 2: Comprehensive Debug Logging

**File:** `custom_components/ipcom/coordinator.py`

**Added logging at critical points:**

1. **Snapshot callback received** (line 94):
   ```python
   _LOGGER.debug(f"Received snapshot callback (timestamp: {snapshot.timestamp})")
   ```

2. **Snapshot converted** (line 98):
   ```python
   _LOGGER.debug(f"Converted snapshot to {len(devices_data)} devices")
   ```

3. **Update scheduled** (lines 108, 112):
   ```python
   _LOGGER.debug("Scheduling coordinator update via call_soon_threadsafe")
   # ... schedule update ...
   _LOGGER.debug("Coordinator update scheduled successfully")
   ```

4. **Data availability check** (lines 220, 224):
   ```python
   _LOGGER.debug(f"Returning cached data with {len(self._latest_data.get('devices', {}))} devices")
   # or
   _LOGGER.debug(f"No cached data available. Client connected: {self._client.is_connected() if self._client else False}")
   ```

**Why:** These logs will tell us exactly:
- Whether snapshots are being received
- Whether the callback is firing
- Whether data conversion is working
- Whether the coordinator update is being triggered
- What state the client is in

## Testing Instructions

### Step 1: Enable Debug Logging

Add to `configuration.yaml`:

```yaml
logger:
  default: info
  logs:
    custom_components.ipcom: debug
    custom_components.ipcom.coordinator: debug
```

### Step 2: Delete Integration and Restart

1. Settings → Devices & Services → IPCom → **DELETE**
2. Settings → System → **Restart Home Assistant**

### Step 3: Re-add Integration

Settings → Devices & Services → Add Integration → IPCom

**Configuration:**
- CLI Path: `ipcom/ipcom_cli.py`
- Host: `megane-david.dyndns.info`
- Port: `5000`
- Scan Interval: `10`

### Step 4: Check Logs

Look for this exact sequence:

```
INFO Setting up IPCom integration: megane-david.dyndns.info:5000
INFO Persistent connection started: megane-david.dyndns.info:5000 (updates every 350ms)
DEBUG Waiting for first snapshot to arrive...
DEBUG Received snapshot callback (timestamp: XXXXX)  ← CRITICAL
DEBUG Converted snapshot to XX devices  ← CRITICAL
DEBUG Scheduling coordinator update via call_soon_threadsafe
DEBUG Coordinator update scheduled successfully
INFO First snapshot received after 0.Xs with XX devices  ← SUCCESS
DEBUG Returning cached data with XX devices
INFO Adding XX light entities  ← SUCCESS
INFO Adding XX cover entities  ← SUCCESS
```

### Step 5: Diagnosis

**If you see:**
- ✅ "First snapshot received after 0.Xs with XX devices" → **SUCCESS**
- ❌ "No snapshot received after 1 second" → **Snapshots not arriving**
- ❌ "Converted snapshot to 0 devices" → **Snapshot empty or mapper issue**
- ❌ No "Received snapshot callback" → **Callback not firing**

## Expected Results

### ✅ Success Indicators

1. **Logs show:**
   - Persistent connection started
   - First snapshot received within 350-700ms
   - Devices found (XX > 0)
   - Entities created

2. **UI shows:**
   - Integration: "XX devices"
   - Entities appear in Developer Tools → States
   - No errors in logs

### ❌ Failure Indicators

1. **No snapshot callback:**
   - Status poll loop not running
   - Device not responding
   - Network/auth issue

2. **Snapshot callback fires but 0 devices:**
   - devices.yaml not loaded
   - Device mapper empty
   - Snapshot data format issue

3. **Devices found but entities not created:**
   - Category mismatch
   - Platform setup issue
   - Data format mismatch

## If Still Failing

If you still get "No devices found" after these fixes, share the full log output including:

1. The entire startup sequence
2. Any errors or warnings
3. Whether you see "Received snapshot callback" messages
4. What "Converted snapshot to X devices" shows

This will tell us exactly where the flow is breaking.

## Files Modified

1. **`custom_components/ipcom/coordinator.py`**
   - Added explicit 1-second wait after connection (lines 132-142)
   - Added debug logging in callback (lines 94, 98, 108, 112)
   - Added debug logging in _async_update_data (lines 220, 224)

## Summary

The key insight is that `start_persistent_connection()` returning `True` doesn't guarantee data is available yet. We need to:

1. Wait for the status poll loop to run (350ms interval)
2. Wait for the first snapshot request to be sent
3. Wait for the response to arrive
4. Wait for the callback to fire and update `self._latest_data`

The new 1-second wait in `async_start()` gives this entire process time to complete before we proceed with platform setup.

**Expected timeline:**
- T+0ms: Connection established, loops started
- T+350ms: First status poll runs, sends snapshot request
- T+400-600ms: Response arrives, callback fires, data available
- T+1000ms: Wait completes, proceed with setup

**Status:** ✅ **READY FOR TESTING**

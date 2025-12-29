# 🔍 Enhanced Diagnostic Logging

**Date:** 2025-12-29 21:20
**Status:** 🔬 **DIAGNOSTIC MODE ACTIVATED**

## Changes Made

### 1. Fixed Async Coroutine Scheduling
**File:** `custom_components/ipcom/coordinator.py:123-136`

Changed from `call_soon_threadsafe()` to `asyncio.run_coroutine_threadsafe()`:

```python
async def update_and_notify():
    """Update data and notify all listening entities."""
    self.data = self._latest_data
    self.last_update_success = True
    self.async_update_listeners()

# Schedule the coroutine in the event loop
asyncio.run_coroutine_threadsafe(update_and_notify(), self.hass.loop)
```

**Why:** `async_update_listeners()` is likely an async method, so we need to properly schedule the coroutine from the worker thread.

### 2. Added Call Counter to is_on Property
**File:** `custom_components/ipcom/light.py:148-162`

Added diagnostic logging to track:
- How many times `is_on` is called
- Log every state change
- Log every 10th call even if state unchanged

```python
# Count how many times this is called
if not hasattr(self, "_is_on_call_count"):
    self._is_on_call_count = 0
self._is_on_call_count += 1

# Log first time or when state changes
if not hasattr(self, "_last_state") or self._last_state != result:
    _LOGGER.critical("💡 Light %s: is_on=%s [call #%d]", ...)
elif self._is_on_call_count % 10 == 0:
    # Log every 10th call even if state hasn't changed
    _LOGGER.critical("💡 Light %s: is_on=%s (unchanged) [call #%d]", ...)
```

## What to Look For in Logs

### Test 1: Are Properties Being Called?

**After restart, grep for:**
```bash
grep "call #" home-assistant.log
```

**Expected if WORKING:**
```
💡 Light keuken: is_on=True [call #1]
💡 Light keuken: is_on=True (unchanged) [call #10]
💡 Light keuken: is_on=True (unchanged) [call #20]
💡 Light keuken: is_on=True (unchanged) [call #30]
```

**If BROKEN (current state):**
```
💡 Light keuken: is_on=True [call #1]
(nothing else - only called once at startup)
```

### Test 2: Are Listeners Being Notified?

**Grep for:**
```bash
grep "Notifying.*listeners" home-assistant.log
```

**Expected:**
```
📡 Notifying 16 listeners
📡 Notifying 16 listeners
📡 Notifying 16 listeners
```

Every ~350ms

### Test 3: Is async_update_listeners Working?

If we see:
- ✅ "Notifying X listeners" every 350ms
- ✅ "call #10", "call #20" etc in logs
- **THEN:** Entities ARE being updated!

If we see:
- ✅ "Notifying X listeners" every 350ms
- ❌ Only "call #1" (no subsequent calls)
- **THEN:** `async_update_listeners()` is not working

## Possible Outcomes

### Outcome A: Properties Being Called Repeatedly
**Logs show:** `call #10`, `call #20`, `call #30`, etc.

**Meaning:**
- ✅ Listeners are being notified
- ✅ Entity properties are being called
- ✅ Mechanism is working!

**Next step:** Check if UI is updating (maybe it's a frontend cache issue)

### Outcome B: Properties Only Called Once
**Logs show:** Only `call #1` for each entity, nothing more

**Meaning:**
- ✅ Listeners are being notified (we see the log)
- ❌ But `async_update_listeners()` is not triggering entity updates
- ❌ Wrong method or wrong usage

**Next step:** Research correct Home Assistant method to trigger entity state updates

### Outcome C: Error in Coroutine Scheduling
**Logs show:** Error about coroutines or event loops

**Meaning:**
- ❌ `asyncio.run_coroutine_threadsafe()` not working correctly
- ❌ Need different approach

**Next step:** Try alternative scheduling method

## What I Suspect

Based on previous logs showing "Notifying 16 listeners" but only 12 `is_on` calls (once each), I suspect:

**Hypothesis:** `async_update_listeners()` exists but doesn't do what we think. It might:
- Just notify that "something changed" without forcing property re-evaluation
- Require a different pattern (like marking entities as "stale")
- Not be the right method for push updates

**Alternative approaches to try if this doesn't work:**
1. Call `async_write_ha_state()` on each entity directly
2. Use `async_request_refresh()` instead
3. Manually iterate through `self._listeners` and call their update methods

## Testing Instructions

1. **Restart Home Assistant**

2. **Wait 10 seconds** (let it run for ~30 updates)

3. **Check logs:**
```bash
# Count total is_on calls
grep -c "call #" home-assistant.log

# See call numbers
grep "call #" home-assistant.log | head -20

# Count listener notifications
grep -c "Notifying.*listeners" home-assistant.log
```

4. **Expected Results:**
   - If working: 300+ is_on calls (12 entities × ~30 updates)
   - If broken: 12 is_on calls (one per entity)

5. **Report back** with:
   - Number of `call #` occurrences
   - Whether you see `call #10`, `call #20`, etc.
   - Any errors in the log

---

**Next Action:** Restart HA, wait 10 seconds, check logs for call counters

This diagnostic logging will definitively show us if entities are being updated or not!

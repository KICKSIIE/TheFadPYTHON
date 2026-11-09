/** Closes forgotten shifts every 30 seconds, even when nobody is browsing. */
import * as attendanceStore from './attendance_store.js';

export function startShiftSweeper(intervalMs = 30000) {
  const tick = () => {
    attendanceStore.closeExpired().catch((error) => {
      console.warn('Attendance closure failed:', error.message);
    });
  };
  tick();
  const timer = setInterval(tick, intervalMs);
  timer.unref?.();
  return timer;
}

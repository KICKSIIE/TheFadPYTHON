/**
 * Shop-time helpers. PostgreSQL stores shop-local wall-clock timestamps; they are parsed with the fixed
 * +08:00 offset (the Philippines has no daylight saving), so formatting never depends on the server zone.
 */
import { SHOP_OFFSET_MINUTES } from './config.js';

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const DAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
const OFFSET_MS = SHOP_OFFSET_MINUTES * 60 * 1000;

export function shopNow() {
  return new Date();
}

export function parseTimestamp(value) {
  if (value === null || value === undefined) return null;
  if (value instanceof Date) return value;
  const text = String(value).replace(' ', 'T');
  return new Date(text.length <= 10 ? `${text}T00:00:00+08:00` : `${text}+08:00`);
}

export function parseDate(value) {
  return parseTimestamp(value);
}

export function shopParts(date) {
  const shifted = new Date(date.getTime() + OFFSET_MS);
  return {
    year: shifted.getUTCFullYear(),
    month: shifted.getUTCMonth(),
    day: shifted.getUTCDate(),
    hours: shifted.getUTCHours(),
    minutes: shifted.getUTCMinutes(),
    seconds: shifted.getUTCSeconds(),
    weekday: shifted.getUTCDay(),
  };
}

const pad = (value, width = 2) => String(value).padStart(width, '0');

export function isoDate(value) {
  if (!value) return '';
  const p = shopParts(value);
  return `${p.year}-${pad(p.month + 1)}-${pad(p.day)}`;
}

export function isoTime(value) {
  const p = shopParts(value);
  return `${pad(p.hours)}:${pad(p.minutes)}`;
}

export function strftime(value, format) {
  if (!value) return '';
  const p = shopParts(value);
  const hour12 = ((p.hours + 11) % 12) + 1;
  const replacements = {
    '%a': DAYS[p.weekday],
    '%A': ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'][p.weekday],
    '%b': MONTHS[p.month],
    '%B': ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September',
      'October', 'November', 'December'][p.month],
    '%d': pad(p.day),
    '%H': pad(p.hours),
    '%I': pad(hour12),
    '%M': pad(p.minutes),
    '%m': pad(p.month + 1),
    '%p': p.hours < 12 ? 'AM' : 'PM',
    '%S': pad(p.seconds),
    '%Y': String(p.year),
    '%y': String(p.year).slice(-2),
  };
  return String(format).replace(/%.?/g, (token) => (token in replacements ? replacements[token] : token));
}

/** Combine a shop date (Date or YYYY-MM-DD) with a time string (HH:MM or HH:MM:SS). */
export function combine(dateValue, timeText) {
  const iso = typeof dateValue === 'string' ? dateValue.slice(0, 10) : isoDate(dateValue);
  const time = String(timeText || '00:00').slice(0, 5);
  return new Date(`${iso}T${time}:00+08:00`);
}

export function atShopTime(dateValue, hours, minutes = 0) {
  return new Date(`${isoDate(dateValue)}T${pad(hours)}:${pad(minutes)}:00+08:00`);
}

export function addDays(value, days) {
  const next = new Date(value.getTime());
  next.setUTCDate(next.getUTCDate() + days);
  return next;
}

export function addMinutes(value, minutes) {
  return new Date(value.getTime() + minutes * 60 * 1000);
}

export function addHours(value, hours) {
  return addMinutes(value, hours * 60);
}

export function addSeconds(value, seconds) {
  return new Date(value.getTime() + seconds * 1000);
}

export function isoweekday(value) {
  const day = shopParts(value).weekday;
  return day === 0 ? 7 : day;
}

export function startOfShopDay(value) {
  return combine(value, '00:00');
}

export function hoursBetween(start, end) {
  return (end.getTime() - start.getTime()) / 3600000;
}

export function roundHours(value) {
  return Math.round((value + Number.EPSILON) * 100) / 100;
}

export function todayIso() {
  return isoDate(shopNow());
}

/** Shop-local timestamp text for PostgreSQL parameters ("2026-11-09T09:00:00", no offset). */
export function shopTimestamp(value) {
  const p = shopParts(value);
  return `${p.year}-${pad(p.month + 1)}-${pad(p.day)}T${pad(p.hours)}:${pad(p.minutes)}:${pad(p.seconds)}`;
}

/** Date-only text for PostgreSQL date parameters ("2026-11-09"). */
export function shopDate(value) {
  return isoDate(value);
}

// Templates call Date methods directly, the same shape they had with Python datetimes.
Date.prototype.strftime = function strftimeMethod(format) { return strftime(this, format); };
Date.prototype.isoformat = function isoformatMethod() { return isoDate(this); };

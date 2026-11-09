import dotenv from 'dotenv';

dotenv.config();

/** The shop runs on Philippine time (UTC+08:00, no daylight saving). */
export const SHOP_OFFSET_MINUTES = 8 * 60;

export const config = {
  secretKey: process.env.SECRET_KEY || 'dev-only-change-me',
  databaseUrl: process.env.DATABASE_URL || 'postgresql://postgres:postgres@localhost:5432/THEFAD',
  dbSchema: 'thefad',
  timezone: 'Asia/Manila',

  // Product photos live in the database; refuse bigger uploads before buffering them.
  maxContentLength: 26 * 1024 * 1024,

  mfaEnabled: (process.env.MFA_ENABLED || 'false').toLowerCase() === 'true',
  // Prototype only: unlock navigation so every page opens without an active shift.
  navUnlocked: (process.env.NAV_UNLOCKED || 'false').toLowerCase() === 'true',

  sessionMaxAge: 8 * 60 * 60 * 1000,

  // Defaults until an admin saves the schedule (Attendance > Schedule).
  shiftStart: '09:00:00',
  shiftEnd: '17:00:00',
  graceMinutes: 15,
  shiftHours: 8,
  maxShiftHours: 24,
  workDays: '1,2,3,4,5,6',
  lowStockDefault: 5,

  store: {
    name: 'The Fad',
    tagline: 'Fashion You Always Deserve',
    facebook: 'https://www.facebook.com/profile.php?id=61580609323200',
    plusCode: '8W6X+2QC',
    address: 'G.Y. Dela Serna St, Lapu-Lapu, Cebu',
    mapUrl: 'https://maps.app.goo.gl/fEHAhXsQ6s6VsaWe8',
    latitude: '10.3100695',
    longitude: '123.9493883',
  },
};

export const LOW_STOCK = 5;

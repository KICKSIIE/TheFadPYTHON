/**
 * Run a navigable copy of The Fad for prototyping.
 *
 * Same code and database as the real app, with one difference: every signed-in staff page opens even when
 * no shift is active. The real app (node run.js) keeps the shift gate enforced.
 */
process.env.NAV_UNLOCKED = 'true';

const { initDb } = await import('../db.js');
const { createApp } = await import('../app.js');
const { startShiftSweeper } = await import('../sweeper.js');

initDb();
const app = createApp();
const port = Number(process.env.PORT || 5001);

app.listen(port, '127.0.0.1', () => {
  console.log('Prototype copy: navigation unlocked, no clock-in required.');
  console.log(`Open http://127.0.0.1:${port}/staff and sign in.`);
  startShiftSweeper();
});

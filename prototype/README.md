# Prototype copy (navigation only)

A second way to run The Fad so you can click through every page while the system is still being built.
It is **not** a fork of the code: `run_prototype.js` imports the real app and sets one flag,
`NAV_UNLOCKED`, which skips only the "clock in to a scheduled shift first" redirect. Sign-in, roles and
every database rule behave exactly as in the real app, and both use the same `THEFAD` database.

```powershell
node prototype\run_prototype.js     # or: npm run prototype
```

Open <http://127.0.0.1:5001/staff> and sign in. A yellow banner reminds you that navigation is unlocked.
The real app still runs from the project root on its own port, e.g. `node run.js`.

| | Real app (`node run.js`) | Prototype (`node prototype/run_prototype.js`) |
|---|---|---|
| Clock-in required before other pages | yes | no |
| Sign-in and roles | yes | yes |
| Same database and stored routines | yes | yes |
| Data you change here | real | real, so use demo accounts while prototyping |

If the prototype ever needs to behave differently from the real app in more than navigation, stop
using the shared code and copy the project into this folder instead — a growing mismatch is easier
to spot in one place than hidden behind a flag.

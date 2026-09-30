# Isolated validation

The controller tests and dashboard tests use fake services and temporary settings. They do not use the operator's Credential Manager records, OBS, camera, YouTube or Facebook. The dashboard server refuses automation and OAuth login; it binds only to loopback and exists only while the test runner is active.

## Browser tests

Requires Python 3.12+ and Node 22+. From the repository root:

```
npm ci --prefix qa
node qa/node_modules/playwright/cli.js install chromium
npm test --prefix qa
```

On Linux CI, use `install --with-deps chromium`. The Python executable defaults to `python`; set `PYTHON` if necessary.

The suite runs the actual HTML/JavaScript against the HTTP controller. It covers pairing, first-run defaults, destination validation, custom schedules and camera steps, persistence, cancelled edits, polling during unsaved changes, remote credential restrictions, phone layout, and disconnection/reconnection. Screenshots and a JSON result go into `qa/results/`, which is ignored by Git. Screenshots use dummy data only. Tests never request a real broadcast.

## Controller regression and native Windows smoke test

```
python -m pip install -r app/requirements.txt
python -m unittest discover -s app/tests -v
```

On Windows only:

```
python qa/windows_smoke.py
```

The native smoke test checks Tk initialization, pywin32 user/session lookup and the availability of the Windows Credential Manager backend. It does not read saved passwords, create elevated tasks, launch OBS or test UAC. A passing Windows runner does not prove that the operator's desktop, OBS plugin or live platforms work end to end.

## Continuous checks

`.github/workflows/validation.yml` runs controller tests on Linux and Windows, and browser tests on Linux. The workflow has read-only repository permissions and no deployment or platform secrets. Browser reports are retained as a GitHub Actions artifact for seven days. The production update feed is not modified.

Before a public release, separately supervise Windows account migration, visible/admin OBS launch, the existing stream key, actual start/end, camera steps and locked/sleep recovery on the intended streaming PC.

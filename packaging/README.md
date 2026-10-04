# Windows installation and update layout

`build_windows.py` runs on Windows after installing app/requirements.txt into a clean CPython 3.12 installation. It copies that complete interpreter (including Tcl/Tk and dependencies) next to app/, verifies imports and Tk using the relocated interpreter, and compiles the per-user installer with Inno Setup 6. The runtime's licenses and a dependency inventory are included.

The installer creates Start-menu/Desktop shortcuts and a normal uninstaller. It uses the current user's LocalAppData and does not elevate or silently change OBS privileges. Settings and Windows Credential Manager entries remain outside the installation. Existing in-app ZIP updates swap only app/, retain the bundled interpreter and keep health-check rollback working. Dependency-set changes still require an installer/runtime update; the source updater rejects incompatible dependency changes.

CI builds the installer and performs a silent installation into a temporary directory, validates the installed Python/Tk/dependencies and uninstalls it. It does not run a public broadcast or enroll accounts. Real Windows operator setup and signed distribution remain release gates.

The pilot build is **unsigned**. Signing requires the publisher's valid signing certificate/service and protected CI secrets. No substitute identity or self-signed trust bypass is configured. Production delivery must add Authenticode signing/verification and authenticated release metadata, pin the final dependency inventory, review third-party licenses and validate on a clean non-developer Windows PC.

"""Windowless entry point with a visible recovery message for import failures."""
if __name__ == '__main__':
    try:
        from launcher import main
        main()
    except Exception as exc:
        import ctypes
        ctypes.windll.user32.MessageBoxW(None,
            type(exc).__name__+': Live Desk could not start.\n\n'
            'Run OPEN-LIVE-DESK-DIAGNOSTICS.cmd in this folder to see the error. '
            'Install requirements using INSTALL-REQUIREMENTS.cmd if needed.',
            'Live Desk startup', 0x10)

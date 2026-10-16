"""Windows notification-area icon. Callbacks are queued for the Tk thread."""
import os, threading
from pathlib import Path

class Tray:
    def __init__(self,callback):
        self.callback=callback;self.hwnd=None;self.thread=None;self.ready=threading.Event();self.available=False;self.tip='Live Desk · Automation paused';self.stopping=False
    def start(self):
        if os.name!='nt':return
        self.thread=threading.Thread(target=self.work,daemon=True);self.thread.start()
    def update(self,armed,next_name=''):
        self.tip=('Live Desk · '+('Automation enabled' if armed else 'Automation paused')+' · '+next_name)[:127]
        if self.hwnd:
            try:
                import win32gui,win32con
                win32gui.PostMessage(self.hwnd,win32con.WM_APP+21,0,0)
            except Exception:pass
    def close(self):
        self.stopping=True
        if self.hwnd:
            try:
                import win32gui,win32con
                win32gui.PostMessage(self.hwnd,win32con.WM_CLOSE,0,0)
            except Exception:pass
    def work(self):
        icon=None
        try:
            import win32gui as g,win32con as k,win32api as a
            restart=g.RegisterWindowMessage('TaskbarCreated');update=k.WM_APP+21;event=k.WM_APP+20
            icon=g.LoadImage(0,str(Path(__file__).parent/'web'/'icon.ico'),k.IMAGE_ICON,32,32,k.LR_LOADFROMFILE)
            def notify(which):g.Shell_NotifyIcon(which,(self.hwnd,0,g.NIF_ICON|g.NIF_MESSAGE|g.NIF_TIP,event,icon,self.tip))
            def handler(hwnd,msg,wparam,lparam):
                if msg==restart:
                    try:notify(g.NIM_ADD);self.available=True
                    except Exception:self.available=False
                    return 0
                if msg==update:
                    try:notify(g.NIM_MODIFY)
                    except Exception:self.available=False
                    return 0
                if msg==event:
                    if lparam==k.WM_LBUTTONDBLCLK:self.callback('dashboard')
                    elif lparam==k.WM_RBUTTONUP:
                        menu=g.CreatePopupMenu()
                        for ident,label in [(1,'Open Live Desk'),(2,'Pause automation'),(3,'Quit Live Desk…')]:g.AppendMenu(menu,k.MF_STRING,ident,label)
                        try:
                            g.SetForegroundWindow(hwnd);x,y=g.GetCursorPos()
                            selection=g.TrackPopupMenu(menu,k.TPM_LEFTALIGN|k.TPM_RETURNCMD|k.TPM_NONOTIFY,x,y,0,hwnd,None)
                            if selection:self.callback({1:'dashboard',2:'pause',3:'quit'}[selection])
                            g.PostMessage(hwnd,k.WM_NULL,0,0)
                        finally:g.DestroyMenu(menu)
                    return 0
                if msg==k.WM_CLOSE:
                    g.DestroyWindow(hwnd);return 0
                if msg==k.WM_DESTROY:
                    try:g.Shell_NotifyIcon(g.NIM_DELETE,(hwnd,0))
                    except Exception:pass
                    self.available=False;g.PostQuitMessage(0);return 0
                return g.DefWindowProc(hwnd,msg,wparam,lparam)
            cls=g.WNDCLASS();cls.hInstance=a.GetModuleHandle(None);cls.lpszClassName='LiveDeskTray-'+str(os.getpid());cls.lpfnWndProc=handler
            atom=g.RegisterClass(cls)
            self.hwnd=g.CreateWindow(atom,'Live Desk tray',0,0,0,0,0,0,0,cls.hInstance,None)
            notify(g.NIM_ADD);self.available=True;self.ready.set()
            if self.stopping:g.PostMessage(self.hwnd,k.WM_CLOSE,0,0)
            g.PumpMessages()
            g.UnregisterClass(cls.lpszClassName,cls.hInstance)
        except Exception:self.available=False
        finally:
            self.ready.set();self.hwnd=None
            if icon:
                try:g.DestroyIcon(icon)
                except Exception:pass

"""Windows host for Live Desk. Run with the same Python used for the old app."""
import os, sys, json, socket, threading, webbrowser
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox
from urllib.parse import quote
from config import BASE
from core import atomic_json
from dashboard import Controller, DashboardServer, lan_addresses

class Launcher:
    def __init__(self, root):
        self.root=root; self.closing=False; self.mobile=None; self.updates_dialog=None
        root.title('Live Desk • Development preview'); root.geometry('700x820');root.minsize(670,780)
        root.configure(bg='#f5f4ef')
        self.controller=Controller()
        self.controller.open_updates=lambda:root.after(0,self.open_updates)
        self.server=DashboardServer(('127.0.0.1',8865),self.controller)
        self.controller.desktop_url='http://127.0.0.1:8865'
        threading.Thread(target=self.server.serve_forever,daemon=True).start()
        self.pref_path=BASE/'dashboard.json'
        self.prefs=json.loads(self.pref_path.read_text('utf-8')) if self.pref_path.exists() else {}
        style=ttk.Style();style.theme_use('clam')
        style.configure('TButton',font=('Segoe UI',10),padding=10,background='#e5a473',foreground='#243b32')
        style.configure('TCombobox',padding=8)
        header=tk.Frame(root,bg='#193d36',padx=30,pady=26);header.pack(fill='x')
        tk.Label(header,text=self.controller.cfg['workspace_name'],font=('Segoe UI',10,'bold'),fg='#b9ccba',bg='#193d36').pack(anchor='w')
        tk.Label(header,text='Live Desk',font=('Segoe UI',28,'bold'),fg='#fff5e6',bg='#193d36').pack(anchor='w',pady=(6,3))
        tk.Label(header,text='Your livestream PC. Connected to your phone.',font=('Segoe UI',11),fg='#c4d0bb',bg='#193d36').pack(anchor='w')
        body=tk.Frame(root,bg='#f5f4ef',padx=30,pady=20);body.pack(fill='both',expand=True)
        app_row=tk.Frame(body,bg='#f5f4ef');app_row.pack(fill='x')
        ttk.Button(app_row,text='Open dashboard  ↗',command=self.open_dashboard).pack(side='left',fill='x',expand=True,padx=(0,8))
        ttk.Button(app_row,text='App updates',command=self.open_updates).pack(side='right')
        obs_row=tk.Frame(body,bg='#f5f4ef');obs_row.pack(fill='x',pady=(10,0))
        self.obs_button=ttk.Button(obs_row,text='Open / Show OBS',command=self.open_obs)
        self.obs_button.pack(side='left',fill='x',expand=True,padx=(0,8))
        ttk.Button(obs_row,text='Set up administrator OBS',command=self.setup_obs_admin).pack(side='right')
        self.obs_status=tk.StringVar(value='OBS opens on this desktop. Administrator setup is needed only once.')
        tk.Label(body,textvariable=self.obs_status,font=('Segoe UI',9),fg='#49644e',bg='#f5f4ef',wraplength=620,justify='left').pack(anchor='w',pady=(6,0))
        self.status=tk.StringVar(value='Dashboard running on this PC.')
        tk.Label(body,textvariable=self.status,font=('Segoe UI',10),fg='#49644e',bg='#f5f4ef',wraplength=595,justify='left').pack(anchor='w',pady=(12,18))
        tk.Label(body,text='MOBILE ACCESS',font=('Segoe UI',10,'bold'),fg='#53674f',bg='#f5f4ef').pack(anchor='w')
        tk.Label(body,text='Use the same trusted Wi-Fi as this PC.',font=('Segoe UI',10),fg='#7c8876',bg='#f5f4ef').pack(anchor='w',pady=(6,10))
        addresses=lan_addresses();self.network=tk.StringVar(value=self.prefs.get('ip') if self.prefs.get('ip') in addresses else (addresses[0] if addresses else ''))
        row=tk.Frame(body,bg='#f5f4ef');row.pack(fill='x')
        self.network_box=ttk.Combobox(row,textvariable=self.network,values=addresses,state='readonly',width=23);self.network_box.pack(side='left',fill='x',expand=True,padx=(0,10))
        self.mobile_button=ttk.Button(row,text='Enable mobile access',command=self.toggle_mobile);self.mobile_button.pack(side='right')
        self.phone_url=tk.StringVar(value='Mobile access is off.')
        tk.Entry(body,textvariable=self.phone_url,state='readonly',readonlybackground='#edf1e6',fg='#2f5942',relief='flat',font=('Consolas',13),justify='center').pack(fill='x',ipady=13,pady=(13,12))
        code_row=tk.Frame(body,bg='#f5f4ef');code_row.pack(fill='x')
        tk.Label(code_row,text='Pairing code:',font=('Segoe UI',10),bg='#f5f4ef',fg='#52634d').pack(side='left')
        self.code=tk.StringVar(value=self.server.pair_code)
        tk.Entry(code_row,textvariable=self.code,state='readonly',show='•',readonlybackground='#f5f4ef',relief='flat',font=('Consolas',12),width=20).pack(side='left',padx=12)
        ttk.Button(code_row,text='Show code',command=self.show_code).pack(side='right')
        tk.Label(body,text='Open the phone address in Chrome/Safari, then enter the code.\nLocal HTTP connection: trusted private Wi-Fi only; no internet port forwarding.',font=('Segoe UI',9),bg='#f5f4ef',fg='#7c8876',justify='left',wraplength=590).pack(anchor='w',pady=(12,18))
        row=tk.Frame(body,bg='#f5f4ef');row.pack(fill='x')
        ttk.Button(row,text='Start with Windows',command=self.startup).pack(side='left',padx=(0,8))
        ttk.Button(row,text='Remove startup',command=self.remove_startup).pack(side='left',padx=(0,8))
        ttk.Button(row,text='Settings / logs',command=lambda:os.startfile(BASE)).pack(side='left')
        tk.Label(body,text='Keep this window running; you can minimize it.\nClosing the browser is fine. Scheduled endings run only when configured and automation is enabled.',font=('Segoe UI',10),bg='#f5f4ef',fg='#52634d',justify='left').pack(anchor='w',pady=(18,0))
        root.protocol('WM_DELETE_WINDOW',self.close)
        # A transient wake request, restored when the app exits. Does not unlock Windows.
        import ctypes
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000001)
        if self.prefs.get('mobile') and self.network.get()==self.prefs.get('ip'):
            self.enable_mobile()
        if self.controller.cfg.get('armed'):self.controller.run('arm')
        root.after(500,self.open_dashboard);root.after(1000,self.update_status)
    def open_dashboard(self):webbrowser.open(self.controller.desktop_url+'/#pair='+quote(self.server.pair_code))
    def open_updates(self):
        if self.closing:return
        if self.updates_dialog:self.updates_dialog.window.lift();return
        from updates_ui import UpdatesDialog
        self.updates_dialog=UpdatesDialog(self)
    def setup_obs_admin(self):
        try:os.startfile(str(Path(__file__).with_name('SETUP-OBS-ADMIN.cmd')))
        except OSError:messagebox.showerror('OBS setup','Open SETUP-OBS-ADMIN.cmd from the extracted app folder.')
    def open_obs(self):
        with self.controller.lock:
            if self.controller.maintenance:return
            exe=self.controller.cfg['obs_exe']
        self.obs_button.configure(state='disabled');self.obs_status.set('Opening / showing OBS…')
        def work():
            from obs_windows import open_obs, OBSLaunchError
            try:result=open_obs(exe)
            except OBSLaunchError as exc:result=str(exc)
            self.controller.log(result)
            if not self.closing:self.root.after(0,lambda:self.obs_finished(result))
        threading.Thread(target=work,daemon=True).start()
    def obs_finished(self,result):
        self.obs_status.set(result);self.obs_button.configure(state='normal')
    def show_code(self):
        messagebox.showinfo('Pair this phone',f'Pairing code (case-sensitive):\n\n{self.server.pair_code}\n\nShare only with the person controlling this livestream PC.\nA new code is generated whenever this Windows app restarts.')
    def enable_mobile(self):
        ip=self.network.get()
        if ip not in lan_addresses():
            messagebox.showerror('Network','No matching local network address. Connect the PC to Wi-Fi/Ethernet and reopen the app.');return
        try:
            mobile=DashboardServer((ip,8866),self.controller,self.server.pair_code)
            mobile.allowed_hosts={ip}
            threading.Thread(target=mobile.serve_forever,daemon=True).start();self.mobile=mobile
            with self.controller.lock:
                self.controller.mobile_enabled=True;self.controller.mobile_urls=[f'http://{ip}:8866']
            self.phone_url.set(f'http://{ip}:8866');self.mobile_button.configure(text='Disable mobile access');self.network_box.configure(state='disabled')
            self.prefs.update(mobile=True,ip=ip);atomic_json(self.pref_path,self.prefs)
        except OSError:messagebox.showerror('Mobile access','Could not open port 8866 on this address. Close another copy or choose the correct network.')
    def toggle_mobile(self):
        if self.mobile:
            self.mobile.shutdown();self.mobile.server_close();self.mobile=None
            with self.controller.lock:self.controller.mobile_enabled=False;self.controller.mobile_urls=[]
            self.prefs['mobile']=False;atomic_json(self.pref_path,self.prefs)
            self.phone_url.set('Mobile access is off.');self.mobile_button.configure(text='Enable mobile access');self.network_box.configure(state='readonly')
        else:self.enable_mobile()
    def startup_path(self):return Path(os.environ['APPDATA'])/'Microsoft/Windows/Start Menu/Programs/Startup/ISKCON-Live-Start.lnk'
    def startup(self):
        try:
            import win32com.client
            shortcut=win32com.client.Dispatch('WScript.Shell').CreateShortCut(str(self.startup_path()))
            exe=Path(sys.executable);gui=exe.with_name('pythonw.exe')
            shortcut.Targetpath=str(gui if gui.exists() else exe)
            shortcut.Arguments='"'+str(Path(__file__).resolve())+'"'
            shortcut.WorkingDirectory=str(Path(__file__).parent.resolve());shortcut.save()
            messagebox.showinfo('Startup saved','Live Desk will open after Windows login. This replaces the old app startup shortcut. Keep this folder in its current location.')
        except Exception:messagebox.showerror('Startup','Could not create shortcut. Install requirements with the same Python used to run this app.')
    def remove_startup(self):
        try:self.startup_path().unlink(missing_ok=True);messagebox.showinfo('Startup removed','Automatic app launch removed. Current automation is unchanged.')
        except OSError:messagebox.showerror('Startup','Could not remove shortcut. Check Windows permissions.')
    def update_status(self):
        if self.closing:return
        with self.controller.lock:self.status.set(self.controller.message)
        self.root.after(1000,self.update_status)
    def close(self):
        if self.updates_dialog and self.updates_dialog.busy:
            messagebox.showinfo('Update in progress','Wait for the update operation to finish.');return
        if not messagebox.askyesno('Close Live Desk?','Future starts, scheduled endings, camera actions and phone control will stop. Existing broadcasts continue. Close the app?'):return
        self.closing=True;self.controller.shutdown();self.status.set('Waiting for the current operation to finish…')
        self.wait_close()
    def wait_close(self):
        if self.controller.worker and self.controller.worker.is_alive():self.root.after(300,self.wait_close);return
        for server in [self.mobile,self.server]:
            if server:server.shutdown();server.server_close()
        import ctypes
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
        self.root.destroy()

def main():
    if os.name!='nt':raise SystemExit('Run launcher.py on the Windows livestream PC.')
    root=tk.Tk();root.withdraw();instance=socket.socket()
    try:instance.bind(('127.0.0.1',47639))
    except OSError:
        messagebox.showinfo('App already running','Close the old ISKCON Live Start app or the other Live Desk window first. Only one controller can run.');root.destroy();return
    try:
        Launcher(root);root.deiconify()
        ready=os.environ.pop('ISKCON_UPDATE_READY',None)
        if ready:Path(ready).write_text('ready',encoding='utf-8')
        root.mainloop()
    except Exception as exc:
        messagebox.showerror('Could not open Live Desk',f'{type(exc).__name__}: check requirements, saved settings and ports 8865/8866.\n\nIn this extracted folder run:\npy -m pip install -r requirements.txt\npy launcher.py')
        root.destroy()
    finally:instance.close()

if __name__=='__main__':main()

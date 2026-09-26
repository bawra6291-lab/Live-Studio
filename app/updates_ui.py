"""Desktop-only update controls. No privileged updater or remote install endpoint."""
import json
import os
import shutil
import threading
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from core import atomic_json
from config import BASE
import updater

class UpdatesDialog:
    def __init__(self, launcher):
        self.launcher=launcher;self.root=launcher.root;self.app_dir=Path(__file__).resolve().parent
        self.work=BASE/'updates';self.work.mkdir(parents=True,exist_ok=True)
        self.prefs_path=self.work/'source.json';self.manifest=None;self.busy=False
        self.window=tk.Toplevel(self.root);self.window.title('Live Desk · Updates');self.window.geometry('670x480')
        self.window.minsize(590,430);self.window.configure(bg='#f5f4ef')
        self.window.protocol('WM_DELETE_WINDOW',self.close)
        body=ttk.Frame(self.window,padding=24);body.pack(fill='both',expand=True)
        ttk.Label(body,text='App updates',font=('Segoe UI',20,'bold')).pack(anchor='w')
        ttk.Label(body,text='Installed version '+updater.installed_version(self.app_dir)).pack(anchor='w',pady=(4,16))
        prefs=json.loads(self.prefs_path.read_text('utf-8')) if self.prefs_path.exists() else {}
        self.source=tk.StringVar(value=prefs.get('manifest_url') or updater.DEFAULT_FEED)
        ttk.Label(body,text='Online update address (one-time setup)').pack(anchor='w')
        self.entry=ttk.Entry(body,textvariable=self.source);self.entry.pack(fill='x',pady=(5,8))
        ttk.Label(body,text='Use only the update address supplied by your app maintainer.',wraplength=590).pack(anchor='w')
        row=ttk.Frame(body);row.pack(fill='x',pady=14)
        self.check_button=ttk.Button(row,text='Check for updates',command=self.check);self.check_button.pack(side='left',padx=(0,10))
        self.install_button=ttk.Button(row,text='Download & install',command=self.install,state='disabled');self.install_button.pack(side='left')
        self.status=tk.StringVar(value='Online updates are not connected yet. Add the permanent update address once.' if not self.source.get() else 'Ready to check for a newer version.')
        ttk.Label(body,textvariable=self.status,wraplength=590,justify='left').pack(anchor='w',fill='x',pady=(0,14))
        self.progress=ttk.Progressbar(body,mode='indeterminate');self.progress.pack(fill='x')
        self.local_button=ttk.Button(body,text='Install an update file…',command=self.local);self.local_button.pack(anchor='w',pady=(16,8))
        ttk.Label(body,text='Install while automation is paused and OBS has no active live, recording or replay. The app restarts; saved connections and schedules remain.',wraplength=590,justify='left').pack(anchor='w')
        self.source.trace_add('write',self.source_changed)
        last=self.work/'last-result.json'
        if last.exists():
            try:self.status.set(json.loads(last.read_text('utf-8'))['message'])
            except (ValueError,KeyError):pass
    def source_changed(self,*_):
        self.manifest=None;self.install_button.configure(state='disabled')
    def close(self):
        if self.busy:return
        self.window.destroy();self.launcher.updates_dialog=None
    def controls(self,busy):
        self.busy=busy
        for widget in (self.entry,self.check_button,self.local_button):widget.configure(state='disabled' if busy else 'normal')
        self.install_button.configure(state='normal' if not busy and self.manifest and self.manifest.get('available') else 'disabled')
        if busy:self.progress.start(15)
        else:self.progress.stop()
    def check(self):
        if self.busy:return
        url=self.source.get().strip()
        if not url:
            self.status.set('Online updates need a permanent release address. Connect release hosting first; this is not an “up to date” result.');return
        try:updater.https_url(url)
        except updater.UpdateError as exc:self.status.set(str(exc));return
        previous=json.loads(self.prefs_path.read_text('utf-8')).get('manifest_url') if self.prefs_path.exists() else None
        if url!=previous:
            if not messagebox.askyesno('Use this update source?', 'Updates from this address can replace the app’s code. Use only your app maintainer’s trusted address.\n\n'+url,parent=self.window):return
            atomic_json(self.prefs_path,{'manifest_url':url})
        self.manifest=None;self.controls(True);self.status.set('Checking for updates…')
        def work():
            try:
                manifest=updater.check_feed(url,updater.installed_version(self.app_dir));error=None
            except Exception as exc:manifest=None;error=str(exc)
            self.root.after(0,lambda:self.checked(manifest,error))
        threading.Thread(target=work,daemon=True).start()
    def checked(self,manifest,error):
        self.manifest=manifest;self.controls(False)
        if error:self.status.set(error)
        elif manifest['available']:self.status.set('Version '+manifest['version']+' is available.\n'+manifest['notes'])
        else:self.status.set('No newer version is published at this update address.')
    def local(self):
        if self.busy:return
        path=filedialog.askopenfilename(parent=self.window,title='Choose a trusted Live Desk update',filetypes=[('Live Desk update ZIP','*.zip')])
        if path:self.install(archive=path)
    def install(self,archive=None):
        if self.busy or (not archive and not self.manifest):return
        if not messagebox.askyesno('Install and restart Live Desk?',
            'Install this update and restart the app?\n\nAutomation must already be paused. Updates are blocked while OBS outputs are active or cannot be checked. A backup of the previous app is kept. Only install files from your app maintainer.',parent=self.window):return
        if self.launcher.obs_button.instate(['disabled']):
            self.status.set('Wait for the OBS window operation to finish first.');return
        try:updater.reserve_install(self.launcher.controller)
        except (ValueError,updater.UpdateError) as exc:self.status.set(str(exc));return
        self.controls(True);self.launcher.obs_button.configure(state='disabled')
        self.status.set('Checking OBS, downloading and verifying the update…')
        def work():
            stage=None
            try:
                updater.check_obs_idle(self.launcher.controller)
                stage,release=updater.prepare_update(self.app_dir,self.work,archive,self.manifest if not archive else None)
                updater.check_obs_idle(self.launcher.controller)
                process,job=updater.start_installer(self.app_dir,stage,self.work)
                self.root.after(0,self.finish_install)
            except Exception as exc:
                if stage:shutil.rmtree(stage,ignore_errors=True)
                updater.release_install(self.launcher.controller)
                text=str(exc) if isinstance(exc,(updater.UpdateError,ValueError)) else 'Update could not be prepared. Your installed app is unchanged.'
                self.root.after(0,lambda:self.failed(text))
        threading.Thread(target=work,daemon=True).start()
    def failed(self,text):
        self.controls(False);self.status.set(text);self.launcher.obs_button.configure(state='normal')
    def finish_install(self):
        self.status.set('Restarting Live Desk to install the update…')
        self.launcher.closing=True;self.launcher.controller.shutdown();self.launcher.wait_close()

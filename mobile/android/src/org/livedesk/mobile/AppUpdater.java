package org.livedesk.mobile;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.Intent;
import android.content.pm.PackageInfo;
import android.content.pm.PackageManager;
import android.content.pm.Signature;
import android.net.Uri;
import android.provider.Settings;
import java.io.*;
import java.net.URL;
import java.security.MessageDigest;
import java.util.Arrays;
import javax.net.ssl.HttpsURLConnection;
import org.json.JSONObject;

/** Same-package, same-certificate in-place updates. Nothing is installed silently. */
public final class AppUpdater {
    private static final String FEED="https://raw.githubusercontent.com/bawra6291-lab/Live-Studio/codex/product-foundation/updates/mobile/pilot/latest.json";
    private static boolean working;
    private final Activity activity;
    public AppUpdater(Activity activity) { this.activity=activity; }
    private void message(String text) { activity.runOnUiThread(() -> { if (!activity.isFinishing()) new AlertDialog.Builder(activity).setTitle("App updates").setMessage(text).setPositiveButton("OK",null).show(); }); }
    private static HttpsURLConnection connection(String address) throws Exception {
        URL url=new URL(address);
        if (!"https".equals(url.getProtocol()) || !"raw.githubusercontent.com".equals(url.getHost()) || url.getUserInfo()!=null || (url.getPort()!=-1&&url.getPort()!=443) ||
            !url.getPath().startsWith("/bawra6291-lab/Live-Studio/codex/product-foundation/updates/mobile/pilot/")) throw new IOException("Untrusted update address");
        HttpsURLConnection c=(HttpsURLConnection)url.openConnection();c.setInstanceFollowRedirects(false);c.setConnectTimeout(10000);c.setReadTimeout(15000);c.setRequestProperty("Cache-Control","no-cache");
        if(c.getResponseCode()!=200) { c.disconnect(); throw new IOException("Update server unavailable"); } return c;
    }
    public void check() {
        synchronized(AppUpdater.class) { if(working) { message("An update check or download is already running.");return; } working=true; }
        message("Checking for a new version…");
        new Thread(() -> {
            try {
                File cached=new File(activity.getCacheDir(),"mobile-update.apk");
                int cachedVersion=activity.getSharedPreferences("updates",0).getInt("verifiedVersion",0);
                if(cached.exists()&&cachedVersion>0) {
                    try {
                        verify(activity,cached,cachedVersion);
                        activity.runOnUiThread(() -> new AlertDialog.Builder(activity).setTitle("Downloaded update ready").setMessage("The update is already verified. Install it with your saved pairing retained.").setNegativeButton("Later",null).setPositiveButton("Install",(d,w)->install()).show());return;
                    } catch(Exception ignored) { cached.delete(); }
                }
                String raw; HttpsURLConnection c=connection(FEED);
                try(InputStream in=c.getInputStream();ByteArrayOutputStream out=new ByteArrayOutputStream()) {
                    byte[] buffer=new byte[4096];int n;while((n=in.read(buffer))!=-1) { if(out.size()+n>65536)throw new IOException("Update feed too large");out.write(buffer,0,n); }raw=out.toString("UTF-8");
                } finally { c.disconnect(); }
                JSONObject feed=new JSONObject(raw);
                PackageInfo installed=activity.getPackageManager().getPackageInfo(activity.getPackageName(),0);
                long current=installed.versionCode;
                int code=feed.optInt("version_code",0);
                if(code<=current) { message("You have the latest version ("+installed.versionName+"). Your paired connection stays saved.");return; }
                String url=feed.getString("apk_url"),hash=feed.getString("sha256");long size=feed.getLong("size_bytes");
                if(!hash.matches("[a-f0-9]{64}")||size<1024||size>50*1024*1024)throw new IOException("Invalid update metadata");
                activity.runOnUiThread(() -> new AlertDialog.Builder(activity).setTitle("Update available: "+feed.optString("version"))
                    .setMessage("Install inside this app. Your saved connection and pairing remain. Android will ask you to approve the installation; the PC schedule keeps running.")
                    .setNegativeButton("Later",null).setPositiveButton("Download update",(d,w)->download(url,hash,size,code)).show());
            } catch(Exception e) { message("Could not check for updates. Check phone internet and try again. "+e.getMessage()); }
            finally { synchronized(AppUpdater.class) { working=false; } }
        },"mobile-update-check").start();
    }
    private static Signature[] signatures(PackageInfo p) {
        if(android.os.Build.VERSION.SDK_INT>=28&&p.signingInfo!=null)return p.signingInfo.getApkContentsSigners();
        return p.signatures;
    }
    public static void verify(Activity a,File file,int version) throws Exception {
        PackageManager pm=a.getPackageManager();int flags=android.os.Build.VERSION.SDK_INT>=28?PackageManager.GET_SIGNING_CERTIFICATES:PackageManager.GET_SIGNATURES;
        PackageInfo incoming=pm.getPackageArchiveInfo(file.getAbsolutePath(),flags),current=pm.getPackageInfo(a.getPackageName(),flags);
        if(incoming==null||!a.getPackageName().equals(incoming.packageName)||incoming.versionCode!=version||incoming.versionCode<=current.versionCode)
            throw new IOException("Wrong app or version");
        Signature[] one=signatures(incoming),two=signatures(current);
        if(one==null||two==null||one.length!=1||two.length!=1||!Arrays.equals(one[0].toByteArray(),two[0].toByteArray()))throw new IOException("Update signing key differs; installation blocked");
    }
    private void download(String url,String expected,long size,int version) {
        synchronized(AppUpdater.class) { if(working)return;working=true; }
        message("Downloading and verifying update…");
        new Thread(() -> {
            File part=new File(activity.getCacheDir(),"mobile-update.part"),apk=new File(activity.getCacheDir(),"mobile-update.apk");
            try {
                HttpsURLConnection c=connection(url);MessageDigest digest=MessageDigest.getInstance("SHA-256");long count=0;
                try(InputStream in=c.getInputStream();FileOutputStream out=new FileOutputStream(part)) {
                    byte[] buffer=new byte[16384];int n;while((n=in.read(buffer))!=-1) { count+=n;if(count>size)throw new IOException("Update size mismatch");digest.update(buffer,0,n);out.write(buffer,0,n); }out.getFD().sync();
                } finally { c.disconnect(); }
                StringBuilder actual=new StringBuilder();for(byte b:digest.digest())actual.append(String.format(java.util.Locale.ROOT,"%02x",b&255));
                if(count!=size||!expected.equals(actual.toString()))throw new IOException("Update verification failed");
                verify(activity,part,version);
                if(apk.exists()&&!apk.delete())throw new IOException("Could not prepare installation");
                if(!part.renameTo(apk))throw new IOException("Could not prepare installation");
                activity.getSharedPreferences("updates",0).edit().putInt("verifiedVersion",version).apply();
                activity.runOnUiThread(() -> new AlertDialog.Builder(activity).setTitle("Update verified").setMessage("Install this update? Saved pairing remains in this app.").setNegativeButton("Later",null).setPositiveButton("Install",(d,w)->install()).show());
            } catch(Exception e) { part.delete();message("Update was not installed. "+e.getMessage()); }
            finally { synchronized(AppUpdater.class) { working=false; } }
        },"mobile-update-download").start();
    }
    private void install() {
        try {
            if(!activity.getPackageManager().canRequestPackageInstalls()) {
                new AlertDialog.Builder(activity).setTitle("Allow app updates").setMessage("Enable Allow from this source for Live Desk, return here, then tap Updates again. The verified download is saved.")
                    .setNegativeButton("Cancel",null).setPositiveButton("Open Android settings",(d,w)->activity.startActivity(new Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,Uri.parse("package:"+activity.getPackageName())))).show();return;
            }
            activity.startActivity(new Intent(Intent.ACTION_VIEW).setDataAndType(Uri.parse("content://org.livedesk.mobile.updates/apk"),"application/vnd.android.package-archive").addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION));
        } catch(Exception e) { message("Android could not open the update installer. "+e.getMessage()); }
    }
}

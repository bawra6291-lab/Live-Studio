package org.livedesk.mobile.qa;
import android.app.Activity;
import android.app.Instrumentation;
import android.content.Intent;
import android.net.Uri;
import android.os.Bundle;
import java.io.*;
import org.livedesk.mobile.AppUpdater;

/** CI-only instrumentation; never packaged in the published companion APK. */
public final class UpgradeTest extends Instrumentation {
    @Override public void onCreate(Bundle args) { super.onCreate(args);start(); }
    private File asset(String name) throws Exception {
        File out=new File(getTargetContext().getCacheDir(),name);
        try(InputStream in=getContext().getAssets().open(name);FileOutputStream dest=new FileOutputStream(out)) {
            byte[] b=new byte[16384];int n;while((n=in.read(b))!=-1)dest.write(b,0,n);
        }return out;
    }
    private void rejected(Activity a,File f,int version) throws Exception {
        boolean refused=false;try{AppUpdater.verify(a,f,version);}catch(IOException expected){refused=true;}
        if(!refused)throw new AssertionError("Invalid APK was accepted");
    }
    @Override public void onStart() {
        Bundle results=new Bundle();
        try {
            Class<?> main=Class.forName("org.livedesk.mobile.MainActivity");
            Activity a=startActivitySync(new Intent(getTargetContext(),main).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
            File next=asset("next.apk"),foreign=asset("foreign.apk");
            AppUpdater.verify(a,next,3);
            rejected(a,next,4);rejected(a,foreign,3);
            rejected(a,new File(getTargetContext().getApplicationInfo().sourceDir),2);
            rejected(a,new File(getContext().getApplicationInfo().sourceDir),3);
            // Installer content provider serves only the verified, private cache file.
            File approved=new File(getTargetContext().getCacheDir(),"mobile-update.apk");
            try(InputStream in=new FileInputStream(next);FileOutputStream out=new FileOutputStream(approved)) {
                byte[] b=new byte[16384];int n;while((n=in.read(b))!=-1)out.write(b,0,n);
            }
            Uri uri=Uri.parse("content://org.livedesk.mobile.updates/apk");
            try(InputStream in=getTargetContext().getContentResolver().openInputStream(uri)) {
                if(in.read()!='P'||in.read()!='K')throw new AssertionError("Wrong APK provider bytes");
            }
            boolean blocked=false;
            try{getTargetContext().getContentResolver().openOutputStream(uri).close();}catch(FileNotFoundException expected){blocked=true;}
            if(!blocked)throw new AssertionError("Provider allowed writes");
            blocked=false;
            try{getTargetContext().getContentResolver().openInputStream(Uri.parse("content://org.livedesk.mobile.updates/../private-setup.json")).close();}catch(FileNotFoundException expected){blocked=true;}
            if(!blocked)throw new AssertionError("Provider allowed another file");
            // Do not leave a fixture offered as a public update.
            approved.delete();next.delete();foreign.delete();
            results.putString("passed","true");results.putString("checks","same signer accepted; wrong signer/version/package and downgrade rejected; provider read-only and path restricted");
            finish(Activity.RESULT_OK,results);
        } catch(Throwable e) { results.putString("error",e.toString());finish(Activity.RESULT_CANCELED,results); }
    }
}

package org.livedesk.mobile;
import android.content.ContentProvider;
import android.content.ContentValues;
import android.database.Cursor;
import android.database.MatrixCursor;
import android.net.Uri;
import android.os.ParcelFileDescriptor;
import android.provider.OpenableColumns;
import java.io.File;
import java.io.FileNotFoundException;

/** Gives only the system installer read access to the one verified APK. */
public final class UpdateProvider extends ContentProvider {
    private File apk(Uri u) throws FileNotFoundException {
        if (!"org.livedesk.mobile.updates".equals(u.getAuthority()) || !"/apk".equals(u.getPath()) || u.getQuery() != null)
            throw new FileNotFoundException();
        return new File(getContext().getCacheDir(), "mobile-update.apk");
    }
    @Override public boolean onCreate() { return true; }
    @Override public String getType(Uri u) { return "application/vnd.android.package-archive"; }
    @Override public ParcelFileDescriptor openFile(Uri u, String mode) throws FileNotFoundException {
        if (!"r".equals(mode)) throw new FileNotFoundException();
        return ParcelFileDescriptor.open(apk(u), ParcelFileDescriptor.MODE_READ_ONLY);
    }
    @Override public Cursor query(Uri u, String[] columns, String selection, String[] args, String sort) {
        try {
            File f=apk(u); String[] names=columns==null?new String[]{OpenableColumns.DISPLAY_NAME,OpenableColumns.SIZE}:columns;
            MatrixCursor result=new MatrixCursor(names); Object[] row=new Object[names.length];
            for(int i=0;i<names.length;i++) row[i]=OpenableColumns.DISPLAY_NAME.equals(names[i])?"Live-Desk-Mobile.apk":OpenableColumns.SIZE.equals(names[i])?f.length():null;
            result.addRow(row); return result;
        } catch(FileNotFoundException e) { return null; }
    }
    @Override public Uri insert(Uri u, ContentValues values) { throw new UnsupportedOperationException(); }
    @Override public int update(Uri u, ContentValues v, String s, String[] a) { throw new UnsupportedOperationException(); }
    @Override public int delete(Uri u, String s, String[] a) { throw new UnsupportedOperationException(); }
}

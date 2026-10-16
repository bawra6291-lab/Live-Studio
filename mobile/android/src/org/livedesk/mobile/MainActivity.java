package org.livedesk.mobile;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.SharedPreferences;
import android.graphics.Color;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.view.View;
import android.view.ViewGroup;
import android.view.inputmethod.InputMethodManager;
import android.webkit.CookieManager;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import java.io.ByteArrayInputStream;

/** Native LAN/HTTPS companion. All operator permissions and writes remain on the PC. */
public final class MainActivity extends Activity {
    private static final int GREEN = Color.rgb(28, 61, 53);
    private static final int PAPER = Color.rgb(248, 247, 241);
    private static final int ORANGE = Color.rgb(242, 179, 128);
    private LinearLayout root;
    private WebView web;
    private String origin;
    private TextView status;
    private SharedPreferences prefs;
    private final Handler handler = new Handler(Looper.getMainLooper());
    private Runnable connectionTimeout;
    private boolean failed;
    private boolean loaded;

    @Override public void onCreate(Bundle savedState) {
        super.onCreate(savedState);
        getWindow().setStatusBarColor(GREEN);
        getWindow().setNavigationBarColor(GREEN);
        if (android.os.Build.VERSION.SDK_INT >= 35) {
            getWindow().setStatusBarColor(PAPER);
            getWindow().setNavigationBarColor(PAPER);
            getWindow().getDecorView().setSystemUiVisibility(View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR | View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR);
        }
        prefs = getSharedPreferences("connection", MODE_PRIVATE);
        String saved = prefs.getString("origin", "");
        try { origin = ConnectionAddress.normalize(saved); showDashboard(); }
        catch (IllegalArgumentException exception) { origin = null; showSetup(""); }
    }
    private int dp(int value) { return Math.round(value * getResources().getDisplayMetrics().density); }
    private LinearLayout column() {
        LinearLayout box = new LinearLayout(this);
        box.setOrientation(LinearLayout.VERTICAL);
        return box;
    }
    private TextView text(String label, int size, int color) {
        TextView item = new TextView(this);
        item.setText(label); item.setTextSize(size); item.setTextColor(color);
        item.setPadding(0, dp(7), 0, dp(7));
        return item;
    }
    private Button button(String label, View.OnClickListener click) {
        Button button = new Button(this);
        button.setText(label); button.setAllCaps(false); button.setTextColor(GREEN);
        button.setOnClickListener(click); return button;
    }
    private void resetRoot() {
        if (connectionTimeout != null) handler.removeCallbacks(connectionTimeout);
        if (web != null) {
            web.stopLoading(); web.setWebViewClient(new WebViewClient());
            web.loadUrl("about:blank");
            if (web.getParent() instanceof ViewGroup) ((ViewGroup)web.getParent()).removeView(web);
            web.removeAllViews(); web.destroy(); web = null;
        }
        root = column(); root.setBackgroundColor(PAPER);
        if (android.os.Build.VERSION.SDK_INT >= 35) {
            root.setOnApplyWindowInsetsListener((view, insets) -> {
                android.graphics.Insets bars = insets.getInsets(android.view.WindowInsets.Type.systemBars() | android.view.WindowInsets.Type.displayCutout());
                android.graphics.Insets keyboard = insets.getInsets(android.view.WindowInsets.Type.ime());
                view.setPadding(bars.left, bars.top, bars.right, Math.max(bars.bottom, keyboard.bottom));
                return insets;
            });
        }
        setContentView(root);
    }
    private void showSetup(String error) {
        resetRoot();
        ScrollView scroll = new ScrollView(this);
        LinearLayout card = column(); card.setPadding(dp(24), dp(30), dp(24), dp(24));
        scroll.addView(card); root.addView(scroll);
        card.addView(text("LIVE DESK · MOBILE", 13, GREEN));
        TextView title = text("Your live desk.\nOn your phone.", 30, GREEN);
        title.setTypeface(null, android.graphics.Typeface.BOLD); card.addView(title);
        card.addView(text("Control your PC's automation, timings and activity.", 16, GREEN));
        card.addView(text("1. Keep Live Desk running on your PC.\n2. Click Enable mobile access in its launcher.\n3. For Wi-Fi, enter the PC address. For mobile internet, enter your HTTPS internet-control address.", 16, GREEN));
        card.addView(text("PC or internet address", 14, GREEN));
        EditText address = new EditText(this);
        address.setSingleLine(true);
        address.setInputType(android.text.InputType.TYPE_CLASS_TEXT | android.text.InputType.TYPE_TEXT_VARIATION_URI);
        address.setHint("http://192.168.29.247:8866");
        address.setText(prefs.getString("origin", ""));
        address.setContentDescription("PC mobile address"); card.addView(address);
        TextView message = text(error, 14, Color.rgb(151, 48, 31)); card.addView(message);
        Button connect = button("Connect to PC", view -> {
            try {
                origin = ConnectionAddress.normalize(address.getText().toString());
                prefs.edit().putString("origin", origin).apply();
                ((InputMethodManager)getSystemService(INPUT_METHOD_SERVICE)).hideSoftInputFromWindow(address.getWindowToken(), 0);
                showDashboard();
            } catch (IllegalArgumentException exception) { message.setText(exception.getMessage()); }
        });
        connect.setBackgroundTintList(android.content.res.ColorStateList.valueOf(ORANGE)); card.addView(connect);
        card.addView(text("Pair once: use the PC pairing code on Wi-Fi or your workspace access code for internet. Internet pairing is remembered across restarts and updates until you sign out or access is revoked. Your YouTube, Facebook and camera setup stays on that PC.", 14, GREEN));
        card.addView(text("Mobile data works with an online HTTPS control server. Keep the PC, its internet and Live Desk running with Internet remote access enabled. Closing this phone app does not pause the PC schedule.", 14, GREEN));
        card.addView(button("Check for updates", view -> new AppUpdater(this).check()));
        card.addView(text("Android 0.2.0", 12, GREEN));
    }
    private void showDashboard() {
        resetRoot(); loaded = false; failed = false;
        LinearLayout bar = new LinearLayout(this); bar.setPadding(dp(8), dp(4), dp(8), dp(4));
        bar.setGravity(android.view.Gravity.CENTER_VERTICAL); bar.setBackgroundColor(GREEN);
        TextView brand = text("Live Desk", 18, Color.WHITE);
        brand.setTypeface(null, android.graphics.Typeface.BOLD);
        bar.addView(brand, new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1));
        bar.addView(button("Refresh", view -> reload()));
        bar.addView(button("Updates", view -> new AppUpdater(this).check()));
        bar.addView(button("PC", view -> new AlertDialog.Builder(this).setTitle("Change PC?")
            .setMessage("This phone will forget its pairing. The PC's current live and automation will continue.")
            .setNegativeButton("Cancel", null).setPositiveButton("Change PC", (dialog, which) -> {
                CookieManager.getInstance().removeAllCookies(done -> {
                    CookieManager.getInstance().flush();
                    android.webkit.WebStorage.getInstance().deleteAllData();
                    showSetup("");
                });
            }).show()));
        root.addView(bar);
        status = text("Connecting to " + origin + "…", 12, GREEN);
        status.setPadding(dp(12), dp(6), dp(12), dp(6)); root.addView(status);
        web = new WebView(this);
        web.setContentDescription("PC dashboard");
        WebSettings settings = web.getSettings();
        settings.setJavaScriptEnabled(true); settings.setDomStorageEnabled(true);
        settings.setAllowFileAccess(false); settings.setAllowContentAccess(false);
        settings.setAllowFileAccessFromFileURLs(false); settings.setAllowUniversalAccessFromFileURLs(false);
        settings.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        settings.setSupportMultipleWindows(false); settings.setJavaScriptCanOpenWindowsAutomatically(false);
        settings.setMediaPlaybackRequiresUserGesture(true);
        settings.setCacheMode(WebSettings.LOAD_NO_CACHE);
        CookieManager.getInstance().setAcceptCookie(true);
        CookieManager.getInstance().setAcceptThirdPartyCookies(web, false);
        web.setWebViewClient(new WebViewClient() {
            @Override public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                if (ConnectionAddress.sameOrigin(request.getUrl().toString(), origin)) return false;
                status.setText("Open platform pages from the PC. This app controls only your paired Live Desk.");
                return true;
            }
            @Override public boolean shouldOverrideUrlLoading(WebView view, String url) {
                return !ConnectionAddress.sameOrigin(url, origin);
            }
            @Override public WebResourceResponse shouldInterceptRequest(WebView view, WebResourceRequest request) {
                if (ConnectionAddress.sameOrigin(request.getUrl().toString(), origin)) return null;
                return new WebResourceResponse("text/plain", "UTF-8", 403, "Blocked", null, new ByteArrayInputStream(new byte[0]));
            }
            @Override public void onPageFinished(WebView view, String url) {
                if (!failed && ConnectionAddress.sameOrigin(url, origin)) {
                    loaded = true;
                    if (connectionTimeout != null) handler.removeCallbacks(connectionTimeout);
                    status.setText((origin.startsWith("https://") ? "Internet controls: " : "PC address: ") + origin + " · status below");
                    CookieManager.getInstance().flush();
                }
            }
            @Override public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error) {
                if (request.isForMainFrame()) connectionFailed();
            }
            @Override public void onReceivedHttpError(WebView view, WebResourceRequest request, WebResourceResponse response) {
                if (request.isForMainFrame()) connectionFailed();
            }
        });
        root.addView(web, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1));
        load();
    }
    private void connectionFailed() {
        failed = true;
        if (connectionTimeout != null) handler.removeCallbacks(connectionTimeout);
        status.setText("Cannot reach PC. Keep Live Desk and PC internet on. For Wi-Fi check Mobile access; for HTTPS check Internet remote access. Tap Refresh to retry or PC to change it.");
    }
    private void load() {
        failed = false; loaded = false;
        status.setText("Connecting to " + origin + "…");
        connectionTimeout = () -> { if (!loaded && web != null) { web.stopLoading(); connectionFailed(); } };
        handler.postDelayed(connectionTimeout, 15000);
        web.loadUrl(origin + "/");
    }
    private void reload() {
        if (connectionTimeout != null) handler.removeCallbacks(connectionTimeout);
        load();
    }
    @Override public void onBackPressed() {
        if (web != null && web.canGoBack()) web.goBack();
        else new AlertDialog.Builder(this).setTitle("Close phone controls?")
            .setMessage("The PC keeps running its current live and schedule. To pause future actions, use Pause automation in the dashboard.")
            .setNegativeButton("Stay", null).setPositiveButton("Close app", (dialog, which) -> finish()).show();
    }
    @Override public void onPause() {
        CookieManager.getInstance().flush();
        super.onPause();
    }
    @Override public void onDestroy() {
        if (connectionTimeout != null) handler.removeCallbacks(connectionTimeout);
        if (web != null) { web.stopLoading(); web.destroy(); }
        super.onDestroy();
    }
}

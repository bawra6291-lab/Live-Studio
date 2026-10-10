package org.livedesk.mobile;

import java.net.URI;
import java.util.Locale;

/** A selected trusted HTTPS relay or the private LAN dashboard, never credentials. */
public final class ConnectionAddress {
    private ConnectionAddress() {}
    public static String normalize(String input) {
        if (input == null) throw new IllegalArgumentException("Enter your PC or HTTPS internet address.");
        String value = input.trim();
        if (!value.startsWith("https://")) return LanAddress.normalize(value);
        try {
            URI u = new URI(value); String h = u.getHost();
            if (!"https".equals(u.getScheme()) || h == null || !h.contains(".") ||
                !h.matches("[A-Za-z0-9.-]+") || h.matches("[0-9.]+") || h.endsWith(".") ||
                u.getRawUserInfo() != null || u.getRawQuery() != null || u.getRawFragment() != null ||
                !(u.getRawPath().isEmpty() || "/".equals(u.getRawPath())) ||
                (u.getPort() != -1 && u.getPort() != 443)) throw new IllegalArgumentException();
            return "https://" + h.toLowerCase(Locale.ROOT);
        } catch (Exception e) { throw new IllegalArgumentException("Use the trusted HTTPS server address without paths or access codes."); }
    }
    public static boolean sameOrigin(String value, String origin) {
        if (origin == null || value == null) return false;
        if (origin.startsWith("http://")) return LanAddress.sameOrigin(value, origin);
        try {
            URI u = new URI(value), b = new URI(origin);
            return "https".equals(u.getScheme()) && u.getRawUserInfo() == null &&
                b.getHost().equalsIgnoreCase(u.getHost()) && (u.getPort() == -1 || u.getPort() == 443);
        } catch (Exception e) { return false; }
    }
}

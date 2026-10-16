package org.livedesk.mobile;

import java.net.URI;
import java.util.Locale;

/** Accept only the Windows launcher's private IPv4 Mobile access origin. */
public final class LanAddress {
    private LanAddress() {}
    public static String normalize(String input) {
        try {
            String value = input.trim();
            if (!value.contains("://")) value = "http://" + value;
            URI uri = new URI(value);
            if (!"http".equals(uri.getScheme()) || uri.getRawUserInfo() != null ||
                uri.getRawQuery() != null || uri.getRawFragment() != null ||
                !(uri.getRawPath().isEmpty() || "/".equals(uri.getRawPath()))) throw new IllegalArgumentException();
            String host = uri.getHost();
            if (host == null) throw new IllegalArgumentException();
            String[] parts = host.split("\\.", -1);
            if (parts.length != 4) throw new IllegalArgumentException();
            int[] octets = new int[4];
            for (int i = 0; i < 4; i++) {
                if (!parts[i].matches("0|[1-9][0-9]{0,2}")) throw new IllegalArgumentException();
                octets[i] = Integer.parseInt(parts[i]);
                if (octets[i] > 255) throw new IllegalArgumentException();
            }
            boolean privateIP = octets[0] == 10 || (octets[0] == 172 && octets[1] >= 16 && octets[1] <= 31) ||
                                (octets[0] == 192 && octets[1] == 168);
            int port = uri.getPort() == -1 ? 8866 : uri.getPort();
            if (!privateIP || port != 8866) throw new IllegalArgumentException();
            return String.format(Locale.ROOT, "http://%s:8866", host);
        } catch (Exception exception) {
            throw new IllegalArgumentException("Enter the PC's Mobile access address, e.g. http://192.168.29.247:8866");
        }
    }
    public static boolean sameOrigin(String candidate, String origin) {
        if (origin == null || candidate == null) return false;
        try {
            URI uri = new URI(candidate);
            URI base = new URI(origin);
            return "http".equals(uri.getScheme()) && uri.getRawUserInfo() == null &&
                   base.getHost().equals(uri.getHost()) && uri.getPort() == 8866;
        } catch (Exception exception) { return false; }
    }
}

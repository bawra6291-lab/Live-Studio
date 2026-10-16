import org.livedesk.mobile.LanAddress;
public final class LanAddressTest {
    private static void bad(String input) {
        try { LanAddress.normalize(input); throw new AssertionError("accepted " + input); }
        catch (IllegalArgumentException expected) {}
    }
    public static void main(String[] args) {
        for (String host : new String[]{"10.0.2.2", "192.168.29.247", "172.16.0.1", "172.31.255.254"}) {
            String expected = "http://" + host + ":8866";
            if (!expected.equals(LanAddress.normalize(host))) throw new AssertionError(host);
            if (!expected.equals(LanAddress.normalize(expected + "/"))) throw new AssertionError(host);
            if (!LanAddress.sameOrigin(expected + "/api/state?x=1", expected)) throw new AssertionError(host);
        }
        for (String input : new String[]{"", "localhost", "127.0.0.1", "8.8.8.8", "169.254.1.1", "172.15.1.1", "172.32.1.1", "192.169.1.1", "https://192.168.1.1:8866", "http://user:pass@192.168.1.1:8866", "192.168.1.1:8865", "192.168.001.1", "192.168.256.1", "http://192.168.1.1:8866/api/state", "192.168.1.1?x=1", "192.168.1.1#hi", "192.168.1.1.evil.test", "file:///etc/passwd", "javascript:alert(1)", "[::1]", "0xc0a80101", "3232235777"}) bad(input);
        String origin = "http://192.168.1.1:8866";
        for (String url : new String[]{"http://192.168.1.1:8865/", "https://192.168.1.1:8866", "http://evil@192.168.1.1:8866", "http://192.168.1.2:8866", "file:///tmp", "data:text/html,hi", "javascript:alert(1)", "http://192.168.1.1.evil.test:8866"}) {
            if (LanAddress.sameOrigin(url, origin)) throw new AssertionError("origin accepted " + url);
        }
        System.out.println("PASS private IPv4 parsing and exact dashboard origin restrictions");
    }
}

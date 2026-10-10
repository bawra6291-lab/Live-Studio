import org.livedesk.mobile.ConnectionAddress;
public final class ConnectionAddressTest {
    public static void main(String[] args) {
        String base=ConnectionAddress.normalize("https://Live-Desk.up.railway.app/");
        if(!base.equals("https://live-desk.up.railway.app"))throw new AssertionError(base);
        if(!ConnectionAddress.sameOrigin(base+"/api/state",base))throw new AssertionError();
        for(String bad:new String[]{"https://evil.test/api","https://name:password@desk.test","https://desk.test?code=abc","https://127.0.0.1","https://desk.test:8866","http://desk.test","file:///data/test","https://desk.test#x"}) {
            try {ConnectionAddress.normalize(bad);throw new AssertionError(bad);}catch(IllegalArgumentException expected) {}
        }
        for(String bad:new String[]{"https://other.test/","https://desk.test.evil.test/","http://desk.test/","https://user@desk.test/","https://desk.test:8866/"})if(ConnectionAddress.sameOrigin(bad,"https://desk.test"))throw new AssertionError(bad);
        System.out.println("HTTPS relay origins and LAN restrictions passed");
    }
}

"""Small HTTPS-proxied control relay. Never exposes the PC listener to the internet."""
import argparse,json,os,secrets,threading,time
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
from store import Store,SESSION_AGE

class Server(ThreadingHTTPServer):
    daemon_threads=True
    def __init__(self,address,store,origin):
        super().__init__(address,Handler);self.store=store;self.origin=origin;self.failures={};self.lock=threading.Lock()

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def setup(self):super().setup();self.connection.settimeout(15)
    def reply(self,status,data,cookie=None):
        raw=json.dumps(data).encode();self.send_response(status)
        for key,value in {'Content-Type':'application/json','Content-Length':str(len(raw)),'Cache-Control':'no-store','X-Content-Type-Options':'nosniff','Referrer-Policy':'no-referrer'}.items():self.send_header(key,value)
        if cookie:self.send_header('Set-Cookie',cookie)
        self.end_headers();self.wfile.write(raw)
    def token(self):
        cookie=SimpleCookie();cookie.load(self.headers.get('Cookie',''))
        return cookie['desk_remote'].value if 'desk_remote' in cookie else ''
    def do_GET(self):
        path=urlsplit(self.path).path
        if path=='/health':return self.reply(200,{'ok':True,'configured':bool(self.server.origin)})
        if path in ('/','/remote.js','/remote.css'):
            name={'/':'index.html','/remote.js':'remote.js','/remote.css':'remote.css'}[path];raw=(Path(__file__).parent/'web'/name).read_bytes()
            self.send_response(200);self.send_header('Content-Type',{'/':'text/html; charset=utf-8','/remote.js':'text/javascript; charset=utf-8','/remote.css':'text/css'}[path]);self.send_header('Content-Length',str(len(raw)));self.send_header('Cache-Control','no-store');self.send_header('Content-Security-Policy',"default-src 'self'; img-src 'self' data:; script-src 'self'; style-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'");self.send_header('X-Content-Type-Options','nosniff');self.end_headers();self.wfile.write(raw);return
        if path.startswith('/api/') and not self.server.origin:return self.reply(503,{'error':'HTTPS server setup is not complete'})
        if path!='/api/state':return self.reply(404,{'error':'Not found'})
        try:
            token=self.token()
            self.reply(200,self.server.store.state(self.server.store.authenticate(token)),cookie=self.session_cookie(token))
        except PermissionError as exc:self.reply(401,{'error':str(exc)})
        except Exception:self.reply(500,{'error':'Could not load remote status'})
    def session_cookie(self,token):return 'desk_remote='+token+'; Secure; HttpOnly; SameSite=Strict; Path=/; Max-Age='+str(SESSION_AGE)
    def do_POST(self):
        if not self.server.origin:return self.reply(503,{'error':'HTTPS server setup is not complete'})
        try:
            if self.headers.get('Content-Type','').split(';')[0]!='application/json':raise ValueError('JSON required')
            size=int(self.headers.get('Content-Length','0'))
            if not 0<size<=65536:raise ValueError('Request too large')
            data=json.loads(self.rfile.read(size))
            if not isinstance(data,dict):raise ValueError('JSON object required')
            store=self.server.store;path=urlsplit(self.path).path
            if path=='/api/agent/poll':
                header=self.headers.get('Authorization','')
                if not header.startswith('Bearer '):raise PermissionError('Agent authorization required')
                agent=store.authenticate(header[7:],agent=True)
                return self.reply(200,{'command':store.poll(agent,data)})
            if self.headers.get('Origin')!=self.server.origin:raise PermissionError('Invalid origin')
            if path=='/api/login':
                # TLS proxy MUST overwrite X-Real-IP; do not expose this listener directly.
                ip=self.headers.get('X-Real-IP',self.client_address[0]);now=time.monotonic()
                with self.server.lock:
                    self.server.failures={k:v for k,v in self.server.failures.items() if v[1]>now}
                    count,expires=self.server.failures.get(ip,(0,now+300))
                    if count>=8:return self.reply(429,{'error':'Try again in five minutes'})
                    code=data.get('code')
                    if not isinstance(code,str) or not 20<=len(code)<=128:raise ValueError('Invalid access code')
                    try:session,csrf=store.login(code)
                    except PermissionError:
                        self.server.failures[ip]=(count+1,expires);raise
                    self.server.failures.pop(ip,None)
                return self.reply(200,{'csrf':csrf},cookie=self.session_cookie(session))
            token=self.token();principal=store.authenticate(token)
            if not secrets.compare_digest(self.headers.get('X-CSRF-Token',''),principal['csrf']):raise PermissionError('Refresh the session')
            if path=='/api/logout':
                store.logout(token);return self.reply(200,{'ok':True},cookie='desk_remote=; Secure; HttpOnly; SameSite=Strict; Path=/; Max-Age=0')
            if path=='/api/command':return self.reply(200,{'id':store.enqueue(principal,data)})
            if path=='/api/revoke':store.revoke(principal,data.get('id'),data.get('kind'));return self.reply(200,{'ok':True})
            return self.reply(404,{'error':'Not found'})
        except PermissionError as exc:self.reply(403,{'error':str(exc)})
        except (ValueError,TypeError) as exc:self.reply(409,{'error':str(exc)})
        except Exception:self.reply(500,{'error':'Remote operation failed'})

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--db',default=os.getenv('LIVE_DESK_DB','relay.db'))
    sub=parser.add_subparsers(dest='command',required=True)
    create=sub.add_parser('create-workspace');create.add_argument('name')
    grant=sub.add_parser('grant');grant.add_argument('workspace');grant.add_argument('role',choices=['owner','operator','viewer','agent']);grant.add_argument('--name',default='Livestream PC')
    serve=sub.add_parser('serve');serve.add_argument('--origin',default=os.getenv('PUBLIC_ORIGIN') or ('https://'+os.environ['RAILWAY_PUBLIC_DOMAIN'] if os.getenv('RAILWAY_PUBLIC_DOMAIN') else None));serve.add_argument('--host',default='127.0.0.1');serve.add_argument('--port',type=int,default=int(os.getenv('PORT','8080')))
    args=parser.parse_args();store=Store(args.db)
    if os.getenv('LIVE_DESK_BOOTSTRAP'):store.bootstrap(json.loads(os.environ['LIVE_DESK_BOOTSTRAP']))
    if args.command=='create-workspace':print(store.create_workspace(args.name))
    elif args.command=='grant':print(json.dumps(store.grant(args.workspace,args.role,args.name)))
    else:
        origin=args.origin or '';p=urlsplit(origin)
        if origin and (p.scheme!='https' or not p.hostname or p.path or p.query or p.fragment or p.username):parser.error('Use a public HTTPS origin without a trailing slash. TLS proxy required.')
        store.mark_offline()
        Server((args.host,args.port),store,origin).serve_forever()
if __name__=='__main__':main()

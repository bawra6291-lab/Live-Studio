"""Disposable TLS relay+fake agent, solely for browser CI. Tokens die with process."""
import json,ssl,sys,tempfile,threading,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'remote'))
from store import Store
from server import Server
root=Path(sys.argv[1]);store=Store(root/'relay.db');w=store.create_workspace('QA')
owner=store.grant(w,'owner');pc=store.grant(w,'agent');agent=store.authenticate(pc['token'],agent=True)
server=Server(('127.0.0.1',0),store,'');server.origin='https://localhost:'+str(server.server_port)
ctx=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);ctx.load_cert_chain(root/'cert.pem',root/'key.pem');server.socket=ctx.wrap_socket(server.socket,server_side=True)
def work():
    ack=None;armed=False
    while True:
        command=store.poll(agent,{'boot':'a'*32,'snapshot':{'armed':armed,'message':'Isolated QA PC','slots':[]},'ack':ack});ack=None
        if command:
            armed=command['action']=='arm';ack={'id':command['id'],'status':'accepted','message':'Fake PC accepted'}
        time.sleep(.1)
threading.Thread(target=work,daemon=True).start()
print(json.dumps({'origin':server.origin,'code':owner['token']}),flush=True)
server.serve_forever()

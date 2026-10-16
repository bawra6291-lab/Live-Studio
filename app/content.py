"""Immutable local thumbnail assets and per-program content; no platform writes here."""
import base64, hashlib, re, struct, zlib
from pathlib import Path
from core import title_for

MAX_IMAGE=2*1024*1024

def image_type(data):
    if len(data)>MAX_IMAGE:raise ValueError('Thumbnail must be at most 2 MB.')
    if data.startswith(b'\x89PNG\r\n\x1a\n') and len(data)>=33 and data[12:16]==b'IHDR':
        pos=8;seen=set()
        while pos<len(data):
            if pos+12>len(data):raise ValueError('Truncated PNG thumbnail.')
            size=int.from_bytes(data[pos:pos+4],'big');tag=data[pos+4:pos+8];end=pos+12+size
            if end>len(data) or zlib.crc32(data[pos+4:end-4])!=int.from_bytes(data[end-4:end],'big'):raise ValueError('PNG thumbnail failed verification.')
            seen.add(tag);pos=end
            if tag==b'IEND':break
        if pos!=len(data) or not {b'IHDR',b'IDAT',b'IEND'}<=seen:raise ValueError('Incomplete PNG thumbnail.')
        w,h=struct.unpack('>II',data[16:24]);kind='image/png'
    elif data.startswith(b'\xff\xd8') and data.endswith(b'\xff\xd9'):
        pos=2;w=h=0;kind='image/jpeg'
        while pos<len(data)-4:
            if data[pos]!=255:pos+=1;continue
            marker=data[pos+1];pos+=2
            if marker in (0,255,216,217) or 208<=marker<=215:continue
            length=int.from_bytes(data[pos:pos+2],'big')
            if length<2 or pos+length>len(data):break
            if marker in (192,193,194) and length>=7:h,w=struct.unpack('>HH',data[pos+3:pos+7]);break
            pos+=length
    else:raise ValueError('Use a JPEG or PNG thumbnail.')
    if not w or not h or max(w,h)>8192:raise ValueError('Invalid thumbnail dimensions; use at most 8192 pixels.')
    return kind

class ContentStore:
    def __init__(self,base):self.folder=Path(base)/'media';self.folder.mkdir(parents=True,exist_ok=True)
    def add(self,encoded):
        if not isinstance(encoded,str) or len(encoded)>MAX_IMAGE*4//3+8:raise ValueError('Thumbnail is too large.')
        try:data=base64.b64decode(encoded,validate=True)
        except Exception:raise ValueError('Invalid thumbnail upload.') from None
        kind=image_type(data);ident=hashlib.sha256(data).hexdigest();path=self.folder/ident
        if not path.exists():
            temp=path.with_suffix('.tmp');temp.write_bytes(data);temp.replace(path)
        return {'id':ident,'type':kind,'size':len(data)}
    def get(self,ident):
        if not isinstance(ident,str) or not re.fullmatch('[a-f0-9]{64}',ident):raise ValueError('Invalid thumbnail ID.')
        path=self.folder/ident
        if not path.is_file():raise ValueError('Saved thumbnail is missing. Upload it again on this PC.')
        data=path.read_bytes()
        if hashlib.sha256(data).hexdigest()!=ident:raise ValueError('Saved thumbnail is damaged. Upload it again.')
        return data,image_type(data)
    def path_for(self,ident):
        data,kind=self.get(ident);path=self.folder/(ident+('.png' if kind=='image/png' else '.jpg'))
        if not path.is_file() or path.read_bytes()!=data:path.write_bytes(data)
        return str(path.resolve())
    def preview(self,slot,day):
        ident=slot.get('thumbnail_days',{}).get(str(day.day),'')
        return {'slot':slot['id'],'date':day.isoformat(),'title':title_for('',{**slot,'title_template':slot.get('title_template') or '{date} | {program}'},day),
                'description':slot.get('description','') if slot.get('description_mode')=='custom' else None,
                'description_source':'Saved text' if slot.get('description_mode')=='custom' else 'Reference livestream (loaded during preparation)',
                'thumbnail_id':ident,'thumbnail_source':'Day '+str(day.day) if ident else 'Reference livestream thumbnail',
                'stream_key_policy':'Reuse the configured existing Official key; never create or rotate a key.'}

"""Telegram channel albums. Connection checks never send a message."""
from contextlib import ExitStack
import json, re
from connections import SetupError
from social_publish import Publisher


def channel_id(value):
    if not isinstance(value,str):raise ValueError('Enter a Telegram @channelusername or numeric -100… channel ID.')
    value=value.strip()
    if not re.fullmatch(r'@[A-Za-z][A-Za-z0-9_]{4,31}|-100[0-9]{5,17}',value):
        raise ValueError('Enter a Telegram @channelusername or numeric -100… channel ID, not an invite link.')
    return value


def bot_token(value):
    if not isinstance(value,str) or not re.fullmatch(r'[0-9]{5,20}:[A-Za-z0-9_-]{20,200}',value.strip()):
        raise ValueError('Paste the complete Telegram bot token from BotFather.')
    return value.strip()


def caption_length(value):return len(value.encode('utf-16-le'))//2


class Telegram(Publisher):
    def request(self,method,data=None,files=None):
        import requests
        try:token=bot_token(self.vault.get('telegram_bot_token'))
        except ValueError:raise SetupError('Save the complete Telegram bot token in Connections.',retryable=False) from None
        if method not in ('getMe','getChat','getChatMember','sendMediaGroup'):raise ValueError('Unsupported Telegram request.')
        try:
            response=requests.post('https://api.telegram.org/bot'+token+'/'+method,
                data=data or {},files=files,timeout=(10,90),allow_redirects=False)
            body=response.json()
            if not isinstance(body,dict):raise ValueError()
        except Exception:
            raise SetupError('Telegram request outcome is uncertain. Inspect the channel before retrying; no automatic retry was sent.',retryable=False) from None
        if not response.ok or body.get('ok') is not True:
            code=body.get('error_code')
            if code==429:message='Telegram request limit reached. Wait before trying again; no automatic retry was sent.'
            elif code==401:message='Telegram bot token is invalid or revoked. Save a new token from BotFather.'
            elif code==403:message='Telegram denied access. Add this bot as a channel administrator with Post messages permission.'
            else:message='Telegram rejected the request. Check the bot token, channel ID and channel administrator permissions.'
            raise SetupError(message,retryable=False)
        return body.get('result')

    def identity(self):
        bot=self.request('getMe')
        if not isinstance(bot,dict) or bot.get('is_bot') is not True or type(bot.get('id'))!=int:
            raise SetupError('Telegram did not return a valid bot account.',retryable=False)
        chat=self.request('getChat',{'chat_id':channel_id(self.cfg.get('telegram_channel',''))})
        if not isinstance(chat,dict) or chat.get('type')!='channel':
            raise SetupError('Select a Telegram channel and add your bot as an administrator.',retryable=False)
        try:ident=channel_id(str(chat.get('id','')))
        except ValueError:raise SetupError('Telegram did not return a valid channel ID.',retryable=False) from None
        member=self.request('getChatMember',{'chat_id':ident,'user_id':bot['id']})
        if not isinstance(member,dict) or member.get('status')!='administrator' or member.get('can_post_messages') is not True:
            raise SetupError('Give this Telegram bot channel administrator access with Post messages permission.',retryable=False)
        username=chat.get('username','')
        if not isinstance(username,str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{4,31}',username):username=''
        return {'id':ident,'name':str(chat.get('title','Telegram channel'))[:120],
                'bot_id':str(bot['id']),'bot_name':str(bot.get('username',''))[:80],'username':username}

    def publish(self,job):
        self.cancelled();self.verify_media(job)
        if job.get('delivery','api')!='api' or job['platforms']!=['telegram'] or len(job['media']) not in (7,10,17):
            raise SetupError('Telegram needs a reviewed 7-photo, 10-photo or two-album draft.',retryable=False)
        if caption_length(job['caption'])>1024:
            raise SetupError('Shorten the Telegram album caption to 1024 characters (emoji may count as two).',retryable=False)
        account=self.identity()
        if account['id']!=job['targets'].get('telegram') or account['bot_id']!=job.get('studio_bot_id'):
            raise SetupError('Telegram bot or channel changed. Prepare and review a new draft.',retryable=False)
        media=job['media'];batches=[media[:7],media[7:]] if len(media)==17 else [media]
        albums=[]
        for number,batch in enumerate(batches,1):
            self.cancelled()
            self.checkpoint(job,'telegram',status='sending',stage=f'Sending album {number} of {len(batches)}',albums=albums)
            with ExitStack() as stack:
                files={};items=[]
                for i,ident in enumerate(batch):
                    path,asset=self.manager.media_path(ident)
                    if asset['type']!='image/jpeg' or asset['size']>10*1024*1024:
                        raise SetupError('Telegram albums need JPG photos under 10 MB.',retryable=False)
                    key='photo'+str(i);files[key]=('darshan.jpg',stack.enter_context(path.open('rb')),'image/jpeg')
                    item={'type':'photo','media':'attach://'+key}
                    if i==0:item['caption']=job['caption']
                    items.append(item)
                result=self.request('sendMediaGroup',{'chat_id':account['id'],'media':json.dumps(items,ensure_ascii=False)},files)
            if (not isinstance(result,list) or len(result)!=len(batch) or any(not isinstance(r,dict) or type(r.get('message_id'))!=int
                    or str(r.get('chat',{}).get('id'))!=account['id'] for r in result)):
                raise SetupError('Telegram returned an incomplete album receipt. Inspect the channel before retrying.',retryable=False)
            mids=[r['message_id'] for r in result]
            prefix=account['username'] or 'c/'+account['id'][4:]
            albums.append({'message_ids':mids,'url':'https://t.me/'+prefix+'/'+str(mids[0]),'count':len(batch)})
            self.checkpoint(job,'telegram',status='partial' if number<len(batches) else 'published',
                stage=f'{number} of {len(batches)} albums posted',albums=albums,
                id=str(albums[0]['message_ids'][0]),url=albums[0]['url'],urls=[a['url'] for a in albums])

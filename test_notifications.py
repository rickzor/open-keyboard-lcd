import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from PIL import Image
sys.path.insert(0,str(Path(__file__).parent/'examples-sandbox'/'automations'))
from notifications import Inbox, validate, serve, send, notification_key
from notification_cards import PRESETS, notification_frames
from lcd_automations import Display, notification_tick
from slack_notifications import map_event


class NotificationTests(unittest.TestCase):
    def test_templates_and_customization(self):
        for template in PRESETS:
            item=validate({'template':template,'source':'Example'})
            frames=notification_frames(item)
            self.assertEqual(len(frames),8)
            self.assertEqual(frames[0].size,(240,136))
        item=validate({'template':'success','theme':{'background':'#123456','accent':'#ABCDEF'},'animate':False})
        frame=notification_frames(item)[0]
        self.assertEqual(frame.getpixel((0,0)),(0x12,0x34,0x56))
        self.assertEqual(len(notification_frames(item)),1)

    def test_reject_invalid_messages(self):
        for payload in [{'template':'unknown'},{'duration':0},{'priority':99},{'ttl':float('nan')},
                        {'message':'x'*241},{'theme':{'accent':'red'}},{'theme':{'file':'/tmp/file'}},
                        {'animate':'yes'},{'shell':'echo bad'},{'icon':'file.svg'}]:
            with self.assertRaises(ValueError): validate(payload)

    def test_queue_priority_duplicate_expiry_and_private_body_cleanup(self):
        with tempfile.TemporaryDirectory() as folder:
            inbox=Inbox(folder)
            inbox.submit({'id':'low','priority':1,'message':'Private text'},100)
            inbox.submit({'id':'high','priority':8},101)
            self.assertEqual(inbox.peek(102)['id'],'high')
            inbox.acknowledge('high')
            self.assertEqual(inbox.submit({'id':'high'},103)['status'],'duplicate')
            self.assertEqual(inbox.peek(104)['id'],'low')
            self.assertIsNone(inbox.peek(401))
            with inbox.connect() as db:
                self.assertEqual(db.execute('SELECT body FROM notices WHERE id="low"').fetchone(),(None,))

    def test_queue_survives_restart_and_is_bounded(self):
        with tempfile.TemporaryDirectory() as folder:
            inbox=Inbox(folder)
            for i in range(100): inbox.submit({'id':str(i)},100)
            self.assertIsNotNone(Inbox(folder).peek(101))
            with self.assertRaises(OverflowError): inbox.submit({'id':'overflow'},101)

    def test_notification_restores_base_and_waits_for_active_alert(self):
        with tempfile.TemporaryDirectory() as folder:
            display=Display(Path(folder)/'display')
            base=display.asset([Image.new('RGB',(240,136),'blue')],4,'base'); display.base(base)
            inbox=Inbox(Path(folder)/'inbox'); config={'notifications':True,'notification_inbox':str(inbox.folder)}
            inbox.submit({'id':'first','template':'success','duration':10},100)
            self.assertTrue(notification_tick(display,config,100))
            inbox.submit({'id':'second','priority':9},101)
            self.assertFalse(notification_tick(display,config,102))
            self.assertEqual(inbox.peek(102)['id'],'second')
            self.assertTrue(display.expire(110)); self.assertEqual(display.state['visible'],base)
            self.assertTrue(notification_tick(display,config,111))
            display.expire(126); self.assertEqual(display.state['visible'],base)

    def test_recover_after_display_success_before_ack(self):
        with tempfile.TemporaryDirectory() as folder:
            display=Display(Path(folder)/'display')
            base=display.asset([Image.new('RGB',(240,136),'blue')],4,'base'); display.base(base)
            inbox=Inbox(Path(folder)/'inbox'); inbox.submit({'id':'a'},100)
            item=inbox.peek(100)
            image=display.asset(notification_frames(item),4,'notification')
            display.alert(image,110,notification_key(item)); display.expire(110)
            self.assertFalse(notification_tick(display,{'notifications':True,'notification_inbox':str(inbox.folder)},111))
            self.assertIsNone(inbox.peek(111)); self.assertEqual(display.state['visible'],base)

    def test_slack_maps_only_app_mentions_and_hides_content_by_default(self):
        payload={'event_id':'Ev123','event':{'type':'app_mention','text':'Private text'}}
        self.assertNotIn('Private',map_event(payload)['message'])
        self.assertEqual(map_event(payload,True)['message'],'Private text')
        self.assertIsNone(map_event({'event_id':'x','event':{'type':'message'}}))

    def test_http_authentication_and_ingestion(self):
        with tempfile.TemporaryDirectory() as folder:
            inbox=Inbox(folder); server=serve(inbox,0)
            worker=threading.Thread(target=server.serve_forever,daemon=True); worker.start()
            try:
                url=f'http://127.0.0.1:{server.server_port}/notify'
                req=urllib.request.Request(url,data=b'{}',headers={'Content-Type':'application/json'})
                with self.assertRaises(urllib.error.HTTPError) as error: urllib.request.urlopen(req)
                self.assertEqual(error.exception.code,401)
                answer=send({'id':'http','template':'success'},folder,server.server_port)
                self.assertEqual(answer['status'],'queued')
                self.assertEqual(inbox.peek(__import__('time').time())['id'],'http')
                req=urllib.request.Request(url,data=b'{}',headers={'Content-Type':'application/json',
                    'Authorization':'Bearer '+inbox.token_path.read_text(),'Origin':'https://example.com'})
                with self.assertRaises(urllib.error.HTTPError) as error: urllib.request.urlopen(req)
                self.assertEqual(error.exception.code,403)
            finally: server.shutdown(); server.server_close(); worker.join(timeout=2)

if __name__=='__main__': unittest.main()

import contextlib
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from PIL import Image

sys.path.insert(0,str(Path(__file__).parent/'examples-sandbox'/'notification-display'))
import display
from qgif import encode_frames


class Keyboard:
    def __init__(self,table):
        self.table=table; self.calls=[]; self.via=SimpleNamespace(identity='device-A'); self.fail=False
    def inspect(self): return self.table
    def keyboard_command(self,*args): self.calls.append(('keyboard',args,{}))
    def sync_time(self): pass
    def command(self,code,*args,**kwargs):
        self.calls.append((code,args,kwargs))
        if code==0x19 and self.fail: raise RuntimeError('Disconnected during write')
        if code==0x15 and args[0]==0: self.table=kwargs['data']


class ResidentTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.folder=Path(self.tmp.name); self.now=0
        self.payload=encode_frames([Image.new('RGB',(240,136),'black')],fps=1)
        entries,blocks=display.plan([('First',self.payload),('Second',self.payload)])
        table=display.table_for(entries[0]); self.keyboard=Keyboard(table)
        @contextlib.contextmanager
        def transport(): yield self.keyboard
        self.manager=display.ResidentDisplay(self.folder,transport,lambda:self.now,lambda options:options[0])
        self.manager.state={'status':'ready','identity':'device-A','mountains':entries,
            'table_hex':table.hex(),'active':0,'last_mountain':0,'until':0,'seen':[]}
        self.manager.save()
        self.sleeper=patch.object(display.time,'sleep'); self.sleeper.start(); self.addCleanup(self.sleeper.stop)
        self.encoder=patch.object(display,'notification_data',return_value=self.payload)
        self.encoder.start(); self.addCleanup(self.encoder.stop)

    def test_switch_is_metadata_only_and_random_avoids_previous(self):
        self.manager.random_mountain()
        self.assertEqual(self.manager.state['active'],1)
        self.assertEqual(self.keyboard.table[3],2)
        self.assertFalse(any(c in (0x18,0x19) for c,_,_ in self.keyboard.calls))

    def test_single_default_returns_to_same_resident_image_without_rewriting(self):
        self.manager.state['mountains']=self.manager.state['mountains'][:1]
        self.manager.notify({'id':'notice'})
        self.keyboard.calls=[]; self.now=60
        inbox=display.Inbox(self.folder/'single-inbox'); self.manager.tick(inbox)
        self.assertEqual(self.manager.state['active'],0)
        self.assertEqual(self.keyboard.table[3],1)
        self.assertFalse(any(c in (0x18,0x19) for c,_,_ in self.keyboard.calls))

    def test_persistent_screen_never_returns_on_timer(self):
        self.manager.show_animation(self.payload,'weather',persistent=True)
        self.keyboard.calls=[]; self.now=7200
        self.manager.tick(display.Inbox(self.folder/'persistent-inbox'))
        self.assertEqual(self.manager.state['active'],'persistent')
        self.assertEqual(self.keyboard.calls,[])

    def test_oversized_animation_is_rejected_before_usb(self):
        payload=encode_frames([Image.new('RGB',(240,136),c) for c in ('red','blue','green','white','yellow')],fps=8)
        self.assertGreater(len(payload),65536)
        with self.assertRaises(ValueError): self.manager.show_animation(payload,'oversized')
        self.assertEqual(self.keyboard.calls,[])

    def test_notification_erases_and_writes_only_block_zero(self):
        mountains=json.loads(json.dumps(self.manager.state['mountains']))
        self.manager.notify({'id':'notice-1'})
        erases=[(a,k) for c,a,k in self.keyboard.calls if c==0x18]
        self.assertEqual(erases,[((3,0,0,1),{'data':b'\x01','wait':False})])
        self.assertEqual(self.keyboard.table[:5],bytes([0,1,1,0,0]))
        writes=[(a,k) for c,a,k in self.keyboard.calls if c==0x19]
        self.assertTrue(writes)
        self.assertTrue(all(a[0]+(a[1]<<8)+(a[2]<<16)+len(k['data'])<=65536 for a,k in writes))
        self.assertEqual(self.manager.state['mountains'],mountains)

    def test_new_notice_resets_timer_and_returns_without_image_writes(self):
        inbox=display.Inbox(self.folder/'inbox')
        inbox.submit({'id':'one','title':'First'},now=0); self.manager.tick(inbox)
        self.assertEqual(self.manager.state['until'],60)
        self.now=50; inbox.submit({'id':'two','title':'Second'},now=50); self.manager.tick(inbox)
        self.assertEqual(self.manager.state['until'],110)
        self.now=109; self.manager.tick(inbox); self.assertEqual(self.manager.state['active'],'notification')
        self.keyboard.calls=[]; self.now=110; self.manager.tick(inbox)
        self.assertEqual(self.manager.state['active'],1)
        self.assertFalse(any(c in (0x18,0x19) for c,_,_ in self.keyboard.calls))

    def test_duplicate_does_not_rewrite_or_reset_timer(self):
        self.manager.notify({'id':'same'}); self.keyboard.calls=[]; self.now=10
        self.manager.notify({'id':'same'})
        self.assertEqual(self.keyboard.calls,[]); self.assertEqual(self.manager.state['until'],60)

    def test_stale_metadata_and_wrong_device_make_no_writes(self):
        self.keyboard.table=bytes(56)
        with self.assertRaises(RuntimeError): self.manager.notify({'id':'one'})
        self.assertEqual(self.keyboard.calls,[])
        self.keyboard.table=bytes.fromhex(self.manager.state['table_hex']); self.keyboard.via.identity='device-B'
        with self.assertRaises(RuntimeError): self.manager.select(1)
        self.assertEqual(self.keyboard.calls,[])

    def test_interrupted_notice_stays_pending_and_never_full_rewrites(self):
        self.keyboard.fail=True
        with self.assertRaises(RuntimeError): self.manager.notify({'id':'one'})
        self.assertEqual(json.loads(self.manager.path.read_text())['status'],'pending')
        self.keyboard.calls=[]
        with self.assertRaises(RuntimeError): self.manager.select(1)
        self.assertEqual(self.keyboard.calls,[])

    def test_restart_retains_deadline_and_deduplication(self):
        self.now=12; self.manager.notify({'id':'one'})
        restarted=display.ResidentDisplay(self.folder)
        self.assertEqual(restarted.state['until'],72)
        self.assertIn(display.notification_key({'id':'one'}),restarted.state['seen'])

    def test_plan_reserves_first_block_and_checks_address_limit(self):
        entries,blocks=display.plan([('A',self.payload),('B',self.payload)])
        self.assertEqual([e['block'] for e in entries],[1,2]); self.assertEqual(blocks,3)
        with patch.object(display,'inspect_qgif',return_value={'width':240,'height':136}):
            with self.assertRaises(ValueError): display.plan([('Too large',bytes(255*65536))])

    def test_initialize_writes_disjoint_library_once_then_only_switches(self):
        source=self.folder/'source.qgif'; source.write_bytes(self.payload)
        collection=self.folder/'collection.json'
        collection.write_text(json.dumps([{'name':name,'qgif':str(source),'sha256':display.digest(self.payload)} for name in ('A','B')]))
        library=self.folder/'library'; display.prepare(collection,library,['A','B'])
        with patch.object(display,'ROOT',self.folder/'fake-repo'):
            self.manager.initialize(library)
        erases=[(a,k) for c,a,k in self.keyboard.calls if c==0x18]
        self.assertEqual(erases,[((0,0,0,1),{'data':b'\x04','wait':False})])
        addresses=[a[0]+(a[1]<<8)+(a[2]<<16) for c,a,k in self.keyboard.calls if c==0x19]
        self.assertEqual({a//65536 for a in addresses},{0,1,2})
        self.assertEqual(self.manager.state['status'],'ready')
        self.keyboard.calls=[]; self.manager.random_mountain()
        self.assertFalse(any(c in (0x18,0x19) for c,_,_ in self.keyboard.calls))

    def test_prepare_rejects_changed_source_hash_before_bundle_creation(self):
        source=self.folder/'source.qgif'; source.write_bytes(self.payload)
        collection=self.folder/'collection.json'
        collection.write_text(json.dumps([{'name':'A','qgif':str(source),'sha256':'incorrect'}]))
        library=self.folder/'library'
        with self.assertRaises(ValueError): display.prepare(collection,library,['A'])
        self.assertFalse(library.exists())

    def test_resume_initialization_writes_only_unchanged_tail_and_never_erases(self):
        source=self.folder/'source.qgif'; source.write_bytes(self.payload)
        collection=self.folder/'collection.json'
        collection.write_text(json.dumps([{'name':name,'qgif':str(source)} for name in ('A','B')]))
        library=self.folder/'library'; display.prepare(collection,library,['A','B'])
        config,_=display.load_library(library)
        self.manager.state.update(status='initializing',mountains=config['mountains'],blocks=config['blocks'],
                                  checkpoint={'image_index':1,'offset':56})
        self.manager.save(); self.manager.resume_initialize(library)
        writes=[a[0]+(a[1]<<8)+(a[2]<<16) for c,a,k in self.keyboard.calls if c==0x19]
        self.assertEqual(writes[0],2*65536+56)
        self.assertTrue(all(2*65536<=a<3*65536 for a in writes))
        self.assertFalse(any(c==0x18 for c,_,_ in self.keyboard.calls))
        self.assertEqual(self.manager.state['status'],'ready')


if __name__=='__main__': unittest.main()

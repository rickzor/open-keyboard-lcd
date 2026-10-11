import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from PIL import Image
import pool
import rt82
from qgif import encode_frames


class PoolTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name)/'ledger.json'
        self.image = encode_frames([Image.new('RGB',(240,136),'red')])
        self.table = rt82.plan_set([self.image]*3,1)[0]
        self.ledger = {'version':1,'status':'ready','identity':'device-a',
                       'next_block':3,'end_block':4,'table_hex':self.table.hex()}
        pool.save_ledger(self.path,self.ledger)
        self.keyboard = Mock()
        self.keyboard.via.identity = 'device-a'

    def test_reservation_includes_spare_inside_total_and_erase(self):
        table,starts,erase = rt82.plan_set([self.image]*3,1)
        self.assertEqual((table[2],starts,erase),(4,[0,1,2],5))
        with self.assertRaises(ValueError): rt82.plan_set([self.image]*3,2)
        with self.assertRaises(ValueError): rt82.plan_set([self.image*5]*3,1)

    def test_append_only_writes_reserved_block_and_burns_it(self):
        before,after,_ = pool.plan_append(self.ledger,self.image,2)
        self.keyboard.inspect.side_effect = [before,after]
        with patch('pool.time.sleep'):
            result = pool.append(self.keyboard,self.image,2,self.path)
        self.assertEqual(result['status'],'exhausted')
        self.assertEqual(before[3:8],after[3:8])
        self.assertEqual(before[13:18],after[13:18])
        self.assertEqual(before[:3],after[:3])
        calls = self.keyboard.command.call_args_list
        self.assertNotIn(0x18,[c.args[0] for c in calls])
        writes = [c for c in calls if c.args[0]==0x19]
        self.assertEqual(b''.join(c.kwargs['data'] for c in writes),self.image)
        self.assertTrue(all(c.args[3]==3 for c in writes))
        self.keyboard.reset_mock()
        with self.assertRaises(RuntimeError): pool.append(self.keyboard,self.image,2,self.path)
        self.keyboard.inspect.assert_not_called()
        self.keyboard.command.assert_not_called()

    def test_interrupted_write_never_releases_allocation(self):
        self.keyboard.inspect.return_value = self.table
        def fail(command,*args,**kwargs):
            if command==0x19:
                state=json.loads(self.path.read_text())
                self.assertEqual((state['status'],state['next_block']),('writing',4))
                raise OSError('disconnected')
        self.keyboard.command.side_effect = fail
        with patch('pool.time.sleep'),self.assertRaises(OSError):
            pool.append(self.keyboard,self.image,3,self.path)
        self.assertEqual(json.loads(self.path.read_text())['status'],'writing')
        with self.assertRaises(RuntimeError): pool.append(self.keyboard,self.image,3,self.path)

    def test_stale_table_or_different_device_causes_no_writes(self):
        for identity,table in [('different',self.table),('device-a',bytes(56))]:
            self.keyboard.via.identity = identity
            self.keyboard.inspect.return_value = table
            with self.assertRaises(RuntimeError): pool.append(self.keyboard,self.image,3,self.path)
            self.keyboard.command.assert_not_called()
        self.assertEqual(json.loads(self.path.read_text())['status'],'ready')

    def test_failed_initialization_cannot_leave_old_ready_state(self):
        self.keyboard.upload_set.side_effect = OSError('disconnect')
        with self.assertRaises(OSError): pool.initialize(self.keyboard,[self.image]*3,self.path)
        self.assertEqual(json.loads(self.path.read_text())['status'],'initializing')

    def test_normal_full_upload_invalidates_pool_before_mutations(self):
        root = self.path.parent
        state = root/'state/append-pool.json'
        pool.save_ledger(state,self.ledger)
        keyboard=object.__new__(rt82.Keyboard)
        def fail(*args,**kwargs):
            self.assertEqual(json.loads(state.read_text())['status'],'invalidated-by-full-upload')
            raise OSError('stopped before mutation')
        keyboard.command=fail
        with patch('rt82.ROOT',root),self.assertRaises(OSError):
            keyboard.upload_set([self.image]*3)

if __name__=='__main__':unittest.main()

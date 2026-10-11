import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock
import rt82


class ProtocolTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = patch('rt82.ROOT', Path(directory.name))
        root.start()
        self.addCleanup(root.stop)

    def save_set(self, directory):
        state = Path(directory)
        folder = state / 'set'
        folder.mkdir()
        images = [b'QGIF' + bytes([n]) * 64 for n in (1, 2, 3)]
        for n, image in enumerate(images, 1):
            (folder / f'slot-{n}.qgif').write_bytes(image)
        table, _, _ = rt82.plan_set(images)
        manifest = {'status': 'acknowledged-and-metadata-verified',
                    'sha256': [hashlib.sha256(b).hexdigest() for b in images],
                    'table_hex': table.hex()}
        (folder / 'manifest.json').write_text(json.dumps(manifest))
        (state / 'current-set.txt').write_text(str(folder))
        return state, folder, images

    def test_full_set_transmits_all_three_exact_payloads(self):
        images = [b'QGIF' + bytes([n]) * (60+n) for n in (1, 2, 3)]
        keyboard = object.__new__(rt82.Keyboard)
        calls = []
        keyboard.command = lambda cmd, *args, **kw: calls.append((cmd, args, kw)) or bytes(64)
        keyboard.keyboard_command = Mock()
        keyboard.sync_time = Mock()
        with patch('rt82.time.sleep'):
            table = keyboard.upload_set(images)
        self.assertEqual(table[:3], bytes([0, 3, 3]))
        for i, original in enumerate(images):
            chunks = [(args, kw['data']) for cmd, args, kw in calls
                      if cmd == 0x19 and args[2] == i]
            self.assertEqual(b''.join(chunk for _, chunk in chunks), original)
            self.assertEqual(chunks[0][0][:3], (0, 0, i))
        erases = [call for call in calls if call[0] == 0x18]
        self.assertEqual(len(erases), 1)
        self.assertEqual(erases[0][1], (0, 0, 0, 1))
        self.assertEqual(erases[0][2]['data'], bytes([4]))

    def test_full_set_rejects_empty_set(self):
        with self.assertRaises(ValueError):
            rt82.plan_set([])

    def test_one_and_two_image_sets_send_matching_counts(self):
        for count in (1, 2):
            images=[b'QGIF'+bytes([n])*60 for n in range(count)]
            keyboard=object.__new__(rt82.Keyboard)
            keyboard.command=Mock(); keyboard.keyboard_command=Mock(); keyboard.sync_time=Mock()
            with patch('rt82.time.sleep'):
                table=keyboard.upload_set(images)
            self.assertEqual(table[:3],bytes([0,count,count]))
            keyboard.keyboard_command.assert_called_once_with(0xE3,bytes([0,0,0,1,0,0,count]))
            self.assertEqual(table[3+5*count:],bytes(56-3-5*count))
            with tempfile.TemporaryDirectory() as directory:
                state=Path(directory); folder=state/'set'; folder.mkdir()
                for i,data in enumerate(images,1): (folder/f'slot-{i}.qgif').write_bytes(data)
                manifest={'status':'acknowledged-and-metadata-verified','sha256':[hashlib.sha256(x).hexdigest() for x in images],'table_hex':table.hex()}
                (folder/'manifest.json').write_text(json.dumps(manifest))
                (state/'current-set.txt').write_text(str(folder))
                paths,_=rt82.load_current_set(state)
                self.assertEqual([p.read_bytes() for p in paths],images)

    def test_delayed_erase_reply_does_not_fail_first_write(self):
        transport = object.__new__(rt82.Transport)
        transport.device = Mock()
        report = rt82.packet(0x19, 0, 0, 11, 3, data=b'abc')
        transport.device.write.return_value = 65
        transport.device.read.side_effect = [[], rt82.packet(0x18), report]
        self.assertEqual(transport.exchange(report), report)

    def test_corrupt_backup_fails_before_usb_open(self):
        with tempfile.TemporaryDirectory() as directory:
            state, folder, _ = self.save_set(directory)
            (folder / 'slot-1.qgif').write_bytes(b'QGIFbad')
            argv = ['rt82.py', 'update-cached-set', 'replacement.gif', '--slot', '2', '--state', str(state)]
            with patch('sys.argv', argv), patch('rt82.Keyboard') as device:
                with self.assertRaisesRegex(RuntimeError, 'corrupt'):
                    rt82.main()
                device.assert_not_called()

    def test_slot_update_retains_other_payloads_and_advances_state(self):
        with tempfile.TemporaryDirectory() as directory:
            state, old_folder, originals = self.save_set(directory)
            new_image = b'QGIF' + bytes([9]) * 70000
            source = state / 'updated.qgif'
            source.write_bytes(new_image)
            expected = [originals[0], new_image, originals[2]]
            keyboard = Mock()
            keyboard.inspect.side_effect = [rt82.plan_set(originals)[0], rt82.plan_set(expected)[0]]
            keyboard.upload_set.return_value = rt82.plan_set(expected)[0]
            argv = ['rt82.py', 'update-cached-set', str(source), '--slot', '2', '--state', str(state)]
            with patch('sys.argv', argv), patch('rt82.Keyboard', return_value=keyboard):
                rt82.main()
            keyboard.upload_set.assert_called_once_with(expected)
            sources, manifest = rt82.load_current_set(state)
            self.assertEqual([p.read_bytes() for p in sources], expected)
            self.assertEqual(manifest['blocks'], [0, 1, 3])
            self.assertTrue((old_folder / 'slot-2.qgif').exists())

    def test_external_metadata_change_refuses_flash_write(self):
        with tempfile.TemporaryDirectory() as directory:
            state, folder, _ = self.save_set(directory)
            keyboard = Mock()
            keyboard.inspect.return_value = bytes(56)
            argv = ['rt82.py', 'update-cached-set', str(folder / 'slot-2.qgif'), '--slot', '2', '--state', str(state)]
            with patch('sys.argv', argv), patch('rt82.Keyboard', return_value=keyboard):
                with self.assertRaisesRegex(RuntimeError, 'metadata differs'):
                    rt82.main()
            keyboard.upload_set.assert_not_called()
            self.assertEqual((state / 'current-set.txt').read_text(), str(folder))

    def test_true_slot_upload_never_falls_back_to_full_rewrite(self):
        argv = ['rt82.py', 'upload', 'unknown.gif', '--slot', '3']
        with patch('sys.argv', argv), patch('rt82.Keyboard') as device, patch('rt82.load_current_set') as backups:
            with self.assertRaisesRegex(RuntimeError, 'True single-slot'):
                rt82.main()
            device.assert_not_called()
            backups.assert_not_called()

    def test_activation_accepts_observed_handshake_response_only_when_allowed(self):
        transport = object.__new__(rt82.Transport)
        transport.device = Mock()
        transport.device.write.return_value = 33
        report = rt82.packet(0xE2, size=32)
        reply = rt82.packet(0xE0, size=32)
        transport.device.read.side_effect = [[], reply]
        self.assertEqual(transport.exchange(report, accepted_commands=(0xE0,)), reply)
        transport.device.read.side_effect = [[], reply]
        with self.assertRaises(RuntimeError): transport.exchange(report)

    def test_report_shape(self):
        report = rt82.packet(0x19, 0x34, 0x12, 0, 3, data=b'abc')
        self.assertEqual(len(report), 64)
        self.assertEqual(report[:8], bytes.fromhex('aa19341200030000'))
        self.assertEqual(report[8:11], b'abc')


if __name__ == '__main__':
    unittest.main()

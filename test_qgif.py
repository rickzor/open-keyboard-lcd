import tempfile
import unittest
from pathlib import Path
from PIL import Image
from qgif import encode_frames,decode_frames,encode_gif,inspect_qgif

class QgifTests(unittest.TestCase):
    def test_large_frame_count_and_storage_report(self):
        image = Image.new('RGB', (4,4), 'red')
        data = encode_frames([image]*1024, 16)
        info = inspect_qgif(data)
        self.assertEqual(data[6:8], b'\x04\x00')
        self.assertEqual(info['frames'], 1024)
        self.assertEqual(info['duration_seconds'], 64)
        self.assertEqual(info['bytes'], 10+8+1025)
        self.assertEqual(info['loop_reset_bytes'], 1)
        for invalid in (data[:-1], data+b'\0', data[:10]+b'\0'+data[11:]):
            with self.assertRaises(ValueError):
                inspect_qgif(invalid)

    def test_gif_frame_cap_can_be_explicitly_overridden(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as d:
            source = Path(d)/'long.gif'
            dest = Path(d)/'long.qgif'
            frames = [Image.new('RGB',(4,4),('red' if i%2 else 'blue')) for i in range(41)]
            frames[0].save(source,save_all=True,append_images=frames[1:],duration=100)
            with self.assertRaisesRegex(ValueError, 'client limit'):
                encode_gif(source,dest)
            with patch('qgif.encode_frames',return_value=b'encoded') as encode:
                encode_gif(source,dest,max_frames=41)
                self.assertEqual(len(encode.call_args.args[0]),41)
            self.assertEqual(dest.read_bytes(),b'encoded')

    def test_hand_calculated_red_block(self):
        data=encode_frames([Image.new('RGB',(4,4),'red')],10)
        self.assertEqual(data,bytes.fromhex('514749460013000100008000f800000000000000'))

    def test_known_wire_pixel_order_and_interpolation(self):
        data=bytes.fromhex('5147494600130001000080ffff00002d2d2d2d00')
        frame=decode_frames(data)[0]
        self.assertEqual(list(frame.get_flattened_data())[:4],[(255,255,255),(170,170,170),(85,85,85),(0,0,0)])

    def test_bitmap_crosses_byte_boundary_and_restores_loop(self):
        first=Image.new('RGB',(36,4),'red');last=first.copy()
        for y in range(4):
            for x in range(32,36):last.putpixel((x,y),(0,0,255))
        data=encode_frames([first,last],24)
        self.assertEqual(data[:10],bytes.fromhex('51474946002f00020800'))
        self.assertEqual(data[10:12],bytes.fromhex('ff80'))
        # Nine initial 8-byte blocks, then only block eight changes.
        self.assertEqual(data[84:86],bytes.fromhex('0080'))
        frames=decode_frames(data)
        self.assertEqual([f.tobytes() for f in frames],[first.tobytes(),last.tobytes(),first.tobytes()])

    def test_identical_frame_emits_only_empty_bitmap(self):
        image=Image.new('RGB',(8,8),'blue')
        one=encode_frames([image]);two=encode_frames([image,image])
        self.assertEqual(len(two),len(one)+1)
        self.assertEqual(two[-2:],b'\0\0')

    def test_dimensions_rate_and_count_bounds(self):
        for dims in [(3,4),(4,5),(1028,4)]:
            with self.assertRaises(ValueError):encode_frames([Image.new('RGB',dims)])
        for fps in (0,129,1.5):
            with self.assertRaises(ValueError):encode_frames([Image.new('RGB',(4,4))],fps)
        with self.assertRaises(ValueError):encode_frames([])
        with self.assertRaises(ValueError):encode_frames([Image.new('RGB',(4,4)),Image.new('RGB',(8,4))])

    def test_truncation_and_missing_keyframe_rejected(self):
        data=encode_frames([Image.new('RGB',(4,4),'red')])
        for n in (0,4,9,10,11,len(data)-1):
            with self.assertRaises(ValueError):decode_frames(data[:n])
        with self.assertRaises(ValueError):decode_frames(data[:10]+bytes(10))

    def test_local_gif_pipeline_without_vendor_or_node(self):
        with tempfile.TemporaryDirectory() as d:
            source=Path(d)/'source.gif';dest=Path(d)/'output.qgif'
            Image.new('RGB',(240,135),'red').save(source)
            data=encode_gif(source,dest)
            self.assertEqual(dest.read_bytes(),data)
            decoded=decode_frames(data)
            self.assertEqual(decoded[0].size,(240,136))
            self.assertEqual(decoded[0].getpixel((120,67)),(255,0,0))

if __name__ == '__main__':unittest.main()

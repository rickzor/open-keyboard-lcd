"""Independent QGIF encoder for the RT82, based on observed file structure.

No vendor code, WebAssembly, or JavaScript is used. See QGIF_FORMAT.md.
"""
import math
import struct
from pathlib import Path
from PIL import Image, ImageSequence


def rgb565(rgb):
    r, g, b = rgb
    return ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)


def expand565(value):
    r, g, b = value >> 11, (value >> 5) & 63, value & 31
    return ((r << 3) | (r >> 2), (g << 2) | (g >> 4), (b << 3) | (b >> 2))


def palette(a, b):
    ca, cb = expand565(a), expand565(b)
    return (ca, cb, tuple((2*x+y)//3 for x,y in zip(ca,cb)),
            tuple((x+2*y)//3 for x,y in zip(ca,cb)))


def distance(a, b):
    return sum((x-y)**2 for x,y in zip(a,b))


def encode_block(pixels):
    """Fit two RGB565 endpoints and 16 MSB-first two-bit selectors."""
    colors = tuple(dict.fromkeys(pixels))
    if len(colors) == 1:
        return struct.pack('<HH', rgb565(colors[0]), 0) + bytes(4)
    # The most distant pair spans the local color range. Unlike the proprietary
    # encoder, this implementation prioritizes a small, inspectable algorithm.
    a, b = max(((a,b) for i,a in enumerate(colors) for b in colors[i+1:]),
               key=lambda pair: distance(*pair))
    a, b = sorted((rgb565(a), rgb565(b)), reverse=True)
    choices = palette(a,b)
    indices = [min(range(4), key=lambda i: distance(pixel,choices[i])) for pixel in pixels]
    rows = bytes(sum(indices[y*4+x] << (6-2*x) for x in range(4)) for y in range(4))
    return struct.pack('<HH', a, b) + rows


def frame_blocks(frame):
    frame = frame.convert('RGB')
    w,h = frame.size
    raw = list(frame.get_flattened_data())
    return tuple(encode_block(tuple(raw[(by+y)*w+bx+x] for y in range(4) for x in range(4)))
                 for by in range(0,h,4) for bx in range(0,w,4))


def delta_frame(previous, current):
    bitmap = bytearray((len(current)+7)//8)
    changed = []
    for i,block in enumerate(current):
        if previous is None or previous[i] != block:
            bitmap[i//8] |= 1 << (7-i%8)
            changed.append(block)
    return bytes(bitmap) + b''.join(changed)


def encode_frames(frames, fps=10):
    frames = list(frames)
    if not 1 <= len(frames) <= 65535:
        raise ValueError('QGIF requires 1..65535 frames')
    if not isinstance(fps,int) or not 1 <= fps <= 128:
        raise ValueError('QGIF frame rate must be an integer from 1 to 128')
    w,h = frames[0].size
    if not (4 <= w <= 1024 and 4 <= h <= 1024 and w%4 == h%4 == 0):
        raise ValueError('QGIF dimensions must be multiples of four, from 4 to 1024')
    if any(frame.size != (w,h) for frame in frames):
        raise ValueError('All QGIF frames must have the same dimensions')
    result = bytearray(b'QGIF' + bytes([0,2*fps-1]) + struct.pack('>H',len(frames))
                       + bytes([w//4-1,h//4-1]))
    first = previous = None
    for frame in frames:
        current = frame_blocks(frame)
        result.extend(delta_frame(previous,current))
        if first is None: first=current
        previous=current
    # The stream includes a final delta back to its first frame for looping.
    result.extend(delta_frame(previous,first))
    return bytes(result)


def encode_gif(source, destination, max_frames=40):
    if not 1 <= max_frames <= 65535:
        raise ValueError('max_frames must be between 1 and 65535')
    with Image.open(source) as image:
        if getattr(image,'n_frames',1) > max_frames:
            raise ValueError(f'Animation exceeds the configured {max_frames}-frame limit; '
                             'this is a client limit, not a verified firmware maximum')
        delay=image.info.get('duration',100) or 100
        fps=max(1,min(128,math.floor(1000/delay+.5)))
        frames=[]
        for frame in ImageSequence.Iterator(image):
            rgba=frame.convert('RGBA').resize((240,136),Image.Resampling.BICUBIC)
            canvas=Image.new('RGBA',rgba.size,(0,0,0,255))
            canvas.alpha_composite(rgba)
            frames.append(canvas.convert('RGB'))
    data=encode_frames(frames,fps)
    Path(destination).write_bytes(data)
    return data


def inspect_qgif(data):
    """Validate record boundaries and report storage/transport costs without decoding pixels."""
    if len(data) < 10 or data[:4] != b'QGIF' or data[4] or not data[5] & 1:
        raise ValueError('Unsupported QGIF header')
    count = int.from_bytes(data[6:8], 'big')
    if not count:
        raise ValueError('Empty QGIF')
    width, height = (data[8]+1)*4, (data[9]+1)*4
    blocks = width*height//16
    mask_bytes = (blocks+7)//8
    offset = 10
    record_sizes = []
    current = [None]*blocks
    first = None
    for frame in range(count+1):
        start = offset
        mask = data[offset:offset+mask_bytes]
        if len(mask) != mask_bytes:
            raise ValueError('Truncated bitmap')
        offset += mask_bytes
        if blocks % 8 and mask[-1] & ((1 << (8-blocks % 8))-1):
            raise ValueError('Nonzero bitmap padding')
        for i in range(blocks):
            if mask[i//8] & (1 << (7-i%8)):
                block = data[offset:offset+8]
                if len(block) != 8:
                    raise ValueError('Truncated block')
                current[i] = block
                offset += 8
            if current[i] is None:
                raise ValueError('First frame contains missing blocks')
        if first is None:
            first = tuple(current)
        record_sizes.append(offset-start)
    if offset != len(data):
        raise ValueError('Trailing QGIF data')
    if tuple(current) != first:
        raise ValueError('Invalid loop reset')
    fps = (data[5]+1)//2
    return {'width': width, 'height': height, 'frames': count, 'fps': fps,
            'duration_seconds': count/fps, 'bytes': len(data),
            'flash_blocks_64k': math.ceil(len(data)/65536),
            'usb_payload_reports': math.ceil(len(data)/56),
            'largest_frame_record_bytes': max(record_sizes[:-1]),
            'loop_reset_bytes': record_sizes[-1]}


def decode_frames(data):
    """Strict reference decoder for format tests; returns frames plus loop reset."""
    if len(data)<10 or data[:4]!=b'QGIF' or data[4]!=0 or not data[5]&1:
        raise ValueError('Unsupported QGIF header')
    count=struct.unpack('>H',data[6:8])[0]
    if not count:raise ValueError('Empty QGIF')
    w,h=(data[8]+1)*4,(data[9]+1)*4
    total=w*h//16; mask_size=(total+7)//8
    blocks=[None]*total; offset=10; frames=[]
    for frame_index in range(count+1):
        mask=data[offset:offset+mask_size];offset+=mask_size
        if len(mask)!=mask_size:raise ValueError('Truncated bitmap')
        for i in range(total):
            if mask[i//8] & (1<<(7-i%8)):
                block=data[offset:offset+8];offset+=8
                if len(block)!=8:raise ValueError('Truncated block')
                blocks[i]=block
            if blocks[i] is None:raise ValueError('First frame contains missing blocks')
        out=Image.new('RGB',(w,h));pixels=out.load()
        for i,block in enumerate(blocks):
            a,b=struct.unpack('<HH',block[:4]);colors=palette(a,b)
            bx=(i%(w//4))*4;by=(i//(w//4))*4
            for y in range(4):
                for x in range(4):pixels[bx+x,by+y]=colors[(block[4+y]>>(6-2*x))&3]
        frames.append(out)
    if offset!=len(data):raise ValueError('Trailing QGIF data')
    if frames[0].tobytes()!=frames[-1].tobytes():raise ValueError('Invalid loop reset')
    return frames

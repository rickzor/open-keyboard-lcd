#!/usr/bin/env python3
"""Browser-free RT82 LCD updater. Protocol recovered from Epomaker Hub."""
import argparse
import ctypes
import datetime
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import time

import hid
from qgif import encode_gif, inspect_qgif

ROOT = Path(__file__).resolve().parent
VID, PID = 14000, 12451
LCD_VID = LCD_PID = 6425


def encode(source, destination):
    return encode_gif(source, destination)


def packet(command, p1=0, p2=0, p3=0, p4=0, data=b'', size=64):
    if len(data) > size - 8:
        raise ValueError('Payload exceeds report size')
    result = bytearray(size)
    result[:6] = bytes([0xAA, command, p1, p2, p3, p4])
    result[8:8 + len(data)] = data
    return bytes(result)


class Transport:
    def __init__(self, vendor, product, usage_page, usage=None):
        devices = [d for d in hid.enumerate(vendor, product)
                   if d['usage_page'] == usage_page and (usage is None or d['usage'] == usage)]
        if len(devices) != 1:
            raise RuntimeError(f'Expected one HID interface {vendor:04x}:{product:04x}; found {len(devices)}')
        identity = repr((devices[0]['path'], devices[0].get('serial_number')))
        self.identity = hashlib.sha256(identity.encode()).hexdigest()
        if sys.platform == 'darwin':
            # Never seize the keyboard from the OS or Chrome.
            ctypes.CDLL(hid.__file__).hid_darwin_set_open_exclusive(0)
        self.device = hid.device()
        try:
            self.device.open_path(devices[0]['path'])
        except OSError as error:
            raise RuntimeError('Cannot open HID interface. Run locally outside the Codex sandbox; '
                               'if macOS requests Input Monitoring, grant it to the running terminal/runtime.') from error

    def exchange(self, report, wait=True, timeout=5000, accepted_commands=()):
        # Drain stale replies, especially the unawaited FLASH_ERASE acknowledgement.
        while self.device.read(64, 1):
            pass
        sent = self.device.write(b'\x00' + report)  # HIDAPI needs report ID 0 prefix.
        if sent != len(report) + 1:
            raise RuntimeError(f'Short HID write: {sent}')
        if not wait:
            return b''
        deadline = time.monotonic() + timeout / 1000
        while time.monotonic() < deadline:
            remaining = max(1, math.ceil((deadline - time.monotonic()) * 1000))
            response = bytes(self.device.read(len(report), remaining))
            if (len(response) == len(report) and response[0] == report[0]
                    and response[1] in (report[1], *accepted_commands)):
                return response
            # FLASH_ERASE is deliberately sent without awaiting its reply, as
            # in Hub. Hardware can deliver that reply after FLASH_WRITE starts.
            if len(response) == 64 and response[:2] == b'\xaa\x18':
                continue
            raise RuntimeError(f'Invalid or timed-out reply to command 0x{report[1]:02x}: {response.hex()}')
        raise RuntimeError(f'Timed out waiting for command 0x{report[1]:02x}')

    def close(self):
        self.device.close()


class Keyboard:
    def __init__(self):
        self.via = Transport(VID, PID, 0xFF60, 0x61)
        self.lcd = None

    def keyboard_command(self, command, payload=b''):
        report = (bytes([0xAA, command]) + payload).ljust(32, b'\x00')
        # This firmware can answer the E2 mode query with an E0 handshake.
        return self.via.exchange(report, accepted_commands=(0xE0,) if command == 0xE2 else ())

    def activate(self):
        for attempt in range(2):
            self.keyboard_command(0xE2)
            for _ in range(5):
                self.keyboard_command(0xE0)
            time.sleep(1 + attempt * 0.5)
            for _ in range(12):
                if any(d['usage_page'] == 0xFF for d in hid.enumerate(LCD_VID, LCD_PID)):
                    self.lcd = Transport(LCD_VID, LCD_PID, 0xFF)
                    return
                time.sleep(0.25)
        raise RuntimeError('LCD HID device 1919:1919 did not appear')

    def command(self, command, *parameters, data=b'', wait=True):
        return self.lcd.exchange(packet(command, *parameters, data=data), wait=wait)

    def sync_time(self):
        now = datetime.datetime.now()
        values = [int(c) for c in f'{now.year:04d}{now.month:02d}']
        values += [(now.weekday() + 1) % 7]
        values += [int(c) for c in now.strftime('%d%H%M%S')]
        self.command(0x10)
        self.command(0x17, 0, 0, 0, 56, data=bytes(values))
        self.command(0x11)

    def inspect(self):
        response = self.command(0x14, 0, 0, 0, 56)
        return response[8:64]

    def screen_info(self):
        response = self.command(0x12, 0, 0, 0, 56)
        width = int.from_bytes(response[20:22], 'little')
        height = int.from_bytes(response[22:24], 'little')
        rotation = response[26]
        if rotation in (1, 3):
            width, height = height, width
        return {'width': width, 'height': height, 'max_slots': response[25],
                'rotation': rotation, 'image_size_field_raw': response[24],
                'image_size_field_units': 'unknown; not a verified flash capacity',
                'response_hex': response.hex()}

    def upload_set(self, images, reserve_blocks=0):
        """Replace all three display slots using Hub's batch-upload sequence."""
        table, starts, erase_blocks = plan_set(images, reserve_blocks)
        pool_path = ROOT / 'state' / 'append-pool.json'
        if not reserve_blocks and pool_path.exists():
            from pool import save_ledger
            save_ledger(pool_path, {'version': 1, 'status': 'invalidated-by-full-upload'})
        self.command(0x1B, 0, 0, 0, 56)
        self.keyboard_command(0xE3, bytes([0, 0, 0, 1, 0, 0, 3]))
        time.sleep(0.1)
        self.command(0x14, 0, 0, 0, 56)
        self.command(0x15, 0, 0, 0, 56, data=table)
        self.command(0x15, 56, 0, 0, 56)
        self.command(0x15, 112, 0, 0, 16)
        self.command(0x16, 0, 0, 0, 56)
        self.command(0x18, 0, 0, 0, 1, data=bytes([erase_blocks]), wait=False)
        time.sleep(0.5 * erase_blocks)
        for slot, (data, start) in enumerate(zip(images, starts), 1):
            print(f'Writing slot {slot}: {len(data)} bytes at block {start}', flush=True)
            for offset in range(0, len(data), 56):
                address = start * 65536 + offset
                chunk = data[offset:offset + 56]
                self.command(0x19, address & 255, (address >> 8) & 255,
                             (address >> 16) & 255, len(chunk), data=chunk)
        self.command(0x1A)
        self.sync_time()
        return table

    def close(self):
        if self.lcd:
            self.lcd.close()
        self.via.close()


def plan_set(images, reserve_blocks=0):
    if reserve_blocks not in (0, 1):
        raise ValueError('Only the tested one-block reservation is supported')
    if len(images) != 3 or any(not image.startswith(b'QGIF') for image in images):
        raise ValueError('Exactly three encoded QGIF images are required')
    table, starts, block = bytearray(56), [], 0
    for i, image in enumerate(images):
        if len(image) >= 1 << 24:
            raise ValueError('Image exceeds the protocol size limit')
        starts.append(block)
        table[3+i*5:8+i*5] = bytes([block, 0]) + len(image).to_bytes(3, 'little')
        block += math.ceil(len(image) / 65536)
        if block + 1 > 255:
            raise ValueError('Complete image set exceeds the protocol block limit')
    if reserve_blocks and (starts != [0, 1, 2] or block != 3):
        raise ValueError('Reserved-space mode requires three images of at most 64 KiB each')
    block += reserve_blocks
    table[:3] = bytes([0, 3, block])
    return bytes(table), starts, block + 1


def load_current_set(state):
    folder = Path((state / 'current-set.txt').read_text().strip())
    manifest = json.loads((folder / 'manifest.json').read_text())
    if manifest.get('status') != 'acknowledged-and-metadata-verified':
        raise RuntimeError('The saved set was not successfully uploaded; use replace-all to establish a complete set')
    sources = [folder / f'slot-{slot}.qgif' for slot in (1, 2, 3)]
    images = [source.read_bytes() for source in sources]
    if [hashlib.sha256(data).hexdigest() for data in images] != manifest.get('sha256'):
        raise RuntimeError('Saved image backup is missing or corrupt; refusing to overwrite the keyboard')
    table, _, _ = plan_set(images)
    if table.hex() != manifest.get('table_hex'):
        raise RuntimeError('Saved slot table does not match the image backups')
    return sources, manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('devices')
    sub.add_parser('probe', help='Activate LCD and read slot metadata; does not erase images')
    sub.add_parser('screen-info', help='Read LCD dimensions and raw device information without flash writes')
    sub.add_parser('sync-time')
    enc = sub.add_parser('encode')
    enc.add_argument('source', type=Path)
    enc.add_argument('destination', type=Path)
    enc.add_argument('--max-frames', type=int, default=40,
                     help='Encoding cap (default 40); higher values are experimental on hardware')
    stats = sub.add_parser('qgif-info', help='Validate a QGIF and show duration/storage costs without USB access')
    stats.add_argument('source', type=Path)
    upload = sub.add_parser('upload', help='True single-slot update (blocked pending protocol verification)')
    upload.add_argument('source', type=Path)
    upload.add_argument('--slot', type=int, choices=[1, 2, 3], required=True)
    upload.add_argument('--state', type=Path, default=ROOT / 'state')
    upload.add_argument('--if-changed', action='store_true')
    batch = sub.add_parser('replace-all', help='Replace all three LCD slots and retain local QGIF backups')
    batch.add_argument('sources', type=Path, nargs=3, metavar='GIF')
    batch.add_argument('--state', type=Path, default=ROOT / 'state')
    cached = sub.add_parser('update-cached-set', help='Explicitly rewrite ALL slots using local backups')
    cached.add_argument('source', type=Path)
    cached.add_argument('--slot', type=int, choices=[1, 2, 3], required=True)
    cached.add_argument('--state', type=Path, default=ROOT / 'state')
    cached.add_argument('--if-changed', action='store_true')
    args = parser.parse_args()
    if args.command == 'qgif-info':
        print(json.dumps(inspect_qgif(args.source.read_bytes()), indent=2))
        return
    if args.command == 'upload':
        raise RuntimeError('True single-slot updates are not yet verified on this firmware. '
                           'Refusing to erase or rewrite other slots. No USB commands were sent.')
    if args.command == 'update-cached-set' and args.source.is_dir():
        candidates = [path for path in args.source.iterdir()
                      if path.is_file() and path.suffix.lower() == '.gif']
        if not candidates:
            raise ValueError(f'No GIFs found in {args.source}')
        args.source = max(candidates, key=lambda path: (path.stat().st_mtime_ns, path.name))
        print(f'Selected newest GIF: {args.source}', flush=True)
    if args.command == 'devices':
        for device in hid.enumerate():
            if device['vendor_id'] in (VID, LCD_VID):
                print({key: value for key, value in device.items() if key != 'path'})
        return
    if args.command == 'encode':
        data = encode_gif(args.source, args.destination, max_frames=args.max_frames)
        print(f'Encoded {len(data)} bytes')
        return
    # A process lock prevents overlapping hourly/manual USB transactions.
    lock_path = ROOT / '.usb.lock'
    with lock_path.open('w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print('Another update is running; skipping')
            return
        previous_manifest = None
        if args.command == 'update-cached-set':
            args.sources, previous_manifest = load_current_set(args.state)
            args.sources[args.slot - 1] = args.source
        if args.command in ('replace-all', 'update-cached-set'):
            transaction = args.state / 'sets' / str(time.time_ns())
            transaction.mkdir(parents=True)
            images = []
            for slot, source in enumerate(args.sources, 1):
                target = transaction / f'slot-{slot}.qgif'
                data = source.read_bytes() if source.suffix.lower() == '.qgif' else encode(source, target)
                target.write_bytes(data)
                images.append(data)
            table, starts, _ = plan_set(images)
            manifest = {'status': 'prepared', 'sources': [str(p.resolve()) for p in args.sources],
                        'sha256': [hashlib.sha256(b).hexdigest() for b in images],
                        'bytes': [len(b) for b in images], 'blocks': starts, 'table_hex': table.hex()}
            (transaction / 'manifest.json').write_text(json.dumps(manifest, indent=2))
            if (args.command == 'update-cached-set' and args.if_changed
                    and manifest['sha256'] == previous_manifest['sha256']):
                print('Saved images unchanged; skipped flash write')
                return
        keyboard = Keyboard()
        try:
            keyboard.activate()
            if args.command == 'screen-info':
                print(json.dumps(keyboard.screen_info(), indent=2))
                keyboard.command(0x11)
            elif args.command == 'probe':
                table = keyboard.inspect()
                print(json.dumps({'table_hex': table.hex(), 'slots': [
                    {'slot': i+1, 'block': table[3+i*5], 'bytes': int.from_bytes(table[5+i*5:8+i*5], 'little')}
                    for i in range(3)]}, indent=2))
                keyboard.command(0x11)
            elif args.command == 'sync-time':
                keyboard.sync_time()
            elif args.command in ('replace-all', 'update-cached-set'):
                before = keyboard.inspect()
                (transaction / 'table-before.bin').write_bytes(before)
                if previous_manifest and before[:18].hex() != previous_manifest['table_hex'][:36]:
                    keyboard.command(0x11)
                    raise RuntimeError('Keyboard slot metadata differs from the saved set; refusing an automatic update')
                manifest['status'] = 'uploading'
                (transaction / 'manifest.json').write_text(json.dumps(manifest, indent=2))
                expected = keyboard.upload_set(images)
                keyboard.lcd.close()
                keyboard.lcd = None
                keyboard.activate()
                actual = keyboard.inspect()
                keyboard.command(0x11)
                (transaction / 'table-after.bin').write_bytes(actual)
                if actual[:18] != expected[:18]:
                    raise RuntimeError('Slot metadata did not match the complete uploaded set')
                manifest['status'] = 'acknowledged-and-metadata-verified'
                (transaction / 'manifest.json').write_text(json.dumps(manifest, indent=2))
                pending = args.state / 'current-set.tmp'
                pending.write_text(str(transaction.resolve()))
                pending.replace(args.state / 'current-set.txt')
                print('All three uploads acknowledged; slot metadata verified. Visual confirmation still required.', flush=True)
        finally:
            keyboard.close()


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, RuntimeError) as error:
        print(f'Error: {error}', file=sys.stderr)
        sys.exit(1)

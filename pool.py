#!/usr/bin/env python3
"""Experimental one-slot append into explicitly initialized spare storage.

Only the tested three one-block images + one spare block layout is supported.
Initialization replaces every image. Append needs no other image payloads.
"""
import argparse
import fcntl
import json
import os
from pathlib import Path
import sys
import tempfile
import time

import rt82
from qgif import encode_gif, inspect_qgif

LEDGER = rt82.ROOT / 'state' / 'append-pool.json'


def save_ledger(path, value):
    """Durably replace state before issuing potentially consuming USB commands."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.pool-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(value, stream, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def load_image(path):
    if path.suffix.lower() == '.qgif':
        data = path.read_bytes()
    else:
        with tempfile.TemporaryDirectory() as directory:
            data = encode_gif(path, Path(directory)/'image.qgif')
    validate_image(data)
    return data


def validate_image(data):
    info = inspect_qgif(data)
    if (info['width'], info['height']) != (240, 136) or len(data) > 65536:
        raise ValueError('Experimental pool images must be 240x136 QGIFs of at most 64 KiB')


def initialize(keyboard, images, path=LEDGER):
    if len(images) != 3:
        raise ValueError('Initialization needs all three images')
    for image in images:
        validate_image(image)
    table, _, _ = rt82.plan_set(images, reserve_blocks=1)
    ledger = {'version': 1, 'status': 'initializing', 'identity': keyboard.via.identity,
              'next_block': 3, 'end_block': 4, 'table_hex': table.hex()}
    save_ledger(path, ledger)  # Invalidates earlier state before any destructive command.
    keyboard.upload_set(images, reserve_blocks=1)
    actual = keyboard.inspect()
    keyboard.command(0x11)
    if actual != table:
        raise RuntimeError('Initialization metadata mismatch; pool remains disabled')
    ledger['status'] = 'ready'
    save_ledger(path, ledger)
    return ledger


def plan_append(ledger, image, slot):
    validate_image(image)
    if slot not in (1, 2, 3):
        raise ValueError('Slot must be 1, 2, or 3')
    if ledger.get('status') == 'exhausted':
        raise RuntimeError('Spare block exhausted; explicitly reinitialize all three images to reserve new space')
    if ledger.get('version') != 1 or ledger.get('status') != 'ready':
        raise RuntimeError('Pool is not ready; explicitly initialize a complete set')
    if ledger.get('next_block') != 3 or ledger.get('end_block') != 4:
        raise RuntimeError('Spare block exhausted or state invalid; no automatic erase is allowed')
    before = bytes.fromhex(ledger['table_hex'])
    if len(before) != 56 or before[:3] != bytes([0, 3, 4]):
        raise RuntimeError('Invalid allocation table')
    for i in range(3):
        entry = before[3+i*5:8+i*5]
        if entry[0] != i or entry[1] or not 1 <= int.from_bytes(entry[2:], 'little') <= 65536:
            raise RuntimeError('Pool no longer has its initialized layout')
    after = bytearray(before)
    offset = 3+(slot-1)*5
    after[offset:offset+5] = bytes([3, 0])+len(image).to_bytes(3, 'little')
    return before, bytes(after), 3


def append(keyboard, image, slot, path=LEDGER):
    ledger = json.loads(path.read_text())
    before, after, block = plan_append(ledger, image, slot)
    if ledger.get('identity') != keyboard.via.identity:
        raise RuntimeError('Different HID identity/path; refusing to use saved allocation state')
    if keyboard.inspect() != before:
        raise RuntimeError('Device table changed; refusing to use saved allocation state')
    ledger.update(status='writing', next_block=4, pending_table_hex=after.hex(), slot=slot)
    save_ledger(path, ledger)  # A crash/failure burns the block; never silently retry.
    keyboard.command(0x1B, 0, 0, 0, 56)
    keyboard.keyboard_command(0xE3, bytes([0, 0, 0, 1, 0, 0, 3]))
    time.sleep(.1)
    keyboard.command(0x14, 0, 0, 0, 56)
    keyboard.command(0x15, 0, 0, 0, 56, data=after)
    keyboard.command(0x15, 56, 0, 0, 56)
    keyboard.command(0x15, 112, 0, 0, 16)
    keyboard.command(0x16, 0, 0, 0, 56)
    for offset in range(0, len(image), 56):
        address = block*65536+offset
        chunk = image[offset:offset+56]
        keyboard.command(0x19, address & 255, (address >> 8) & 255,
                         (address >> 16) & 255, len(chunk), data=chunk)
    keyboard.command(0x1A)
    keyboard.sync_time()
    actual = keyboard.inspect()
    keyboard.command(0x11)
    if actual != after:
        raise RuntimeError('Append metadata mismatch; consumed block remains unavailable')
    ledger.update(status='exhausted', table_hex=after.hex())
    ledger.pop('pending_table_hex', None)
    save_ledger(path, ledger)
    return ledger


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    init = sub.add_parser('init', help='REPLACE ALL three images and reserve one spare block')
    init.add_argument('sources', nargs=3, type=Path)
    update = sub.add_parser('append', help='Replace one slot once; never erase storage')
    update.add_argument('source', type=Path)
    update.add_argument('--slot', type=int, choices=(1, 2, 3), required=True)
    sub.add_parser('status')
    args = parser.parse_args()
    if args.command == 'status':
        print(LEDGER.read_text() if LEDGER.exists() else 'No pool initialized')
        return
    images = [load_image(p) for p in args.sources] if args.command == 'init' else [load_image(args.source)]
    with (rt82.ROOT/'.usb.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.command == 'append':
            # Exhausted/incomplete ledgers fail before even opening a HID interface.
            plan_append(json.loads(LEDGER.read_text()), images[0], args.slot)
        keyboard = rt82.Keyboard()
        try:
            keyboard.activate()
            result = initialize(keyboard, images) if args.command == 'init' else append(keyboard, images[0], args.slot)
            print(json.dumps(result, indent=2))
            print('Commands acknowledged and metadata matched; visual playback is not verified automatically.')
        finally:
            keyboard.close()


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, RuntimeError, KeyError) as error:
        print(f'Error: {error}', file=sys.stderr)
        sys.exit(1)

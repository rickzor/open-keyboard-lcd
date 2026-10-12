"""Read macOS display power state; no screen capture or display control."""
import ctypes
import time

class DisplaySleep:
    def __init__(self,settle_seconds=3,clock=time.monotonic):
        self.clock=clock;self.settle=settle_seconds;self.candidate=None;self.since=0
        self.cg=ctypes.CDLL('/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics')
        self.cg.CGGetOnlineDisplayList.argtypes=[ctypes.c_uint32,ctypes.POINTER(ctypes.c_uint32),ctypes.POINTER(ctypes.c_uint32)]
        self.cg.CGGetOnlineDisplayList.restype=ctypes.c_int32
        self.cg.CGDisplayIsAsleep.argtypes=[ctypes.c_uint32];self.cg.CGDisplayIsAsleep.restype=ctypes.c_uint32
    def read(self):
        ids=(ctypes.c_uint32*32)();count=ctypes.c_uint32()
        error=self.cg.CGGetOnlineDisplayList(32,ids,ctypes.byref(count))
        if error or not count.value:return None
        return all(self.cg.CGDisplayIsAsleep(ids[i]) for i in range(count.value))
    def poll(self):
        value=self.read();now=self.clock()
        if value is None:
            self.candidate=None;return None
        if value!=self.candidate:self.candidate=value;self.since=now
        return value if now-self.since>=self.settle else None

"""EventKit app with its own macOS privacy identity; temporary results stay local."""
import json
import plistlib
from pathlib import Path
import subprocess
import tempfile
ROOT=Path(__file__).resolve().parents[2]
APP=Path.home()/'Library/Application Support/OpenKeyboardLCD/Keyboard LCD Calendar.app'

def build():
    contents=APP/'Contents';(contents/'MacOS').mkdir(parents=True,exist_ok=True)
    info={'CFBundleIdentifier':'org.open-keyboard-lcd.calendar-reader','CFBundleName':'Keyboard LCD Calendar',
        'CFBundleExecutable':'calendar-reader','CFBundlePackageType':'APPL','CFBundleVersion':'1',
        'LSUIElement':True,'NSCalendarsFullAccessUsageDescription':'Read upcoming meetings for one-minute reminders on your keyboard. Events stay on this Mac.'}
    with (contents/'Info.plist').open('wb') as out:plistlib.dump(info,out)
    subprocess.run(['xcrun','clang','-fobjc-arc','-O2','-mmacosx-version-min=14.0','-framework','Foundation','-framework','EventKit',str(ROOT/'examples-sandbox/automations/CalendarReader.m'),'-o',str(contents/'MacOS/calendar-reader')],check=True)
    for attr in ('com.apple.FinderInfo','com.apple.ResourceFork'):
        subprocess.run(['xattr','-dr',attr,str(APP)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    subprocess.run(['codesign','--force','--sign','-','--identifier',info['CFBundleIdentifier'],str(APP)],check=True)

def read(authorize=False):
    with tempfile.TemporaryDirectory(prefix='calendar-',dir=APP.parent) as folder:
        path=Path(folder)/'events.json'
        args=['/usr/bin/open','-W','-n',str(APP),'--args','--output',str(path)]
        if authorize:args+=['--authorize']
        subprocess.run(args,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=135 if authorize else 20,check=True)
        if not path.exists():raise RuntimeError('Calendar permission unavailable')
        return json.loads(path.read_text())
if __name__=='__main__':
    import sys
    if '--build' in sys.argv:build()
    else:
        read(authorize='--authorize' in sys.argv)
        print('Calendar access ready. Event details are not printed.')

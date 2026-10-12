#!/usr/bin/env python3
"""Install, inspect, or remove this user's macOS LCD LaunchAgent."""
import argparse
import os
from pathlib import Path
import plistlib
import subprocess
import sys
import time
ROOT=Path(__file__).resolve().parents[2]
LABEL='org.open-keyboard-lcd.weather-notifications'
p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['install','status','uninstall']);p.add_argument('--seed-weather',type=Path);a=p.parse_args()
path=Path.home()/'Library/LaunchAgents'/f'{LABEL}.plist';domain=f'gui/{os.getuid()}';target=f'{domain}/{LABEL}'
if a.action=='status':
 result=subprocess.run(['launchctl','print',target],capture_output=True,text=True)
 # launchctl print includes inherited secrets: only emit operational fields.
 for line in result.stdout.splitlines():
  if line.strip().startswith(('state =','pid =','runs =','last exit code =')):print(line.strip())
 if result.returncode:print('Service is not loaded.')
 raise SystemExit(result.returncode)
if a.action=='uninstall':
 subprocess.run(['launchctl','bootout',target],check=False)
 path.unlink(missing_ok=True);raise SystemExit(0)
logs=ROOT/'state/weather-notifications';logs.mkdir(parents=True,exist_ok=True,mode=0o700)
args=[sys.executable,'-u',str(Path(__file__).with_name('service.py'))]
if a.seed_weather:args+=['--seed-weather',str(a.seed_weather.resolve())]
config={'Label':LABEL,'ProgramArguments':args,'WorkingDirectory':str(ROOT),
 'EnvironmentVariables':{'OPENAI_API_KEY':''},
 'RunAtLoad':True,'KeepAlive':{'SuccessfulExit':False},'ThrottleInterval':60,
 'ProcessType':'Standard','Umask':63,
 'StandardOutPath':str(logs/'service.log'),'StandardErrorPath':str(logs/'error.log')}
path.parent.mkdir(parents=True,exist_ok=True)
if subprocess.run(['launchctl','print',target],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0:
 subprocess.run(['launchctl','bootout',target],check=True)
 time.sleep(2)
with path.open('wb') as out:plistlib.dump(config,out)
subprocess.run(['launchctl','bootstrap',domain,str(path)],check=True)
print('Installed and started '+LABEL)

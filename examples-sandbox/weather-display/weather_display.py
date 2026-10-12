#!/usr/bin/env python3
"""Weather-reel experiment, linked to the resident notification controller."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'notification-display'))
import display

display.DEFAULT_STATE=display.ROOT/'state'/'weather-display'
display.DEFAULT_NAMES=['Lo-fi 3D Weather']

if __name__=='__main__': display.main()

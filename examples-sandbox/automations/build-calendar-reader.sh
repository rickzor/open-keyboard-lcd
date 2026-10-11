#!/bin/sh
set -eu
cd "$(dirname "$0")"
xcrun clang -fobjc-arc -O2 -mmacosx-version-min=14.0 \
  -framework Foundation -framework EventKit CalendarReader.m \
  -Wl,-sectcreate,__TEXT,__info_plist,CalendarReader-Info.plist -o calendar-reader
codesign --force --sign - --identifier org.open-keyboard-lcd.calendar-reader calendar-reader
printf '%s\n' 'Built calendar-reader. Run ./calendar-reader --authorize once in your terminal.'

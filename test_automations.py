import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from PIL import Image
sys.path.insert(0,str(Path(__file__).parent/'examples-sandbox'/'automations'))
from lcd_automations import Display, due_meetings, tick
from widgets import crop_for_lcd, weather_frames


class AutomationTests(unittest.TestCase):
    def test_fit_width_then_center_crop_or_pad(self):
        im=Image.new('RGB',(120,100),'red')
        # After width doubles, the 50px central source band spans 100px.
        for y in range(25,75):
            for x in range(120): im.putpixel((x,y),(0,255,0))
        result=crop_for_lcd(im)
        self.assertEqual(result.size,(240,136))
        self.assertEqual(result.getpixel((120,0)),(255,0,0))
        self.assertEqual(result.getpixel((120,67)),(0,255,0))
        self.assertEqual(result.getpixel((120,134)),(255,0,0))
        self.assertEqual(result.getpixel((0,135)),(0,0,0))
        wide=crop_for_lcd(Image.new('RGB',(480,100),'blue'))
        self.assertEqual(wide.getpixel((0,42)),(0,0,255))
        self.assertEqual(wide.getpixel((239,91)),(0,0,255))
        self.assertEqual(wide.getpixel((120,41)),(0,0,0))

    def test_weather_is_animated_but_temperature_is_still(self):
        frames=weather_frames({'code':61,'temperature':63,'unit':'F','day':True,'time':'12:30'})
        self.assertNotEqual(frames[0].tobytes(),frames[3].tobytes())
        self.assertEqual(frames[0].crop((10,35,135,80)).tobytes(),frames[3].crop((10,35,135,80)).tobytes())

    def test_alert_restores_exact_prior_image_after_restart_and_overlap(self):
        with tempfile.TemporaryDirectory() as folder:
            display=Display(folder)
            def asset(color): return display.asset([Image.new('RGB',(240,136),color)],4,color)
            original=asset('blue'); display.base(original)
            alert=asset('red'); display.alert(alert,160,'a')
            second=asset('yellow'); display.alert(second,175,'b')
            changed=asset('green'); display.base(changed)
            self.assertEqual(display.state['visible'],second)
            self.assertEqual(display.state['restore'],original)
            resumed=Display(folder); self.assertFalse(resumed.expire(174))
            self.assertTrue(resumed.expire(175)); self.assertEqual(resumed.state['visible'],original)
            resumed.alert(alert,200,'a') # previously consumed event stays deduplicated
            self.assertEqual(resumed.state['visible'],original)

    def test_interrupted_transaction_fails_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder)/'display.json').write_text(json.dumps({'pending':True,'usb':True}))
            with self.assertRaisesRegex(RuntimeError,'interrupted'): Display(folder,usb=True)

    def test_explicit_reinitialization_clears_old_alert(self):
        with tempfile.TemporaryDirectory() as folder:
            display=Display(folder)
            base=display.asset([Image.new('RGB',(240,136),'blue')],4,'base'); display.base(base)
            alert=display.asset([Image.new('RGB',(240,136),'red')],4,'alert'); display.alert(alert,200,'x')
            display.base(base,initialize=True)
            self.assertNotIn('until',display.state)
            self.assertEqual(display.state['visible'],base)

    def test_event_window_and_exclusions(self):
        events=[{'id':str(i),'start':start} for i,start in enumerate([99,100,101,160,161])]
        events += [{'id':'all-day','start':150,'all_day':True},{'id':'declined','start':150,'declined':True}]
        found=due_meetings(events,100,{})
        self.assertEqual([x[0] for x in found],[101,160])
        self.assertEqual(len(due_meetings(events,100,{found[0][1]:161})),1)

    def test_periods_and_meeting_priority(self):
        with tempfile.TemporaryDirectory() as folder:
            display=Display(folder); base=display.asset([Image.new('RGB',(240,136),'blue')],4,'base'); display.base(base)
            calls=[]
            providers={'giphy':lambda *a:(calls.append('giphy') or [Image.new('RGB',(240,136),'green')],{}),
                       'weather':lambda *a: calls.append('weather') or {'code':0,'temperature':63,'unit':'F','day':True},
                       'calendar':lambda *a:[]}
            config={'giphy':True,'weather':True}; schedule={}
            tick(display,config,100,schedule,providers)
            self.assertEqual(calls,['giphy'])
            tick(display,config,1899,schedule,providers); self.assertEqual(calls,['giphy'])
            tick(display,config,1900,schedule,providers); self.assertEqual(calls,['giphy','weather'])
            config['calendar']=True
            providers['calendar']=lambda *a:[{'id':'a','start':3750,'title':'Private meeting'}]
            tick(display,config,3700,schedule,providers)
            self.assertEqual(display.state['visible']['label'],'meeting')
            self.assertEqual(calls,['giphy','weather'])

if __name__=='__main__': unittest.main()

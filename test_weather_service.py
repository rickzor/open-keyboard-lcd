import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).parent/'examples-sandbox/weather-notifications'))
import service as s
class ServiceTests(unittest.TestCase):
 def test_notification_restart_deadline_and_latest_weather(self):
  with tempfile.TemporaryDirectory() as tmp:
   now=[100];controller=SimpleNamespace(state={})
   screen=s.Screen(controller,Path(tmp),lambda:now[0]);screen.show=Mock()
   inbox=s.Inbox(Path(tmp)/'inbox');screen.weather(b'old')
   inbox.submit({'id':'test','title':'Meeting','template':'calendar','duration':60},now=100)
   screen.tick(inbox);self.assertEqual(screen.state['until'],160)
   screen.weather(b'new');now[0]=159;screen.tick(inbox);self.assertEqual(screen.show.call_count,1)
   restored=s.Screen(controller,Path(tmp),lambda:now[0]);restored.show=Mock()
   now[0]=160;restored.tick(inbox);restored.show.assert_called_once_with(b'new')
 def test_all_minimal_presets_fit_safe_block(self):
  for kind in s.PRESETS:
   data=s.card(dict(template=kind,title='A longer meeting title here',source='Calendar',message='In 1 minute'))
   self.assertLessEqual(len(data),65536)
 def test_new_notice_resets_deadline(self):
  with tempfile.TemporaryDirectory() as tmp:
   now=[100];screen=s.Screen(SimpleNamespace(state={}),Path(tmp),lambda:now[0]);screen.show=Mock()
   inbox=s.Inbox(Path(tmp)/'inbox')
   for ident in ['one','two']:
    inbox.submit({'id':ident,'title':'Notice','duration':60},now=now[0]);screen.tick(inbox);now[0]+=30
   self.assertEqual(screen.state['until'],190)
if __name__=='__main__':unittest.main()

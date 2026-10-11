from pathlib import Path
import sys
import tempfile
import unittest
import json
sys.path.insert(0,str(Path(__file__).parent/'examples-sandbox'/'flyover'))
from flyover import Geography, frame, height, inside, generate_location, select_locations, HERE


class FlyoverTests(unittest.TestCase):
    def test_mountain_collection_preserves_cities(self):
        locations=json.loads((HERE/'locations.json').read_text())
        mountains=select_locations(locations)
        self.assertEqual(len(mountains),10)
        self.assertEqual(len({p['name'] for p in mountains}),10)
        self.assertIn('Alaska Range - Denali',[p['name'] for p in mountains])
        self.assertIn('Himalaya - Annapurna',[p['name'] for p in mountains])
        self.assertIn('Selkirks - Mount Sir Donald',[p['name'] for p in mountains])
        self.assertNotIn('Dolomites - Tre Cime',[p['name'] for p in mountains])
        self.assertNotIn('Southern Alps - Aoraki',[p['name'] for p in mountains])
        self.assertIn('San Francisco',[p['name'] for p in select_locations(locations,'city')])
        with tempfile.TemporaryDirectory() as folder:
            for location in locations: Geography(location,folder)

    def test_custom_center_and_bearing(self):
        location=generate_location('Custom ridge',46,8,length_km=12,bearing=90)
        self.assertEqual(location['route'][2],[46,8])
        self.assertLess(location['route'][0][1],8)
        self.assertGreater(location['route'][-1][1],8)
        with tempfile.TemporaryDirectory() as folder:
            geo=Geography(location,folder)
            self.assertAlmostEqual(geo.dist[-1],12000,delta=.1)
        for center in [(90,0),(0,float('nan'))]:
            with self.assertRaises(ValueError): generate_location('bad',*center)
        with self.assertRaises(ValueError): generate_location('bad',46,8,length_km=0)

    def test_route_endpoints_and_coordinate_projection(self):
        with tempfile.TemporaryDirectory() as folder:
            geo=Geography({'name':'test','route':[[37.85,-122.526],[37.686,-122.436]],'labels':['START','END']},folder)
            self.assertEqual(geo.position(0)[0],geo.route[0])
            for actual,expected in zip(geo.position(1)[0],geo.route[-1]):
                self.assertAlmostEqual(actual,expected)
            lat,lon=geo.latlon(*geo.xy(37.8,-122.4))
            self.assertAlmostEqual(lat,37.8); self.assertAlmostEqual(lon,-122.4)
            geo.elevation=lambda x,y:0
            images=[frame(geo,[],t) for t in (0,.5,1)]
            for image in images:
                self.assertEqual(image.size,(240,136))
                self.assertLessEqual(set(image.get_flattened_data()),{(0,0,0),(255,255,255)})
            self.assertNotEqual(images[0].crop((0,123,240,136)).tobytes(),images[2].crop((0,123,240,136)).tobytes())

    def test_invalid_routes_and_bounded_heights(self):
        with tempfile.TemporaryDirectory() as folder:
            for route in ([[0,0]],[[0,0],[0,.00001]],[[0,0],[0,80]]):
                with self.assertRaises(ValueError): Geography({'name':'bad','route':route},folder)
        self.assertEqual(height({'building:levels':'3'}),9)
        self.assertEqual(height({'height':'1000'}),300)
        self.assertEqual(height({'height':'n/a'}),6)

    def test_vegetation_stays_inside_polygon(self):
        polygon=[(0,0),(10,0),(10,10),(0,10)]
        self.assertTrue(inside(5,5,polygon)); self.assertFalse(inside(20,5,polygon))

if __name__=='__main__': unittest.main()

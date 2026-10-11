#!/usr/bin/env python3
"""SANDBOX: real terrain/OSM, white-on-black 60-second LCD flyover. No scheduler installed."""
import argparse
from bisect import bisect_right
import datetime as dt
import fcntl
import hashlib
import io
import json
import math
from pathlib import Path
import random
import re
import ssl
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
from PIL import Image, ImageDraw, ImageFont

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from qgif import encode_frames, inspect_qgif
HERE=Path(__file__).resolve().parent
R=6371000


def generate_location(name, latitude, longitude, length_km=14, bearing=0):
    """Create a centered flyover route on demand; bearing is clockwise from north.

    Coordinates are explicit so mountains need not be indexed by a city geocoder.
    This constructs a cinematic route, not a terrain-aware navigation plan.
    """
    values=(latitude,longitude,length_km,bearing)
    if not all(math.isfinite(v) for v in values) or not -79<latitude<79 or not -178<longitude<178 or not 1<=length_km<=30:
        raise ValueError('Use finite coordinates away from poles/dateline and a route length of 1–30 km')
    if not isinstance(name,str) or not name.strip(): raise ValueError('A location name is required')
    angle=math.radians(bearing%360)
    route=[]
    for fraction in (-.5,-.25,0,.25,.5):
        distance=fraction*length_km*1000
        lat=latitude+math.degrees(distance*math.cos(angle)/R)
        lon=longitude+math.degrees(distance*math.sin(angle)/(R*math.cos(math.radians(latitude))))
        route.append([round(lat,7),round(lon,7)])
    return {'name':name.strip(),'category':'mountain','route':route,
            'labels':[name.strip().upper()]*len(route),
            'generator':{'center':[latitude,longitude],'length_km':length_km,'bearing':bearing%360}}


def select_locations(locations, collection='mountain'):
    selected=[p for p in locations if collection=='all' or p.get('category','city')==collection]
    if not selected: raise ValueError(f'No locations in collection: {collection}')
    return selected


def fetch(url, cache, data=None, limit=30_000_000):
    cache=Path(cache)
    if cache.exists(): return cache.read_bytes()
    context=ssl.create_default_context()
    if sys.platform=='darwin' and Path('/etc/ssl/cert.pem').exists(): context.load_verify_locations('/etc/ssl/cert.pem')
    req=urllib.request.Request(url,data=data,headers={'User-Agent':'open-keyboard-lcd-sandbox/0.1 (geographic wireframe experiment)'})
    with urllib.request.urlopen(req,timeout=150,context=context) as response: result=response.read(limit+1)
    if len(result)>limit: raise ValueError('Geodata download exceeds budget')
    cache.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=cache.parent,delete=False) as stream:
        stream.write(result); temporary=Path(stream.name)
    temporary.replace(cache)
    return result


def resolve_location(name, locations, cache):
    for location in locations:
        if location['name'].casefold()==name.casefold(): return location
    query=urllib.parse.urlencode({'name':name,'count':1,'language':'en','format':'json'})
    data=json.loads(fetch('https://geocoding-api.open-meteo.com/v1/search?'+query,
        cache/('geocode-'+hashlib.sha256(name.encode()).hexdigest()+'.json')))
    result=data.get('results',[])
    if not result: raise ValueError('Location not found; use a route JSON file for precise coordinates')
    lat,lon=result[0]['latitude'],result[0]['longitude']
    return generate_location(result[0]['name'],lat,lon,length_km=10,bearing=180)


class Geography:
    def __init__(self, location, cache):
        self.location=location; self.cache=Path(cache); self.tiles={}
        route=location['route']
        if not 2<=len(route)<=30 or any(len(p)!=2 or not all(math.isfinite(v) for v in p) or not -80<p[0]<80 or not -179<p[1]<179 for p in route):
            raise ValueError('Route needs 2–30 valid lat/lon waypoints away from poles/dateline')
        self.lat0=sum(p[0] for p in route)/len(route); self.lon0=sum(p[1] for p in route)/len(route)
        self.scale=math.cos(math.radians(self.lat0))
        self.route=[self.xy(*p) for p in route]
        self.dist=[0]
        for a,b in zip(self.route,self.route[1:]): self.dist.append(self.dist[-1]+math.dist(a,b))
        if not 1000<=self.dist[-1]<=50000: raise ValueError('Route length must be 1–50 km')
        self.bounds=(min(p[0] for p in self.route)-2500,min(p[1] for p in self.route)-2500,
                     max(p[0] for p in self.route)+2500,max(p[1] for p in self.route)+2500)
        # Bound daily acquisition and mesh size; reject extreme or dateline-spanning routes.
        if (self.bounds[2]-self.bounds[0])*(self.bounds[3]-self.bounds[1])>500_000_000:
            raise ValueError('Route bounding area exceeds 500 km²')

    def xy(self,lat,lon): return ((lon-self.lon0)*math.pi/180*R*self.scale,(lat-self.lat0)*math.pi/180*R)
    def latlon(self,x,y): return (self.lat0+y/R*180/math.pi,self.lon0+x/(R*self.scale)*180/math.pi)
    def elevation(self,x,y):
        lat,lon=self.latlon(x,y); z=11; count=2**z
        tx=(lon+180)/360*count; ty=(1-math.asinh(math.tan(math.radians(lat)))/math.pi)/2*count
        tile=(int(tx),int(ty))
        if tile not in self.tiles:
            if len(self.tiles)>=32: raise ValueError('Terrain tile budget exceeded')
            url=f'https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{tile[0]}/{tile[1]}.png'
            payload=fetch(url,self.cache/f'terrain-{z}-{tile[0]}-{tile[1]}.png',limit=1_000_000)
            with Image.open(io.BytesIO(payload)) as im: self.tiles[tile]=im.convert('RGB')
        r,g,b=self.tiles[tile].getpixel((min(255,int((tx%1)*256)),min(255,int((ty%1)*256))))
        return max(0,r*256+g+b/256-32768)

    def position(self,t):
        distance=max(0,min(1,t))*self.dist[-1]
        i=min(len(self.route)-2,max(0,bisect_right(self.dist,distance)-1))
        amount=(distance-self.dist[i])/max(1,self.dist[i+1]-self.dist[i])
        a,b=self.route[i:i+2]
        return (a[0]+(b[0]-a[0])*amount,a[1]+(b[1]-a[1])*amount),i

    def osm(self):
        x0,y0,x1,y1=self.bounds; south,west=self.latlon(x0,y0); north,east=self.latlon(x1,y1)
        box=f'{south:.5f},{west:.5f},{north:.5f},{east:.5f}'
        # One bounded query, cached for subsequent renders. Full building footprints,
        # roads, coastlines and vegetation polygons, not a fabricated city texture.
        corridor=','.join(str(v) for point in self.location['route'] for v in point)
        query=f'''[out:json][timeout:100][maxsize:134217728];(
way[building](around:400,{corridor});way[highway~"^(motorway|trunk|primary|secondary|tertiary)$"]({box});
way[natural~"^(coastline|wood|scrub)$"]({box});way[landuse=forest]({box});
way[leisure=park]({box});way[man_made=bridge]({box}););out tags geom;'''
        digest=hashlib.sha256(query.encode()).hexdigest()
        payload=fetch('https://overpass-api.de/api/interpreter',self.cache/('osm-'+digest+'.json'),
            urllib.parse.urlencode({'data':query}).encode())
        result=json.loads(payload)
        if result.get('remark'): raise RuntimeError('Overpass returned an incomplete/error response: '+result['remark'][:160])
        return result['elements']


def height(tags):
    try:
        if tags.get('height'):
            match=re.match(r'([0-9.]+)',tags['height'])
            if match: return min(300,max(4,float(match[1])))
        return min(150,max(6,float(tags.get('building:levels','2'))*3))
    except (ValueError,TypeError): return 8


def inside(x,y,polygon):
    result=False
    for a,b in zip(polygon,polygon[1:]+polygon[:1]):
        if (a[1]>y)!=(b[1]>y) and x<(b[0]-a[0])*(y-a[1])/(b[1]-a[1])+a[0]: result=not result
    return result


def scene(geo, elements):
    # Faces fill black before drawing white edges, producing approximate hidden-line removal.
    primitives=[]; counts={'terrain_faces':0,'buildings':0,'roads':0,'vegetation_symbols':0,'bridges':0}
    def add(points,face=False,kind='terrain'):
        if len(points)>=2:
            center=tuple(sum(p[k] for p in points)/len(points) for k in range(3))
            primitives.append((points,face,kind,center))
    x0,y0,x1,y1=geo.bounds
    nx=max(10,round((x1-x0)/280)); ny=max(10,round((y1-y0)/280))
    grid=[]
    for j in range(ny+1):
        row=[]
        for i in range(nx+1):
            x=x0+(x1-x0)*i/nx; y=y0+(y1-y0)*j/ny
            row.append((x,y,geo.elevation(x,y)))
        grid.append(row)
    for j in range(ny):
        for i in range(nx):
            points=[grid[j][i],grid[j][i+1],grid[j+1][i+1],grid[j+1][i]]
            if max(p[2] for p in points)<1: continue # black water, no ocean mesh
            add(points,True); counts['terrain_faces']+=1
    # Stable spatial sampling keeps dense cities legible at 240 pixels; no claims of completeness.
    buildings=[e for e in elements if e.get('tags',{}).get('building') and e.get('geometry')]
    buildings.sort(key=lambda e:hashlib.sha256(str(e['id']).encode()).digest())
    buildings=buildings[:2200]
    for e in buildings:
        polygon=[geo.xy(p['lat'],p['lon']) for p in e['geometry']]
        if len(polygon)<4: continue
        polygon=polygon[:-1] if polygon[0]==polygon[-1] else polygon
        if len(polygon)>12: polygon=polygon[::math.ceil(len(polygon)/12)]
        cx=sum(p[0] for p in polygon)/len(polygon); cy=sum(p[1] for p in polygon)/len(polygon)
        base=geo.elevation(cx,cy)+1; h=height(e['tags'])
        roof=[(x,y,base+h) for x,y in polygon]
        add(roof,True,'building')
        for a,b in zip(polygon,polygon[1:]+polygon[:1]):
            add([(a[0],a[1],base),(b[0],b[1],base),(b[0],b[1],base+h),(a[0],a[1],base+h)],True,'building')
        counts['buildings']+=1
    rng=random.Random(47)
    for e in elements:
        tags=e.get('tags',{}); points=[geo.xy(p['lat'],p['lon']) for p in e.get('geometry',[])]
        points=[p for p in points if x0<=p[0]<=x1 and y0<=p[1]<=y1]
        if len(points)<2 or tags.get('building'): continue
        if tags.get('highway') or tags.get('natural')=='coastline' or tags.get('man_made')=='bridge':
            bridge=tags.get('bridge') not in (None,'no') or tags.get('man_made')=='bridge'
            # Deck height is schematic when OSM does not supply engineering elevations.
            line=[(x,y,geo.elevation(x,y)+(65 if bridge else 3)) for x,y in points]
            for a,b in zip(line,line[1:]): add([a,b],False,'bridge' if bridge else 'road')
            counts['bridges' if bridge else 'roads']+=1
            if bridge and len(line)>=2:
                for a in line[::max(1,len(line)//3)]: add([(a[0],a[1],0),a],False,'bridge')
        if tags.get('natural') in ('wood','scrub') or tags.get('landuse')=='forest' or tags.get('leisure')=='park':
            # Tree positions are deterministic symbols inside mapped vegetation, not surveyed individual trees.
            if counts['vegetation_symbols']>=550: continue
            xmin,xmax=min(p[0] for p in points),max(p[0] for p in points)
            ymin,ymax=min(p[1] for p in points),max(p[1] for p in points)
            amount=min(30,max(2,int((xmax-xmin)*(ymax-ymin)/60000)))
            for _ in range(amount*3):
                if amount<=0 or counts['vegetation_symbols']>=550: break
                x=rng.uniform(xmin,xmax); y=rng.uniform(ymin,ymax)
                if not inside(x,y,points): continue
                z=geo.elevation(x,y); h=22
                add([(x-9,y,z+5),(x,y,z+h),(x+9,y,z+5),(x-9,y,z+5)],False,'tree')
                add([(x,y,z),(x,y,z+9)],False,'tree')
                counts['vegetation_symbols']+=1; amount-=1
    return primitives,counts


def vector(a,b): return tuple(x-y for x,y in zip(a,b))
def dot(a,b): return sum(x*y for x,y in zip(a,b))
def normalize(a):
    length=math.sqrt(dot(a,a)); return tuple(x/max(length,1e-9) for x in a)
def cross(a,b): return (a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])


def frame(geo,primitives,t):
    point,index=geo.position(t)
    future,_=geo.position(min(1,t+2000/geo.dist[-1]))
    if math.dist(point,future)<100:
        prev,_=geo.position(max(0,t-.02)); direction=normalize((point[0]-prev[0],point[1]-prev[1],0))
        future=(point[0]+direction[0]*1600,point[1]+direction[1]*1600)
    altitude=1800*(1-t)+420*t
    camera=(point[0],point[1],geo.elevation(*point)+altitude)
    target=(future[0],future[1],geo.elevation(*future)+60)
    forward=normalize(vector(target,camera)); right=normalize(cross(forward,(0,0,1))); up=cross(right,forward)
    def project(p):
        relative=vector(p,camera); depth=dot(relative,forward)
        if depth<50: return None
        return (120+140*dot(relative,right)/depth,65-140*dot(relative,up)/depth,depth)
    visible=[]
    for points,face,kind,center in primitives:
        relative=vector(center,camera); depth=dot(relative,forward)
        if depth<40 or depth>9000: continue
        if kind in ('building','tree') and depth>4500: continue
        projected=[project(p) for p in points]
        if any(p is None for p in projected): continue
        xy=[(p[0],p[1]) for p in projected]
        if max(p[0] for p in xy)<0 or min(p[0] for p in xy)>239 or max(p[1] for p in xy)<9 or min(p[1] for p in xy)>120: continue
        visible.append((sum(p[2] for p in projected)/len(projected),xy,face))
    im=Image.new('1',(240,136),0); d=ImageDraw.Draw(im)
    for _,xy,face in sorted(visible,key=lambda item:item[0],reverse=True):
        if face: d.polygon(xy,fill=0,outline=1)
        else: d.line(xy,fill=1,width=1)
    d.rectangle((0,0,239,10),fill=0); d.rectangle((0,121,239,135),fill=0)
    face=ImageFont.load_default(size=9)
    labels=geo.location.get('labels',[geo.location['name']]*len(geo.route))
    label=labels[min(index,len(labels)-1)] if t<.97 else labels[-1]
    d.text((3,0),label[:30],font=face,fill=1)
    lat,lon=geo.latlon(*point)
    coordinates=f'{abs(lat):.4f}°{"N" if lat>=0 else "S"}  {abs(lon):.4f}°{"E" if lon>=0 else "W"}'
    d.text((3,124),coordinates,font=ImageFont.load_default(size=9),fill=1)
    if t<.045:
        d.rectangle((0,12,239,23),fill=0)
        d.text((3,13),'© OpenStreetMap | AWS/Mapzen',font=ImageFont.load_default(size=8),fill=1)
    d.line((0,120,round(239*t),120),fill=1)
    return im.convert('RGB')


def render(location,out,cache,fps=8):
    out=Path(out); out.mkdir(parents=True,exist_ok=False)
    geo=Geography(location,cache)
    print('Fetching mapped buildings, roads, coastlines and vegetation...',flush=True)
    elements=geo.osm()
    print(f'Building scene from {len(elements)} OSM features...',flush=True)
    primitives,counts=scene(geo,elements)
    (out/'scene-summary.json').write_text(json.dumps({'location':location,'counts':counts,'terrain_tiles':len(geo.tiles)},indent=2))
    frames=[]
    for n in range(60*fps):
        frames.append(frame(geo,primitives,n/(60*fps-1)))
        if n%(fps*10)==0: print(f'Rendered {n//fps}/60 seconds',flush=True)
    frames[0].save(out/'flyover.gif',save_all=True,append_images=frames[1:],duration=[10*(int((i+1)*100/fps)-int(i*100/fps)) for i in range(len(frames))],loop=0,optimize=False)
    print('Encoding keyboard QGIF...',flush=True)
    data=encode_frames(frames,fps=fps); (out/'flyover.qgif').write_bytes(data)
    info=inspect_qgif(data)
    if len(data)>7_031_890: raise ValueError('Encoded animation exceeds tested single-image byte bound; not uploading')
    if any(set(im.get_flattened_data())-{(0,0,0),(255,255,255)} for im in frames): raise ValueError('Unexpected non-monochrome pixel')
    sheet=Image.new('RGB',(720,272),'black')
    for i,index in enumerate([0,len(frames)//5,2*len(frames)//5,3*len(frames)//5,4*len(frames)//5,len(frames)-1]): sheet.paste(frames[index],((i%3)*240,(i//3)*136))
    sheet.save(out/'contact-sheet.png')
    info.update(location=location,counts=counts,sha256=hashlib.sha256(data).hexdigest(),
        attribution=['https://www.openstreetmap.org/copyright','https://registry.opendata.aws/terrain-tiles/'],
        limitations=['Sampled OSM building footprints; inferred heights where missing','Schematic bridge elevations and vegetation symbols','No surveyed individual trees or complete architectural model','Single-image hardware playback requires visual confirmation'])
    (out/'manifest.json').write_text(json.dumps(info,indent=2)+'\n')
    return out/'flyover.qgif'


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--location',help='Preset or place name; defaults to Himalaya - Annapurna'); p.add_argument('--random',action='store_true')
    p.add_argument('--collection',choices=['mountain','city','all'],default='mountain',help='Collection for random selection')
    p.add_argument('--center',type=float,nargs=2,metavar=('LAT','LON'),help='Generate a custom route around these coordinates on demand')
    p.add_argument('--length-km',type=float,default=14)
    p.add_argument('--bearing',type=float,default=0,help='Travel direction in degrees clockwise from north')
    p.add_argument('--locations',type=Path,default=HERE/'locations.json')
    p.add_argument('--route',type=Path,help='JSON object with name, route lat/lon pairs, optional labels')
    p.add_argument('--out',type=Path,default=ROOT/'state'/'flyover')
    p.add_argument('--cache',type=Path,default=ROOT/'state'/'flyover-geodata')
    p.add_argument('--upload',action='store_true',help='Replace all keyboard images with the generated single-image set')
    p.add_argument('--daily',action='store_true',help='Stay running; attempt once per local calendar day; no service installation')
    args=p.parse_args()
    if sum([args.random,args.route is not None,args.center is not None])>1:
        p.error('--random, --route and --center are mutually exclusive')
    args.out.mkdir(parents=True,exist_ok=True)
    with (args.out/'runner.lock').open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        while True:
            day=dt.date.today().isoformat(); marker=args.out/(day+('-uploaded' if args.upload else '-rendered')+'-completed.json')
            if not args.daily or not marker.exists():
                locations=json.loads(args.locations.read_text())
                if args.route: location=json.loads(args.route.read_text())
                elif args.center: location=generate_location(args.location or 'Custom location',*args.center,args.length_km,args.bearing)
                elif args.random:
                    choices=select_locations(locations,args.collection)
                    location=random.Random(day+json.dumps(choices,sort_keys=True)).choice(choices)
                else: location=resolve_location(args.location or 'Himalaya - Annapurna',locations,args.cache)
                destination=args.out/(day+'-'+str(time.time_ns()))
                encoded=render(location,destination,args.cache)
                if args.upload:
                    subprocess.run([sys.executable,str(ROOT/'rt82.py'),'replace-all',str(encoded)],check=True)
                marker.write_text(json.dumps({'date':day,'location':location['name'],'output':str(destination.resolve()),'uploaded':args.upload},indent=2))
                print(f'Complete: {destination}',flush=True)
            if not args.daily: break
            time.sleep(30)


if __name__=='__main__':
    try: main()
    except KeyboardInterrupt: pass

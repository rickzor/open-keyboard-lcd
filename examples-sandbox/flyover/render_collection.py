#!/usr/bin/env python3
"""Render the preset collection to local files. Never uploads or schedules jobs."""
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import hashlib
import json
from pathlib import Path
import re
import time
from flyover import Geography, HERE, ROOT, render, select_locations


def render_one(location, destination, cache):
    print(f"Rendering {location['name']}...",flush=True)
    encoded=render(location,destination,cache)
    return {'name':location['name'],'directory':str(destination.resolve()),
            'qgif':str(encoded.resolve()),'status':'rendered'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--locations',type=Path,default=HERE/'locations.json')
    parser.add_argument('--collection',choices=['mountain','city','all'],default='mountain')
    parser.add_argument('--out',type=Path,default=ROOT/'state'/'flyover-collection')
    parser.add_argument('--cache',type=Path,default=ROOT/'state'/'flyover-geodata')
    parser.add_argument('--workers',type=int,choices=[1,2,3],default=2)
    args=parser.parse_args()
    locations=select_locations(json.loads(args.locations.read_text()),args.collection)
    args.out.mkdir(parents=True,exist_ok=True)
    results=[]; pending={}
    with ProcessPoolExecutor(max_workers=args.workers) as executor:
        # Public Overpass acquisition stays sequential; CPU rendering can overlap.
        for location in locations:
            slug=re.sub('[^a-z0-9]+','-',location['name'].lower()).strip('-')
            directory=args.out/slug
            manifest=directory/'manifest.json'
            if manifest.exists():
                prior=json.loads(manifest.read_text()); encoded=directory/'flyover.qgif'
                if prior['location']==location and encoded.exists() and hashlib.sha256(encoded.read_bytes()).hexdigest()==prior['sha256']:
                    results.append({'name':location['name'],'directory':str(directory.resolve()),'status':'already-rendered'})
                    continue
            if directory.exists(): directory=args.out/(slug+'-'+str(time.time_ns()))
            try:
                print(f"Acquiring map data: {location['name']}",flush=True)
                Geography(location,args.cache).osm()
                future=executor.submit(render_one,location,directory,args.cache)
                pending[future]=location['name']
            except Exception as error:
                results.append({'name':location['name'],'status':'failed','error':str(error)})
        for future in as_completed(pending):
            name=pending[future]
            try: results.append(future.result()); print(f'Complete: {name}',flush=True)
            except Exception as error:
                results.append({'name':name,'status':'failed','error':str(error)})
                print(f'Failed: {name}: {error}',flush=True)
            (args.out/'collection.json').write_text(json.dumps(results,indent=2)+'\n')
    (args.out/'collection.json').write_text(json.dumps(results,indent=2)+'\n')
    if any(r['status']=='failed' for r in results): raise SystemExit(1)
    print(f'{len(results)} animations ready; no keyboard uploads performed.',flush=True)


if __name__=='__main__': main()

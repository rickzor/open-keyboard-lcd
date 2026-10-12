#!/usr/bin/env python3
"""Procedural low-poly 3D weather loops, full color on pure black; synthetic demo."""
import argparse, hashlib, json, math, sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from qgif import encode_frames,inspect_qgif
KINDS=['SUNNY','MOON','SUN AND CLOUD','MOON AND CLOUD','CLOUDY','FOG','RAIN','SNOW','THUNDER','WIND']
FPS=8; FRAMES=16

def sphere(faces,center,r,color,phase=0):
    rings=[]
    for j in range(6):
        phi=-math.pi/2+j*math.pi/5
        rings.append([(center[0]+r*math.cos(phi)*math.cos(i*math.pi/4+phase),center[1]+r*math.sin(phi),center[2]+r*math.cos(phi)*math.sin(i*math.pi/4+phase)) for i in range(8)])
    for j in range(5):
        for i in range(8):
            pts=[rings[j][i],rings[j][(i+1)%8],rings[j+1][(i+1)%8],rings[j+1][i]]
            normal=[sum(p[k]-center[k] for p in pts)/(4*r) for k in range(3)]
            light=max(0,sum(a*b for a,b in zip(normal,(-.4,.65,.65))))
            shade=.35+.65*round(light*4)/4
            faces.append((pts,tuple(min(255,int(c*shade)) for c in color)))

def prism(faces,poly,depth,color,z=0):
    front=[(x,y,z+depth/2) for x,y in poly];back=[(x,y,z-depth/2) for x,y in poly]
    faces.extend([(front,color),(back,tuple(int(c*.4) for c in color))])
    for i in range(len(poly)):
        n=(i+1)%len(poly);faces.append(([front[i],front[n],back[n],back[i]],tuple(int(c*(.55+.12*(i%3))) for c in color)))

def box(faces,x,y,w,h,depth,color,z=0):
    prism(faces,[(x-w/2,y-h/2),(x+w/2,y-h/2),(x+w/2,y+h/2),(x-w/2,y+h/2)],depth,color,z)

def frame(kind,n,labels=True):
    phase=n*2*math.pi/FRAMES;faces=[]
    cloudy=kind not in ('SUNNY','MOON','WIND')
    if kind in ('SUNNY','SUN AND CLOUD'):
        cx,cy=(-18,23) if cloudy else (0,7)
        sphere(faces,(cx,cy,-8),17,(255,187,32),phase*.15)
        for i in range(8):
            a=i*math.pi/4+phase/8;r=27+2*math.sin(phase)
            x,y=cx+r*math.cos(a),cy+r*math.sin(a)
            prism(faces,[(x-3,y),(x,y+6),(x+3,y),(x,y-6)],6,(255,126,18),-8)
    if kind in ('MOON','MOON AND CLOUD'):
        cx,cy=(-18,24) if cloudy else (0,8)
        poly=[(cx+24*math.cos(a),cy+24*math.sin(a)) for a in [math.radians(60+i*30) for i in range(9)]]
        poly += [(cx+9+21*math.cos(a),cy+21*math.sin(a)) for a in [math.radians(270-i*30) for i in range(7)]]
        poly=[(x,y+2*math.sin(phase)) for x,y in poly]
        prism(faces,poly,9,(141,188,255),-7)
        for x,y in [(31,29),(37,5),(-30,-15)]: sphere(faces,(x,y,0),2+(n%8)/12,(255,224,133))
    if cloudy:
        sway=2*math.sin(phase)
        for x,y,z,r in [(-20,2,5,17),(0,11,0,21),(21,2,4,16)]:
            sphere(faces,(x+sway,y,z),r,(135,187,224))
        box(faces,sway,-5,53,17,20,(124,178,219),3)
    if kind in ('RAIN','SNOW','THUNDER'):
        for i in range(5):
            x=-27+i*13;y=-22-((n*2+i*5)%18)
            if kind=='SNOW': sphere(faces,(x,y,6),3,(194,243,255),phase)
            else:prism(faces,[(x,y+5),(x-3,y-2),(x,y-5),(x+3,y-2)],4,(35,155,255),8)
    if kind=='THUNDER' and 3<=n<=11:
        prism(faces,[(3,-9),(-9,-27),(0,-27),(-5,-42),(16,-20),(6,-20)],6,(255,209,36),19)
    if kind=='FOG':
        for i in range(3):box(faces,4*math.sin(phase+i),-23-i*7,66-i*6,3,8,(101,221,207),8)
    if kind=='WIND':
        for row in range(3):
            for col in range(6):
                x=-35+col*13+5*math.sin(phase+row);y=19-row*18+4*math.sin(col*.8+phase)
                box(faces,x,y,11,3,6,(55+row*40,230,192),col%2*4)
    yaw=.28+.08*math.sin(phase);pitch=.24
    def project(p):
        x,y,z=p;x,z=x*math.cos(yaw)+z*math.sin(yaw),-x*math.sin(yaw)+z*math.cos(yaw)
        y,z=y*math.cos(pitch)-z*math.sin(pitch),y*math.sin(pitch)+z*math.cos(pitch)
        return (120+x*1.15,70-y*1.15,z)
    projected=[([project(p) for p in pts],color) for pts,color in faces]
    im=Image.new('RGB',(240,136),(0,0,0));d=ImageDraw.Draw(im)
    for pts,color in sorted(projected,key=lambda item:sum(p[2] for p in item[0])/len(item[0])):
        d.polygon([(p[0],p[1]) for p in pts],fill=color)
    if labels: d.text((120,7),'WEATHER / LO-FI 3D',font=ImageFont.load_default(size=10),fill='#86a3bc',anchor='mt')
    if labels: d.text((120,117),kind,font=ImageFont.load_default(size=12),fill='white',anchor='mt')
    return im

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True);args=p.parse_args();args.out.mkdir(parents=True,exist_ok=True)
    all_frames=[];manifest=[];sheet=Image.new('RGB',(720,544),'black')
    for i,kind in enumerate(KINDS):
        frames=[frame(kind,n) for n in range(FRAMES)];all_frames.extend(frames)
        name=kind.lower().replace(' ','-');data=encode_frames(frames,fps=FPS)
        (args.out/(name+'.qgif')).write_bytes(data)
        frames[0].save(args.out/(name+'.gif'),save_all=True,append_images=frames[1:],duration=[120,130]*8,loop=0,optimize=False)
        manifest.append({'name':kind,**inspect_qgif(data),'fits_notification_block':len(data)<=65536})
        sheet.paste(frames[4],((i%3)*240,(i//3)*136))
        print(kind,len(data),flush=True)
    data=encode_frames(all_frames,fps=FPS);encoded=args.out/'weather-reel.qgif';encoded.write_bytes(data)
    all_frames[0].save(args.out/'weather-reel.gif',save_all=True,append_images=all_frames[1:],duration=[120,130]*80,loop=0,optimize=False)
    sheet.save(args.out/'preview.png')
    (args.out/'manifest.json').write_text(json.dumps({'loops':manifest,'reel':inspect_qgif(data),'synthetic_demo':True},indent=2)+'\n')
    (args.out/'collection.json').write_text(json.dumps([{'name':'Lo-fi 3D Weather','qgif':str(encoded.resolve()),'sha256':hashlib.sha256(data).hexdigest()}],indent=2)+'\n')
    print('REEL',len(data),flush=True)
if __name__=='__main__':main()

"""Generate an animation with frequent pixel changes and a visible ending marker."""
import argparse,hashlib,json
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
from qgif import encode_frames,inspect_qgif
parser=argparse.ArgumentParser(description="Generate LCD capacity-test assets locally; never opens USB.")
parser.add_argument('--frames',type=int,default=512,help='Changing frames, followed by seven hold frames')
parser.add_argument('--output',type=Path,required=True,help='New output directory')
parser.add_argument('--font',default='/System/Library/Fonts/Supplemental/Arial Bold.ttf',help='TrueType font; defaults to the font used in macOS trials')
args=parser.parse_args()
if not 1 <= args.frames <= 1024:
 parser.error('--frames must be between 1 and 1024 for this bounded generator')
font=ImageFont.truetype(args.font,28)
out=args.output
out.mkdir(parents=True,exist_ok=False)
frames=[]
for n in range(args.frames):
 im=Image.new('RGB',(240,136),(15+(3*n)%220,20+(n*31)%130,25+(n*47)%150));d=ImageDraw.Draw(im)
 d.text((120,48),f'SIZE TEST {args.frames}',font=font,anchor='mm',fill='white',stroke_width=2,stroke_fill='black')
 label=f'FRAME {n+1:02d} / {args.frames}' if n<args.frames-1 else f'END {args.frames}'
 d.text((120,84),label,font=font,anchor='mm',fill='lime' if n>=args.frames-1 else 'cyan',stroke_width=2,stroke_fill='black')
 # Changing pixels outside the text area increase encoded size.
 for y in range(0,136,4):
  for x in range(0,240,4):
   if not (5<=x<=235 and 25<=y<=109):
    d.point((x,y),fill=((n*53+x)%256,(n*79+y)%256,(n*97)%256))
 frames.append(im)
frames.extend([frames[-1].copy() for _ in range(7)])
path=out/'animation.qgif';data=encode_frames(frames,fps=8);path.write_bytes(data)
frames[0].save(out/'animation.gif',save_all=True,append_images=frames[1:],duration=125,loop=0,optimize=False)
info=inspect_qgif(data);info['sha256']=hashlib.sha256(data).hexdigest();(out/'animation.json').write_text(json.dumps(info,indent=2)+'\n');print(json.dumps(info,indent=2))

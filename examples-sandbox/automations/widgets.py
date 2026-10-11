"""Local 240x136 widget rendering and bounded network providers."""
import io
import json
import math
import os
import ssl
import sys
from pathlib import Path
import urllib.error
import urllib.parse
import urllib.request

from PIL import Image, ImageDraw, ImageFont

SIZE = (240, 136)


def font(size):
    for name in ('/System/Library/Fonts/Supplemental/Arial Bold.ttf', 'DejaVuSans.ttf'):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    return ImageFont.load_default(size=size)


def request(url, limit=2_000_000):
    context=ssl.create_default_context()
    # python.org macOS runtimes may lack a configured CA bundle. Add the system
    # public CA bundle without disabling certificate or hostname verification.
    if sys.platform=='darwin' and Path('/etc/ssl/cert.pem').exists():
        context.load_verify_locations('/etc/ssl/cert.pem')
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={
                'User-Agent': 'open-keyboard-lcd-examples/1.0'}), timeout=15, context=context) as response:
            data = response.read(limit + 1)
    except urllib.error.HTTPError as error:
        raise RuntimeError(f'Provider returned HTTP {error.code}') from None
    except (urllib.error.URLError, TimeoutError):
        raise RuntimeError('Provider network request failed') from None
    if len(data) > limit:
        raise ValueError('Provider response exceeds size limit')
    return data


def weather(latitude=37.7749, longitude=-122.4194, units='fahrenheit'):
    query = urllib.parse.urlencode(dict(latitude=latitude, longitude=longitude,
        current='temperature_2m,weather_code,is_day', temperature_unit=units,
        timezone='auto'))
    result = json.loads(request('https://api.open-meteo.com/v1/forecast?' + query))
    current = result['current']
    return {'temperature': float(current['temperature_2m']),
            'code': int(current['weather_code']), 'day': bool(current['is_day']),
            'time': current['time'], 'unit': 'F' if units == 'fahrenheit' else 'C'}


def condition(code):
    if code == 0: return 'Clear'
    if code in (1, 2): return 'Partly cloudy'
    if code == 3: return 'Cloudy'
    if code in (45, 48): return 'Fog'
    if code in (71, 73, 75, 77, 85, 86): return 'Snow'
    if code in (95, 96, 99): return 'Thunderstorm'
    if code in (51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82): return 'Rain'
    return 'Weather'


def clipped(draw, text, width, face):
    text = ' '.join(str(text).split())
    while text and draw.textlength(text, font=face) > width:
        text = text[:-1]
    return text


def weather_frames(data, location='San Francisco, CA'):
    """Twelve frames at 6 FPS: text stays still, icon moves in a two-second loop."""
    result = []
    kind = condition(data['code'])
    for n in range(12):
        phase = 2 * math.pi * n / 12
        im = Image.new('RGB', SIZE, '#0d1930'); d = ImageDraw.Draw(im)
        d.rounded_rectangle((5, 5, 234, 130), radius=12, outline='#385678', width=1)
        d.text((14, 11), clipped(d, location, 213, font(15)), font=font(15), fill='#b9d9f8')
        # Sun rays pulse; moon floats slightly at night.
        if kind in ('Clear', 'Partly cloudy'):
            cx, cy = 184, 59
            if data.get('day', True):
                r = 15 + 2 * math.sin(phase)
                for k in range(8):
                    a = k * math.pi / 4
                    d.line((cx+23*math.cos(a), cy+23*math.sin(a),
                            cx+28*math.cos(a), cy+28*math.sin(a)), fill='#ffcb59', width=2)
                d.ellipse((cx-r, cy-r, cx+r, cy+r), fill='#ffd66c')
            else:
                cy += int(2 * math.sin(phase))
                d.ellipse((cx-18, cy-18, cx+18, cy+18), fill='#dce9ff')
                d.ellipse((cx-6, cy-23, cx+25, cy+8), fill='#0d1930')
        if kind != 'Clear':
            x = int(3 * math.sin(phase)); y = 56
            for box in ((153+x,y,194+x,y+26),(171+x,y-10,211+x,y+24),(186+x,y,222+x,y+26)):
                d.ellipse(box, fill='#bfd2e5')
            d.rounded_rectangle((160+x,y+12,214+x,y+29),radius=7,fill='#bfd2e5')
            if kind in ('Rain', 'Thunderstorm', 'Snow'):
                for k in range(4):
                    xx = 162 + k*15; yy = 87 + ((n*2+k*6)%20)
                    if kind == 'Snow': d.ellipse((xx,yy,xx+3,yy+3),fill='white')
                    else: d.line((xx,yy,xx-3,yy+6),fill='#62baff',width=2)
            if kind == 'Thunderstorm' and n in (2,3,8):
                d.polygon([(191,76),(180,92),(190,91),(185,105),(203,85),(193,86)],fill='#ffd66c')
            if kind == 'Fog':
                for k in range(3):
                    d.line((153+x,89+7*k,219-x,89+7*k), fill='#8099b2',width=2)
        d.text((14, 36), f"{data['temperature']:.0f}°{data['unit']}", font=font(36), fill='white')
        d.text((14, 81), kind, font=font(14), fill='#b9d9f8')
        stamp = data.get('time','').split('T')[-1][:5]
        d.text((14, 114), f'{stamp}  Open-Meteo', font=font(10), fill='#849fbf')
        result.append(im)
    return result


def meeting_frames(title, start_label):
    result=[]
    for n in range(8):
        im=Image.new('RGB',SIZE,'#20172f'); d=ImageDraw.Draw(im)
        d.rounded_rectangle((5,5,234,130),radius=12,outline='#edbc67' if n<4 else '#98794c',width=3)
        d.text((15,17),'MEETING IN 1 MIN',font=font(19),fill='#ffcf7d')
        words=str(title).split(); line=''; lines=[]
        for word in words:
            if d.textlength((line+' '+word).strip(),font=font(18))>205 and line:
                lines.append(line); line=word
            else: line=(line+' '+word).strip()
        if line: lines.append(line)
        for i,line in enumerate(lines[:2]):
            d.text((15,51+23*i),clipped(d,line,207,font(18)),font=font(18),fill='white')
        d.text((15,109),f'Starts {start_label}',font=font(13),fill='#c0aed5')
        result.append(im)
    return result


def save_gif(frames, path, fps):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    frames[0].save(path,save_all=True,append_images=frames[1:],duration=round(1000/fps),loop=0,optimize=False)


def giphy_frames(tag='cute animals', approved_ids=None):
    key=os.environ.get('GIPHY_API_KEY')
    if not key: raise RuntimeError('Set GIPHY_API_KEY in the process environment')
    # Use the random endpoint: no reordering of a search/trending result grid.
    query=urllib.parse.urlencode({'api_key':key,'tag':tag,'rating':'g'})
    item=json.loads(request('https://api.giphy.com/v1/gifs/random?'+query))['data']
    if item.get('rating') != 'g': raise ValueError('GIPHY did not return a G-rated GIF')
    if approved_ids is not None and item.get('id') not in approved_ids:
        raise ValueError('GIPHY selection is not in the configured reviewed-ID allowlist')
    url=item['images']['original']['url']
    host=urllib.parse.urlsplit(url)
    if host.scheme!='https' or not (host.hostname or '').endswith('.giphy.com'):
        raise ValueError('Unexpected GIPHY media URL')
    payload=request(url,limit=8_000_000)
    frames=[]
    with Image.open(io.BytesIO(payload)) as source:
        if source.width*source.height>4_000_000: raise ValueError('GIF dimensions exceed budget')
        for n in range(min(getattr(source,'n_frames',1),24)):
            source.seek(n)
            im=crop_for_lcd(source.convert('RGB'))
            draw=ImageDraw.Draw(im)
            draw.rectangle((0,119,239,135),fill='black')
            draw.text((8,121),'Powered By GIPHY',font=font(11),fill='white')
            frames.append(im)
    return frames, {'id':item['id'],'rating':'g'}


def crop_for_lcd(frame):
    """Fit source width to 240, preserve aspect ratio, then center-crop vertically."""
    width,height=frame.size
    scaled_height=max(1,round(height*240/width))
    frame=frame.resize((240,scaled_height),Image.Resampling.LANCZOS)
    top=max(0,(scaled_height-135)//2)
    cropped=frame.crop((0,top,240,min(scaled_height,top+135)))
    result=Image.new('RGB',SIZE,'black')
    result.paste(cropped,(0,(135-cropped.height)//2))
    return result

"""Small-screen notification presets; no external assets or emoji fonts required."""
from PIL import Image, ImageDraw
from widgets import font, clipped

PRESETS={
 'message': {'title':'New message','accent':'#83baff','background':'#0d1b32','icon':'message'},
 'slack': {'title':'Slack mention','accent':'#d5a4ff','background':'#231632','icon':'message'},
 'calendar': {'title':'Meeting soon','accent':'#ffadd2','background':'#301928','icon':'calendar'},
 'reminder': {'title':'A little reminder','accent':'#ffcf80','background':'#2b2316','icon':'bell'},
 'success': {'title':'All done','accent':'#78e5bb','background':'#102820','icon':'check'},
 'warning': {'title':'Needs attention','accent':'#ffd36b','background':'#2d2411','icon':'warning'},
 'error': {'title':'Something went wrong','accent':'#ff9a99','background':'#30191e','icon':'warning'},
 'automation': {'title':'Automation update','accent':'#7edfe5','background':'#10272f','icon':'spark'},
 'focus': {'title':'Time to focus','accent':'#b9b0ff','background':'#1d1c35','icon':'focus'},
}
ICONS={'message','calendar','bell','check','warning','spark','focus'}


def lines(draw,text,face,width,limit):
    words=str(text).split(); result=[]; line=''
    for word in words:
        trial=(line+' '+word).strip()
        if draw.textlength(trial,font=face)>width and line:
            result.append(clipped(draw,line,width,face)); line=word
        else: line=trial
    if line: result.append(clipped(draw,line,width,face))
    if len(result)>limit:
        result=result[:limit]; last=result[-1]
        while last and draw.textlength(last+'…',font=face)>width: last=last[:-1]
        result[-1]=last+'…'
    return result


def draw_icon(d,kind,color):
    # Every icon fits inside the 22x22 badge at (13,11).
    if kind=='message':
        d.rounded_rectangle((15,14,33,26),radius=3,outline=color,width=2)
        d.line((19,26,18,30,24,26),fill=color,width=2)
        d.line((19,18,29,18),fill=color,width=1)
    elif kind=='calendar':
        d.rounded_rectangle((15,14,33,30),radius=2,outline=color,width=2)
        d.line((15,19,33,19),fill=color,width=2)
        for x in (20,28): d.line((x,11,x,16),fill=color,width=2)
        d.rectangle((20,23,23,26),fill=color)
    elif kind=='check': d.line((15,22,21,28,33,15),fill=color,width=3)
    elif kind=='warning':
        d.polygon([(24,12),(34,30),(14,30)],outline=color,width=2)
        d.line((24,19,24,24),fill=color,width=2); d.point((24,27),fill=color)
    elif kind=='bell':
        d.arc((17,13,31,29),180,360,fill=color,width=2)
        d.line((17,21,17,27,31,27,31,21),fill=color,width=2)
        d.arc((22,26,27,31),0,180,fill=color,width=2)
    elif kind=='focus':
        d.ellipse((15,13,33,31),outline=color,width=2)
        d.line((24,16,24,23,29,26),fill=color,width=2)
    else:
        d.polygon([(24,11),(27,19),(35,22),(27,25),(24,33),(21,25),(13,22),(21,19)],fill=color)


def notification_frames(item):
    preset=PRESETS[item.get('template','message')]
    theme=dict(preset,text='#f4f7fc',muted='#bbc6d6')
    theme.update(item.get('theme',{})); icon=item.get('icon',preset['icon'])
    result=[]
    for n in range(8 if item.get('animate',True) else 1):
        im=Image.new('RGB',(240,136),theme['background']); d=ImageDraw.Draw(im)
        d.rounded_rectangle((4,4,235,131),radius=12,outline=theme['accent'],width=1)
        d.rounded_rectangle((5,5,8,130),radius=2,fill=theme['accent'])
        draw_icon(d,icon,theme['accent'])
        d.text((43,15),clipped(d,item.get('source','Notification').upper(),168,font(11)),font=font(11),fill=theme['accent'])
        # Subtle status pulse, not a flashing full screen.
        radius=2 if n<4 else 3
        d.ellipse((220-radius,22-radius,220+radius,22+radius),fill=theme['accent'])
        title=item.get('title',preset['title'])
        for i,line in enumerate(lines(d,title,font(18),207,2)):
            d.text((15,40+21*i),line,font=font(18),fill=theme['text'])
        for i,line in enumerate(lines(d,item.get('message',''),font(12),207,2)):
            d.text((15,86+15*i),line,font=font(12),fill=theme['muted'])
        result.append(im)
    return result

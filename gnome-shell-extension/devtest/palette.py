"""Derive a coherent ramp from one surface colour, and check it before use."""
import colorsys, sys

def hexrgb(h): h=h.lstrip('#'); return tuple(int(h[i:i+2],16) for i in (0,2,4))
def rgbhex(t): return '#%02x%02x%02x' % tuple(max(0,min(255,round(c))) for c in t)
def mix(a,b,t): return tuple(x+(y-x)*t for x,y in zip(hexrgb(a),hexrgb(b)))
def lin(c):
    c/=255
    return c/12.92 if c<=0.03928 else ((c+0.055)/1.055)**2.4
def lum(h):
    r,g,b=hexrgb(h); return .2126*lin(r)+.7152*lin(g)+.0722*lin(b)
def cr(a,b):
    la,lb=lum(a),lum(b); hi,lo=max(la,lb),min(la,lb); return (hi+.05)/(lo+.05)

def ramp(surface):
    W = '#ffffff'
    return {
        'surface':  surface,
        'border':   rgbhex(mix(surface, W, 0.16)),
        'divider':  rgbhex(mix(surface, W, 0.08)),
        'hover':    rgbhex(mix(surface, W, 0.05)),
        'hover2':   rgbhex(mix(surface, W, 0.11)),
        'dashrest': rgbhex(mix(surface, W, 0.05)),
        'dashover': rgbhex(mix(surface, W, 0.10)),
        'text':     rgbhex(mix(surface, W, 0.93)),
        'secondary':rgbhex(mix(surface, W, 0.58)),
        'dim':      rgbhex(mix(surface, W, 0.36)),
    }

if __name__ == '__main__':
    for name, surf in [("current slate","#1e242f"),("graphite","#202329"),
                       ("gunmetal","#24282f"),("warm charcoal","#252229")]:
        r = ramp(surf)
        print(f"\n{name}  surface {surf}")
        for k in ('text','secondary','dim'):
            v = r[k]; ratio = cr(v, surf)
            need = 4.5 if k != 'dim' else 3.0
            print(f"   {k:10} {v}  {ratio:5.2f}:1  {'ok' if ratio>=need else 'FAIL'}")
        for k in ('border','divider','hover'):
            print(f"   {k:10} {r[k]}")

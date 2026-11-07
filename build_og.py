#!/usr/bin/env python3
"""Build og.png (1200x630) for the crypto signal board."""
import json
from PIL import Image, ImageDraw, ImageFont

W, H = 1200, 630
BG = (11, 14, 20)
BG2 = (18, 23, 34)
LINE = (35, 43, 58)
TX = (232, 236, 244)
TX2 = (154, 166, 189)
TX3 = (102, 113, 138)
BUY = (0, 211, 149)
SELL = (255, 77, 109)
HOLD = (245, 181, 68)

REG = '/tmp/Vazirmatn-Regular.ttf'
BOLD = '/tmp/Vazirmatn-Bold.ttf'

img = Image.new('RGB', (W, H), BG)
d = ImageDraw.Draw(img)

# background gradient + glow
for y in range(H):
    t = y / H
    d.line([(0, y), (W, y)], fill=(
        int(BG[0] + (BG2[0] - BG[0]) * t * 0.9),
        int(BG[1] + (BG2[1] - BG[1]) * t * 0.9),
        int(BG[2] + (BG2[2] - BG[2]) * t * 0.9)))
glow = Image.new('RGB', (W, H), BG)
gd = ImageDraw.Draw(glow)
gd.ellipse([W - 520, -220, W + 160, 300], fill=(0, 60, 46))
glow = glow.filter(__import__('PIL.ImageFilter', fromlist=['ImageFilter']).GaussianBlur(90))
img = Image.blend(img, glow, 0.22)
d = ImageDraw.Draw(img)

f_title = ImageFont.truetype(BOLD, 52)
f_sub = ImageFont.truetype(REG, 26)
f_small = ImageFont.truetype(REG, 22)
f_num = ImageFont.truetype(BOLD, 46)
f_lbl = ImageFont.truetype(REG, 20)
f_tag = ImageFont.truetype(BOLD, 22)

# RTL helper: draw right-aligned
def rtl(x_right, y, text, font, fill):
    bbox = d.textbbox((0, 0), text, font=font)
    d.text((x_right - (bbox[2] - bbox[0]), y), text, font=font, fill=fill, anchor='la')

# logo mark
d.rounded_rectangle([60, 56, 124, 120], radius=16, fill=BG2, outline=BUY, width=4)
d.line([(76, 100), (88, 82), (99, 92), (112, 70)], fill=BUY, width=7, joint='curve')

rtl(1140, 58, 'داشبورد سیگنال ۱۰۰ کوین برتر', f_title, TX)
rtl(1140, 124, 'ICT · الیوت · ایچیموکو — به‌روزرسانی ساعتی', f_sub, TX2)

# separator
d.line([(60, 190), (1140, 190)], fill=LINE, width=2)

# stats
try:
    sig = json.load(open('/root/crypto-dashboard/data/signals.json'))
    nb, ns, nh = sig.get('buy', 0), sig.get('sell', 0), sig.get('hold', 0)
    regime = sig.get('regime_fa', '—')
except Exception:
    nb = ns = nh = 0
    regime = '—'

cards = [('خرید', nb, BUY), ('انتظار', nh, HOLD), ('فروش', ns, SELL)]
x = 1140
for label, n, col in cards:
    w = 230
    d.rounded_rectangle([x - w, 230, x, 350], radius=16, fill=BG2, outline=LINE, width=2)
    rtl(x - 22, 246, label, f_lbl, TX3)
    rtl(x - 22, 274, str(n), f_num, col)
    x -= (w + 24)

# regime pill
d.rounded_rectangle([60, 230, 340, 350], radius=16, fill=BG2, outline=LINE, width=2)
rtl(318, 246, 'رژیم بازار', f_lbl, TX3)
rtl(318, 274, regime, f_num, TX)

# bottom strip
d.rounded_rectangle([60, 396, 1140, 556], radius=16, fill=BG2, outline=LINE, width=2)
rtl(1116, 418, 'حکم خرید / فروش برای ۱۰۰ کوین برتر — بدون سرور، بدون هزینه', f_tag, TX)

x = 1116
for label, col in [('BUY', BUY), ('HOLD', HOLD), ('SELL', SELL)]:
    tw = 150
    d.rounded_rectangle([x - tw, 466, x, 522], radius=12, fill=BG, outline=col, width=2)
    bbox = d.textbbox((0, 0), label, font=f_tag)
    d.text((x - tw / 2 - (bbox[2] - bbox[0]) / 2, 478), label, font=f_tag, fill=col)
    x -= (tw + 20)

rtl(1116, 580, 'apluscancode.github.io/crypto-signal-board', f_small, TX3)

img.save('/root/crypto-dashboard/og.png')
print('og.png written', img.size)

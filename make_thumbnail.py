# -*- coding: utf-8 -*-
"""
'사진 모자이크' 움직이는 썸네일 생성기
  출력: photo_mosaic_thumbnail.webp (애니메이션 · 주 산출물), thumbnail.gif (호환용),
        thumbnail-frame.png (정지 대표컷), og-image.png (링크 카드 1200×630)
실행: python make_thumbnail.py        (og 만: python make_thumbnail.py og)

재료는 _thumb_src/ — 도구가 직접 그린 예시 그림(picnic.png · chat.png)과 도구가 구운 결과
(picnic_mosaic/blur/sticker.png · chat_fill.png), 자동으로 찾은 얼굴 자리(regions.json).
사람은 누가 봐도 그림인 예시 인물이고, 대화 속 이름·번호는 홍길동·010-0000-0000 이다.
장면
  ① 제목과 원본 단체 사진이 첫 장면부터 보인다(목록 썸네일이 빈 화면이 되지 않게)
  ② 훑는 선이 지나가며 얼굴 네 개에 점선 동그라미 — 「얼굴 4명 자동으로 찾음」
  ③ 모자이크 → 흐리게 → 스티커 → 다시 모자이크(아래 단추 줄이 따라 켜진다)
  ④ 오른쪽 대화 캡처가 올라오고 이름·연락처·주소·계좌가 검은 막대로 덮인다
  ⑤ 배지 세 개 — 마지막 프레임(대표컷)에 모두 보인다
"""
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, '_thumb_src')
NAME = os.path.basename(HERE)
W, H = 800, 450
FPS = 12.5
DUR = int(1000 / FPS)
NF = 60                      # 4.8초

BG0 = (16, 12, 34)
BG1 = (52, 34, 110)
WHITE = (244, 242, 252)
MUTED = (190, 182, 226)
ACC = (138, 98, 236)
ACC2 = (180, 156, 255)
GREEN = (52, 211, 153)
BOLD = "C:/Windows/Fonts/malgunbd.ttf"
REG = "C:/Windows/Fonts/malgun.ttf"
_fc = {}
REG_JSON = json.load(open(os.path.join(SRC, 'regions.json'), encoding='utf-8'))


def F(path, size):
    k = (path, size)
    if k not in _fc:
        _fc[k] = ImageFont.truetype(path, size)
    return _fc[k]


def glyph_ok(s, font):
    """맑은고딕에 없는 글자는 두부(□)로 찍힌다 — 쓰기 전에 걸러 낸다"""
    def bm(ch):
        m = font.getmask(ch)
        return (m.size, bytes(m))
    miss = bm(chr(0x10FFFD))
    for ch in set(s):
        if ch.strip() and bm(ch) == miss:
            raise AssertionError('글꼴에 없는 글자: %r in %r' % (ch, s))


def tw(d, s, font):
    return d.textbbox((0, 0), s, font=font)[2]


def text(d, xy, s, font, fill):
    glyph_ok(s, font)
    d.text(xy, s, font=font, fill=fill)


def ease(t):
    t = max(0.0, min(1.0, t))
    return 1 - (1 - t) ** 3


_ld = {}


def load(name, w=None, h=None):
    k = (name, w, h)
    if k not in _ld:
        im = Image.open(os.path.join(SRC, name)).convert('RGBA')
        if w:
            im = im.resize((w, max(1, round(im.height * w / im.width))), Image.LANCZOS)
        elif h:
            im = im.resize((max(1, round(im.width * h / im.height)), h), Image.LANCZOS)
        _ld[k] = im
    return _ld[k].copy()


def rounded(im, r):
    m = Image.new('L', im.size, 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, im.width - 1, im.height - 1), radius=r, fill=255)
    im.putalpha(m)
    return im


def shadowed(im, blur=9, off=(0, 7), alpha=140, pad=24):
    w, h = im.size
    out = Image.new('RGBA', (w + pad * 2, h + pad * 2), (0, 0, 0, 0))
    sh = Image.new('RGBA', im.size, (0, 0, 0, alpha))
    sh.putalpha(im.split()[3].point(lambda v: v * alpha // 255))
    layer = Image.new('RGBA', out.size, (0, 0, 0, 0))
    layer.paste(sh, (pad + off[0], pad + off[1]), sh)
    layer = layer.filter(ImageFilter.GaussianBlur(blur))
    out.alpha_composite(layer)
    out.alpha_composite(im, (pad, pad))
    return out


_bg = {}


def background(w, h):
    if (w, h) in _bg:
        return _bg[(w, h)].copy()
    bg = Image.new('RGB', (w, h), BG0)
    px = bg.load()
    for y in range(h):
        for x in range(w):
            t = (x / w) * .55 + (y / h) * .45
            px[x, y] = tuple(int(BG0[i] + (BG1[i] - BG0[i]) * t) for i in range(3))
    glow = Image.new('L', (w, h), 0)
    ImageDraw.Draw(glow).ellipse((w * .1, h * .25, w * .75, h * 1.3), fill=80)
    glow = glow.filter(ImageFilter.GaussianBlur(w * .08))
    bg = Image.composite(Image.new('RGB', (w, h), (88, 60, 190)), bg, glow)
    _bg[(w, h)] = bg
    return bg.copy()


def pill(fr, x, y, s, font, fg, bg, pad=(13, 6)):
    """반투명 알약 — ImageDraw 로 바로 그리면 알파가 섞이지 않고 덮어써져 흰 상자가 된다. 층을 따로 그려 합친다"""
    lay = Image.new('RGBA', fr.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    w = tw(d, s, font)
    d.rounded_rectangle((x, y, x + w + pad[0] * 2, y + font.size + pad[1] * 2 + 2), radius=(font.size + pad[1] * 2) // 2, fill=bg)
    text(d, (x + pad[0], y + pad[1] - 2), s, font, fg)
    fr.alpha_composite(lay)
    return w + pad[0] * 2


def blend(a, b, t):
    return Image.blend(a, b, max(0.0, min(1.0, t)))


def picnic_card(t, w):
    """단체 사진 — 원본 → 얼굴 찾기 → 효과 바뀜. 반환: (그림, 지금 켜진 효과)"""
    org = load('picnic.png', w)
    mos, blu, stk = load('picnic_mosaic.png', w), load('picnic_blur.png', w), load('picnic_sticker.png', w)
    k = w / 1600
    # 효과 시간표
    if t < .30:
        im, fx = org, None
    elif t < .40:
        im, fx = blend(org, mos, (t - .30) / .06), 'mosaic'
    elif t < .50:
        im, fx = blend(mos, blu, (t - .44) / .05), ('mosaic' if t < .465 else 'blur')
    elif t < .60:
        im, fx = blend(blu, stk, (t - .54) / .05), ('blur' if t < .565 else 'sticker')
    else:
        im, fx = blend(stk, mos, (t - .64) / .05), ('sticker' if t < .665 else 'mosaic')
    im = im.copy()
    d = ImageDraw.Draw(im)
    # 훑는 선과 점선 동그라미
    sweep = (t - .08) / .22
    faces = sorted(REG_JSON['faces'], key=lambda f: f['x'])
    if 0 < sweep < 1.15:
        x = int(sweep * w)
        if sweep < 1:
            lay = Image.new('RGBA', im.size, (0, 0, 0, 0))
            ld = ImageDraw.Draw(lay)
            for i in range(26):
                ld.line((x - i, 0, x - i, im.height), fill=ACC2 + (int(110 * (1 - i / 26)),))
            ld.line((x, 0, x, im.height), fill=(255, 255, 255, 230), width=2)
            im.alpha_composite(lay)
    show_ring = .08 < t < .74
    for f in faces:
        cx = (f['x'] + f['w'] / 2) * k
        if show_ring and sweep * w > cx:
            box = (f['x'] * k, f['y'] * k, (f['x'] + f['w']) * k, (f['y'] + f['h']) * k)
            p = ease((sweep * w - cx) / (w * .12))
            pad = (1 - p) * 10
            bb = (box[0] - pad, box[1] - pad, box[2] + pad, box[3] + pad)
            d.ellipse(bb, outline=(0, 0, 0, 150), width=4)
            # 점선 흉내 — 흰 호를 끊어 그린다
            for a in range(0, 360, 24):
                d.arc(bb, a, a + 14, fill=(255, 255, 255, 255), width=2)
    return rounded(im, 14), fx


def chat_card(t, h):
    org = load('chat.png', h=h)
    k = h / 1500
    im = org.copy()
    d = ImageDraw.Draw(im)
    regs = REG_JSON['chat']
    order = [7, 5, 6, 0, 1, 3, 2, 4]  # 머리 이름 → 말풍선 이름 → 받는 분·연락처·주소·송장 → 계좌
    order = [i for i in order if i < len(regs)] + [i for i in range(len(regs)) if i not in order]
    for n, i in enumerate(order):
        r = regs[i]
        p = ease((t - .50 - n * .022) / .07)
        if p <= 0:
            continue
        x0, y0 = r['x'] * k, r['y'] * k
        d.rectangle((x0, y0, x0 + r['w'] * k * p, y0 + r['h'] * k), fill=(17, 17, 17, 255))
    return rounded(im, 12)


def compose(t, W, H, k=1.0, og=False):
    fr = background(W, H).convert('RGBA')
    d = ImageDraw.Draw(fr)
    S = lambda v: int(round(v * k))
    tf, sf = F(BOLD, S(36)), F(REG, S(18))
    title, sub = '사진 모자이크', '얼굴은 자동으로 찾고, 이름·번호는 칠해서 가린다'
    if og:
        tf, sf = F(BOLD, S(44)), F(REG, S(21))
    tx = S(36) if not og else (W - tw(d, title, tf)) // 2
    sx = S(38) if not og else (W - tw(d, sub, sf)) // 2
    text(d, (tx, S(18) if not og else S(8)), title, tf, WHITE)
    text(d, (sx, S(18) + S(48) if not og else S(8) + S(62)), sub, sf, MUTED)
    base_y = S(108) if not og else S(176)
    ox = 0 if not og else (W - S(800)) // 2

    # ② ③ 단체 사진
    pw = S(468)
    card, fx = picnic_card(t, pw)
    sc = shadowed(card, blur=S(8), pad=S(22))
    fr.alpha_composite(sc, (ox + S(30) - S(22), base_y - S(22)))
    ph_h = card.height
    # 얼굴 찾음 배지
    a = ease((t - .22) / .08) * (1 - ease((t - .74) / .06))
    if a > 0:
        pill(fr, ox + S(44), base_y + S(12), '얼굴 4명 자동으로 찾음', F(BOLD, S(14)), (16, 12, 34, int(255 * a)), GREEN + (int(240 * a),))
    # 효과 단추 줄
    labels = [('mosaic', '모자이크'), ('blur', '흐리게'), ('fill', '칠하기'), ('sticker', '스티커')]
    cf = F(BOLD, S(14))
    xx = ox + S(30)
    yy = base_y + ph_h + S(12)
    for key, lab in labels:
        bg = ACC + (255,) if key == fx else (255, 255, 255, 34)
        fg = (255, 255, 255, 255) if key == fx else MUTED + (255,)
        if key == 'fill' and t > .5:
            bg = (17, 17, 17, 255) if t < .78 else (255, 255, 255, 34)
            fg = (255, 255, 255, 255) if t < .78 else MUTED + (255,)
        xx += pill(fr, xx, yy, lab, cf, fg, bg) + S(7)

    # ④ 대화 캡처
    e = ease((t - .38) / .12)
    if e > 0:
        ch_h = S(296)
        cc = shadowed(chat_card(t, ch_h), blur=S(8), pad=S(22))
        x = ox + S(540) - S(22)
        y = base_y - S(22) + int((1 - e) * S(300))
        fr.alpha_composite(cc, (x, y))
        if t > .70:
            p = ease((t - .70) / .06)
            pill(fr, ox + S(540), base_y + S(296) + S(12), '이름·번호·주소 칠하기', cf, (255, 255, 255, int(255 * p)), (17, 17, 17, int(235 * p)))

    # ⑤ 배지 — 제목 오른쪽 위
    chips = ['업로드 없이', '여러 장 한 번에', '위치 정보 삭제']
    bf = F(BOLD, S(13))
    if not og:
        xr = W - S(28)
        for i, s in enumerate(chips[::-1]):
            p = ease((t - .78 - (2 - i) * .04) / .08)
            wv = tw(d, s, bf) + S(24)
            xr -= wv
            if p > 0:
                bg = ACC + (int(235 * p),) if s == '업로드 없이' else (255, 255, 255, int(46 * p))
                pill(fr, xr, S(30) + int((1 - p) * 10), s, bf, (255, 255, 255, int(255 * p)), bg, pad=(12, 5))
            xr -= S(6)
    else:
        total = sum(tw(d, s, bf) + S(24) for s in chips) + S(8) * 2
        x = (W - total) // 2
        for s in chips:
            bg = ACC + (235,) if s == '업로드 없이' else (255, 255, 255, 46)
            x += pill(fr, x, S(122), s, bf, (255, 255, 255, 255), bg, pad=(12, 5)) + S(8)
    return fr.convert('RGB')


def make_og():
    Wo, Ho = 1200, 630
    im = compose(1.0, Wo, Ho, k=1.15, og=True)
    d = ImageDraw.Draw(im)
    assert tw(d, '사진 모자이크', F(BOLD, round(44 * 1.15))) <= 630, 'og 제목이 가운데 띠를 넘는다'
    im.save(os.path.join(HERE, 'og-image.png'), optimize=True)
    return im


def main():
    if len(sys.argv) > 1 and sys.argv[1] == 'og':
        make_og()
        return
    frames = [compose(i / (NF - 1), W, H) for i in range(NF)]
    frames[-1].save(os.path.join(HERE, 'thumbnail-frame.png'), optimize=True)
    durs = [DUR] * NF
    durs[-1] = 1400          # 마지막 대표컷에서 잠깐 멈춘다
    frames[0].save(os.path.join(HERE, NAME + '_thumbnail.webp'), save_all=True, append_images=frames[1:],
                   duration=durs, loop=0, quality=82, method=6)
    pal = [f.quantize(colors=200, method=Image.MEDIANCUT, dither=Image.FLOYDSTEINBERG) for f in frames]
    pal[0].save(os.path.join(HERE, 'thumbnail.gif'), save_all=True, append_images=pal[1:], duration=durs, loop=0, optimize=True)
    make_og()
    for n in (NAME + '_thumbnail.webp', 'thumbnail.gif', 'thumbnail-frame.png', 'og-image.png'):
        print(n, os.path.getsize(os.path.join(HERE, n)))


if __name__ == '__main__':
    main()

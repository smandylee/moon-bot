"""메시지를 '명언 짤' 이미지로 만드는 렌더러.

왼쪽에 흑백 프로필 사진이 오른쪽 검은 배경으로 스며들고,
오른쪽에 메시지 내용과 작성자 이름이 들어간다.
디스코드와 무관한 순수 Pillow 코드라 단독으로 테스트할 수 있다.
"""
import io
import os
import re
from functools import lru_cache
from typing import List, Optional

from PIL import Image, ImageDraw, ImageFont, ImageOps

WIDTH, HEIGHT = 1200, 630
AVATAR_SIZE = HEIGHT              # 왼쪽에 꽉 차는 정사각형
TEXT_LEFT = 600                   # 텍스트 영역 시작 x
TEXT_RIGHT = WIDTH - 50           # 텍스트 영역 끝 x
TEXT_CENTER_X = (TEXT_LEFT + TEXT_RIGHT) // 2
TEXT_MAX_WIDTH = TEXT_RIGHT - TEXT_LEFT
QUOTE_MAX_HEIGHT = 400
MAX_QUOTE_CHARS = 300
WATERMARK = "Moon Bot"

_FONT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fonts')
_FONT_REGULAR = os.path.join(_FONT_DIR, 'NotoSansKR-Regular.otf')
_FONT_LIGHT = os.path.join(_FONT_DIR, 'NotoSansKR-Light.otf')

_CUSTOM_EMOJI = re.compile(r'<a?:(\w+):\d+>')


@lru_cache(maxsize=64)
def _font(path: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size)


def clean_quote_text(text: str) -> str:
    """커스텀 이모지 태그를 :이름: 으로 줄이고 공백을 정리한다."""
    text = _CUSTOM_EMOJI.sub(r':\1:', text or '')
    lines = [line.strip() for line in text.strip().splitlines()]
    text = '\n'.join(line for line in lines if line)
    if len(text) > MAX_QUOTE_CHARS:
        text = text[:MAX_QUOTE_CHARS].rstrip() + '…'
    return text


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> List[str]:
    """단어 단위로 줄바꿈하고, 한 단어가 너무 길면 글자 단위로 자른다."""
    lines: List[str] = []
    for paragraph in text.split('\n'):
        current = ''
        for word in paragraph.split(' '):
            candidate = f'{current} {word}' if current else word
            if draw.textlength(candidate, font=font) <= max_width:
                current = candidate
                continue
            if current:
                lines.append(current)
            current = ''
            for ch in word:
                if draw.textlength(current + ch, font=font) <= max_width:
                    current += ch
                else:
                    lines.append(current)
                    current = ch
        lines.append(current)
    return lines


def _fit_quote(draw, text: str):
    """텍스트 영역에 들어가는 가장 큰 글자 크기를 찾는다."""
    for size in (60, 54, 48, 42, 38, 34, 30, 27, 24, 22):
        font = _font(_FONT_REGULAR, size)
        lines = _wrap(draw, text, font, TEXT_MAX_WIDTH)
        line_height = int(size * 1.35)
        if line_height * len(lines) <= QUOTE_MAX_HEIGHT:
            return font, lines, line_height

    # 제일 작은 크기로도 넘치면 들어가는 데까지만 쓰고 말줄임
    max_lines = QUOTE_MAX_HEIGHT // line_height
    lines = lines[:max_lines]
    lines[-1] = lines[-1][:-1].rstrip() + '…'
    return font, lines, line_height


def _avatar_layer(avatar_bytes: Optional[bytes]) -> Image.Image:
    """흑백 아바타 + 오른쪽으로 갈수록 검게 사라지는 마스크."""
    if avatar_bytes:
        avatar = Image.open(io.BytesIO(avatar_bytes)).convert('RGB')
        avatar = ImageOps.fit(avatar, (AVATAR_SIZE, AVATAR_SIZE), Image.LANCZOS)
        avatar = ImageOps.grayscale(avatar).convert('RGB')
    else:
        avatar = Image.new('RGB', (AVATAR_SIZE, AVATAR_SIZE), (60, 60, 60))

    # 아바타 폭의 30% 지점부터 끝까지 경계 없이 서서히 투명해진다 (smoothstep)
    fade_start = int(AVATAR_SIZE * 0.3)
    gradient = Image.new('L', (AVATAR_SIZE, 1), 255)
    for x in range(fade_start, AVATAR_SIZE):
        t = (x - fade_start) / (AVATAR_SIZE - fade_start)
        gradient.putpixel((x, 0), int(255 * (1 - t * t * (3 - 2 * t))))
    mask = gradient.resize((AVATAR_SIZE, AVATAR_SIZE))
    avatar.putalpha(mask)
    return avatar


def render_quote_card(
    text: str,
    display_name: str,
    username: str,
    avatar_bytes: Optional[bytes] = None,
) -> bytes:
    """명언 카드 PNG 바이트를 반환한다."""
    text = clean_quote_text(text)
    canvas = Image.new('RGB', (WIDTH, HEIGHT), (0, 0, 0))
    avatar = _avatar_layer(avatar_bytes)
    canvas.paste(avatar, (0, 0), avatar)

    draw = ImageDraw.Draw(canvas)
    quote_font, lines, line_height = _fit_quote(draw, text)
    name_font = _font(_FONT_LIGHT, 28)
    handle_font = _font(_FONT_LIGHT, 20)

    name_gap, handle_gap = 28, 10
    block_height = line_height * len(lines) + name_gap + 40 + handle_gap + 26
    y = (HEIGHT - block_height) // 2

    for line in lines:
        draw.text((TEXT_CENTER_X, y), line, font=quote_font, fill=(255, 255, 255), anchor='mt')
        y += line_height

    y += name_gap
    draw.text((TEXT_CENTER_X, y), f'- {display_name}', font=name_font, fill=(225, 225, 225), anchor='mt')
    y += 40 + handle_gap
    draw.text((TEXT_CENTER_X, y), f'@{username}', font=handle_font, fill=(140, 140, 140), anchor='mt')

    draw.text((WIDTH - 20, HEIGHT - 16), WATERMARK, font=handle_font, fill=(110, 110, 110), anchor='rb')

    out = io.BytesIO()
    canvas.save(out, format='PNG', optimize=True)
    return out.getvalue()

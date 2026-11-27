"""Тестовые картинки генерируются кодом, а не лежат файлами в репозитории.

Так мы точно знаем их свойства: эта резкая, эта размыта, эта тёмная,
а эта — копия той же картинки другого размера. И результат воспроизводим:
одинаковый seed — одинаковая картинка.
"""
from __future__ import annotations

import io
import random

from PIL import Image, ImageDraw, ImageFilter


def _scene(width: int, height: int, seed: int, dark: bool = False) -> Image.Image:
    """Резкая «сцена» из случайных прямоугольников, кругов и линий."""
    rnd = random.Random(seed)
    lo, hi = (0, 45) if dark else (0, 255)
    img = Image.new("RGB", (width, height), tuple(rnd.randint(lo, hi) for _ in range(3)))
    draw = ImageDraw.Draw(img)
    for _ in range(120):
        x1, y1 = rnd.randrange(width), rnd.randrange(height)
        x2, y2 = x1 + rnd.randint(10, width // 3), y1 + rnd.randint(10, height // 3)
        color = tuple(rnd.randint(lo, hi) for _ in range(3))
        shape = rnd.choice(("rect", "ellipse", "line"))
        if shape == "rect":
            draw.rectangle((x1, y1, x2, y2), fill=color)
        elif shape == "ellipse":
            draw.ellipse((x1, y1, x2, y2), fill=color)
        else:
            draw.line((x1, y1, x2, y2), fill=color, width=rnd.randint(1, 6))
    return img


def encode(img: Image.Image, fmt: str = "JPEG", **kwargs) -> bytes:
    buf = io.BytesIO()
    if fmt == "JPEG":
        kwargs.setdefault("quality", 90)
    img.save(buf, format=fmt, **kwargs)
    return buf.getvalue()


def sharp(width: int = 800, height: int = 600, seed: int = 1, fmt: str = "JPEG") -> bytes:
    """Обычное резкое фото."""
    return encode(_scene(width, height, seed), fmt)


def blurred(width: int = 800, height: int = 600, seed: int = 1) -> bytes:
    """Та же сцена, сильно размытая — analyzer должен отметить is_blurry."""
    return encode(_scene(width, height, seed).filter(ImageFilter.GaussianBlur(12)))


def dark(width: int = 800, height: int = 600, seed: int = 1) -> bytes:
    """Тёмная сцена — analyzer должен отметить is_underexposed."""
    return encode(_scene(width, height, seed, dark=True))


def resized_copy(width: int = 800, height: int = 600, seed: int = 1,
                 scale: float = 0.5) -> bytes:
    """Копия sharp(...) другого размера и качества — должна найтись как дубликат."""
    img = _scene(width, height, seed)
    small = img.resize((int(width * scale), int(height * scale)), Image.LANCZOS)
    return encode(small, quality=70)


def png_of_exact_size(size: int) -> bytes:
    """PNG ровно size байт: маленькая картинка + «хвост» из нулей.
    Сервис проверяет заголовок картинки, а лишние байты в конце ему не мешают."""
    head = encode(_scene(64, 64, seed=7), "PNG")
    if size < len(head):
        raise ValueError(f"минимальный размер {len(head)} байт")
    return head + b"\0" * (size - len(head))


# ---------- не картинки ----------
TEXT = "это не картинка\n".encode()
BROKEN_JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 200   # заголовок JPEG, внутри мусор


def gif() -> bytes:
    return encode(_scene(64, 64, seed=3).convert("P"), "GIF")

from pathlib import Path

from PIL import ImageFont

from nttl.imaging.fonts import available_fonts, font_directories, font_name


def test_font_directories_are_absolute():
    assert all(directory.is_absolute() for directory in font_directories())


def test_available_fonts_are_unique_readable_files():
    fonts = available_fonts()
    if not fonts:  # a container may ship without any font installed
        return
    names = [entry["name"] for entry in fonts]
    assert names == sorted(names, key=str.lower)
    assert len(names) == len(set(names))
    for entry in fonts[:5]:
        assert Path(entry["path"]).is_file()
        ImageFont.truetype(entry["path"], 12)


def test_an_unreadable_file_falls_back_to_its_name(tmp_path):
    broken = tmp_path / "Not_A-Font.ttf"
    broken.write_bytes(b"nope")
    assert font_name(broken) == "Not A Font"

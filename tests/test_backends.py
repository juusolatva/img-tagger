"""Tests for the Ollama and LM Studio request helpers, using fake clients (no server needed)."""

import base64
import io

import pytest
from conftest import FakeOllamaClient, FakeOpenAIClient, _Obj, make_animated, make_gif, make_image
from PIL import Image

import img_tagger


def sent_ollama_image(client: FakeOllamaClient) -> bytes:
    return client.calls[0]["messages"][0]["images"][0]


def sent_lm_studio_image(client: FakeOpenAIClient) -> tuple[str, bytes]:
    url = client.calls[0]["messages"][0]["content"][1]["image_url"]["url"]
    header, data = url.split(",", 1)
    return header.removeprefix("data:").removesuffix(";base64"), base64.b64decode(data)


class TestGetTagsOllama:
    def test_sends_prompt_and_original_bytes_without_pixel_budget(self, tmp_path):
        image = make_image(tmp_path / "a.jpg")
        client = FakeOllamaClient()
        client.reply = "a, b, c"

        result = img_tagger.get_tags_ollama(client, "qwen3-vl:8b", image, "describe it", max_megapixels=0)

        assert result == "a, b, c"
        assert client.calls == [
            {
                "model": "qwen3-vl:8b",
                "messages": [{"role": "user", "content": "describe it", "images": [image.read_bytes()]}],
            }
        ]

    def test_sends_scaled_copy_by_default(self, tmp_path):
        image = make_image(tmp_path / "a.jpg", size=(2000, 1000))
        client = FakeOllamaClient()
        img_tagger.get_tags_ollama(client, "m", image, "p")
        with Image.open(io.BytesIO(sent_ollama_image(client))) as sent:
            assert sent.width * sent.height <= img_tagger.DEFAULT_MAX_MEGAPIXELS * 1_000_000
            assert sent.size == (1414, 707)


class TestGetTagsLmStudio:
    @pytest.mark.parametrize(
        "name, mime",
        [("a.jpg", "image/jpeg"), ("a.png", "image/png"), ("a.webp", "image/webp")],
    )
    def test_sends_base64_data_url_with_mime_type(self, tmp_path, name, mime):
        image = make_image(tmp_path / name)
        client = FakeOpenAIClient()

        img_tagger.get_tags_lm_studio(client, "some-model", image, "describe it", max_megapixels=0)

        call = client.calls[0]
        assert call["model"] == "some-model"
        text_part, image_part = call["messages"][0]["content"]
        assert text_part == {"type": "text", "text": "describe it"}
        assert image_part["type"] == "image_url"
        assert sent_lm_studio_image(client) == (mime, image.read_bytes())

    def test_gif_mime_type(self, tmp_path):
        image = make_gif(tmp_path / "a.gif")
        client = FakeOpenAIClient()
        img_tagger.get_tags_lm_studio(client, "m", image, "p", max_megapixels=0)
        assert sent_lm_studio_image(client)[0] == "image/gif"

    def test_mime_type_follows_content_not_extension(self, tmp_path):
        image = tmp_path / "really_png.jpg"
        Image.new("RGB", (4, 4)).save(image, format="PNG")
        for max_megapixels in (0, 1):
            client = FakeOpenAIClient()
            img_tagger.get_tags_lm_studio(client, "m", image, "p", max_megapixels=max_megapixels)
            assert sent_lm_studio_image(client)[0] == "image/png"

    def test_unknown_format_falls_back_to_jpeg_without_pixel_budget(self, tmp_path):
        bogus = tmp_path / "bogus.png"
        bogus.write_bytes(b"not an image")
        client = FakeOpenAIClient()
        img_tagger.get_tags_lm_studio(client, "m", bogus, "p", max_megapixels=0)
        assert sent_lm_studio_image(client)[0] == "image/jpeg"

    def test_returns_message_content(self, tmp_path):
        image = make_image(tmp_path / "a.png")
        client = FakeOpenAIClient()
        client.chat = _Obj(completions=_Obj(create=lambda **kw: _Obj(choices=[_Obj(message=_Obj(content="x, y"))])))
        assert img_tagger.get_tags_lm_studio(client, "m", image, "p") == "x, y"


def model_image(data: bytes, max_megapixels: float = 1.0) -> tuple[Image.Image, str]:
    sent, mime = img_tagger._model_image(data, max_megapixels)
    image = Image.open(io.BytesIO(sent))
    image.load()
    return image, mime


class TestModelImage:
    @pytest.mark.parametrize("size", [(4000, 3000), (1080, 2400), (5000, 200)])
    def test_scales_down_to_the_budget_keeping_aspect_ratio(self, tmp_path, size):
        source = make_image(tmp_path / "a.jpg", size=size).read_bytes()
        sent, mime = model_image(source)
        assert mime == "image/jpeg"
        assert sent.width * sent.height <= 1_000_000
        assert sent.width * sent.height > 990_000
        assert abs(sent.width / sent.height - size[0] / size[1]) < 0.01

    def test_budget_is_configurable(self, tmp_path):
        source = make_image(tmp_path / "a.jpg", size=(2000, 2000)).read_bytes()
        assert model_image(source, 0.25)[0].size == (500, 500)
        assert model_image(source, 2.0)[0].size == (1414, 1414)

    def test_small_images_are_never_enlarged(self, tmp_path):
        source = make_image(tmp_path / "a.png", size=(300, 200)).read_bytes()
        sent, mime = model_image(source)
        assert (sent.size, mime) == ((300, 200), "image/png")

    def test_applies_exif_orientation(self, tmp_path):
        path = tmp_path / "rotated.jpg"
        exif = Image.Exif()
        exif[0x0112] = 6  # Orientation: rotate 90° clockwise to view
        Image.new("RGB", (40, 20), (10, 20, 30)).save(path, format="JPEG", exif=exif)
        sent, _ = model_image(path.read_bytes())
        assert sent.size == (20, 40)
        assert 0x0112 not in sent.getexif()

    def test_strips_metadata(self, tmp_path):
        path = tmp_path / "gps.jpg"
        exif = Image.Exif()
        exif[0x010E] = "secret description"  # ImageDescription
        Image.new("RGB", (64, 48)).save(path, format="JPEG", exif=exif)
        img_tagger.write_metadata(str(path), ["tag one", "tag two"])
        sent, _ = img_tagger._model_image(path.read_bytes())
        assert b"secret description" not in sent
        assert img_tagger.PROCESSED_MARKER.encode() not in sent
        assert b"Exif" not in sent and b"xmp" not in sent.lower()

    def test_transparency_is_kept_as_png(self, tmp_path):
        path = tmp_path / "alpha.webp"
        Image.new("RGBA", (2000, 1000), (255, 0, 0, 128)).save(path, format="WEBP")
        sent, mime = model_image(path.read_bytes())
        assert (mime, sent.format, sent.mode) == ("image/png", "PNG", "RGBA")
        assert sent.width * sent.height <= 1_000_000

    def test_opaque_webp_becomes_jpeg(self, tmp_path):
        source = make_image(tmp_path / "a.webp", size=(1500, 1000)).read_bytes()
        sent, mime = model_image(source)
        assert (mime, sent.format) == ("image/jpeg", "JPEG")

    @pytest.mark.parametrize("make", [make_gif, make_animated], ids=["gif", "webp"])
    def test_animated_images_send_only_the_first_frame(self, tmp_path, make):
        path = make(tmp_path / ("a.gif" if make is make_gif else "a.webp"))
        sent, _ = model_image(path.read_bytes())
        assert not getattr(sent, "is_animated", False)
        red, green, blue = sent.convert("RGB").getpixel((0, 0))
        assert red > 240 and green < 16 and blue < 16  # the red first frame (JPEG may shift it slightly)

    def test_sixteen_bit_png_keeps_its_brightness(self, tmp_path):
        path = tmp_path / "deep.png"
        Image.new("I;16", (8, 8), 40000).save(path, format="PNG")
        sent, mime = model_image(path.read_bytes())
        assert mime == "image/png"
        assert sent.convert("L").getpixel((0, 0)) == 40000 // 256

    def test_zero_budget_sends_the_original(self, tmp_path):
        source = make_image(tmp_path / "a.jpg", size=(3000, 2000)).read_bytes()
        assert img_tagger._model_image(source, 0) == (source, "image/jpeg")


class TestModelImageFallback:
    def test_truncated_jpeg_falls_back_to_the_original(self, tmp_path):
        full = make_image(tmp_path / "a.jpg", size=(1600, 1200)).read_bytes()
        truncated = full[: len(full) // 2]
        assert img_tagger.get_image_format(truncated) == "JPEG"  # passes the pipeline's format check
        assert img_tagger._model_image(truncated) == (truncated, "image/jpeg")

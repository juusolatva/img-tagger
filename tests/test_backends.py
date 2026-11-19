"""Tests for the Ollama and LM Studio request helpers, using fake clients (no server needed)."""

import base64
import io
import struct
import zlib

import conftest
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
        assert b"Exif" not in sent
        assert b"xmp" not in sent.lower()

    def test_transparency_is_kept_as_png(self, tmp_path):
        path = tmp_path / "alpha.webp"
        Image.new("RGBA", (2000, 1000), (255, 0, 0, 128)).save(path, format="WEBP")
        sent, mime = model_image(path.read_bytes())
        assert (mime, sent.format, sent.mode) == ("image/png", "PNG", "RGBA")
        assert sent.width * sent.height <= 1_000_000

    @pytest.mark.parametrize(("mode", "color"), [("RGB", (255, 0, 0)), ("L", 255)])
    def test_png_transparent_colour_is_kept_as_alpha(self, tmp_path, mode, color):
        path = tmp_path / f"trns-{mode}.png"
        image = Image.new(mode, (2000, 1000), color)
        image.paste(0, (0, 0, 1000, 1000))  # left half in the transparent colour
        image.save(path, format="PNG", transparency=0 if mode == "L" else (0, 0, 0))
        sent, mime = model_image(path.read_bytes())
        assert mime == "image/png"
        assert sent.mode == "RGBA"
        assert sent.getpixel((10, 10))[3] == 0  # transparent area stays transparent
        assert sent.getpixel((sent.width - 10, 10))[3] == 255

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
        # the red first frame (JPEG may shift it slightly)
        assert red > 240
        assert green < 16
        assert blue < 16

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


class TestMissingContent:
    def test_ollama_none_content_becomes_empty(self, tmp_path):
        client = FakeOllamaClient()
        client.reply = None
        assert img_tagger.get_tags_ollama(client, "m", make_image(tmp_path / "a.png"), "p") == ""

    def test_lm_studio_none_content_becomes_empty(self, tmp_path):
        client = FakeOpenAIClient()
        client.reply = None
        assert img_tagger.get_tags_lm_studio(client, "m", make_image(tmp_path / "a.png"), "p") == ""


class TestModelImageAnyPillowError:
    @pytest.mark.parametrize("error", [struct.error("bad EXIF"), zlib.error("bad"), TypeError("x")])
    def test_errors_outside_oserror_fall_back_to_the_original(self, tmp_path, monkeypatch, error):
        source = make_image(tmp_path / "a.png").read_bytes()

        def broken(*args):
            raise error

        monkeypatch.setattr(img_tagger, "_scaled_image", broken)
        assert img_tagger._model_image(source) == (source, "image/png")


class TestSnapshotArgument:
    @pytest.mark.parametrize("backend", ["ollama", "lm-studio"])
    def test_given_snapshot_is_sent_without_reading_the_path(self, tmp_path, backend):
        data = make_image(tmp_path / "a.png").read_bytes()
        missing = tmp_path / "gone.png"
        if backend == "ollama":
            client = FakeOllamaClient()
            img_tagger.get_tags_ollama(client, "m", missing, "p", 0, data=data)
            assert sent_ollama_image(client) == data
        else:
            client = FakeOpenAIClient()
            img_tagger.get_tags_lm_studio(client, "m", missing, "p", 0, data=data)
            assert sent_lm_studio_image(client) == ("image/png", data)


class TestCheckServer:
    """_check_server(): fail before any image if the server is down or lacks the model."""

    @pytest.fixture
    def models(self, monkeypatch, fake_ollama, fake_openai):
        """Sets what the fake servers list."""

        def set_models(*names):
            monkeypatch.setattr(conftest, "FAKE_MODELS", list(names))

        return set_models

    @pytest.mark.parametrize(
        ("backend", "listed", "model"),
        [
            ("ollama", "qwen3-vl:8b", "qwen3-vl:8b"),
            ("ollama", "llava:latest", "llava"),  # Ollama's implicit default tag
            ("ollama", "user/llava:latest", "user/llava"),
            ("lm-studio", "qwen/qwen3-vl-8b", "qwen/qwen3-vl-8b"),
            ("lm-studio", "qwen/qwen3-vl-8b@q4_k_m", "qwen/qwen3-vl-8b"),  # extra quantization
        ],
    )
    def test_listed_model_passes(self, models, backend, listed, model):
        models("other:1b", listed)
        img_tagger._check_server(backend, "http://fake:1", model)

    @pytest.mark.parametrize(
        ("backend", "listed", "model"),
        [
            ("ollama", "qwen3-vl:4b", "qwen3-vl:8b"),  # another tag of the same model
            ("ollama", "llava:13b", "llava"),  # only :latest is implied
            ("lm-studio", "qwen3-vl:8b-other", "qwen3-vl:8b"),
        ],
    )
    def test_similar_name_is_not_a_match(self, models, backend, listed, model):
        models(listed)
        with pytest.raises(img_tagger._ServerCheckError, match="has no model"):
            img_tagger._check_server(backend, "http://fake:1", model)

    def test_missing_ollama_model_suggests_pull(self, models):
        models("b:1b", "a:1b")
        with pytest.raises(img_tagger._ServerCheckError) as exc:
            img_tagger._check_server("ollama", "http://fake:1", "qwen3-vl:8b")
        message = str(exc.value)
        assert "Ollama server at http://fake:1 has no model 'qwen3-vl:8b'" in message
        assert "Available models: a:1b, b:1b." in message
        assert "ollama pull qwen3-vl:8b" in message

    def test_ollama_name_on_lm_studio_explains_id_format(self, models):
        models("qwen/qwen3-vl-8b")
        with pytest.raises(img_tagger._ServerCheckError) as exc:
            img_tagger._check_server("lm-studio", "http://fake:1", img_tagger.DEFAULT_MODEL)
        assert "LM Studio model ids differ from Ollama names" in str(exc.value)

    @pytest.mark.parametrize("backend", ["ollama", "lm-studio"])
    def test_available_models_skip_blank_names_and_repeats(self, models, backend):
        models("b:1b", "", None, "a:1b", "b:1b")
        with pytest.raises(img_tagger._ServerCheckError, match=r"Available models: a:1b, b:1b\."):
            img_tagger._check_server(backend, "http://fake:1", "x")

    def test_no_models_listed(self, models):
        models()
        with pytest.raises(img_tagger._ServerCheckError, match="Available models: none"):
            img_tagger._check_server("lm-studio", "http://fake:1", "x")

    @pytest.mark.parametrize("backend", ["ollama", "lm-studio"])
    def test_unreachable_server(self, monkeypatch, backend):
        def refuse():
            raise ConnectionError("connection refused")

        class DownClient:  # both SDK shapes: Ollama's client.list(), LM Studio's client.models.list()
            list = staticmethod(refuse)
            models = _Obj(list=refuse)

        monkeypatch.setattr(img_tagger, "_create_client", lambda *args: DownClient())
        with pytest.raises(img_tagger._ServerCheckError, match="Could not reach the .* server at http://fake:1") as exc:
            img_tagger._check_server(backend, "http://fake:1", "x")
        assert isinstance(exc.value.__cause__, ConnectionError)

    @pytest.mark.parametrize(("timeout", "expected"), [(600, img_tagger.SERVER_CHECK_TIMEOUT), (3, 3)])
    def test_check_uses_short_timeout(self, monkeypatch, timeout, expected):
        timeouts = []

        def fake_client(backend, host, client_timeout):
            timeouts.append(client_timeout)
            return FakeOllamaClient()

        monkeypatch.setattr(img_tagger, "_create_client", fake_client)
        img_tagger._check_server("ollama", "http://fake:1", "test-model", timeout)
        assert timeouts == [expected]

    def test_main_stops_before_any_image(self, models, tmp_path, capsys, no_quit_listener):
        models("other:1b")
        image = make_image(tmp_path / "a.png")
        assert img_tagger.main([str(tmp_path), "--host", "http://fake:1"]) == 1
        assert "Error: The Ollama server at http://fake:1 has no model" in capsys.readouterr().out
        assert all(client.calls == [] for client in FakeOllamaClient.instances)
        assert not img_tagger.is_already_processed(image)

    def test_clear_needs_no_server(self, models, tmp_path):
        models()
        make_image(tmp_path / "a.png")
        assert img_tagger.main([str(tmp_path), "--clear"]) == 0
        assert FakeOllamaClient.instances == []

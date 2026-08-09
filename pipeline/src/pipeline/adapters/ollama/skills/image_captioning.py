"""ImageCaptioningSkillPort adapter: a local vision-capable Ollama model describes
an extracted image in text. Requires a vision model pulled locally (e.g.
`ollama pull llava`) — not one of the chat/embedding models this project already
assumes are present."""

from __future__ import annotations

import base64
from pathlib import Path

from pipeline.adapters.ollama.client import OllamaClient
from pipeline.domain.source_document import ParsedImage

_PROMPT = (
    "Describe this image in one or two plain sentences, focused on any data, "
    "numbers, or labeled content it shows (e.g. a chart's values, a diagram's "
    "labels) rather than generic visual description."
)


class OllamaImageCaptioningSkill:
    def __init__(self, client: OllamaClient, model: str) -> None:
        self._client = client
        self._model = model

    def caption(self, image: ParsedImage) -> str:
        image_base64 = base64.b64encode(Path(image.path).read_bytes()).decode("ascii")
        return self._client.generate_with_image(self._model, _PROMPT, image_base64).strip()

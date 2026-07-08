from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Callable, Protocol, TypeVar

from .config import EffectiveConfig, load_dotenv
from .errors import ProviderError


T = TypeVar("T")


class ProgressReporter(Protocol):
    def __call__(self, message: str) -> None:
        ...

KNOWN_DIMENSIONS = {
    ("openai", "text-embedding-3-small"): 1536,
    ("openai", "text-embedding-3-large"): 3072,
    ("openai", "text-embedding-ada-002"): 1536,
    ("gemini", "gemini-embedding-2"): 3072,
    ("gemini", "gemini-embedding-001"): 3072,
    ("gemini", "text-embedding-004"): 768,
    ("gemini", "embedding-001"): 768,
}


@dataclass(frozen=True)
class GenerationResult:
    text: str
    token_usage: dict[str, int] | None = None


class BaseProvider:
    name: str

    def __init__(self, config: EffectiveConfig):
        self.config = config
        self.timeout = int(config.get("request_timeout_seconds"))
        self.retries = int(config.get("request_retries"))

    @property
    def embedding_model(self) -> str:
        return self.config.embedding_model

    @property
    def generation_model(self) -> str:
        return self.config.generation_model

    def expected_dimensions(self) -> int | None:
        return KNOWN_DIMENSIONS.get((self.name, self.embedding_model))

    def embed_texts(self, texts: list[str], progress: ProgressReporter | None = None) -> list[list[float]]:
        raise NotImplementedError

    def generate(
        self,
        question: str,
        context: str,
        progress: ProgressReporter | None = None,
    ) -> GenerationResult:
        raise NotImplementedError

    def _retry(
        self,
        operation: str,
        fn: Callable[[], T],
        retries: int | None = None,
        progress: ProgressReporter | None = None,
    ) -> T:
        last_error: Exception | None = None
        attempts = retries or self.retries
        for attempt in range(1, attempts + 1):
            try:
                return fn()
            except Exception as exc:  # SDK exception types differ by provider.
                last_error = exc
                if attempt >= attempts:
                    break
                wait_seconds = self._retry_delay_seconds(exc) or min(2 ** (attempt - 1), 8)
                if progress:
                    progress(f"{operation} hit a retryable error; waiting {wait_seconds:.1f}s before retry {attempt + 1}/{attempts}.")
                time.sleep(wait_seconds)
        raise ProviderError(f"{self.name} {operation} failed: {last_error}") from last_error

    def _retry_delay_seconds(self, exc: Exception) -> float | None:
        text = str(exc)
        marker = "retryDelay': '"
        if marker in text:
            tail = text.split(marker, 1)[1]
            raw = tail.split("'", 1)[0]
            if raw.endswith("s"):
                try:
                    return float(raw[:-1])
                except ValueError:
                    return None
        marker = '"retryDelay": "'
        if marker in text:
            tail = text.split(marker, 1)[1]
            raw = tail.split('"', 1)[0]
            if raw.endswith("s"):
                try:
                    return float(raw[:-1])
                except ValueError:
                    return None
        return None


class OpenAIProvider(BaseProvider):
    name = "openai"

    def __init__(self, config: EffectiveConfig):
        super().__init__(config)
        load_dotenv()
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ProviderError("Missing OPENAI_API_KEY for OpenAI provider.")
        from openai import OpenAI

        self.client = OpenAI(api_key=api_key, timeout=self.timeout, max_retries=0)

    def embed_texts(self, texts: list[str], progress: ProgressReporter | None = None) -> list[list[float]]:
        if not texts:
            return []

        def call():
            response = self.client.embeddings.create(model=self.embedding_model, input=texts)
            return [item.embedding for item in response.data]

        if progress:
            progress(f"Embedding {len(texts)} chunks with OpenAI.")
        return self._retry("embedding", call, progress=progress)

    def generate(
        self,
        question: str,
        context: str,
        progress: ProgressReporter | None = None,
    ) -> GenerationResult:
        prompt = grounded_prompt(question, context)

        def call():
            if progress:
                progress(f"Generating answer with OpenAI model {self.generation_model}.")
            response = self.client.chat.completions.create(
                model=self.generation_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
            )
            usage = None
            if response.usage:
                usage = {
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens,
                }
            return GenerationResult(text=response.choices[0].message.content or "", token_usage=usage)

        return self._retry("generation", call)


class GeminiProvider(BaseProvider):
    name = "gemini"

    def __init__(self, config: EffectiveConfig):
        super().__init__(config)
        load_dotenv()
        api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ProviderError("Missing GOOGLE_API_KEY or GEMINI_API_KEY for Gemini provider.")
        from google import genai

        self.client = genai.Client(api_key=api_key)

    def embed_texts(self, texts: list[str], progress: ProgressReporter | None = None) -> list[list[float]]:
        if not texts:
            return []
        delay = float(self.config.get("gemini_embedding_delay_seconds"))
        retries = int(self.config.get("gemini_embedding_retries"))

        def embed_one(text: str) -> list[float]:
            result = self.client.models.embed_content(model=self.embedding_model, contents=text)
            embedding = result.embeddings[0].values
            return list(embedding)

        embeddings: list[list[float]] = []
        for index, text in enumerate(texts):
            if progress:
                progress(f"Embedding chunk {index + 1}/{len(texts)} with Gemini.")
            embeddings.append(
                self._retry(
                    f"embedding chunk {index + 1}/{len(texts)}",
                    lambda text=text: embed_one(text),
                    retries=retries,
                    progress=progress,
                )
            )
            if delay and index < len(texts) - 1:
                if progress:
                    progress(f"Waiting {delay:.1f}s before next Gemini embedding request.")
                time.sleep(delay)
        return embeddings

    def generate(
        self,
        question: str,
        context: str,
        progress: ProgressReporter | None = None,
    ) -> GenerationResult:
        prompt = grounded_prompt(question, context)

        def call():
            if progress:
                progress(f"Generating answer with Gemini model {self.generation_model}.")
            response = self.client.models.generate_content(model=self.generation_model, contents=prompt)
            return GenerationResult(text=response.text or "", token_usage=None)

        return self._retry("generation", call, progress=progress)


def provider_from_config(config: EffectiveConfig) -> BaseProvider:
    if config.provider == "openai":
        return OpenAIProvider(config)
    if config.provider == "gemini":
        return GeminiProvider(config)
    raise ProviderError(f"Unsupported provider: {config.provider}")


def grounded_prompt(question: str, context: str) -> str:
    return (
        "Answer the question using only the retrieved context below. "
        "If the context is insufficient, say that the answer cannot be found in the provided documents.\n\n"
        f"Question:\n{question}\n\nContext:\n{context}\n"
    )

"""T090: ClaudeHeadlessLLMAdapter.

Spawns `claude -p` via asyncio subprocess. Constitution Principle III:
no Anthropic SDK import, no API key read. Times out callouts at 30 s
and Q&A at 90 s with exponential-backoff retry on transient failures
(research R-8).
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass

from fh6.domain.ports.llm_port import LLMAvailability, LLMPort, LLMRequest
from fh6.infrastructure.llm.templates import load_template, render
from fh6.infrastructure.logging import get_logger

log = get_logger(__name__)


@dataclass(slots=True)
class HeadlessConfig:
    binary: str = "claude"
    callout_timeout_s: float = 30.0
    qa_timeout_s: float = 90.0
    max_retries: int = 3
    initial_backoff_s: float = 0.5


class ClaudeBinaryMissing(RuntimeError):
    """Raised when `claude --version` exits non-zero or is absent."""


class ClaudeHeadlessLLMAdapter(LLMPort):
    def __init__(self, config: HeadlessConfig | None = None) -> None:
        self._cfg = config or HeadlessConfig()

    async def availability(self) -> LLMAvailability:
        try:
            proc = await asyncio.create_subprocess_exec(
                self._cfg.binary,
                "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _stderr = await asyncio.wait_for(proc.communicate(), timeout=2.0)
        except FileNotFoundError:
            return LLMAvailability(available=False, reason="claude_cli_not_installed")
        except TimeoutError:
            return LLMAvailability(available=False, reason="claude_cli_version_check_timeout")
        if proc.returncode != 0:
            return LLMAvailability(
                available=False,
                reason=f"claude_cli_exit_{proc.returncode}",
            )
        model = stdout.decode("utf-8", errors="replace").strip() or "claude-cli"
        return LLMAvailability(available=True, reason=None, model=model)

    async def _run(self, prompt: str, *, timeout: float) -> str:  # noqa: ASYNC109
        backoff = self._cfg.initial_backoff_s
        last_err: Exception | None = None
        for _attempt in range(self._cfg.max_retries):
            try:
                proc = await asyncio.create_subprocess_exec(
                    self._cfg.binary,
                    "-p",
                    "--output-format",
                    "text",
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(prompt.encode("utf-8")),
                    timeout=timeout,
                )
                if proc.returncode == 0:
                    return stdout.decode("utf-8", errors="replace").strip()
                last_err = RuntimeError(
                    f"claude exit {proc.returncode}: {stderr.decode(errors='replace')[:200]}"
                )
            except FileNotFoundError as e:
                raise ClaudeBinaryMissing(str(e)) from e
            except TimeoutError as e:
                last_err = e
            await asyncio.sleep(backoff)
            backoff *= 2
        assert last_err is not None
        raise last_err

    async def generate_callout(self, request: LLMRequest) -> str:
        template = load_template(request.template_name)
        prompt = render(template, request.context)
        return await self._run(prompt, timeout=self._cfg.callout_timeout_s)

    def stream_answer(self, request: LLMRequest) -> AsyncIterator[str]:
        template = load_template(request.template_name)
        prompt = render(template, request.context)
        cfg = self._cfg

        async def _gen() -> AsyncIterator[str]:
            proc = await asyncio.create_subprocess_exec(
                cfg.binary,
                "-p",
                "--output-format",
                "stream-json",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            assert proc.stdin is not None and proc.stdout is not None
            proc.stdin.write(prompt.encode("utf-8"))
            await proc.stdin.drain()
            proc.stdin.close()
            try:
                while True:
                    line = await asyncio.wait_for(proc.stdout.readline(), timeout=cfg.qa_timeout_s)
                    if not line:
                        break
                    yield line.decode("utf-8", errors="replace")
            finally:
                if proc.returncode is None:
                    proc.terminate()
                await proc.wait()

        return _gen()

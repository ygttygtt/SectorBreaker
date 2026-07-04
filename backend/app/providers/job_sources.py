"""Job-source provider adapters for talent-demand intelligence."""

from __future__ import annotations

import asyncio
import json
import os
import shlex
import shutil
from dataclasses import asdict
from typing import Any

from backend.app.providers.interfaces import (
    JobPostingSource,
    JobSourceQuery,
    JobSourceStatus,
)


class DisabledJobSourceProvider:
    def __init__(self, message: str = "未启用招聘信源 Provider。") -> None:
        self.message = message

    async def status(self) -> JobSourceStatus:
        return JobSourceStatus(
            provider="disabled",
            configured=False,
            available=False,
            message=self.message,
            diagnostics=["设置 JOB_SOURCE_PROVIDER=boss_agent_cli 并安装本地 Boss CLI 后可启用。"],
        )

    async def search_jobs(self, query: JobSourceQuery) -> list[JobPostingSource]:
        return []


class BossAgentCliProvider:
    """Adapter for local Boss-compatible CLI tools that can emit JSON jobs."""

    def __init__(
        self,
        *,
        command: str = "boss",
        args_template: str | None = None,
        timeout_seconds: int = 45,
    ) -> None:
        self.command = command.strip() or "boss"
        self.args_template = args_template
        self.timeout_seconds = max(5, timeout_seconds)

    async def status(self) -> JobSourceStatus:
        command_parts = self._split_command(self.command)
        executable = command_parts[0] if command_parts else self.command
        available = bool(shutil.which(executable) or os.path.exists(executable))
        return JobSourceStatus(
            provider="boss_agent_cli",
            configured=True,
            available=available,
            message=(
                f"Boss CLI 可用：{self.command}"
                if available
                else f"未找到 Boss CLI 命令：{self.command}"
            ),
            diagnostics=[] if available else [
                "请先安装 boss-agent-cli 或把 BOSS_AGENT_CLI_COMMAND 指向可执行文件。",
                "如果该工具命令参数不同，可配置 BOSS_AGENT_CLI_ARGS_TEMPLATE。",
            ],
        )

    async def search_jobs(self, query: JobSourceQuery) -> list[JobPostingSource]:
        status = await self.status()
        if not status.available:
            return []

        argv = self._build_argv(query)
        try:
            process = await asyncio.create_subprocess_exec(
                *argv,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=self.timeout_seconds)
        except (OSError, TimeoutError, asyncio.TimeoutError):
            return []

        if process.returncode != 0:
            return []

        text = _decode_cli_output(stdout).strip()
        if not text and stderr:
            text = _decode_cli_output(stderr).strip()
        return self._parse_jobs(text)

    def _build_argv(self, query: JobSourceQuery) -> list[str]:
        if not self.args_template:
            argv = self._split_command(self.command)
            argv.extend(["search", "--query", query.keyword, "--limit", str(query.limit), "--json"])
            if query.city:
                argv.extend(["--city", query.city])
            return argv
        city = query.city or ""
        rendered = self.args_template.format(
            command=self.command,
            keyword=query.keyword,
            query=query.keyword,
            city=city,
            limit=query.limit,
            filters=json.dumps(query.filters or {}, ensure_ascii=False),
        )
        return self._split_command(rendered)

    @staticmethod
    def _split_command(command: str) -> list[str]:
        return shlex.split(command, posix=os.name != "nt")

    def _parse_jobs(self, text: str) -> list[JobPostingSource]:
        if not text:
            return []
        payloads = self._load_payloads(text)
        jobs: list[JobPostingSource] = []
        for payload in payloads:
            if not isinstance(payload, dict):
                continue
            job = self._payload_to_job(payload)
            if job.title:
                jobs.append(job)
        return jobs

    def _load_payloads(self, text: str) -> list[dict[str, Any]]:
        try:
            loaded = json.loads(text)
        except json.JSONDecodeError:
            return self._load_jsonl(text)
        if isinstance(loaded, list):
            return [item for item in loaded if isinstance(item, dict)]
        if isinstance(loaded, dict):
            for key in ("jobs", "items", "results", "data"):
                value = loaded.get(key)
                if isinstance(value, list):
                    return [item for item in value if isinstance(item, dict)]
            return [loaded]
        return []

    @staticmethod
    def _load_jsonl(text: str) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                loaded = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(loaded, dict):
                rows.append(loaded)
        return rows

    def _payload_to_job(self, payload: dict[str, Any]) -> JobPostingSource:
        skills = payload.get("skills") or payload.get("tags") or payload.get("skill_tags")
        if isinstance(skills, str):
            skills = [item.strip() for item in skills.replace("，", ",").split(",") if item.strip()]
        if not isinstance(skills, list):
            skills = []
        job = JobPostingSource(
            title=self._first_text(payload, "title", "job_title", "name", "position", "positionName"),
            company=self._first_text(payload, "company", "company_name", "brandName", "companyName"),
            location=self._first_text(payload, "location", "city", "address", "area", "workCity"),
            salary_text=self._first_text(payload, "salary", "salary_text", "salaryDesc", "pay"),
            experience_text=self._first_text(payload, "experience", "experience_text", "jobExperience", "exp"),
            education_text=self._first_text(payload, "education", "education_text", "jobDegree", "degree"),
            description=self._first_text(payload, "description", "desc", "job_desc", "detail", "postDescription"),
            skills=[str(item).strip() for item in skills if str(item).strip()],
            url=self._first_text(payload, "url", "job_url", "href", "link"),
            source_provider="boss_agent_cli",
            raw_payload=payload,
        )
        return job

    @staticmethod
    def _first_text(payload: dict[str, Any], *keys: str) -> str | None:
        for key in keys:
            value = payload.get(key)
            if value is None:
                continue
            text = str(value).strip()
            if text:
                return text
        return None


def job_source_status_to_dict(status: JobSourceStatus) -> dict[str, Any]:
    return asdict(status)


def _decode_cli_output(payload: bytes) -> str:
    for encoding in ("utf-8", "gb18030"):
        try:
            return payload.decode(encoding)
        except UnicodeDecodeError:
            continue
    return payload.decode("utf-8", errors="replace")

"""
github_connector.py — GitHub MCP Connector for Nerve Layer

Recebe webhooks/eventos do GitHub MCP e emite eventos para o Nerve bus.

Responsabilidades:
  - on_pr_merged(): recebe webhook do GitHub, emite pr.merged
  - on_push(): recebe push event, emite code.pushed
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import bus.event_bus as event_bus


class GitHubConnector:
    """Conector MCP para GitHub → Nerve event bus."""

    def __init__(self, event_bus_module: Any = None):
        """
        Inicializa o conector GitHub.

        Args:
            event_bus_module: módulo bus.event_bus (ou mock para testes)
        """
        self.event_bus = event_bus_module or event_bus

    def on_pr_merged(self, github_payload: dict) -> str:
        """
        Recebe webhook do GitHub MCP para PR merged.

        Args:
            github_payload: dict com campos:
              - pull_request_id: ID único do PR
              - pull_request_number: número do PR (ex: 123)
              - repository_name: nome completo do repo (ex: "owner/repo")
              - merged_at: timestamp do merge
              - merged_by: login do usuário que fez merge
              - branch: nome da branch do PR
              - target_branch: branch alvo (ex: "main")
              - title: título do PR
              - commit_count: número de commits
              - url: URL do PR

        Returns:
            event_id gerado pelo EventBus
        """
        # Mapear payload GitHub para schema pr.merged
        event_payload = {
            "pull_request_id": github_payload.get("pull_request_id"),
            "pull_request_number": github_payload.get("pull_request_number"),
            "repository_name": github_payload.get("repository_name"),
            "merged_at": github_payload.get("merged_at", datetime.now(timezone.utc).isoformat()),
            "merged_by": github_payload.get("merged_by"),
        }

        # Adicionar campos opcionais
        if "branch" in github_payload:
            event_payload["branch"] = github_payload["branch"]

        if "target_branch" in github_payload:
            event_payload["target_branch"] = github_payload["target_branch"]

        if "title" in github_payload:
            event_payload["title"] = github_payload["title"]

        if "commit_count" in github_payload:
            event_payload["commit_count"] = github_payload["commit_count"]

        if "url" in github_payload:
            event_payload["url"] = github_payload["url"]

        # Criar e emitir evento
        event = {
            "name": "pr.merged",
            "source": "github",
            "payload": event_payload,
        }

        return self.event_bus.emit(event)

    def on_push(self, github_payload: dict) -> str:
        """
        Recebe webhook do GitHub MCP para push de commits.

        Args:
            github_payload: dict com campos:
              - repository_name: nome completo do repo
              - branch: nome da branch
              - pushed_at: timestamp do push
              - commit_count: número de commits
              - pushed_by: login do usuário
              - commits: lista de SHAs
              - url: URL da branch
              - is_default_branch: bool, se é main/master

        Returns:
            event_id gerado pelo EventBus
        """
        # Mapear payload GitHub para schema code.pushed
        event_payload = {
            "repository_name": github_payload.get("repository_name"),
            "branch": github_payload.get("branch"),
            "pushed_at": github_payload.get("pushed_at", datetime.now(timezone.utc).isoformat()),
            "commit_count": github_payload.get("commit_count", 1),
        }

        # Adicionar campos opcionais
        if "pushed_by" in github_payload:
            event_payload["pushed_by"] = github_payload["pushed_by"]

        if "commits" in github_payload:
            event_payload["commits"] = github_payload["commits"]

        if "url" in github_payload:
            event_payload["url"] = github_payload["url"]

        if "is_default_branch" in github_payload:
            event_payload["is_default_branch"] = github_payload["is_default_branch"]

        # Criar e emitir evento
        event = {
            "name": "code.pushed",
            "source": "github",
            "payload": event_payload,
        }

        return self.event_bus.emit(event)

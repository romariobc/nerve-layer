"""
linear_connector.py — Linear MCP Connector for Nerve Layer

Recebe webhooks/eventos do Linear MCP e emite eventos quando status muda.

Responsabilidades:
  - on_issue_status_changed(): recebe webhook do Linear, emite project.status.changed
  - query_project_status(): consulta estado do projeto (sem emitir evento)
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import bus.event_bus as event_bus


class LinearConnector:
    """Conector MCP para Linear → Nerve event bus."""

    def __init__(self, event_bus_module: Any = None, api_key: str = ""):
        """
        Inicializa o conector Linear.

        Args:
            event_bus_module: módulo bus.event_bus (ou mock para testes)
            api_key: chave de API do Linear (para chamadas futuras)
        """
        self.event_bus = event_bus_module or event_bus
        self.api_key = api_key

    def on_issue_status_changed(self, linear_payload: dict) -> str:
        """
        Recebe webhook do Linear MCP para mudança de status de issue/projeto.

        Args:
            linear_payload: dict com campos:
              - project_id: ID do projeto no Linear
              - project_name: nome do projeto
              - issue_count: número de issues no projeto
              - status: estado agregado ('backlog', 'todo', 'in_progress', 'in_review', 'done')
              - team_id: ID do time no Linear
              - url: URL direto para o projeto

        Returns:
            event_id gerado pelo EventBus
        """
        # Mapear payload Linear para schema project.status.changed
        event_payload = {
            "project_id": linear_payload.get("project_id"),
            "project_name": linear_payload.get("project_name"),
            "issue_count": linear_payload.get("issue_count", 0),
            "status": linear_payload.get("status"),
        }

        # Adicionar campos opcionais se presentes
        if "updated_at" in linear_payload:
            event_payload["updated_at"] = linear_payload["updated_at"]
        else:
            event_payload["updated_at"] = datetime.now(timezone.utc).isoformat()

        if "team_id" in linear_payload:
            event_payload["team_id"] = linear_payload["team_id"]

        if "url" in linear_payload:
            event_payload["url"] = linear_payload["url"]

        # Criar e emitir evento
        event = {
            "name": "project.status.changed",
            "source": "linear",
            "payload": event_payload,
        }

        return self.event_bus.emit(event)

    def query_project_status(self, project_id: str) -> dict:
        """
        Consulta o estado atual de um projeto no Linear (sem emitir evento).

        Args:
            project_id: ID do projeto no Linear

        Returns:
            dict com estado do projeto:
              {
                "project_id": str,
                "project_name": str,
                "issue_count": int,
                "status": str,
                "url": str
              }

        Nota: Esta é uma operação de consulta que não emite evento.
        Em produção, isso chamaria a Linear API via autenticação.
        """
        # Mock implementation — em produção chamaria Linear API
        return {
            "project_id": project_id,
            "project_name": "Unknown Project",
            "issue_count": 0,
            "status": "backlog",
            "url": f"https://linear.app/projects/{project_id}",
            "_mocked": True,
        }

"""
figma_connector.py — Figma MCP Connector for Nerve Layer

Recebe webhooks/eventos do Figma MCP (bidirecional, disponível desde mar 2026)
e emite eventos design.component.changed no Nerve event bus.

Responsabilidades:
  - on_component_changed(): recebe mudança de componente, valida e emite
  - on_variable_changed(): recebe mudança de token/variável, emite como component
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import bus.event_bus as event_bus


class FigmaConnector:
    """Conector MCP para Figma → Nerve event bus."""

    def __init__(self, event_bus_module: Any = None):
        """
        Inicializa o conector Figma.

        Args:
            event_bus_module: módulo bus.event_bus (ou mock para testes)
        """
        self.event_bus = event_bus_module or event_bus

    def on_component_changed(self, figma_payload: dict) -> str:
        """
        Recebe webhook do Figma MCP para mudança de componente.

        Args:
            figma_payload: dict com campos:
              - component_id: ID do componente no Figma
              - file_key: chave do arquivo Figma
              - component_name: nome do componente (ex: "Button/Primary")
              - change_type: 'created', 'modified', 'deleted', 'renamed'
              - project_slug: slug do projeto
              - breaking: bool, indica se é mudança breaking
              - affected_tokens: list de design tokens afetados
              - figma_url: URL direto para o componente

        Returns:
            event_id gerado pelo EventBus
        """
        # Mapear payload Figma para schema design.component.changed
        event_payload = {
            "component_id": figma_payload.get("component_id"),
            "component_name": figma_payload.get("component_name"),
            "project_slug": figma_payload.get("project_slug"),
            "changed_at": figma_payload.get("changed_at", datetime.now(timezone.utc).isoformat()),
            "change_type": figma_payload.get("change_type"),
        }

        # Adicionar campos opcionais se presentes
        if "affected_tokens" in figma_payload:
            event_payload["affected_tokens"] = figma_payload["affected_tokens"]

        if "figma_url" in figma_payload:
            event_payload["figma_url"] = figma_payload["figma_url"]

        if "breaking" in figma_payload:
            event_payload["breaking"] = figma_payload["breaking"]

        # Criar e emitir evento
        event = {
            "name": "design.component.changed",
            "source": "figma",
            "payload": event_payload,
        }

        return self.event_bus.emit(event)

    def on_variable_changed(self, figma_payload: dict) -> str:
        """
        Recebe webhook do Figma MCP para mudança de token/variável de design.

        Args:
            figma_payload: dict com campos:
              - variable_id: ID da variável no Figma
              - variable_name: nome da variável (ex: "color/primary")
              - change_type: 'created', 'modified', 'deleted'
              - project_slug: slug do projeto
              - figma_url: URL direto para a variável

        Returns:
            event_id gerado pelo EventBus
        """
        # Mapear variável como um "componente virtual" do tipo variable
        event_payload = {
            "component_id": figma_payload.get("variable_id"),
            "component_name": figma_payload.get("variable_name"),
            "project_slug": figma_payload.get("project_slug"),
            "changed_at": figma_payload.get("changed_at", datetime.now(timezone.utc).isoformat()),
            "change_type": figma_payload.get("change_type"),
        }

        if "figma_url" in figma_payload:
            event_payload["figma_url"] = figma_payload["figma_url"]

        # Marcar como mudança de token (breaking se for modificação de var importante)
        event_payload["breaking"] = figma_payload.get("breaking", False)

        event = {
            "name": "design.component.changed",
            "source": "figma",
            "payload": event_payload,
        }

        return self.event_bus.emit(event)

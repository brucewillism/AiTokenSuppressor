#!/usr/bin/env python3
"""Valida docker-compose.prod.yml e, se existir, a saída de `docker compose config`."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docker-compose.prod.yml"

REQUIRED_PORTS = {
    "redis": "127.0.0.1:8106:6379",
    "api": "127.0.0.1:8105:8000",
    "flower": "127.0.0.1:8104:5556",
    "litellm": "127.0.0.1:8101:4001",
    "frontend": "127.0.0.1:8100:80",
    "prometheus": "127.0.0.1:8102:9090",
    "grafana": "127.0.0.1:8103:3000",
}


def fail(message: str) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(1)


def image_uses_latest(image: str) -> bool:
    without_digest = image.split("@", 1)[0]
    tag = without_digest.rsplit(":", 1)[-1] if ":" in without_digest else ""
    return tag == "latest" or tag.endswith("-latest")


def check_source(data: dict) -> None:
    if data.get("name") != "ai-token-suppressor":
        fail("o projeto Compose precisa se chamar ai-token-suppressor")

    networks = data.get("networks") or {}
    network = networks.get("ai-token-suppressor")
    if not isinstance(network, dict):
        fail("falta a rede ai-token-suppressor")
    if network.get("name") != "ai-token-suppressor" or network.get("driver") != "bridge":
        fail("a rede precisa ter name ai-token-suppressor e driver bridge")

    services = data.get("services") or {}
    if not services:
        fail("nenhum serviço no compose")

    for name, service in services.items():
        if service.get("restart") != "unless-stopped":
            fail(f"{name}: restart precisa ser unless-stopped")
        health = service.get("healthcheck") or {}
        if not health.get("test"):
            fail(f"{name}: healthcheck ausente")
        env_file = service.get("env_file") or []
        if isinstance(env_file, str):
            env_file = [env_file]
        normalized = []
        for item in env_file:
            if isinstance(item, dict):
                normalized.append(item.get("path"))
            else:
                normalized.append(item)
        if ".env" not in normalized:
            fail(f"{name}: env_file precisa incluir .env")
        image = service.get("image")
        if not isinstance(image, str) or not image:
            fail(f"{name}: image ausente")
        if image_uses_latest(image):
            fail(f"{name}: tag latest proibida em {image}")
        ports = service.get("ports") or []
        expected = REQUIRED_PORTS.get(name)
        if expected is None:
            if ports:
                fail(f"{name}: não deve publicar porta no host")
            continue
        if ports != [expected]:
            fail(f"{name}: porta publicada precisa ser {expected}")
        if not expected.startswith("127.0.0.1:"):
            fail(f"{name}: bind fora do loopback")


def check_rendered(data: dict) -> None:
    def walk(node: object) -> None:
        if isinstance(node, dict):
            if "published" in node and "target" in node:
                if node.get("host_ip") != "127.0.0.1":
                    fail(f"porta publicada fora do loopback: {node.get('host_ip')}")
            host_ip = node.get("host_ip")
            if host_ip not in (None, "", "127.0.0.1"):
                fail(f"host_ip fora do loopback: {host_ip}")
            image = node.get("image")
            if isinstance(image, str) and image_uses_latest(image):
                fail(f"tag latest no compose renderizado: {image}")
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)
        elif isinstance(node, str) and (
            node.startswith("0.0.0.0:") or node.startswith("[::]:")
        ):
            fail(f"porta publicada fora do loopback: {node}")

    walk(data)
    services = data.get("services") or {}
    for name, service in services.items():
        if service.get("restart") != "unless-stopped":
            fail(f"renderizado {name}: restart inesperado")
        if not (service.get("healthcheck") or {}).get("test"):
            fail(f"renderizado {name}: healthcheck ausente")


def load(path: Path) -> dict:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        fail(f"{path} não é um mapeamento YAML")
    return raw


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rendered", type=Path)
    args = parser.parse_args()
    check_source(load(SOURCE))
    if args.rendered:
        check_rendered(load(args.rendered))
    print("docker-compose.prod.yml ok")


if __name__ == "__main__":
    main()

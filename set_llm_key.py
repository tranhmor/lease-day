#!/usr/bin/env python3
"""Safely enter LLM_API_KEY in terminal (hidden input, not saved to shell history),
write it into rental_game/.env (chmod 600), and optionally run diagnose --ping.

Usage:
    python3 set_llm_key.py
    python3 set_llm_key.py --model deepseek-v4.1-flash
"""
import argparse
import getpass
import os
from pathlib import Path
import subprocess
import sys

ENV_PATH = Path(__file__).resolve().parent / ".env"


def _upsert_env_line(lines: list, key: str, value: str) -> list:
    out = []
    replaced = False
    prefix = f"{key}="
    for ln in lines:
        if not replaced and ln.lstrip() and not ln.lstrip().startswith("#") and ln.strip().startswith(prefix):
            out.append(f"{key}={value}")
            replaced = True
        else:
            out.append(ln)
    if not replaced:
        out.append(f"{key}={value}")
    return out


def _mask(secret: str) -> str:
    if len(secret) <= 8:
        return "*" * len(secret)
    return f"{secret[:4]}...{secret[-4:]} (len={len(secret)})"


def main() -> int:
    ap = argparse.ArgumentParser(description="Safely set LLM_API_KEY in rental_game/.env")
    ap.add_argument("--model", type=str, default=None, help="Optional: also switch LLM_MODEL in .env")
    ap.add_argument("--no-ping", action="store_true", help="Only save key, do not prompt to run diagnose --ping")
    args = ap.parse_args()

    if not ENV_PATH.exists():
        print(f"未找到 {ENV_PATH}，将新建。")
        lines = [
            "LLM_BASE_URL=https://api.wokey.ai/v1",
            "LLM_MODEL=hy4-flash",
            "LLM_API_KEY=",
            "LLM_USE_PROXY=1",
            "LLM_TIMEOUT=90",
        ]
    else:
        lines = ENV_PATH.read_text(encoding="utf-8").splitlines()

    if args.model:
        lines = _upsert_env_line(lines, "LLM_MODEL", args.model.strip())

    try:
        raw_key = getpass.getpass("请粘贴 Wokey API Key（输入隐藏，不留终端历史，回车确认）: ")
    except (EOFError, KeyboardInterrupt):
        print("\n已取消。")
        return 1

    api_key = raw_key.strip().strip('"').strip("'")
    if not api_key:
        print("输入为空，未修改 .env。")
        return 1

    lines = _upsert_env_line(lines, "LLM_API_KEY", api_key)
    ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.chmod(ENV_PATH, 0o600)

    # Show active non-secret config
    active = {}
    for ln in lines:
        s = ln.strip()
        if s and not s.startswith("#") and "=" in s:
            k, v = s.split("=", 1)
            active[k.strip()] = v.strip()

    print(f"\n已写入 {ENV_PATH} (权限 600):")
    print(f"  LLM_BASE_URL = {active.get('LLM_BASE_URL', '')}")
    print(f"  LLM_MODEL    = {active.get('LLM_MODEL', '')}")
    print(f"  LLM_API_KEY  = {_mask(api_key)}")

    if args.no_ping:
        return 0

    try:
        ans = input("\n是否立即执行连通性测试 (diagnose --ping，发 2 条真实请求)? [Y/n]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return 0

    if ans in ("", "y", "yes"):
        print()
        proc = subprocess.run(
            [sys.executable, "-m", "prototype_v07.diagnose", "--ping"],
            cwd=str(ENV_PATH.parent),
        )
        return proc.returncode
    return 0


if __name__ == "__main__":
    sys.exit(main())

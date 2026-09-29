"""Архив готовых разборов для переноса на другой сервер.

По умолчанию переносит только карточки, кандидатов и манифесты.
--include-ledger добавляет журнал расходов: используйте при миграции своего
сервера, а не при подготовке примера для другого пользователя.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import tarfile
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNS = ROOT / "radar-runs"
NEEDED = ("manifest.json", "candidates.jsonl", "cards.json")


def cards_version() -> str:
    text = (ROOT / "radar" / "server.py").read_text(encoding="utf-8")
    found = re.search(r'^CARDS_VERSION\s*=\s*"([^"]+)"', text, re.MULTILINE)
    if not found:
        sys.exit("не нашёл CARDS_VERSION в radar/server.py")
    return found.group(1)


def usable_runs(version: str) -> list[tuple[Path, dict]]:
    out = []
    for run in sorted(RUNS.glob("*")):
        if not all((run / name).exists() for name in NEEDED):
            continue
        try:
            cards = json.loads((run / "cards.json").read_text(encoding="utf-8"))
            manifest = json.loads((run / "manifest.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if cards.get("version") != version or manifest.get("mode") != "live":
            continue
        out.append((run, {"query": manifest.get("query", ""), "area": manifest.get("area", ""),
                          "cost": manifest.get("cost_rub", 0),
                          "trends": len(cards.get("trends") or [])}))
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true", help="показать состав без упаковки")
    ap.add_argument("--out", default=str(Path(__file__).resolve().parent / "runs-seed.tar.gz"))
    ap.add_argument("--include-ledger", action="store_true")
    args = ap.parse_args()

    version = cards_version()
    runs = usable_runs(version)
    if not runs:
        sys.exit(f"нет прогонов с версией карточек {version}: на сервере нечего показывать")

    print(f"версия карточек: {version}")
    for run, info in runs:
        print(f"  {run.name:34} {info['trends']:2} позиций  {info['cost']:6.2f} ₽  "
              f"{info['area']}: {info['query'][:44]}")
    if args.list:
        return

    ledger = RUNS / "ledger.json"
    with tempfile.TemporaryDirectory() as tmp:
        stage = Path(tmp) / "radar-runs"
        for run, _ in runs:
            target = stage / run.name
            target.mkdir(parents=True)
            for name in NEEDED:
                shutil.copy2(run / name, target / name)
        if args.include_ledger and ledger.exists():
            shutil.copy2(ledger, stage / "ledger.json")
            print("учёт расходов: ledger.json включён")
        else:
            print("Журнал расходов не включён; при миграции перенесите его отдельно.")
        out = Path(args.out)
        with tarfile.open(out, "w:gz") as tar:
            tar.add(stage, arcname="radar-runs")
    size = out.stat().st_size / 1024
    print(f"готово: {out} ({size:.0f} КБ)")
    print("Архив содержит radar-runs/. Не распаковывайте его поверх действующего состояния без резервной копии.")


if __name__ == "__main__":
    main()

"""Учёт расходов на поиск и модель: резерв до запроса, уточнение после ответа.

Новый журнал начинается с нулевых лимитов. Бюджет задаётся командой topup.
Существующий журнал сохраняет остатки и историю; доступ защищён файловой блокировкой.
"""
from __future__ import annotations

import contextlib
import fcntl
import json
import math
import os
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .config import Prices, RUNS_DIR  # noqa: F401  (Prices реэкспортируется)

VERSION = "ledger/1"
DEFAULT_PATH = RUNS_DIR / "ledger.json"
# Начальные лимиты не дают разрешения на платные вызовы.
SEED = {"search_remaining_rub": 0.0, "llm_remaining_rub": 0.0}
KEEP_CALLS = 2000


class LimitReached(RuntimeError):
    """Остаток исчерпан. Не ошибка выполнения, а граница разрешения пользователя."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _atomic_write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


@dataclass
class Reservation:
    kind: str                 # search | llm
    amount: float
    at: str
    note: str = ""
    settled: bool = False
    actual: float | None = None
    reservation_id: str = ""


@dataclass
class Ledger:
    """Остатки и история. Один файл — один источник правды о расходах."""

    path: Path = DEFAULT_PATH
    _lock: threading.RLock = field(default_factory=threading.RLock, repr=False)

    @contextlib.contextmanager
    def _file(self):
        """Блокировка файла на время чтения-записи: процессов может быть несколько."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        guard = self.path.with_suffix(".lock")
        with guard.open("a+") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            if self.path.exists():
                try:
                    data = json.loads(self.path.read_text(encoding="utf-8"))
                except json.JSONDecodeError as exc:
                    raise RuntimeError("Журнал расходов повреждён; вызовы заблокированы. "
                                       "Восстановите журнал, не создавая новый бюджет.") from exc
                if not isinstance(data, dict):
                    raise RuntimeError("Некорректный журнал расходов; бюджет не восстановлен.")
                amounts = [data.get("search_remaining_rub"), data.get("llm_remaining_rub")]
                spent = data.get("spent")
                if not isinstance(spent, dict):
                    raise RuntimeError("В журнале отсутствуют расходы; вызовы заблокированы.")
                amounts += [spent.get("search"), spent.get("llm")]
                if any(type(v) not in (int, float) or not math.isfinite(v) or v < 0
                       for v in amounts):
                    raise RuntimeError("Некорректные суммы в журнале; вызовы заблокированы.")
            else:
                data = {"version": VERSION, "created": _now(), "calls": [],
                        "calls_dropped": 0, "spent": {"search": 0.0, "llm": 0.0}, **SEED}
            yield data
            _atomic_write(self.path, data)

    def remaining(self) -> dict:
        with self._lock, self._file() as data:
            return {"search": round(data["search_remaining_rub"], 4),
                    "llm": round(data["llm_remaining_rub"], 4),
                    "spent": {k: round(v, 4) for k, v in data["spent"].items()}}

    def reserve(self, amount: float, kind: str, note: str = "") -> Reservation:
        """Списывает худший случай до обращения к провайдеру.

        Резерв, а не постфактум: при обрыве соединения деньги уже потрачены провайдером,
        и учёт, который пишет только успешные ответы, занижает расход.
        """
        if kind not in ("search", "llm"):
            raise ValueError(f"неизвестная корзина расходов: {kind}")
        if type(amount) not in (int, float) or not math.isfinite(amount) or amount < 0:
            raise ValueError("резерв должен быть конечным неотрицательным числом")
        key = f"{kind}_remaining_rub"
        with self._lock, self._file() as data:
            campaign = data.get("active_campaign")
            if campaign:
                used = data["spent"][kind] - campaign["opening_spent"][kind]
                if used + amount > campaign["limits"][kind] + 1e-9:
                    raise LimitReached(f"лимит текущего этапа {kind} исчерпан; "
                                       "старые остатки не расходуются сверх нового лимита")
            if amount > data[key] + 1e-9:
                raise LimitReached(
                    f"остаток корзины «{kind}» {data[key]:.2f} ₽ меньше требуемых "
                    f"{amount:.2f} ₽; корзины раздельны, переносить нельзя без разрешения")
            data[key] -= amount
            data["spent"][kind] += amount
            record = {"id": uuid.uuid4().hex, "kind": kind, "reserved": round(amount, 6), "actual": None,
                      "at": _now(), "note": note[:120], "status": "reserved"}
            data["calls"].append(record)
            # Active reservations must remain addressable until settlement.
            if len(data["calls"]) > KEEP_CALLS:
                removable = [r for r in data["calls"][:-KEEP_CALLS] if r["status"] != "reserved"]
                remove_ids = {id(r) for r in removable}
                data["calls_dropped"] += len(removable)
                data["calls"] = [r for r in data["calls"] if id(r) not in remove_ids]
            return Reservation(kind=kind, amount=amount, at=record["at"], note=note,
                               reservation_id=record["id"])

    def settle(self, reservation: Reservation, actual: float | None) -> None:
        """Возвращает разницу. `actual=None` — результат неизвестен, резерв остаётся."""
        if reservation.settled:
            return
        if actual is not None and (type(actual) not in (int, float) or not math.isfinite(actual) or actual < 0):
            raise ValueError("стоимость должна быть конечным неотрицательным числом")
        key = f"{reservation.kind}_remaining_rub"
        with self._lock, self._file() as data:
            record = next((r for r in data["calls"] if r.get("id") == reservation.reservation_id), None)
            if not record:
                raise RuntimeError("резерв не найден; возврат средств запрещён")
            if record["status"] == "reserved":
                refund = reservation.amount - actual if actual is not None else 0.0
                data[key] += refund
                data["spent"][reservation.kind] -= refund
                record.update(actual=round(actual, 6) if actual is not None else None,
                              status="settled" if actual is not None else "unknown")
        reservation.settled = True
        reservation.actual = actual

    def authorize(self, authorization_id: str, search: float, llm: float, reason: str) -> dict:
        """Record an explicit user grant once; cap this work cycle separately from old funds."""
        limits = {"search": search, "llm": llm}
        # Ноль допустим: пополняют обычно одну корзину (29.09.2026 кончилась корзина
        # модели при остатке поиска 537 ₽). Хотя бы одна сумма обязана быть больше нуля,
        # иначе это не разрешение, а пустая запись.
        if not authorization_id or any(type(v) not in (int, float) or not math.isfinite(v) or v < 0
                                       for v in limits.values()):
            raise ValueError("некорректное разрешение бюджета")
        if not any(v > 0 for v in limits.values()):
            raise ValueError("разрешение без денег: хотя бы одна корзина должна быть больше нуля")
        with self._lock, self._file() as data:
            grants = data.setdefault("authorizations", [])
            existing = next((g for g in grants if g["id"] == authorization_id), None)
            if existing:
                if existing["limits"] != limits:
                    raise ValueError("идентификатор разрешения уже использован с другими суммами")
                return existing
            grant = {"id": authorization_id, "at": _now(), "limits": limits,
                     "reason": reason, "opening_spent": dict(data["spent"])}
            for kind, amount in limits.items():
                data[f"{kind}_remaining_rub"] += amount
            grants.append(grant)
            data["active_campaign"] = dict(grant)
        return grant

    @contextlib.contextmanager
    def paid(self, amount: float, kind: str, note: str = ""):
        """Резерв на вход, возврат разницы на выход. Исключение сохраняет резерв."""
        res = self.reserve(amount, kind, note)
        holder: dict = {"actual": None}
        try:
            yield holder
        finally:
            self.settle(res, holder.get("actual"))


_shared: Ledger | None = None


def shared() -> Ledger:
    """Один учёт на процесс: сервис и CLI не должны вести разные книги."""
    global _shared
    if _shared is None:
        _shared = Ledger()
    return _shared


def llm_cost(input_tokens: int, output_tokens: int, prices: Prices | None = None) -> float:
    p = prices or Prices()
    return (input_tokens / 1e6 * p.llm_input_rub_per_mtok
            + output_tokens / 1e6 * p.llm_output_rub_per_mtok)


def _cli(argv: list[str] | None = None) -> int:  # pragma: no cover - тонкая обёртка
    """Состояние и пополнение корзин из командной строки.

    Пополнение — не бухгалтерская формальность: публичный сервис отказывает в живом
    прогоне, если остатка не хватает на полный, и после пополнения счёта у провайдера
    он обязан узнать о новых деньгах отсюда.

        python -m radar.ledger status
        python -m radar.ledger topup --id 2026-09-29-llm300 --llm 300 --reason "пополнение под MVP"
    """
    import argparse

    ap = argparse.ArgumentParser(prog="radar.ledger")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status", help="остаток корзин и расход")
    top = sub.add_parser("topup", help="записать пополнение корзины")
    top.add_argument("--id", required=True, help="идентификатор разрешения: повтор не удвоит сумму")
    top.add_argument("--search", type=float, default=0.0, help="рубли в корзину поиска")
    top.add_argument("--llm", type=float, default=0.0, help="рубли в корзину модели")
    top.add_argument("--reason", default="", help="зачем пополнено")
    args = ap.parse_args(argv)

    ledger = Ledger()
    if args.cmd == "status":
        left = ledger.remaining()
        print(f"поиск: {left['search']:.2f} ₽   модель: {left['llm']:.2f} ₽")
        print(f"потрачено — поиск: {left['spent']['search']:.2f} ₽, "
              f"модель: {left['spent']['llm']:.2f} ₽")
        return 0

    try:
        grant = ledger.authorize(args.id, args.search, args.llm, args.reason or "пополнение")
    except ValueError as exc:
        print(f"отказ: {exc}")
        return 2
    left = ledger.remaining()
    print(f"разрешение {grant['id']} от {grant['at']}: "
          f"поиск +{grant['limits']['search']:.2f} ₽, модель +{grant['limits']['llm']:.2f} ₽")
    print(f"теперь поиск: {left['search']:.2f} ₽, модель: {left['llm']:.2f} ₽")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_cli())

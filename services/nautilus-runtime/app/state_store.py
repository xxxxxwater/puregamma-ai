from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from threading import RLock


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class RuntimeStateStore:
    def __init__(self, path: str):
        self.path = path
        self._lock = RLock()
        self._init()

    def _connect(self):
        connection = sqlite3.connect(self.path, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        return connection

    def _init(self) -> None:
        with self._connect() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS commands (
              id TEXT PRIMARY KEY, idempotency_key TEXT NOT NULL UNIQUE, command_type TEXT NOT NULL,
              payload TEXT NOT NULL, status TEXT NOT NULL, result TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS runs (
              id TEXT PRIMARY KEY, strategy_id TEXT NOT NULL, strategy_version INTEGER NOT NULL,
              account_id TEXT, mode TEXT NOT NULL, status TEXT NOT NULL, payload TEXT NOT NULL,
              started_at TEXT, stopped_at TEXT, updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS orders (
              client_order_id TEXT NOT NULL, sequence INTEGER NOT NULL, idempotency_key TEXT NOT NULL UNIQUE,
              run_id TEXT, account_id TEXT NOT NULL, state TEXT NOT NULL, payload TEXT NOT NULL,
              filled_quantity REAL NOT NULL DEFAULT 0, remaining_quantity REAL NOT NULL,
              exchange_order_id TEXT, error TEXT, created_at TEXT NOT NULL,
              PRIMARY KEY(client_order_id, sequence)
            );
            CREATE TABLE IF NOT EXISTS events (
              id INTEGER PRIMARY KEY AUTOINCREMENT, event_type TEXT NOT NULL, aggregate_id TEXT NOT NULL,
              payload TEXT NOT NULL, created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS market_quotes (
              asset TEXT PRIMARY KEY, symbol TEXT NOT NULL, price REAL NOT NULL,
              provider TEXT NOT NULL, source_timestamp TEXT NOT NULL, payload TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS paper_positions (
              account_id TEXT NOT NULL, instrument TEXT NOT NULL, quantity REAL NOT NULL,
              average_price REAL NOT NULL, realized_pnl REAL NOT NULL, payload TEXT NOT NULL,
              updated_at TEXT NOT NULL, PRIMARY KEY(account_id, instrument)
            );
            """)

    def command(
        self, command_id: str, idempotency_key: str, command_type: str, payload: dict
    ) -> tuple[dict, bool]:
        with self._lock, self._connect() as db:
            existing = db.execute(
                "SELECT * FROM commands WHERE idempotency_key=?", (idempotency_key,)
            ).fetchone()
            if existing:
                return self._row(existing), False
            now = now_iso()
            db.execute(
                "INSERT INTO commands VALUES(?,?,?,?,?,?,?,?)",
                (
                    command_id,
                    idempotency_key,
                    command_type,
                    json.dumps(payload),
                    "RECEIVED",
                    "{}",
                    now,
                    now,
                ),
            )
            return {
                "id": command_id,
                "idempotency_key": idempotency_key,
                "command_type": command_type,
                "payload": payload,
                "status": "RECEIVED",
                "result": {},
            }, True

    def complete_command(self, command_id: str, status: str, result: dict) -> None:
        with self._lock, self._connect() as db:
            db.execute(
                "UPDATE commands SET status=?, result=?, updated_at=? WHERE id=?",
                (status, json.dumps(result), now_iso(), command_id),
            )

    def upsert_run(self, run: dict) -> None:
        with self._lock, self._connect() as db:
            existing = db.execute(
                "SELECT id FROM runs WHERE id=?", (run["id"],)
            ).fetchone()
            values = (
                run["strategy_id"],
                run["strategy_version"],
                run.get("account_id"),
                run["mode"],
                run["status"],
                json.dumps(run),
                run.get("started_at"),
                run.get("stopped_at"),
                now_iso(),
                run["id"],
            )
            if existing:
                db.execute(
                    "UPDATE runs SET strategy_id=?,strategy_version=?,account_id=?,mode=?,status=?,payload=?,started_at=?,stopped_at=?,updated_at=? WHERE id=?",
                    values,
                )
            else:
                db.execute(
                    "INSERT INTO runs(strategy_id,strategy_version,account_id,mode,status,payload,started_at,stopped_at,updated_at,id) VALUES(?,?,?,?,?,?,?,?,?,?)",
                    values,
                )

    def get_run(self, run_id: str) -> dict | None:
        with self._connect() as db:
            row = db.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
            return json.loads(row["payload"]) if row else None

    def list_runs(self) -> list[dict]:
        with self._connect() as db:
            return [
                json.loads(row["payload"])
                for row in db.execute(
                    "SELECT * FROM runs ORDER BY updated_at DESC"
                ).fetchall()
            ]

    def append_order(self, order: dict) -> tuple[dict, bool]:
        with self._lock, self._connect() as db:
            existing = db.execute(
                "SELECT * FROM orders WHERE idempotency_key=?",
                (order["idempotency_key"],),
            ).fetchone()
            if existing:
                return self._order_row(existing), False
            db.execute(
                "INSERT INTO orders(client_order_id,sequence,idempotency_key,run_id,account_id,state,payload,filled_quantity,remaining_quantity,exchange_order_id,error,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    order["client_order_id"],
                    order["sequence"],
                    order["idempotency_key"],
                    order.get("run_id"),
                    order["account_id"],
                    order["state"],
                    json.dumps(order),
                    order.get("filled_quantity", 0),
                    order["remaining_quantity"],
                    order.get("exchange_order_id"),
                    order.get("error"),
                    now_iso(),
                ),
            )
            return order, True

    def latest_order(self, client_order_id: str) -> dict | None:
        with self._connect() as db:
            row = db.execute(
                "SELECT * FROM orders WHERE client_order_id=? ORDER BY sequence DESC LIMIT 1",
                (client_order_id,),
            ).fetchone()
            return self._order_row(row) if row else None

    def open_orders(self, account_id: str | None = None) -> list[dict]:
        terminal = ("FILLED", "CANCELED", "REJECTED", "EXPIRED")
        sql = "SELECT * FROM orders WHERE state NOT IN (?,?,?,?)"
        params: list = list(terminal)
        if account_id:
            sql += " AND account_id=?"
            params.append(account_id)
        with self._connect() as db:
            return [self._order_row(row) for row in db.execute(sql, params).fetchall()]

    def latest_orders(self, account_id: str | None = None) -> list[dict]:
        sql = """
        SELECT current.* FROM orders current
        JOIN (
          SELECT client_order_id, MAX(sequence) AS sequence
          FROM orders GROUP BY client_order_id
        ) latest
        ON current.client_order_id=latest.client_order_id AND current.sequence=latest.sequence
        """
        params: list[str] = []
        if account_id:
            sql += " WHERE current.account_id=?"
            params.append(account_id)
        sql += " ORDER BY current.created_at DESC"
        with self._connect() as db:
            return [self._order_row(row) for row in db.execute(sql, params)]

    def event(self, event_type: str, aggregate_id: str, payload: dict) -> None:
        with self._connect() as db:
            db.execute(
                "INSERT INTO events(event_type,aggregate_id,payload,created_at) VALUES(?,?,?,?)",
                (event_type, aggregate_id, json.dumps(payload), now_iso()),
            )

    def save_market_quotes(self, quotes: list[dict]) -> None:
        with self._lock, self._connect() as db:
            for quote in quotes:
                db.execute(
                    "INSERT INTO market_quotes(asset,symbol,price,provider,source_timestamp,payload,updated_at) VALUES(?,?,?,?,?,?,?) "
                    "ON CONFLICT(asset) DO UPDATE SET symbol=excluded.symbol,price=excluded.price,provider=excluded.provider,source_timestamp=excluded.source_timestamp,payload=excluded.payload,updated_at=excluded.updated_at",
                    (
                        quote["asset"],
                        quote["symbol"],
                        float(quote["price"]),
                        quote["provider"],
                        quote["timestamp"],
                        json.dumps(quote),
                        now_iso(),
                    ),
                )

    def list_market_quotes(self, assets: list[str] | None = None) -> list[dict]:
        sql = "SELECT payload FROM market_quotes"
        params: list[str] = []
        if assets:
            placeholders = ",".join("?" for _ in assets)
            sql += f" WHERE asset IN ({placeholders})"
            params.extend(assets)
        sql += " ORDER BY asset"
        with self._connect() as db:
            return [json.loads(row["payload"]) for row in db.execute(sql, params)]

    def list_events(
        self, limit: int = 100, event_type: str | None = None
    ) -> list[dict]:
        sql = "SELECT * FROM events"
        params: list = []
        if event_type:
            sql += " WHERE event_type=?"
            params.append(event_type)
        sql += " ORDER BY id DESC LIMIT ?"
        params.append(max(1, min(limit, 500)))
        with self._connect() as db:
            return [
                {
                    "id": row["id"],
                    "event_type": row["event_type"],
                    "aggregate_id": row["aggregate_id"],
                    "payload": json.loads(row["payload"]),
                    "created_at": row["created_at"],
                }
                for row in db.execute(sql, params)
            ]

    def save_paper_position(self, position: dict) -> None:
        with self._lock, self._connect() as db:
            db.execute(
                "INSERT INTO paper_positions(account_id,instrument,quantity,average_price,realized_pnl,payload,updated_at) VALUES(?,?,?,?,?,?,?) "
                "ON CONFLICT(account_id,instrument) DO UPDATE SET quantity=excluded.quantity,average_price=excluded.average_price,realized_pnl=excluded.realized_pnl,payload=excluded.payload,updated_at=excluded.updated_at",
                (
                    position["account_id"],
                    position["instrument"],
                    float(position["quantity"]),
                    float(position["average_price"]),
                    float(position.get("realized_pnl", 0)),
                    json.dumps(position),
                    now_iso(),
                ),
            )

    def list_paper_positions(self, account_id: str | None = None) -> list[dict]:
        sql = "SELECT payload FROM paper_positions"
        params: list[str] = []
        if account_id:
            sql += " WHERE account_id=?"
            params.append(account_id)
        sql += " ORDER BY instrument"
        with self._connect() as db:
            return [json.loads(row["payload"]) for row in db.execute(sql, params)]

    def recover_uncertain_orders(self) -> int:
        with self._lock, self._connect() as db:
            rows = db.execute(
                "SELECT * FROM orders WHERE state IN ('SUBMITTING','SUBMITTED','CANCEL_PENDING')"
            ).fetchall()
            for row in rows:
                payload = json.loads(row["payload"])
                payload["state"] = "RECONCILIATION_REQUIRED"
                db.execute(
                    "UPDATE orders SET state='RECONCILIATION_REQUIRED',payload=? WHERE client_order_id=? AND sequence=?",
                    (json.dumps(payload), row["client_order_id"], row["sequence"]),
                )
            return len(rows)

    @staticmethod
    def _row(row) -> dict:
        value = dict(row)
        value["payload"] = json.loads(value["payload"])
        value["result"] = json.loads(value["result"])
        return value

    @staticmethod
    def _order_row(row) -> dict:
        value = json.loads(row["payload"])
        value.update(
            {
                "state": row["state"],
                "filled_quantity": row["filled_quantity"],
                "remaining_quantity": row["remaining_quantity"],
                "exchange_order_id": row["exchange_order_id"],
                "error": row["error"],
            }
        )
        return value

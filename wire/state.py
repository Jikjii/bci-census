"""Where the Wire remembers what it has already seen.

Two backends with one interface: a JSON file for local runs, and a DynamoDB table on AWS.
Values are stored as JSON strings so DynamoDB never converts numbers to Decimal.
Each source keeps one record (last run, failures, recently seen ids), so a run costs a
handful of reads and writes no matter how many items a feed returns.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path


class FileState:
    def __init__(self, path: str | os.PathLike):
        self.path = Path(path)
        try:
            self.data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.data = {}

    def get(self, key: str) -> dict | None:
        value = self.data.get(key)
        return json.loads(json.dumps(value)) if value is not None else None  # a copy, like a fresh read

    def put(self, key: str, value: dict, ttl_days: int | None = None) -> None:
        self.data[key] = value
        self.flush()

    def delete(self, key: str) -> None:
        self.data.pop(key, None)
        self.flush()

    def acquire_lock(self, owner: str, seconds: int) -> bool:
        return True  # a local run is a single process

    def release_lock(self, owner: str) -> None:
        pass

    def flush(self) -> None:
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(self.data, indent=1, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.path)


class DynamoState:
    """Single-table store: pk (string), data (JSON string), expires_at (epoch seconds, TTL)."""

    LOCK_KEY = "lock"

    def __init__(self, table_name: str, table=None):
        if table is None:
            import boto3  # present in the Lambda runtime

            table = boto3.resource("dynamodb").Table(table_name)
        self.table = table

    def get(self, key: str) -> dict | None:
        item = self.table.get_item(Key={"pk": key}).get("Item")
        if not item:
            return None
        return json.loads(item["data"])

    def put(self, key: str, value: dict, ttl_days: int | None = None) -> None:
        record = {"pk": key, "data": json.dumps(value, ensure_ascii=False)}
        if ttl_days:
            record["expires_at"] = int(time.time()) + ttl_days * 86400
        self.table.put_item(Item=record)

    def delete(self, key: str) -> None:
        self.table.delete_item(Key={"pk": key})

    def acquire_lock(self, owner: str, seconds: int) -> bool:
        """Only one run at a time, so a slow minute can't send the same alert twice."""
        now = int(time.time())
        try:
            self.table.put_item(
                Item={"pk": self.LOCK_KEY, "data": json.dumps({"owner": owner}), "expires_at": now + seconds},
                ConditionExpression="attribute_not_exists(pk) OR expires_at < :now",
                ExpressionAttributeValues={":now": now},
            )
            return True
        except Exception as exc:  # ConditionalCheckFailedException means another run holds it
            if "ConditionalCheckFailed" in type(exc).__name__ or "ConditionalCheckFailed" in str(exc):
                return False
            raise

    def release_lock(self, owner: str) -> None:
        try:
            self.table.delete_item(
                Key={"pk": self.LOCK_KEY},
                ConditionExpression="contains(#d, :owner)",
                ExpressionAttributeNames={"#d": "data"},
                ExpressionAttributeValues={":owner": owner},
            )
        except Exception:
            pass  # expired or taken over; the TTL cleans it up


def open_state(settings) -> FileState | DynamoState:
    if settings.table:
        return DynamoState(settings.table)
    return FileState(settings.state_path)

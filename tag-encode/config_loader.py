"""
FlavorProvider abstraction for tag-encode.

LocalJsonFlavorProvider: reads from configs/copacker_<ID>.json  (current)
S3FlavorProvider:        stub — implement to pull from AWS S3    (future)

To switch to S3 later, instantiate S3FlavorProvider in main.py instead.
"""

import json
import os
from abc import ABC, abstractmethod


class FlavorProvider(ABC):
    @abstractmethod
    def get_copacker_id(self) -> str: ...

    @abstractmethod
    def get_copacker_name(self) -> str: ...

    @abstractmethod
    def get_flavors(self) -> list[dict]: ...

    def get_active_flavors(self) -> list[dict]:
        """Flavors that should appear in the dropdown (non-Deprecated, vendor_item filled)."""
        return [f for f in self.get_flavors() if f.get("status") != "Deprecated"]


# ──────────────────────────────────────────────────────────────
# Local JSON implementation (current)
# ──────────────────────────────────────────────────────────────

class LocalJsonFlavorProvider(FlavorProvider):
    """
    Loads from configs/copacker_<ID>.json.
    Pass config_path to point at a specific file,
    or copacker_id to auto-locate under configs/.
    """

    def __init__(self, config_path: str | None = None, copacker_id: str | None = None):
        if config_path is None and copacker_id is None:
            raise ValueError("Provide config_path or copacker_id")
        if config_path is None:
            config_path = os.path.join(
                os.path.dirname(__file__), "configs", f"copacker_{copacker_id}.json"
            )
        if not os.path.exists(config_path):
            raise FileNotFoundError(f"Config not found: {config_path}")
        with open(config_path) as f:
            self._data = json.load(f)

    def get_copacker_id(self) -> str:
        return self._data["copacker_id"]

    def get_copacker_name(self) -> str:
        return self._data["copacker_name"]

    def get_flavors(self) -> list[dict]:
        return self._data.get("flavors", [])

    @staticmethod
    def list_available(configs_dir: str | None = None) -> list[dict]:
        """Return a list of {copacker_id, copacker_name, path} for all config files found."""
        if configs_dir is None:
            configs_dir = os.path.join(os.path.dirname(__file__), "configs")
        result = []
        if not os.path.isdir(configs_dir):
            return result
        for fname in sorted(os.listdir(configs_dir)):
            if fname.startswith("copacker_") and fname.endswith(".json"):
                path = os.path.join(configs_dir, fname)
                try:
                    with open(path) as f:
                        d = json.load(f)
                    result.append({
                        "copacker_id":   d.get("copacker_id", ""),
                        "copacker_name": d.get("copacker_name", ""),
                        "short_name":    d.get("short_name", ""),
                        "path":          path,
                    })
                except Exception:
                    pass
        return result


# ──────────────────────────────────────────────────────────────
# S3 stub (future)
# ──────────────────────────────────────────────────────────────

class S3FlavorProvider(FlavorProvider):
    """
    Future implementation: pull flavor list from AWS S3.

    The existing TagPrinter 2.3 downloads from S3 (177 total flavors,
    then filters to the relevant copacker subset).

    To implement:
      1. pip install boto3
      2. Fill in BUCKET and KEY below
      3. Parse the S3 flavor JSON into the same schema as the local config
      4. Swap LocalJsonFlavorProvider for S3FlavorProvider in main.py

    Schema returned by get_flavors() must match:
      [{"flavor_number": int, "flavor_name": str, "gtin": str,
        "vendor_item": str, "status": str}, ...]
    """

    S3_BUCKET = "bevi-tag-encode"   # TODO: confirm bucket name
    S3_KEY    = "flavors.json"      # TODO: confirm key / path

    def __init__(self, copacker_id: str):
        self._copacker_id = copacker_id
        self._data = self._fetch()

    def _fetch(self) -> dict:
        try:
            import boto3  # type: ignore
            s3 = boto3.client("s3")
            obj = s3.get_object(Bucket=self.S3_BUCKET, Key=self.S3_KEY)
            all_flavors = json.loads(obj["Body"].read())
            # TODO: filter all_flavors for this copacker_id and map to schema
            raise NotImplementedError("S3FlavorProvider._fetch: map S3 response to config schema")
        except ImportError:
            raise RuntimeError("boto3 not installed. Run: pip install boto3")

    def get_copacker_id(self) -> str:
        return self._copacker_id

    def get_copacker_name(self) -> str:
        return self._data.get("copacker_name", self._copacker_id)

    def get_flavors(self) -> list[dict]:
        return self._data.get("flavors", [])

"""Consume generated schema, never maintain a second StarIntel model."""
import hashlib
import json
import math
from decimal import Decimal
from pathlib import Path
from jsonschema import Draft202012Validator

NS = "org.starintel/wpa@1"
SCHEMA = json.loads((Path(__file__).parent / "_release/generated/schema.json").read_text())
TYPES = {"network-device": "NetworkDevice", "wireless-network": "WirelessNetwork", "wireless-station": "WirelessStation",
         "geo-point": "GeoPoint", "location": "Location", "relation": "Relation", "event": "Event"}


def stable_id(kind, *parts):
    raw = json.dumps(parts, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return "wpa:" + kind + ":" + hashlib.sha256(raw.encode()).hexdigest()[:32]


def reference(doc):
    return {"schema": "org.starintel/core@1/" + doc["dtype"], "id": doc["id"]}


def document(dtype, dataset, identity, **fields):
    if not isinstance(dataset, str) or not dataset.strip():
        raise ValueError("dataset must be nonempty")
    doc = dict(id=identity, dataset=dataset, dtype=dtype, schemaVersion="0.10.1", **fields)
    validate(doc)
    return doc


def validate(doc):
    if doc.get("schemaVersion") != "0.10.1" or doc.get("dtype") not in TYPES:
        raise ValueError("unsupported canonical document contract")
    # JSON Schema alone accepts NaN as a Python number; JSON wire never does.
    json.dumps(doc, allow_nan=False)
    Draft202012Validator({"$ref": "#/$defs/" + TYPES[doc["dtype"]], "$defs": SCHEMA["$defs"]}).validate(doc)
    return doc


def finite(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(label + " must be a finite number")
    return float(value)


def timestamp(value):
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("observedAt must be a nonnegative Unix timestamp")
    return value


def point(dataset, lat, lon, identity, **fields):
    finite(lat, "latitude"); finite(lon, "longitude")
    if not -90 <= lat <= 90 or not -180 <= lon <= 180:
        raise ValueError("coordinates out of range")
    fields = {key: format(Decimal(str(value)), "f") if key in ("accuracyMeters", "altitudeMeters") else value
              for key, value in fields.items()}
    return document("geo-point", dataset, identity, geometryType="point",
                    latitude=format(Decimal(str(lat)), "f"), longitude=format(Decimal(str(lon)), "f"), **fields)


def relation(dataset, source, destination, predicate, evidence=(), **fields):
    return document("relation", dataset, stable_id("relation", dataset, source["id"], destination["id"], predicate),
                    source=reference(source), destination=reference(destination), predicate=predicate,
                    evidence=[reference(doc) for doc in evidence], **fields)


def validate_bundle(docs):
    by_id = {doc["id"]: doc for doc in docs}
    ids = set(by_id)
    if len(ids) != len(docs):
        raise ValueError("duplicate output IDs")
    for doc in docs:
        validate(doc)
        refs = [doc[k] for k in ("geometry", "location") if k in doc]
        if doc["dtype"] == "relation":
            refs.extend([doc["source"], doc["destination"], *doc.get("evidence", [])])
        for ref in refs:
            target = by_id.get(ref["id"])
            if target is None:
                raise ValueError("dangling canonical reference")
            if target["dataset"] != doc["dataset"] or ref["schema"] != reference(target)["schema"]:
                raise ValueError("reference contract or dataset mismatch")
    return docs

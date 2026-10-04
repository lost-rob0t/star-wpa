"""Normalize source evidence into generated StarIntel 0.10.1 contracts."""
import csv
import io
import math
import re
from datetime import datetime, timezone
from .contracts import NS, document, finite, point, reference, relation, stable_id, timestamp, validate_bundle

MAC = re.compile(r"(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}\Z")


def mac(value):
    if not isinstance(value, str) or not MAC.fullmatch(value):
        raise ValueError("invalid MAC address")
    return value.lower()


def unix_time(value):
    if isinstance(value, int):
        return timestamp(value)
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("source timestamp needs a timezone")
    return timestamp(int(parsed.timestamp()))


def security(value):
    v = str(value).lower().replace("-", " ")
    if "wpa3" in v and "wpa2" in v:
        return "wpa2wpa3-psk"
    for version in ("wpa3", "wpa2", "wpa"):
        if version in v:
            return version + ("-enterprise" if "eap" in v or "enterprise" in v else "-psk")
    if "wep" in v:
        return "wep"
    if v in ("open", "opn", "none"):
        return "open"
    return "unknown"


def unique(docs):
    # Canonical entity IDs are stable; observations remain separate event records.
    result = {}
    for doc in docs:
        previous = result.get(doc["id"])
        if previous and doc["dtype"] in ("wireless-network", "wireless-station"):
            first = min(previous.get("firstSeen", 2**63), doc.get("firstSeen", 2**63))
            if previous.get("lastSeen", 0) > doc.get("lastSeen", 0):
                doc = previous.copy()
            if first != 2**63:
                doc["firstSeen"] = first
        result[doc["id"]] = doc
    return validate_bundle(list(result.values()))


def observations(request):
    if not isinstance(request["observations"], list) or len(request["observations"]) > 1000:
        raise ValueError("observation batches are limited to 1000 readings")
    dataset = request["dataset"]
    receiver = request["receiverId"]
    provider = request.get("provider", "listener")
    if not isinstance(receiver, str) or not receiver.strip():
        raise ValueError("receiverId must be nonempty")
    docs = []
    for row in request["observations"]:
        at = timestamp(row["observedAt"])
        bssid = mac(row["bssid"])
        fields = {k: row[k] for k in ("ssid", "channel", "frequencyMhz", "signalDbm") if row.get(k) is not None}
        ap = document("wireless-network", dataset, stable_id("network", dataset, bssid), bssid=bssid,
                      security=security(row.get("security", "unknown")), firstSeen=at, lastSeen=at, **fields)
        data = {"receiverId": receiver, "provider": provider, "bssid": bssid, "networkId": ap["id"]}
        for k in ("signalDbm", "latitude", "longitude", "distanceMeters", "rangeAccuracyMeters"):
            if row.get(k) is not None:
                finite(row[k], k)
                data[k] = row[k]
        if "distanceMeters" in data and data["distanceMeters"] <= 0:
            raise ValueError("distanceMeters must be positive")
        if "rangeAccuracyMeters" in data and data["rangeAccuracyMeters"] <= 0:
            raise ValueError("rangeAccuracyMeters must be positive")
        if ("latitude" in data) != ("longitude" in data):
            raise ValueError("receiver position needs both coordinates")
        event = document("event", dataset, stable_id("sighting", dataset, at, data), eventKind="wireless-sighting",
                         observedAt=at, collector="star:v1:collector:wireless:" + provider, extensions={NS: data})
        docs.extend([ap, event, relation(dataset, event, ap, "observed-network", [event], validAt=at)])
        if "latitude" in data:
            geo = point(dataset, data["latitude"], data["longitude"], stable_id("receiver-point", event["id"]),
                        observedAt=at, extensions={NS: {"geography": "direct", "receiverId": receiver}})
            loc = document("location", dataset, stable_id("receiver-location", event["id"]), geometry=reference(geo))
            docs.extend([geo, loc, relation(dataset, event, loc, "observed-at", [event], validAt=at)])
    return unique(docs)


def ingest_kismet(request):
    if not isinstance(request["devices"], list) or len(request["devices"]) > 1000:
        raise ValueError("Kismet batches are limited to 1000 devices")
    rows, stations = [], []
    for device in request["devices"]:
        # Consume the actual Kismet dotted-field device export, rather than inventing a wire model.
        dtype = device.get("kismet.device.base.type", "")
        address = mac(device["kismet.device.base.macaddr"])
        at = timestamp(device["kismet.device.base.last_time"])
        dot11 = device.get("dot11.device", {})
        signal = device.get("kismet.device.base.signal", {}).get("kismet.common.signal.last_signal")
        if "client" in dtype.lower() or "station" in dtype.lower():
            stations.append((address, at, signal, dot11.get("dot11.device.last_bssid")))
            continue
        if "ap" not in dtype.lower():
            continue  # Bluetooth/other PHY devices are not Wi-Fi APs.
        record = dot11.get("dot11.device.last_beaconed_ssid_record", {})
        row = {"bssid": address, "observedAt": at, "signalDbm": signal,
               "ssid": record.get("dot11.advertisedssid.ssid", dot11.get("dot11.device.last_beaconed_ssid")),
               "security": record.get("dot11.advertisedssid.crypt_string", device.get("kismet.device.base.crypt", "unknown"))}
        channel = device.get("kismet.device.base.channel")
        if channel and str(channel).isdigit():
            row["channel"] = int(channel)
        # Device aggregate geo is not the receiver position of this specific reading.
        rows.append(row)
    docs = observations(dict(request, provider="kismet", observations=rows))
    for address, at, signal, bssid in stations:
        docs.extend(station_documents(request, address, at, signal, bssid))
    return unique(docs)


def station_documents(request, address, at, signal, bssid, packets=None, probes=None):
    dataset = request["dataset"]
    fields = {}
    if signal is not None:
        fields["signalDbm"] = signal
    if packets is not None:
        fields["packets"] = packets
    if probes:
        fields["probeSsids"] = probes
    associated = isinstance(bssid, str) and MAC.fullmatch(bssid)
    if associated:
        fields["lastBssid"] = mac(bssid)
    station = document("wireless-station", dataset, stable_id("station", dataset, address), mac=address,
                       stationType="station", firstSeen=at, lastSeen=at, **fields)
    event = document("event", dataset, stable_id("station-observation", dataset, request["receiverId"], at, address, fields),
                     eventKind="wireless-station-observation", observedAt=at,
                     extensions={NS: {"receiverId": request["receiverId"], "stationId": station["id"]}})
    docs = [station, event, relation(dataset, event, station, "observed-station", [event], validAt=at)]
    if associated:
        ap = document("wireless-network", dataset, stable_id("network", dataset, mac(bssid)), bssid=mac(bssid), security="unknown")
        docs.extend([ap, relation(dataset, station, ap, "associated-with", [event], validAt=at)])
    return docs


def ingest_gpsd(request):
    if not isinstance(request["reports"], list) or len(request["reports"]) > 1000:
        raise ValueError("GPSD batches are limited to 1000 reports")
    docs = []
    for report in request["reports"]:
        if report.get("class") != "TPV" or report.get("mode", 0) < 2:
            continue
        at = unix_time(report.get("time", request.get("observedAt")))
        extra = {}
        if report.get("altMSL") is not None:
            extra["altitudeMeters"] = finite(report["altMSL"], "altitudeMeters")
        if report.get("epx") is not None and report.get("epy") is not None:
            epx, epy = finite(report["epx"], "epx"), finite(report["epy"], "epy")
            if min(epx, epy) < 0:
                raise ValueError("negative GPS uncertainty")
            extra["accuracyMeters"] = math.hypot(epx, epy)
        geo = point(request["dataset"], report["lat"], report["lon"],
                    stable_id("gps-point", request["dataset"], request["receiverId"], at, report),
                    observedAt=at, extensions={NS: {"provider": "gpsd", "receiverId": request["receiverId"], "geography": "direct"}}, **extra)
        loc = document("location", request["dataset"], stable_id("gps-location", geo["id"]), geometry=reference(geo))
        event = document("event", request["dataset"], stable_id("gps-fix", geo["id"]), eventKind="gps-fix", observedAt=at,
                         extensions={NS: {"receiverId": request["receiverId"], "mode": report["mode"]}})
        docs.extend([geo, loc, event, relation(request["dataset"], event, loc, "observed-at", [event], validAt=at)])
    return unique(docs)


def ingest_airodump(request):
    rows, stations, header = [], [], None
    for values in csv.reader(io.StringIO(request["csv"])):
        values = [value.strip() for value in values]
        if not values or not any(values):
            continue
        if values[0] in ("BSSID", "Station MAC"):
            header = values
            continue
        if header is None:
            raise ValueError("missing airodump CSV header")
        if len(values) < len(header) - 1:
            raise ValueError("truncated airodump CSV row")
        row = dict(zip(header, values))
        # airodump timestamps use local wall time; require an explicit offset (UTC default documented).
        at = unix_time(row["Last time seen"].replace(" ", "T") + request.get("timezoneOffset", "+00:00"))
        if header[0] == "BSSID":
            row = {"bssid": row["BSSID"], "observedAt": at, "ssid": row.get("ESSID", ""),
                   "channel": int(row["channel"]), "signalDbm": int(row["Power"]), "security": row.get("Privacy", "unknown")}
            fix = request.get("receiverFix")
            if fix and abs(timestamp(fix["observedAt"]) - at) <= request.get("maxFixAgeSeconds", 5):
                row.update(latitude=fix["latitude"], longitude=fix["longitude"])
            rows.append(row)
        else:
            probes = values[len(header) - 1:]
            stations.append((mac(row["Station MAC"]), at, int(row["Power"]), row.get("BSSID"),
                             int(row["# packets"]), [p for p in probes if p]))
    docs = observations(dict(request, provider="listener", observations=rows))
    for args in stations:
        docs.extend(station_documents(request, *args))
    return unique(docs)


def ingest_wardrive(request):
    """Extract WarStar/WiGLE conversion from server PR #311 into this owner.

    HTTP principal/auth checks remain at the server boundary. Input is an
    operator-local export, not a new public unauthenticated endpoint.
    """
    samples = request["observations"]
    if not isinstance(samples, list) or not 1 <= len(samples) <= 100:
        raise ValueError("wardrive expects 1..100 observations")
    receiver = request.get("receiverId", request.get("device_id"))
    if not isinstance(receiver, str) or not receiver:
        raise ValueError("wardrive needs an installation/receiver identity")
    docs = []
    for sample in samples:
        millis = timestamp(sample["time"])
        at = millis // 1000
        address = mac(sample["address"])
        source_id = sample["id"]
        if isinstance(source_id, bool) or not isinstance(source_id, int) or source_id < 1:
            raise ValueError("wardrive sample id must be a positive integer")
        level = sample["level"]
        if isinstance(level, bool) or not isinstance(level, int) or not -200 <= level <= 100:
            raise ValueError("invalid radio signal level")
        radio = sample.get("radio", "WIFI").upper()
        if radio in ("W", "WIFI"):
            row = {"bssid": address, "observedAt": at, "latitude": sample["latitude"], "longitude": sample["longitude"],
                   "signalDbm": level, "security": sample.get("security", "unknown"), "ssid": sample.get("name")}
            if sample.get("frequency", 0) > 0:
                row["frequencyMhz"] = sample["frequency"]
            docs.extend(observations(dict(request, receiverId=receiver, provider="wardrive", observations=[row])))
        elif radio in ("B", "BT", "BLUETOOTH", "BLE"):
            dataset = request["dataset"]
            device = document("network-device", dataset, stable_id("bluetooth-device", dataset, address),
                              deviceId=address, deviceClass="unknown", extensions={NS: {"radio": radio}})
            event = document("event", dataset, stable_id("wardrive-bt", dataset, receiver, source_id, millis, sample),
                             eventKind="wireless-bluetooth-sighting", observedAt=at,
                             extensions={NS: {"receiverId": receiver, "signalDbm": level, "deviceId": device["id"]}})
            geo = point(dataset, sample["latitude"], sample["longitude"], stable_id("receiver-point", event["id"]),
                        observedAt=at, extensions={NS: {"geography": "direct", "receiverId": receiver}})
            loc = document("location", dataset, stable_id("receiver-location", event["id"]), geometry=reference(geo))
            docs.extend([device, event, geo, loc, relation(dataset, event, device, "observed-device", [event], validAt=at),
                         relation(dataset, event, loc, "observed-at", [event], validAt=at)])
        else:
            raise ValueError("unsupported wardrive radio")
    return unique(docs)

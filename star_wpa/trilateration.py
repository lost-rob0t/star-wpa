"""Bounded local-plane multilateration of independent receiver evidence."""
import math
from collections import defaultdict
from .contracts import NS, document, finite, point, reference, relation, stable_id, timestamp, validate_bundle
from .ingest import unique

EARTH_RADIUS = 6371008.8


def solve2(a, b, c, u, v):
    determinant = a * c - b * b
    if determinant <= 1e-6 * (a + c) ** 2:
        raise ValueError("receiver geometry is degenerate or poorly conditioned")
    return (c * u - b * v) / determinant, (a * v - b * u) / determinant, determinant


def ranges(data, model):
    if "distanceMeters" in data:
        distance = finite(data["distanceMeters"], "distanceMeters")
    else:
        if not model or "signalDbm" not in data:
            raise ValueError("trilateration needs measured ranges or an explicit calibrated RSSI model")
        power = finite(model["referenceDbm"], "referenceDbm")
        exponent = finite(model["pathLossExponent"], "pathLossExponent")
        if exponent <= 0:
            raise ValueError("pathLossExponent must be positive")
        distance = 10 ** ((power - finite(data["signalDbm"], "signalDbm")) / (10 * exponent))
    if not math.isfinite(distance) or distance <= 0:
        raise ValueError("range must be positive and finite")
    return distance


def fit(events, model, max_baseline):
    lat0 = sum(e["extensions"][NS]["latitude"] for e in events) / len(events)
    lon0 = events[0]["extensions"][NS]["longitude"]
    if abs(lat0) > 85:
        raise ValueError("local-plane solver does not support polar geometry")
    coslat = math.cos(math.radians(lat0))
    samples = []
    for event in events:
        data = event["extensions"][NS]
        lat, lon = finite(data["latitude"], "latitude"), finite(data["longitude"], "longitude")
        if not -90 <= lat <= 90 or not -180 <= lon <= 180:
            raise ValueError("receiver coordinates out of range")
        x = EARTH_RADIUS * math.radians((lon - lon0 + 180) % 360 - 180) * coslat
        y = EARTH_RADIUS * math.radians(lat - lat0)
        sigma = finite(data.get("rangeAccuracyMeters", 5), "rangeAccuracyMeters")
        if sigma <= 0:
            raise ValueError("range uncertainty must be positive")
        samples.append((x, y, ranges(data, model), sigma))
    baseline = max(math.hypot(a[0] - b[0], a[1] - b[1]) for a in samples for b in samples)
    if baseline > max_baseline:
        raise ValueError("receiver baseline exceeds local-plane limit")
    x0, y0, r0, _ = samples[0]
    a = b = c = u = v = 0.0
    for x, y, radius, sigma in samples[1:]:
        dx, dy = 2 * (x - x0), 2 * (y - y0)
        rhs = r0**2 - radius**2 + x*x + y*y - x0*x0 - y0*y0
        weight = 1 / (sigma*sigma)
        a += weight*dx*dx; b += weight*dx*dy; c += weight*dy*dy
        u += weight*dx*rhs; v += weight*dy*rhs
    x, y, _ = solve2(a, b, c, u, v)
    for _ in range(25):
        a = b = c = u = v = 0.0
        for sx, sy, radius, sigma in samples:
            measured = max(math.hypot(x - sx, y - sy), 1e-9)
            dx, dy = (x - sx)/measured, (y - sy)/measured
            residual, weight = radius - measured, 1/(sigma*sigma)
            a += weight*dx*dx; b += weight*dx*dy; c += weight*dy*dy
            u += weight*dx*residual; v += weight*dy*residual
        step_x, step_y, determinant = solve2(a, b, c, u, v)
        x += step_x; y += step_y
        if math.hypot(step_x, step_y) < 1e-5:
            break
    else:
        raise ValueError("trilateration failed to converge")
    if max(math.hypot(x - sx, y - sy) for sx, sy, _, _ in samples) > max_baseline:
        raise ValueError("estimated position exceeds local-plane limit")
    residuals = [math.hypot(x-sx, y-sy)-radius for sx, sy, radius, _ in samples]
    rms = math.sqrt(sum(r*r for r in residuals)/len(samples))
    # Conservative scale estimate with geometry dilution; never claim exact RF position.
    accuracy = max(1.0, math.sqrt((a+c)/determinant), rms * math.sqrt(len(samples)/max(1, len(samples)-2)))
    lat = lat0 + math.degrees(y/EARTH_RADIUS)
    lon = (lon0 + math.degrees(x/(EARTH_RADIUS*coslat)) + 180) % 360 - 180
    return lat, lon, accuracy, rms


def trilaterate(request):
    dataset = request["dataset"]
    window = request.get("windowSeconds", 10)
    if isinstance(window, bool) or not isinstance(window, int) or not 1 <= window <= 3600:
        raise ValueError("windowSeconds must be an integer in 1..3600")
    max_baseline = finite(request.get("maxBaselineMeters", 5000), "maxBaselineMeters")
    max_residual = finite(request.get("maxResidualMeters", 100), "maxResidualMeters")
    if not 0 < max_baseline <= 20000 or max_residual <= 0:
        raise ValueError("invalid solver bounds")
    docs = request["documents"]
    validate_bundle(docs)
    groups = defaultdict(dict)
    networks = {d["id"]: d for d in docs if d["dtype"] == "wireless-network" and d["dataset"] == dataset}
    for event in sorted(docs, key=lambda d: (d.get("observedAt", 0), d["id"])):
        data = event.get("extensions", {}).get(NS, {})
        if event["dataset"] != dataset or event["dtype"] != "event" or event.get("eventKind") != "wireless-sighting":
            continue
        if "latitude" not in data or "longitude" not in data:
            continue
        at = timestamp(event["observedAt"])
        network = networks.get(data.get("networkId"))
        if network is None or data.get("bssid") != network["bssid"]:
            raise ValueError("observation network reference does not match transmitter")
        receiver = data.get("receiverId")
        if not isinstance(receiver, str) or not receiver:
            raise ValueError("observation lacks receiver identity")
        groups[(network["id"], at // window)][receiver] = event
    outputs = []
    for (network_id, bucket), receivers in sorted(groups.items()):
        if len(receivers) < 3:
            continue
        events = sorted(receivers.values(), key=lambda e: e["id"])
        lat, lon, accuracy, rms = fit(events, request.get("rssiModel"), max_baseline)
        if rms > max_residual:
            raise ValueError("range residual exceeds configured limit")
        proof = {"geography": "derived", "method": "weighted-local-plane-multilateration",
                 "evidenceIds": [e["id"] for e in events], "receiverIds": sorted(receivers),
                 "residualRmsMeters": rms, "windowStart": bucket*window, "windowEnd": (bucket+1)*window,
                 "validFrom": min(e["observedAt"] for e in events), "validUntil": max(e["observedAt"] for e in events),
                 "rangeAccuracyDefaultMeters": 5, "rssiModel": request.get("rssiModel")}
        identity = stable_id("estimate", dataset, network_id, proof)
        geo = point(dataset, lat, lon, identity, accuracyMeters=accuracy,
                    observedAt=proof["validUntil"], extensions={NS: proof})
        loc = document("location", dataset, stable_id("estimate-location", identity), geometry=reference(geo))
        outputs.extend([geo, loc, relation(dataset, networks[network_id], loc, "estimated-location", events,
                                          validAt=proof["validFrom"], endedAt=proof["validUntil"],
                                          extensions={NS: {"geography": "derived"}})])
    if not outputs:
        raise ValueError("no window contains at least three independent positioned receivers")
    return unique([d for d in docs if d["dataset"] == dataset] + outputs)

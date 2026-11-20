#!/usr/bin/env python3
"""Prometheus exporter for Flexit EcoNordic WH4 (Siemens Climatix POS3.67) via BACnet/IP.

Read-only: the exporter only issues ReadPropertyMultiple requests, it never writes.

Every scrape triggers one BACnet read of all points in points.yaml (in chunks), unless the
previous read is younger than --cache-seconds. Device info and enum state texts are read once
from the device and refreshed when the device has been unreachable.
"""

import argparse
import asyncio
import logging
import os
import threading
import time
from dataclasses import dataclass, field

import yaml
from bacpypes3.apdu import ErrorRejectAbortNack
from bacpypes3.app import Application
from bacpypes3.argparse import SimpleArgumentParser
from bacpypes3.basetypes import ErrorType
from bacpypes3.pdu import Address
from bacpypes3.primitivedata import ObjectIdentifier, PropertyIdentifier
from prometheus_client import REGISTRY, start_http_server
from prometheus_client.core import CounterMetricFamily, GaugeMetricFamily, InfoMetricFamily
from prometheus_client.registry import Collector

log = logging.getLogger("wh4_exporter")

PREFIX = "wh4_"
TYPES = ("gauge", "counter", "enum", "bool")
DEVICE_PROPS = ["objectName", "modelName", "vendorName", "firmwareRevision",
                "applicationSoftwareVersion", "description"]


def pid(name):
    """Normalised property name as returned by bacpypes3 ("presentValue" -> "present-value")."""
    return str(PropertyIdentifier(name))


@dataclass
class Point:
    object: str
    metric: str
    type: str
    labels: dict = field(default_factory=dict)
    scale: float = 1.0
    help: str = ""

    @property
    def key(self):
        # normalised "<type>,<instance>" as returned by bacpypes3
        return str(ObjectIdentifier(self.object))


def load_points(path):
    with open(path) as f:
        raw = yaml.safe_load(f)["points"]
    points = []
    for p in raw:
        point = Point(object=p["object"], metric=p["metric"], type=p.get("type", "gauge"),
                      labels={k: str(v) for k, v in (p.get("labels") or {}).items()},
                      scale=float(p.get("scale", 1.0)), help=p.get("help", ""))
        if point.type not in TYPES:
            raise ValueError(f"{point.object}: unknown type {point.type!r}")
        points.append(point)

    # all points of one metric must share label keys and type
    by_metric = {}
    for p in points:
        first = by_metric.setdefault(p.metric, p)
        if first.type != p.type or set(first.labels) != set(p.labels):
            raise ValueError(f"metric {p.metric}: inconsistent type or label keys ({p.object})")
    return points


class BacnetReader:
    """Owns a bacpypes3 Application running in its own asyncio loop thread."""

    def __init__(self, local_address, target, device_id, instance, chunk_size, timeout):
        self.local_address = local_address
        self.target = Address(target)
        self.device = ObjectIdentifier(f"device,{device_id}")
        self.instance = instance
        self.chunk_size = chunk_size
        self.timeout = timeout
        self.loop = asyncio.new_event_loop()
        threading.Thread(target=self.loop.run_forever, name="bacnet", daemon=True).start()
        self.app = self.run(self._start())

    def run(self, coro):
        return asyncio.run_coroutine_threadsafe(coro, self.loop).result()

    async def _start(self):
        args = SimpleArgumentParser().parse_args([
            "--address", self.local_address,
            "--instance", str(self.instance),
            "--name", "wh4-exporter",
        ])
        return Application.from_args(args)

    async def _rpm(self, objects, props):
        """ReadPropertyMultiple for objects x props. Returns {(object, prop): value|Exception}."""
        params = []
        for obj in objects:
            params += [obj, list(props)]
        response = await asyncio.wait_for(
            self.app.read_property_multiple(self.target, params), self.timeout)
        if response is None or isinstance(response, ErrorRejectAbortNack):
            raise RuntimeError(f"ReadPropertyMultiple failed: {response!r}")
        result = {}
        for obj_id, prop_id, _index, value in response:
            if isinstance(value, ErrorType):
                value = RuntimeError(f"{value.errorClass}: {value.errorCode}")
            result[(str(obj_id), str(prop_id))] = value
        return result

    async def _read_chunked(self, objects, props):
        result = {}
        for i in range(0, len(objects), self.chunk_size):
            result.update(await self._rpm(objects[i:i + self.chunk_size], props))
        return result

    def read(self, objects, props=("presentValue",)):
        return self.run(self._read_chunked(list(objects), props))

    def read_device_info(self):
        values = self.run(self._rpm([str(self.device)], DEVICE_PROPS))
        info = {}
        for prop in DEVICE_PROPS:
            value = values.get((str(self.device), pid(prop)))
            info[prop] = "" if value is None or isinstance(value, Exception) else str(value)
        return info


def _number(value):
    """Convert a bacpypes3 present value (Real, Unsigned, BinaryPV, ...) to float."""
    if isinstance(value, (int, float)):
        return float(value)
    return float(int(value))


class WH4Collector(Collector):
    def __init__(self, reader, points, cache_seconds):
        self.reader = reader
        self.points = points
        self.cache_seconds = cache_seconds
        self.lock = threading.Lock()
        self.device_info = None
        self.state_texts = {}  # point key -> [text for state 1, 2, ...]
        self.values = {}
        self.errors = {}
        self.up = False
        self.duration = 0.0
        self.last_read = 0.0

    # --- reading --------------------------------------------------------------------
    def _load_metadata(self):
        self.device_info = self.reader.read_device_info()
        log.info("device: %s", self.device_info)
        enums = [p.key for p in self.points if p.type == "enum"]
        texts = self.reader.read(enums, ("stateText",))
        for key in enums:
            value = texts.get((key, pid("stateText")))
            self.state_texts[key] = [str(t) for t in value] if isinstance(value, list) else []

    def refresh(self):
        with self.lock:
            if time.monotonic() - self.last_read < self.cache_seconds:
                return
            start = time.monotonic()
            try:
                if self.device_info is None:
                    self._load_metadata()
                raw = self.reader.read([p.key for p in self.points])
            except Exception as e:  # network error, timeout, abort, ...
                log.warning("BACnet read failed: %s %s", type(e).__name__, e)
                self.up = False
                self.values, self.errors = {}, {}
                self.device_info = None  # re-read metadata once the device is back
            else:
                self.up = True
                self.values, self.errors = {}, {}
                for p in self.points:
                    value = raw.get((p.key, pid("presentValue")))
                    if value is None or isinstance(value, Exception):
                        self.errors[p.key] = value
                        continue
                    try:
                        self.values[p.key] = _number(value)
                    except (TypeError, ValueError) as e:
                        self.errors[p.key] = e
                if self.errors:
                    log.warning("failed points: %s", self.errors)
            self.duration = time.monotonic() - start
            self.last_read = time.monotonic()

    # --- exposition -----------------------------------------------------------------
    def describe(self):
        return []

    def collect(self):
        self.refresh()

        up = GaugeMetricFamily(PREFIX + "up", "1 if the last BACnet read of the WH4 succeeded")
        up.add_metric([], 1.0 if self.up else 0.0)
        yield up
        duration = GaugeMetricFamily(PREFIX + "scrape_duration_seconds",
                                     "Duration of the last BACnet read")
        duration.add_metric([], self.duration)
        yield duration
        errors = GaugeMetricFamily(PREFIX + "point_errors",
                                   "Number of points that could not be read in the last read")
        errors.add_metric([], float(len(self.errors)))
        yield errors

        if self.device_info:
            info = InfoMetricFamily(PREFIX + "device", "Device information read via BACnet")
            info.add_metric([], {
                "name": self.device_info["objectName"],
                "model": self.device_info["modelName"],
                "vendor": self.device_info["vendorName"],
                "firmware": self.device_info["firmwareRevision"],
                "application": self.device_info["applicationSoftwareVersion"],
                "serial": self.device_info["description"],
            })
            yield info

        if not self.up:
            return

        families = {}
        for p in self.points:
            if p.key not in self.values:
                continue
            value = self.values[p.key]
            label_keys = list(p.labels)
            label_values = [p.labels[k] for k in label_keys]
            name = PREFIX + p.metric
            help_text = p.help or p.object

            if p.type == "counter":
                fam = families.get(name) or families.setdefault(
                    name, CounterMetricFamily(name, help_text, labels=label_keys))
                fam.add_metric(label_values, value * p.scale)
            elif p.type == "enum":
                code_name = name + "_code"
                code = families.get(code_name) or families.setdefault(
                    code_name, GaugeMetricFamily(code_name, help_text + " (raw state number)",
                                                 labels=label_keys))
                code.add_metric(label_values, value)
                fam = families.get(name) or families.setdefault(
                    name, GaugeMetricFamily(name, help_text, labels=label_keys + ["state"]))
                texts = self.state_texts.get(p.key) or []
                for i, text in enumerate(texts, start=1):
                    fam.add_metric(label_values + [text], 1.0 if int(value) == i else 0.0)
                if not texts or not 1 <= int(value) <= len(texts):
                    fam.add_metric(label_values + [str(int(value))], 1.0)
            else:  # gauge, bool
                fam = families.get(name) or families.setdefault(
                    name, GaugeMetricFamily(name, help_text, labels=label_keys))
                fam.add_metric(label_values, value * p.scale)

        yield from families.values()


def main():
    env = os.environ.get
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--target", default=env("WH4_TARGET"),
                        help="WH4 BACnet/IP address, host[:port] (required)")
    parser.add_argument("--device-id", type=int, default=int(env("WH4_DEVICE_ID", "2")),
                        help="BACnet device instance of the WH4 (default %(default)s)")
    parser.add_argument("--local-address", default=env("WH4_LOCAL_ADDRESS", "0.0.0.0:47809"),
                        help="local BACnet address to bind, ip[/prefix][:port] (default %(default)s). "
                             "Use a port other than 47808 if something else on the host speaks BACnet.")
    parser.add_argument("--instance", type=int, default=int(env("WH4_INSTANCE", "3999999")),
                        help="BACnet device instance of the exporter itself (default %(default)s)")
    parser.add_argument("--points", default=env("WH4_POINTS",
                                                os.path.join(os.path.dirname(__file__), "points.yaml")))
    parser.add_argument("--listen", default=env("WH4_LISTEN", "0.0.0.0:9846"),
                        help="HTTP listen address for /metrics (default %(default)s)")
    parser.add_argument("--cache-seconds", type=float, default=float(env("WH4_CACHE_SECONDS", "5")),
                        help="reuse a BACnet read younger than this (default %(default)s)")
    parser.add_argument("--chunk-size", type=int, default=int(env("WH4_CHUNK_SIZE", "150")),
                        help="objects per ReadPropertyMultiple request (default %(default)s). "
                             "The WH4 segments large responses fine; one request is the fastest.")
    parser.add_argument("--timeout", type=float, default=float(env("WH4_TIMEOUT", "10")),
                        help="timeout per BACnet request in seconds (default %(default)s)")
    parser.add_argument("--once", action="store_true",
                        help="read all points once, print them and exit")
    parser.add_argument("--log-level", default=env("WH4_LOG_LEVEL", "INFO"))
    args = parser.parse_args()
    if not args.target:
        parser.error("--target (or WH4_TARGET) is required, e.g. --target 192.168.1.50")

    logging.basicConfig(level=args.log_level.upper(),
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    points = load_points(args.points)
    log.info("loaded %d points from %s", len(points), args.points)

    reader = BacnetReader(args.local_address, args.target, args.device_id, args.instance,
                          args.chunk_size, args.timeout)
    collector = WH4Collector(reader, points, args.cache_seconds)

    if args.once:
        from prometheus_client import generate_latest
        from prometheus_client.registry import CollectorRegistry
        registry = CollectorRegistry()
        registry.register(collector)
        print(generate_latest(registry).decode(), end="")
        return 0 if collector.up else 1

    REGISTRY.register(collector)
    host, _, port = args.listen.rpartition(":")
    start_http_server(int(port), addr=host or "0.0.0.0")
    log.info("listening on http://%s/metrics, target %s device %d",
             args.listen, args.target, args.device_id)
    threading.Event().wait()


if __name__ == "__main__":
    raise SystemExit(main())

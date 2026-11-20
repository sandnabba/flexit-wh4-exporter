"""Fake wh4-exporter for dashboard development without a heat pump.

Replays a saved /metrics page (sample-metrics.txt) and lets values drift so graphs have shape:
temperatures and percentages follow a ~12 minute sine, counters keep increasing and the heat
pump cycles between Normal operation and Standby. The labelled enum series ({state="..."})
are replayed unchanged, only the *_code series change.
"""
import http.server
import math
import random
import re
import sys
import time

BASE = open(sys.argv[1]).read().splitlines()
START = time.time()
LINE = re.compile(r"^(\w+)(\{[^}]*\})? (\S+)$")


def value(name, v):
    t = time.time() - START
    wave = math.sin(t / 120)
    if name.endswith("_total"):
        return v + t * (6 if "seconds" in name else 1 / 300)
    if name == "wh4_heat_pump_state_code":
        return 4 if wave > 0 else 1
    if name == "wh4_heat_pump_plant_mode_code":
        return 15 if wave > 0 else 5
    if name == "wh4_heat_pump_compressor_hertz":
        return max(0.0, 77 * wave)
    if name.endswith("_celsius") and not any(k in name for k in ("curve", "setpoint", "limit")):
        return v + 2 * wave + random.uniform(-0.2, 0.2)
    if name.endswith(("_percent", "_rpm", "_hour", "_watts")):
        return max(0.0, v * (1 + 0.1 * wave) + random.uniform(-1, 1))
    return v


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        out = []
        for line in BASE:
            m = LINE.match(line)
            if m and not line.startswith("#"):
                out.append(f"{m.group(1)}{m.group(2) or ''} {value(m.group(1), float(m.group(3)))}")
            else:
                out.append(line)
        body = ("\n".join(out) + "\n").encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; version=0.0.4")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


http.server.HTTPServer(("0.0.0.0", 9846), Handler).serve_forever()

"""Generates wh4-dashboard.json. Usage: python3 build_dashboard.py wh4-dashboard.json"""
import json, sys

GRAFANA_VERSION = "13.2.4"  # version the dashboard was built and tested with
DS = {"type": "prometheus", "uid": "${datasource}"}
I = 'instance=~"$instance"'

# Categorical slots in fixed order (validated palette, light steps). Status colors are separate.
C = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
GOOD, WARN, SERIOUS, CRIT, GRAY = "#0ca30c", "#fab219", "#ec835a", "#d03b3b", "#8e8e8e"

_id = [0]
def nid():
    _id[0] += 1
    return _id[0]

def target(expr, legend="", ref="A", instant=False, fmt="time_series"):
    t = {"datasource": DS, "expr": expr, "legendFormat": legend or "__auto", "refId": ref,
         "range": not instant, "instant": instant, "format": fmt}
    return t

def color_override(name, color, extra=None):
    props = [{"id": "color", "value": {"mode": "fixed", "fixedColor": color}}]
    props += extra or []
    return {"matcher": {"id": "byName", "options": name}, "properties": props}

def timeseries(title, targets, unit, pos, colors=None, description="", minv=None, maxv=None,
               dashed=(), draw="line", overrides_extra=None, decimals=None):
    overrides = []
    for i, (name, color) in enumerate((colors or {}).items()):
        extra = [{"id": "custom.lineStyle", "value": {"fill": "dash", "dash": [8, 6]}}] if name in dashed else None
        overrides.append(color_override(name, color, extra))
    overrides += overrides_extra or []
    defaults = {
        "unit": unit,
        "color": {"mode": "palette-classic"},
        "custom": {"drawStyle": draw, "lineWidth": 2, "fillOpacity": 0, "showPoints": "never",
                   "spanNulls": 120000, "axisSoftMin": minv, "axisSoftMax": maxv,
                   "lineInterpolation": "linear", "gradientMode": "none"},
    }
    if decimals is not None:
        defaults["decimals"] = decimals
    return {"id": nid(), "type": "timeseries", "title": title, "description": description,
            "datasource": DS, "gridPos": pos, "targets": targets,
            "fieldConfig": {"defaults": defaults, "overrides": overrides},
            "options": {"legend": {"displayMode": "list", "placement": "bottom", "showLegend": True},
                        "tooltip": {"mode": "multi", "sort": "none"}}}

def stat(title, targets, unit, pos, description="", text_mode="value", thresholds=None,
         mappings=None, color_mode="none", decimals=None, reduce="lastNotNull", graph=False):
    defaults = {"unit": unit, "mappings": mappings or [],
                "thresholds": {"mode": "absolute", "steps": thresholds or [{"color": "text", "value": None}]},
                "color": {"mode": "thresholds"}}
    if decimals is not None:
        defaults["decimals"] = decimals
    return {"id": nid(), "type": "stat", "title": title, "description": description,
            "datasource": DS, "gridPos": pos, "targets": targets,
            "fieldConfig": {"defaults": defaults, "overrides": []},
            "options": {"reduceOptions": {"calcs": [reduce], "fields": "", "values": False},
                        "textMode": text_mode, "colorMode": color_mode,
                        "graphMode": "area" if graph else "none", "justifyMode": "auto",
                        "orientation": "auto", "wideLayout": True, "showPercentChange": False}}

def row(title, y, collapsed=False, panels=None):
    return {"id": nid(), "type": "row", "title": title, "collapsed": collapsed,
            "gridPos": {"h": 1, "w": 24, "x": 0, "y": y}, "panels": panels or []}

def value_map(states, colors):
    """states: {number: text}; colors: {text: color}"""
    return [{"type": "value", "options": {str(k): {"text": v, "color": colors.get(v, GRAY), "index": i}
                                          for i, (k, v) in enumerate(states.items())}}]

# Enum texts as reported by the WH4 (stateText). The exporter also exposes them as labels.
HP_STATE = {1: "Standby", 2: "Air purge process", 3: "Startup process", 4: "Normal operation",
            5: "Stop process", 6: "Defrost operation", 7: "Standby when error", 8: "Manual operation",
            9: "Forced fan operation", 10: "Forced pump operation"}
HP_STATE_COLORS = {"Normal operation": C[0], "Startup process": C[2], "Stop process": C[2],
                   "Defrost operation": C[6], "Air purge process": C[4], "Manual operation": C[4],
                   "Forced fan operation": C[4], "Forced pump operation": C[4],
                   "Standby when error": CRIT, "Standby": GRAY}
PLANT = {1: "Off", 2: "Vent.heating from tank", 3: "Load tank", 4: "Load tank & vent.heating",
         5: "Space heating from tank", 6: "Space heat.& vent.heat.from tank", 7: "Load tank & space heat.",
         8: "Load tank & space heat.& vent.", 9: "HP not available", 10: "Swi-off delay flow through heat.",
         11: "Legionella prev.vent.heat.", 12: "Legionella prev.space heat.", 13: "Space heat.with HP",
         14: "Space heat.& vent.with HP", 15: "Load tank & space heat.with HP",
         16: "Load tank & vent.& space with HP", 17: "Legionella prev.tank"}
# Group colours by what the system does: from tank = aqua, heat pump to house = blue,
# loading tank = orange, legionella = yellow, not available = critical.
PLANT_COLORS = {}
for k, v in PLANT.items():
    if "Legionella" in v: PLANT_COLORS[v] = C[3]
    elif v == "HP not available": PLANT_COLORS[v] = CRIT
    elif v == "Off" or "Swi-off" in v: PLANT_COLORS[v] = GRAY
    elif "Load tank" in v and "with HP" in v: PLANT_COLORS[v] = C[6]
    elif "Load tank" in v: PLANT_COLORS[v] = C[1]
    elif "with HP" in v: PLANT_COLORS[v] = C[0]
    else: PLANT_COLORS[v] = C[2]
DHW = {1: "Comfort", 2: "Economy", 3: "Boost", 4: "Temporary boost", 5: "Forced charge",
       6: "Economy delay", 7: "Legionella prevention"}
DHW_COLORS = {"Comfort": C[1], "Economy": C[2], "Boost": C[7], "Temporary boost": C[7],
              "Forced charge": C[7], "Economy delay": C[2], "Legionella prevention": C[3]}
# multi-state-value 361: includes the temporary modes (multi-state-value 42 stays on "Home")
VENT = {1: "Off", 2: "Away", 3: "Home", 4: "High", 5: "Cooker hood", 6: "Fireplace", 7: "Forced ventilation"}
VENT_COLORS = {"Off": GRAY, "Away": C[2], "Home": C[0], "High": C[1], "Cooker hood": C[4],
               "Fireplace": C[7], "Forced ventilation": C[6]}

OPMODE = {1: "Protection", 2: "Economy", 3: "Pre-Comfort", 4: "Comfort"}
OPMODE_COLORS = {"Protection": GRAY, "Economy": C[2], "Pre-Comfort": C[0], "Comfort": C[1]}
MAINT = {1: "None", 2: "Legionella prevention, DHW", 3: "Legionella prevention, SH",
         4: "Heat revovery, stop request", 5: "Legionella prevention, VH", 6: "Fire damper, test",
         7: "Maintenance, valve and damper", 8: "Heat revovery, restart request"}
MAINT_COLORS = {"None": GRAY, "Legionella prevention, DHW": C[3], "Legionella prevention, SH": C[3],
                "Legionella prevention, VH": C[3], "Heat revovery, stop request": C[6],
                "Heat revovery, restart request": C[6], "Fire damper, test": C[7],
                "Maintenance, valve and damper": C[4]}
HP_MAINT = {1: "None", 2: "Forced fan", 3: "Forced pump air purge", 4: "Forced heating", 5: "Forced pump"}
HP_MAINT_COLORS = {"None": GRAY, **{v: C[4] for v in HP_MAINT.values() if v != "None"}}

panels = []
y = 0

# ---- Overview ------------------------------------------------------------------------
panels.append(stat("Outdoor", [target(f'wh4_air_temperature_celsius{{{I},position="outdoor"}}', "Outdoor")],
                   "celsius", {"h": 4, "w": 3, "x": 0, "y": y}, decimals=1,
                   description="Outdoor air temperature (ventilation unit sensor B4)."))
panels.append(stat("Heat pump", [target(f'max by (state) (wh4_heat_pump_state{{{I}}}) == 1', "{{state}}", instant=True)],
                   "none", {"h": 4, "w": 5, "x": 3, "y": y}, text_mode="name",
                   description="Heat pump state (multi-state-input 1)."))
panels.append(stat("Plant mode", [target(f'max by (state) (wh4_heat_pump_plant_mode{{{I}}}) == 1', "{{state}}", instant=True)],
                   "none", {"h": 4, "w": 6, "x": 8, "y": y}, text_mode="name",
                   description="What the heat pump system is doing: loading the tank, heating the house "
                               "from the tank or directly with the heat pump (multi-state-value 40)."))
panels.append(stat("Compressor", [target(f'wh4_heat_pump_compressor_hertz{{{I}}}', "Compressor")],
                   "hertz", {"h": 4, "w": 3, "x": 14, "y": y}, decimals=0))
panels.append(stat("Hot water, top", [target(f'wh4_tank_temperature_celsius{{{I},position="top"}}', "Top")],
                   "celsius", {"h": 4, "w": 3, "x": 17, "y": y}, decimals=1))
alarm = stat("Alarm", [target(f'wh4_alarm_code{{{I}}}', "{{class}}")], "none",
             {"h": 4, "w": 4, "x": 20, "y": y}, text_mode="value_and_name", color_mode="background",
             description="Present alarm code per class (A = alarm, B = maintenance). 0 = no alarm. "
                         "Codes are listed in the Flexit GO manual, e.g. 1020 = replace filter.",
             mappings=[{"type": "value", "options": {"0": {"text": "OK", "color": GOOD, "index": 0}}},
                       {"type": "value", "options": {"1020": {"text": "1020 Filter", "index": 1}}}],
             thresholds=[{"color": GOOD, "value": None}, {"color": WARN, "value": 1}])
alarm["fieldConfig"]["overrides"].append(
    {"matcher": {"id": "byName", "options": "A"},
     "properties": [{"id": "thresholds", "value": {"mode": "absolute", "steps": [
         {"color": GOOD, "value": None}, {"color": CRIT, "value": 1}]}}]})
panels.append(alarm)
y += 4

# ---- Heating -------------------------------------------------------------------------
panels.append(row("Space heating", y)); y += 1
panels.append(timeseries(
    "Heating circuit", [
        target(f'wh4_heating_flow_temperature_celsius{{{I}}}', "Flow", "A"),
        target(f'wh4_heating_flow_setpoint_celsius{{{I}}}', "Flow setpoint", "B"),
        target(f'wh4_heating_return_temperature_celsius{{{I}}}', "Return", "C")],
    "celsius", {"h": 9, "w": 12, "x": 0, "y": y},
    colors={"Flow": C[1], "Flow setpoint": C[1], "Return": C[0]}, dashed=("Flow setpoint",),
    description="Space heating flow and return temperature. The setpoint comes from the heating curve."))

xy = {
    "id": nid(), "type": "xychart", "title": "Heating curve vs. actual flow temperature",
    "description": "Line: the 7-point heating curve configured in the unit. Dots: measured flow "
                   "temperature against outdoor temperature over the selected time range.",
    "datasource": DS, "gridPos": {"h": 9, "w": 12, "x": 12, "y": y},
    "targets": [
        target(f'wh4_air_temperature_celsius{{{I},position="outdoor"}}', "Outdoor", "A"),
        target(f'wh4_heating_flow_temperature_celsius{{{I}}}', "Flow", "B"),
        target(f'max by (point) (wh4_heating_curve_outdoor_celsius{{{I}}})', "{{point}}", "C", instant=True, fmt="table"),
        target(f'max by (point) (wh4_heating_curve_flow_celsius{{{I}}})', "{{point}}", "D", instant=True, fmt="table"),
    ],
    "transformations": [
        {"id": "joinByField", "filter": {"id": "byRefId", "options": "/^(A|B)$/"},
         "options": {"byField": "Time", "mode": "inner"}},
        {"id": "joinByField", "filter": {"id": "byRefId", "options": "/^(C|D)$/"},
         "options": {"byField": "point", "mode": "inner"}},
        {"id": "organize", "options": {"renameByName": {"Value #C": "Curve outdoor", "Value #D": "Curve flow"}}},
        {"id": "sortBy", "filter": {"id": "byRefId", "options": "/^(C|D)$/"},
         "options": {"sort": [{"field": "Curve outdoor"}]}},
    ],
    "fieldConfig": {"defaults": {"unit": "celsius", "color": {"mode": "fixed", "fixedColor": C[1]},
                                 "custom": {"show": "points", "pointSize": {"fixed": 5}, "lineWidth": 2,
                                            "fillOpacity": 50}},
                    "overrides": []},
    "options": {
        "mapping": "manual",
        "series": [
            {"frame": {"matcher": {"id": "byIndex", "options": 0}},
             "x": {"matcher": {"id": "byName", "options": "Outdoor"}},
             "y": {"matcher": {"id": "byName", "options": "Flow"}},
             "name": {"fixed": "Measured"}},
            {"frame": {"matcher": {"id": "byIndex", "options": 1}},
             "x": {"matcher": {"id": "byName", "options": "Curve outdoor"}},
             "y": {"matcher": {"id": "byName", "options": "Curve flow"}},
             "name": {"fixed": "Heating curve"}},
        ],
        "legend": {"showLegend": True, "displayMode": "list", "placement": "bottom"},
        "tooltip": {"mode": "single"},
    },
}
xy["fieldConfig"]["overrides"] = [
    {"matcher": {"id": "byName", "options": "Curve flow"},
     "properties": [{"id": "custom.show", "value": "points+lines"},
                    {"id": "color", "value": {"mode": "fixed", "fixedColor": C[0]}},
                    {"id": "custom.pointSize", "value": {"fixed": 8}}]},
    {"matcher": {"id": "byName", "options": "Flow"},
     "properties": [{"id": "color", "value": {"mode": "fixed", "fixedColor": C[1]}}]},
]
panels.append(xy)
y += 9
panels.append(timeseries(
    "Outdoor temperature", [target(f'wh4_air_temperature_celsius{{{I},position="outdoor"}}', "Outdoor", "A")],
    "celsius", {"h": 7, "w": 8, "x": 0, "y": y}, colors={"Outdoor": C[0]}))
panels.append(timeseries(
    "Heating circulation pump", [target(f'wh4_heating_pump_percent{{{I}}}', "Circulation pump", "A")],
    "percent", {"h": 7, "w": 8, "x": 8, "y": y}, minv=0, maxv=100, colors={"Circulation pump": C[0]},
    description="Speed of the space heating circulation pump."))
panels.append(timeseries(
    "Mixing valve, tank to heating circuit", [
        target(f'wh4_tank_consumer_valve_percent{{{I}}}', "Mixing valve", "A")],
    "percent", {"h": 7, "w": 8, "x": 16, "y": y}, minv=0, colors={"Mixing valve": C[2]}, decimals=1,
    description="Storage tank consumer valve (analog-output 26). It mixes hot tank water into the space "
                "heating circuit when the house is heated from the tank. With a hot tank and a low flow "
                "setpoint it works in the bottom few percent, where small movements give large flow "
                "temperature steps. The axis is not fixed at 100 % so these movements stay visible."))
y += 7

# ---- Heat pump -----------------------------------------------------------------------
panels.append(row("Heat pump", y)); y += 1
timeline = {
    "id": nid(), "type": "state-timeline", "title": "Operating states",
    "description": "Heat pump state, plant mode, hot water state, ventilation mode and operating mode "
                   "(selects the temperature setpoint). Maintenance functions are at the bottom.",
    "datasource": DS, "gridPos": {"h": 9, "w": 24, "x": 0, "y": y},
    "targets": [
        target(f'wh4_heat_pump_state_code{{{I}}}', "Heat pump", "A"),
        target(f'wh4_heat_pump_plant_mode_code{{{I}}}', "Plant mode", "B"),
        target(f'wh4_dhw_state_code{{{I}}}', "Hot water", "C"),
        target(f'wh4_ventilation_mode_detail_code{{{I}}}', "Ventilation", "D"),
        target(f'wh4_operating_mode_code{{{I}}}', "Operating mode", "E"),
    ],
    "fieldConfig": {"defaults": {"color": {"mode": "fixed", "fixedColor": GRAY},
                                 "custom": {"fillOpacity": 85, "lineWidth": 0}},
                    "overrides": [
                        {"matcher": {"id": "byName", "options": "Heat pump"},
                         "properties": [{"id": "mappings", "value": value_map(HP_STATE, HP_STATE_COLORS)}]},
                        {"matcher": {"id": "byName", "options": "Plant mode"},
                         "properties": [{"id": "mappings", "value": value_map(PLANT, PLANT_COLORS)}]},
                        {"matcher": {"id": "byName", "options": "Hot water"},
                         "properties": [{"id": "mappings", "value": value_map(DHW, DHW_COLORS)}]},
                        {"matcher": {"id": "byName", "options": "Ventilation"},
                         "properties": [{"id": "mappings", "value": value_map(VENT, VENT_COLORS)}]},
                        {"matcher": {"id": "byName", "options": "Operating mode"},
                         "properties": [{"id": "mappings", "value": value_map(OPMODE, OPMODE_COLORS)}]},
                    ]},
    "options": {"showValue": "auto", "mergeValues": True, "alignValue": "left", "rowHeight": 0.85,
                "legend": {"showLegend": False}, "tooltip": {"mode": "single"}},
}
panels.append(timeline)
y += 9
panels.append(timeseries(
    "Compressor speed", [target(f'wh4_heat_pump_compressor_hertz{{{I}}}', "Compressor", "A")],
    "hertz", {"h": 8, "w": 8, "x": 0, "y": y}, colors={"Compressor": C[0]}, minv=0,
    description="Inverter compressor speed feedback."))
panels.append(timeseries(
    "Heat pump water and hot gas", [
        target(f'wh4_heat_pump_temperature_celsius{{{I},sensor="water_out"}}', "Water out", "A"),
        target(f'wh4_heat_pump_temperature_celsius{{{I},sensor="water_in"}}', "Water in", "B"),
        target(f'wh4_heat_pump_temperature_celsius{{{I},sensor="discharge_gas"}}', "Discharge gas", "C")],
    "celsius", {"h": 8, "w": 8, "x": 8, "y": y},
    colors={"Water out": C[1], "Water in": C[0], "Discharge gas": C[2]},
    description="Water in/out of the CO2 gas cooler and compressor discharge (hot gas) temperature."))
panels.append(timeseries(
    "Heat pump air side", [
        target(f'wh4_heat_pump_temperature_celsius{{{I},sensor="air_inlet"}}', "Air inlet", "A"),
        target(f'wh4_heat_pump_temperature_celsius{{{I},sensor="deicing"}}', "De-icing", "B")],
    "celsius", {"h": 8, "w": 8, "x": 16, "y": y},
    colors={"Air inlet": C[0], "De-icing": C[2]},
    description="Air entering the heat pump (exhaust air from the ventilation mixed with outdoor air) "
                "and the evaporator de-icing sensor."))
y += 8
panels.append(timeseries(
    "Condenser pump", [target(f'wh4_heat_pump_condenser_pump_percent{{{I}}}', "Condenser pump", "A")],
    "percent", {"h": 7, "w": 8, "x": 0, "y": y}, minv=0, maxv=100, colors={"Condenser pump": C[0]},
    description="Pump that circulates water from the bottom of the tank through the heat pump's gas "
                "cooler and back to the tank. A low flow during loading gives a high outlet temperature "
                "in one pass. It may also run while the compressor is off (Forced pump operation)."))
panels.append(timeseries(
    "Heat pump fan", [target(f'wh4_heat_pump_fan_speed_rpm{{{I}}}', "Heat pump fan", "A")],
    "suffix: rpm", {"h": 7, "w": 8, "x": 8, "y": y}, minv=0, colors={"Heat pump fan": C[0]},
    description="Fan that draws air through the heat pump's evaporator. It also helps the ventilation "
                "unit's extract fan while the heat pump runs."))
panels.append(timeseries(
    "Tank changeover valve", [target(f'wh4_tank_changeover_valve_percent{{{I}}}', "Changeover valve", "A")],
    "percent", {"h": 7, "w": 8, "x": 16, "y": y}, minv=0, maxv=100, colors={"Changeover valve": C[0]},
    description="Valve that decides where in the tank the water from the heat pump returns."))
y += 7

# ---- Hot water -----------------------------------------------------------------------
panels.append(row("Hot water and electric heaters", y)); y += 1
panels.append(timeseries(
    "Tank temperatures", [
        target(f'wh4_tank_temperature_celsius{{{I},position="top"}}', "Top", "A"),
        target(f'wh4_tank_temperature_celsius{{{I},position="middle"}}', "Middle", "B"),
        target(f'wh4_tank_temperature_celsius{{{I},position="bottom"}}', "Bottom", "C")],
    "celsius", {"h": 8, "w": 12, "x": 0, "y": y},
    colors={"Top": C[1], "Middle": C[2], "Bottom": C[0]},
    description="Hot water tank sensors. In Economy mode the tank is reloaded when the top sensor "
                "drops, in Comfort mode when the middle sensor drops."))
panels.append(timeseries(
    "Electric heaters", [
        target(f'wh4_flow_heater_request_percent{{{I}}}', "Flow-through heater (water)", "A"),
        target(f'wh4_reheater_control_percent{{{I}}}', "Supply air reheater", "B")],
    "percent", {"h": 8, "w": 12, "x": 12, "y": y}, minv=0, maxv=100,
    colors={"Flow-through heater (water)": C[0], "Supply air reheater": C[1]},
    description="Direct electric heating. The flow-through heater (3 kW) backs up hot water and space "
                "heating; the reheater heats the supply air when heat recovery is not enough."))
y += 8
panels.append(timeseries(
    "Supply air reheater control", [
        target(f'wh4_reheater_control_percent{{{I}}}', "Output", "A"),
        target(f'wh4_reheater_heating_request_percent{{{I}}}', "Heating request", "B"),
        target(f'wh4_reheater_heating_request_min_percent{{{I}}}', "Minimum request", "C")],
    "percent", {"h": 8, "w": 12, "x": 0, "y": y}, minv=0, maxv=100,
    colors={"Output": C[1], "Heating request": C[0], "Minimum request": C[0]}, dashed=("Minimum request",),
    description="Heating request from the supply air temperature control to the electric reheater "
                "(analog-value 196), its minimum (analog-value 195) and the reheater output signal."))
panels.append(timeseries(
    "Supply air reheater power", [target(f'wh4_reheater_power_watts{{{I}}}', "Power", "A")],
    "watt", {"h": 8, "w": 8, "x": 12, "y": y}, minv=0, colors={"Power": C[1]},
    description="Electric power of the supply air reheater as calculated by the unit."))
panels.append(stat("Reheater energy",
                   [target(f'avg_over_time(wh4_reheater_power_watts{{{I}}}[$__range]) * $__range_s / 3600 / 1000',
                           "Energy", instant=True)],
                   "kwatth", {"h": 4, "w": 4, "x": 20, "y": y}, decimals=1,
                   description="Supply air reheater energy over the selected time range (average power x time)."))
panels.append(stat("Reheater avg. power",
                   [target(f'avg_over_time(wh4_reheater_power_watts{{{I}}}[$__range])', "Average", instant=True)],
                   "watt", {"h": 4, "w": 4, "x": 20, "y": y + 4}, decimals=0,
                   description="Average supply air reheater power over the selected time range."))
y += 8

# ---- Ventilation ---------------------------------------------------------------------
panels.append(row("Ventilation", y)); y += 1
panels.append(timeseries(
    "Air temperatures", [
        target(f'wh4_air_temperature_celsius{{{I},position="supply"}}', "Supply", "A"),
        target(f'wh4_air_temperature_celsius{{{I},position="extract"}}', "Extract", "B"),
        target(f'wh4_air_temperature_celsius{{{I},position="exhaust"}}', "Exhaust", "C"),
        target(f'wh4_air_temperature_celsius{{{I},position="outdoor"}}', "Outdoor", "D")],
    "celsius", {"h": 8, "w": 12, "x": 0, "y": y},
    colors={"Supply": C[1], "Extract": C[0], "Exhaust": C[2], "Outdoor": C[6]},
    description="Extract air is the best available proxy for indoor temperature on the WH4."))
panels.append(timeseries(
    "Air flow", [
        target(f'wh4_airflow_cubic_meters_per_hour{{{I},fan="supply"}}', "Supply", "A"),
        target(f'wh4_airflow_cubic_meters_per_hour{{{I},fan="extract"}}', "Extract", "B"),
        target(f'wh4_airflow_setpoint_cubic_meters_per_hour{{{I},fan="supply"}}', "Supply setpoint", "C"),
        target(f'wh4_airflow_setpoint_cubic_meters_per_hour{{{I},fan="extract"}}', "Extract setpoint", "D")],
    "suffix: m³/h", {"h": 8, "w": 12, "x": 12, "y": y},
    colors={"Supply": C[1], "Extract": C[0], "Supply setpoint": C[1], "Extract setpoint": C[0]},
    dashed=("Supply setpoint", "Extract setpoint"), minv=0,
    description="Measured air flow and its setpoint. The setpoint changes with the ventilation mode, "
                "e.g. Cooker hood lowers extract air because the kitchen hood extracts on its own."))
y += 8
panels.append(timeseries(
    "Heat recovery", [
        target(f'wh4_heat_recovery_efficiency_percent{{{I}}}', "Efficiency", "A"),
        target(f'wh4_heat_recovery_rotor_percent{{{I}}}', "Rotor speed", "B")],
    "percent", {"h": 8, "w": 12, "x": 0, "y": y}, minv=0, maxv=100,
    colors={"Efficiency": C[2], "Rotor speed": C[0]}))
panels.append(timeseries(
    "Fan speed", [
        target(f'wh4_fan_speed_rpm{{{I},fan="supply"}}', "Supply", "A"),
        target(f'wh4_fan_speed_rpm{{{I},fan="extract"}}', "Extract", "B")],
    "suffix: rpm", {"h": 8, "w": 12, "x": 12, "y": y}, minv=0,
    colors={"Supply": C[1], "Extract": C[0]}))
y += 8
panels.append(timeseries(
    "Supply air setpoints", [
        target(f'wh4_air_temperature_celsius{{{I},position="supply"}}', "Supply air", "A"),
        target(f'wh4_supply_air_temperature_setpoint_celsius{{{I}}}', "Present setpoint", "B"),
        target(f'wh4_operating_mode_setpoint_celsius{{{I},mode="comfort"}}', "Comfort", "C"),
        target(f'wh4_operating_mode_setpoint_celsius{{{I},mode="pre_comfort"}}', "Pre-Comfort", "D"),
        target(f'wh4_operating_mode_setpoint_celsius{{{I},mode="economy"}}', "Economy", "E")],
    "celsius", {"h": 8, "w": 8, "x": 0, "y": y},
    colors={"Supply air": C[1], "Present setpoint": C[1], "Comfort": C[0], "Pre-Comfort": C[2],
            "Economy": C[6]},
    dashed=("Present setpoint", "Comfort", "Pre-Comfort", "Economy"), decimals=1,
    description="Measured supply air temperature, the setpoint in use and the setpoint of each operating "
                "mode. The operating mode (see Operating states) picks which one applies, so the "
                "effective setpoint can be lower than the one set in the app. The Protection setpoint "
                "is left out to keep the scale readable."))
panels.append(timeseries(
    "Fan differential pressure", [
        target(f'wh4_fan_pressure_pascals{{{I},fan="supply"}}', "Supply", "A"),
        target(f'wh4_fan_pressure_pascals{{{I},fan="extract"}}', "Extract", "B")],
    "pressurepa", {"h": 8, "w": 8, "x": 8, "y": y}, minv=0,
    colors={"Supply": C[1], "Extract": C[0]},
    description="Pressure drop across each fan's inlet nozzle. The unit calculates air flow from it as "
                "K-factor x sqrt(pressure) (K-factor: analog-value 154 supply, 233 extract). This is not "
                "the pressure drop over the filter: the unit holds the air flow constant, so this "
                "pressure only changes with the ventilation mode. See Fan speed per air flow for filter "
                "clogging."))
panels.append(timeseries(
    "Fan speed per air flow (filter indicator)", [
        target(f'(wh4_fan_speed_rpm{{{I},fan="supply"}} / wh4_airflow_cubic_meters_per_hour{{{I},fan="supply"}}) '
               f'and on(instance) (wh4_ventilation_mode_detail_code{{{I}}} == 3)', "Supply", "A"),
        target(f'(wh4_fan_speed_rpm{{{I},fan="extract"}} / wh4_airflow_cubic_meters_per_hour{{{I},fan="extract"}}) '
               f'and on(instance) (wh4_ventilation_mode_detail_code{{{I}}} == 3) '
               f'and on(instance) (wh4_heat_pump_compressor_hertz{{{I}}} == 0)', "Extract", "B")],
    "suffix: rpm per m³/h", {"h": 8, "w": 8, "x": 16, "y": y}, colors={"Supply": C[1], "Extract": C[0]},
    decimals=2,
    description="Fan speed needed per m³/h of air. As a filter clogs, the fan has to spin faster for the "
                "same air flow, so this ratio creeps up and drops back when the filter is replaced. Only "
                "shown in Home mode, because other modes change the air path. The extract ratio is also "
                "hidden while the heat pump compressor runs: the heat pump fan then helps the extract "
                "fan and the ratio drops by about 15 %. A temporary rise in both ratios on humid nights "
                "around or below 0 °C, together with falling heat recovery efficiency, is frost in the "
                "rotary heat exchanger rather than the filter."))
y += 8

# ---- Runtime -------------------------------------------------------------------------
panels.append(row("Runtime and maintenance", y)); y += 1
FUNCS = [("heat_pump", "Heat pump"), ("space_heating", "Space heating"), ("heating_from_tank", "Heating from tank"),
         ("dhw", "Hot water only"), ("dhw_and_space_heating", "Hot water + space heating"),
         ("flow_heater", "Flow-through heater"), ("reheater", "Supply air reheater")]
bg = {
    "id": nid(), "type": "bargauge", "title": "Operating hours in selected range",
    "description": "Increase of the unit's operating hour counters over the dashboard time range. "
                   "The counters have 1 hour resolution, so short ranges are coarse.",
    "datasource": DS, "gridPos": {"h": 8, "w": 12, "x": 0, "y": y},
    "targets": [target(f'increase(wh4_operating_seconds_total{{{I},function="{f}"}}[$__range]) / 3600', name,
                       chr(65 + i), instant=True) for i, (f, name) in enumerate(FUNCS)],
    "fieldConfig": {"defaults": {"unit": "suffix: h", "decimals": 1, "min": 0,
                                 "color": {"mode": "fixed", "fixedColor": C[0]},
                                 "thresholds": {"mode": "absolute", "steps": [{"color": C[0], "value": None}]}},
                    "overrides": [color_override("Flow-through heater", C[7]),
                                  color_override("Supply air reheater", C[7])]},
    "options": {"orientation": "horizontal", "displayMode": "basic", "showUnfilled": True,
                "valueMode": "text", "namePlacement": "left", "sizing": "auto",
                "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False}},
}
panels.append(bg)
panels.append(stat("Heat pump starts in range",
                   [target(f'increase(wh4_heat_pump_starts_total{{{I}}}[$__range])', "Starts", instant=True)],
                   "none", {"h": 4, "w": 4, "x": 12, "y": y}, decimals=0))
panels.append(stat("Runtime per start",
                   [target(f'increase(wh4_operating_seconds_total{{{I},function="heat_pump"}}[$__range]) / ignoring(function) '
                           f'increase(wh4_heat_pump_starts_total{{{I}}}[$__range])', "Per start", instant=True)],
                   "s", {"h": 4, "w": 4, "x": 16, "y": y}, decimals=1,
                   description="Average heat pump runtime per start in the selected range. Short runtimes "
                               "mean frequent cycling."))
panels.append(stat("Filter used",
                   [target(f'wh4_filter_operating_hours{{{I}}} / wh4_filter_replace_interval_hours{{{I}}}',
                           "Filter", instant=True)],
                   "percentunit", {"h": 4, "w": 4, "x": 20, "y": y}, decimals=0, color_mode="background",
                   thresholds=[{"color": GOOD, "value": None}, {"color": WARN, "value": 0.9},
                               {"color": SERIOUS, "value": 1.0}],
                   description="Filter operating time relative to the replacement interval."))
panels.append(stat("Heat pump starts (total)", [target(f'wh4_heat_pump_starts_total{{{I}}}', "Starts", instant=True)],
                   "none", {"h": 4, "w": 4, "x": 12, "y": y + 4}, decimals=0))
panels.append(stat("Heat pump hours (total)",
                   [target(f'wh4_operating_seconds_total{{{I},function="heat_pump"}} / 3600', "Hours", instant=True)],
                   "suffix: h", {"h": 4, "w": 4, "x": 16, "y": y + 4}, decimals=0))
panels.append(stat("Exporter",
                   [target(f'wh4_up{{{I}}}', "up", instant=True)], "none", {"h": 4, "w": 4, "x": 20, "y": y + 4},
                   color_mode="background",
                   mappings=[{"type": "value", "options": {"1": {"text": "Up", "color": GOOD, "index": 0},
                                                           "0": {"text": "Down", "color": CRIT, "index": 1}}}],
                   description="1 if the exporter's last BACnet read succeeded."))
y += 8
maint = {
    "id": nid(), "type": "state-timeline", "title": "Maintenance",
    "description": "Maintenance functions such as legionella prevention and valve/damper exercise, and "
                   "the heat pump's service mode. Normally None.",
    "datasource": DS, "gridPos": {"h": 5, "w": 24, "x": 0, "y": y},
    "targets": [
        target(f'wh4_maintenance_function_code{{{I}}}', "Maintenance", "A"),
        target(f'wh4_heat_pump_maintenance_mode_code{{{I}}}', "HP maintenance", "B"),
    ],
    "fieldConfig": {"defaults": {"color": {"mode": "fixed", "fixedColor": GRAY},
                                 "custom": {"fillOpacity": 85, "lineWidth": 0}},
                    "overrides": [
                        {"matcher": {"id": "byName", "options": "Maintenance"},
                         "properties": [{"id": "mappings", "value": value_map(MAINT, MAINT_COLORS)}]},
                        {"matcher": {"id": "byName", "options": "HP maintenance"},
                         "properties": [{"id": "mappings", "value": value_map(HP_MAINT, HP_MAINT_COLORS)}]},
                    ]},
    "options": {"showValue": "auto", "mergeValues": True, "alignValue": "left", "rowHeight": 0.85,
                "legend": {"showLegend": False}, "tooltip": {"mode": "single"}},
}
panels.append(maint)
y += 5

dashboard = {
    "__inputs": [],
    "title": "Flexit EcoNordic WH4",
    "uid": "flexit-wh4",
    "description": "Flexit EcoNordic WH4 heat pump and ventilation unit via wh4-exporter (BACnet/IP).",
    "tags": ["flexit", "wh4", "heat-pump", "bacnet"],
    "timezone": "browser",
    "editable": True,
    "graphTooltip": 1,
    "refresh": "1m",
    "schemaVersion": 41,
    "time": {"from": "now-24h", "to": "now"},
    # Built-in: annotations added on this dashboard. "WH4 changes": annotations from anywhere in
    # the organisation tagged "wh4", e.g. a log of setting changes posted through the API.
    "annotations": {"list": [
        {"name": "Annotations & Alerts", "builtIn": 1, "type": "dashboard", "enable": True,
         "hide": True, "iconColor": "rgba(0, 211, 255, 1)",
         "datasource": {"type": "grafana", "uid": "-- Grafana --"}},
        {"name": "WH4 changes", "enable": True, "hide": False, "iconColor": GRAY,
         "datasource": {"type": "grafana", "uid": "-- Grafana --"},
         "target": {"type": "tags", "tags": ["wh4"], "matchAny": False, "limit": 200}},
    ]},
    "templating": {"list": [
        {"name": "datasource", "label": "Data source", "type": "datasource", "query": "prometheus",
         "current": {}, "hide": 0, "refresh": 1},
        {"name": "instance", "label": "Instance", "type": "query", "datasource": DS,
         "query": {"query": "label_values(wh4_up, instance)", "refId": "instance"},
         "definition": "label_values(wh4_up, instance)", "refresh": 2, "current": {},
         "includeAll": False, "multi": False, "hide": 0, "sort": 1},
    ]},
    "panels": panels,
}

for p in panels:
    if p["type"] != "row":
        p["pluginVersion"] = GRAFANA_VERSION
json.dump(dashboard, open(sys.argv[1], "w"), indent=2, ensure_ascii=False)
print(f"{len(panels)} panels -> {sys.argv[1]}")

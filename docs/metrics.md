# Metrics

All metrics have the prefix `wh4_` (left out in the table below).
[points.yaml](../points.yaml) has the complete list with the BACnet object behind each metric.

Enum (multi-state) points are exported twice:

* as `<name>{state="..."}` with one series per state, where the active state is 1. The state texts
  are read from the unit.
* as `<name>_code` with the raw state number.

Operating hours are exported as counters in seconds (`*_seconds_total`).

## Unit metrics

| Metric | Labels | |
|---|---|---|
| `air_temperature_celsius` | `position` = outdoor, supply, extract, exhaust | |
| `effective_room_temperature_celsius` | | the extract air temperature on the WH4 |
| `fan_speed_rpm`, `fan_control_percent` | `fan` = supply, extract | |
| `fan_pressure_pascals` | `fan` | pressure across the fan inlet nozzle; air flow = K-factor × √pressure |
| `airflow_cubic_meters_per_hour`, `airflow_setpoint_cubic_meters_per_hour` | `fan` | |
| `heat_recovery_rotor_percent`, `heat_recovery_efficiency_percent` | | |
| `reheater_control_percent`, `reheater_power_watts` | | electric supply air reheater |
| `reheater_heating_request_percent`, `reheater_heating_request_min_percent` | | heating request to the reheater |
| `operating_mode` | `state` | enum: Comfort/Pre-Comfort/Economy/Protection, selects the temperature setpoint |
| `operating_mode_setpoint_celsius` | `mode` | setpoint of each operating mode |
| `maintenance_function` | `state` | enum: legionella prevention, heat recovery stop, valve and damper exercise |
| `heat_pump_maintenance_mode` | `state` | enum: forced fan/pump/heating (service) |
| `ventilation_mode`, `ventilation_mode_detail` | `state` | enum |
| `heat_pump_state`, `heat_pump_plant_mode`, `heat_pump_protection_state` | `state` | enum |
| `heat_pump_compressor_hertz` | | |
| `heat_pump_temperature_celsius` | `sensor` = water_in, water_out, discharge_gas, air_inlet, deicing, inverter_heatsink | |
| `heat_pump_thermal_power_request_watts` | | power the controller *requests* from the heat pump, not a measurement |
| `heat_pump_starts_total` | | counter |
| `tank_temperature_celsius` | `position` = top, middle, bottom | |
| `tank_consumer_valve_percent` | | mixing valve from the tank to the heating circuit |
| `flow_heater_request_percent`, `flow_heater_stage_percent` | `stage` | electric flow-through heater |
| `dhw_mode`, `dhw_state` | `state` | hot water mode (Comfort/Economy/Boost) and state |
| `dhw_setpoint_celsius` | `mode` | |
| `heating_flow_temperature_celsius`, `heating_return_temperature_celsius`, `heating_flow_setpoint_celsius` | | |
| `heating_curve_outdoor_celsius`, `heating_curve_flow_celsius` | `point` = 1..7 | the configured heating curve |
| `heating_curve_shift_kelvin`, `heating_flow_limit_celsius` | `limit` | |
| `alarm_code` | `class` = A, B | present alarm code, 0 = none |
| `filter_operating_hours`, `filter_replace_interval_hours` | | |
| `operating_seconds_total` | `function` | operating hour counters |
| `ventilation_mode_seconds_total` | `mode` | |

## Exporter metrics

| Metric | |
|---|---|
| `wh4_up` | 1 if the last BACnet read succeeded |
| `wh4_scrape_duration_seconds` | duration of the last read |
| `wh4_point_errors` | number of points that couldn't be read |
| `wh4_device_info` | model, firmware, application version and serial number as labels |

## PromQL tips

* When dividing `wh4_operating_seconds_total{function=...}` by another series, use
  `ignoring(function)`.
* The operating hour counters only step once per hour, so use `increase()` over hours or days
  rather than minutes.

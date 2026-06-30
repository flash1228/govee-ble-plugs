"""Thermo-hygrometer SKUs registered as broadcast monitor-only sensors
(temperature / humidity / battery), curated to the classic Govee packed-24 ``0xEC88``
advertisement format that ``codecs.sensor.parse_th_broadcast`` decodes.

Deliberately conservative: leak/motion/door/CO2/BBQ-probe sensors use different broadcast
layouts (or are gateway-managed) and are out of scope here. Models not listed simply aren't
offered as sensors (no wrong/empty entities)."""

TH_SENSOR_SKUS = (
    "H5051", "H5052", "H5053", "H5071", "H5072", "H5074", "H5075", "H5100",
    "H5101", "H5102", "H5103", "H5104", "H5105", "H5106", "H5108", "H5110",
    "H5111", "H5174", "H5177", "H5179",
)

# Swisscom InternetBox Integration

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/custom-components/hacs)
![GitHub Release](https://img.shields.io/github/v/release/schmidtfx/swisscom-internetbox-hass)
![GitHub License](https://img.shields.io/github/license/schmidtfx/swisscom-internetbox-hass)

This is the Swisscom InternetBox Integration for Home Assistant.

## Features

- Connects to your local Swisscom InternetBox
- Creates device trackers for devices on your local network
- Creates sensors for the router itself, including current download and upload speed
- Downloadable diagnostics for bug reports, with identifying data redacted

### Sensors

All sensors below are grouped under a single device representing your InternetBox.

| Sensor | Description | Enabled by default |
| :----- | :---------- | :----------------- |
| Connected devices | Number of devices known to the InternetBox | ✅ |
| Online devices | Number of those devices currently active | ✅ |
| Software version | Firmware version reported by the InternetBox (diagnostic) | ✅ |
| Model | Model name reported by the InternetBox (diagnostic) | ✅ |
| Uptime | Uptime of the InternetBox in seconds | ❌ |
| External IP | WAN-side IP address of the InternetBox (diagnostic) | ✅ |
| WAN received | Total bytes received on the WAN interface | ❌ |
| WAN sent | Total bytes sent on the WAN interface | ❌ |
| Download speed | Current WAN download rate, averaged over the poll interval | ✅ |
| Upload speed | Current WAN upload rate, averaged over the poll interval | ✅ |
| Link state | State of the WAN link | ✅ |
| Link type | Type of the WAN link, e.g. fiber or DSL (diagnostic) | ✅ |

**Download speed** and **Upload speed** are derived from the WAN byte counters, so they
need two polls before they report anything and stay *unknown* until then. They are
reported in bytes per second; change the unit per entity under ⚙️ **Settings** ➤
**Unit of measurement** if you prefer Mbit/s.

### Binary sensors

| Binary sensor | Description | Enabled by default |
| :------------ | :---------- | :----------------- |
| WAN connectivity | Whether the WAN link is up, for use in automations | ✅ |

> [!NOTE]
> **Uptime**, **WAN received** and **WAN sent** are disabled by default. They will not
> show up until you enable them, which is expected and not a bug. To enable one, go to
> **Settings** ➤ **Devices & Services** ➤ **Swisscom Internetbox**, open the device, select
> the entity (use the *+n entities not shown* link if needed) and enable it via
> ⚙️ **Settings** ➤ **Enabled**.

## Installation

There are two ways this integration can be installed into Home Assistant.

The easiest and recommended way is to install the integration using HACS, which makes future updates easy to track and install.

Alternatively, installation can be done manually copying the files in this repository into `custom_components` directory in the Home Assistant configuration directory:

1. Open the configuration directory of your Home Assistant installation.
2. If you do not have a custom_components directory, create it.
3. In the custom_components directory, create a new directory called `swisscom_internetbox`.
4. Copy all files from the `custom_components/swisscom_internetbox/` directory in this repository into the `swisscom_internetbox` directory.
5. Restart Home Assistant.
6. Add the integration to Home Assistant (see **Configuration**).

## Configuration Details

Configuration is done through the Home Assistant UI.

To add the integration, go to **Settings** ➤ **Devices & Services** ➤ **Integrations**, click ➕ **Add Integration**, and search for "Swisscom Internetbox".

### Configuration Variables

| Name | Type | Default | Description |
| :--- | :--- | :------ | :---------- |
| `host` | `string` | `internetbox.swisscom.ch` | The hostname of the InternetBox |
| `password` | `string` | `-` | Your InternetBox Password |
| `ssl` | `boolean` | `true` | Whether to use a SSL connection |
| `verify_ssl` | `boolean` | `true` | Whether to use ensure to establish a secure SSL connection |

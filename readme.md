# Swisscom InternetBox Integration

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/custom-components/hacs)
![GitHub Release](https://img.shields.io/github/v/release/schmidtfx/swisscom-internetbox-hass)
![GitHub License](https://img.shields.io/github/license/schmidtfx/swisscom-internetbox-hass)

This is the Swisscom InternetBox Integration for Home Assistant.

## Features

- Connects to your local Swisscom InternetBox
- Creates device trackers for devices on your local network

## Installation

There are two ways this integration can be installed into Home Assistant.

The easiest and recommended way is to install the integration using HACS, which makes future updates easy to track and install.

Alternatively, installation can be done manually copying the files in this repository into `custom_components` directory in the Home Assistant configuration directory:

1. Open the configuration directory of your Home Assistant installation.
2. If you do not have a custom_components directory, create it.
3. In the custom_components directory, create a new directory called `ekz_tariffs`.
4. Copy all files from the `custom_components/ekz_tariffs/` directory in this repository into the `ekz_tariffs` directory.
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

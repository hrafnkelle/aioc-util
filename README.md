# aioc-util

`aioc-util.py` is a command-line tool for configuring the [AIOC](https://github.com/skuep/AIOC)
device, including viewing its internal registers and change them, including setting the PTT source.

## Requirements

- Python 3
- [hid](https://pypi.org/project/hid/) Python package to access the USB HID interface

## Installation

Create and activate a virtual environment, then install dependencies:

```bash
python3 -m venv venv
source venv/bin/activate
pip install hid
```

## Udev rule (Linux)

A udev rule is provided to allow non-root access to the AIOC device. Install it by copying
the file to `/etc/udev/rules.d/`, then reload rules and replug the device:

```bash
sudo cp udev/rules.d/91-aioc.conf /etc/udev/rules.d/
sudo udevadm control --reload
sudo udevadm trigger
# Unplug and replug your AIOC USB device
```

After this, you can run `aioc-util.py` without sudo.

## Windows

On Windows, you need to provide the `hidapi.dll` library. Download the Windows release build of the [hidapi](https://github.com/libusb/hidapi) project (from the Releases page), locate `hidapi.dll`, and copy it into this project's root directory (alongside `aioc-util.py`).

## Usage

```bash
./aioc-util.py --help
```

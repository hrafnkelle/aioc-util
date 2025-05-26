# aioc-util

`aioc-util.py` is a command-line tool for configuring the [AIOC](https://github.com/skuep/AIOC)
device, viewing its internal registers and change them, including setting the PTT source.

This utility is written by Hrafnkell Eiríksson TF3HR based on code from [G1LRO](https://g1lro.uk/?p=676) and from [Simon Küppers/skuep](https://github.com/skuep/AIOC/pull/93#issuecomment-2571321845).

## Requirements

- Python 3
- [hid](https://pypi.org/project/hid/) Python package to access the USB HID interface

## Installation

Clone this repository (or [download it zipped](https://github.com/hrafnkelle/aioc-util/archive/refs/heads/main.zip))
```bash
git clone https://github.com/hrafnkelle/aioc-util.git
```

Create and activate a virtual environment in the cloned repository, then install dependencies:

```bash
cd aioc-util
python3 -m venv venv
source venv/bin/activate
pip install hid
```

A virtual environment is reccomended since the distribution provided HID python module seems to be an older version (at least on Debian/Raspian OS). That way the hid module can be pip installed without affecting the whole system. If you have installed python3-hid or python3-hidapi with apt you may need to uninstall that.<>

## Linux

A udev rule is provided to allow non-root access to the AIOC device. Install it by copying
the file to `/etc/udev/rules.d/`, then reload rules and replug the device:

```bash
sudo cp udev/rules.d/91-aioc.conf /etc/udev/rules.d/
sudo udevadm control --reload
sudo udevadm trigger
```

Unplug and replug your AIOC USB device after installing the rule.

After this, you can run `aioc-util.py` without sudo.

The [libusb/hidapi](https://github.com/libusb/hidapi) project also has a udev rule that could be used.

If needed, install libhidapi-hidraw0 and libhidapi-libusb
```bash
sudo apt install libhidapi-hidraw0 libhidapi-libusb
```

## Windows

On Windows, you need to provide the `hidapi.dll` library. Download the Windows release build of the [hidapi](https://github.com/libusb/hidapi) project (from the Releases page), locate `hidapi.dll`, and copy it into this project's root directory (alongside `aioc-util.py`).

## Usage

List the available command line arguments
```bash
./aioc-util.py --help
```

### Example: Setting VPTT/VCOS control registers

```bash
./aioc-util.py --vptt-lvlctrl 0x80 --vptt-timctrl 10 --vcos-lvlctrl 0xff --vcos-timctrl 20 --store
```

### Example: Accessing an AIOC with custom USB VID/PID

```bash
./aioc-util.py --open-usb 0x1234 0x5678 --dump
```

### Finding the VID/PID

If you need to find the USB Vendor ID (VID) and Product ID (PID) for your device, you can use the following commands:

- **Linux**: use `lsusb` to list USB devices and look for your device’s VID:PID pair.
- **Windows (PowerShell)**:

  ```powershell
  Get-PnpDevice -PresentOnly | Where-Object { $_.InstanceId -like "USB\\VID*" } | Select-Object Name, InstanceId
  ```

## Application examples

You may need to set the AIOC register values to defaults before using the suggestions below.

```bash
./aioc-util.py --defaults 
```


### APRSDroid

To use with [APRSDroid](https://aprsdroid.org/), the virtual PTT should be enabled on the AIOC. This way you don't have to rely on the VOX function of your radio to key the radio for transmission.

```bash
./aioc-util.py --ptt1 VPTT --store
```

### AllStarLink3

It is simple to set up an [AllStarLink](https://www.allstarlink.org/) node with the AIOC. 

Make sure you have a udev rule to allow access to the HID functionality of the AIOC like described above. Set the VCOS_TIMCTRL register to 1500

```bash
./aioc-util.py --vcos-tmctrl 1500 --store
```

ASL3 supports the AIOC on its default USB VID PID values. You can edit the file `/etc/asterisk/res_usbradio.conf` and 
uncomment the line with the AIOC USB VID and PID values. This way you don't have to change the VID and PID so it looks like a CM108 interface. If you would rather change the VID and PID values then you can do that with
```bash
./aioc-util.py --set-usb 0x0d8c 0x000c --store
```


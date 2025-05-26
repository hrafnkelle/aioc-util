import argparse
import os
import sys
from enum import IntEnum, IntFlag
from struct import Struct

# On Windows, ensure hidapi.dll is available
if os.name == "nt":
    import ctypes

    script_dir = os.path.dirname(os.path.abspath(__file__))
    dll_path = os.path.join(script_dir, "hidapi.dll")
    try:
        if os.path.exists(dll_path):
            ctypes.WinDLL(dll_path)
        else:
            ctypes.WinDLL("hidapi.dll")
    except OSError as e:
        print("Could not load hidapi.dll:", e)
        sys.exit(1)

import hid


class Register(IntEnum):
    MAGIC = 0x00
    USBID = 0x08
    AIOC_IOMUX0 = 0x24
    AIOC_IOMUX1 = 0x25
    CM108_IOMUX0 = 0x44
    CM108_IOMUX1 = 0x45
    CM108_IOMUX2 = 0x46
    CM108_IOMUX3 = 0x47
    SERIAL_CTRL = 0x60
    SERIAL_IOMUX0 = 0x64
    SERIAL_IOMUX1 = 0x65
    SERIAL_IOMUX2 = 0x66
    SERIAL_IOMUX3 = 0x67
    VPTT_LVLCTRL = 0x82
    VPTT_TIMCTRL = 0x84
    VCOS_LVLCTRL = 0x92
    VCOS_TIMCTRL = 0x94


class Command(IntFlag):
    NONE = 0x00
    WRITESTROBE = 0x01
    DEFAULTS = 0x10
    RECALL = 0x40
    STORE = 0x80


class PTTSource(IntFlag):
    NONE = 0x00000000
    CM108GPIO1 = 0x00000001
    CM108GPIO2 = 0x00000002
    CM108GPIO3 = 0x00000004
    CM108GPIO4 = 0x00000008
    SERIALDTR = 0x00000100
    SERIALRTS = 0x00000200
    SERIALDTRNRTS = 0x00000400
    SERIALNDTRRTS = 0x00000800
    VPTT = 0x00001000

    def __str__(self):
        name = self.name
        if name is not None:
            return name
        parts = [m.name for m in type(self) if m.value and (m in self)]
        if parts:
            return "|".join(parts)
        return hex(self.value)


class CM108ButtonSource(IntFlag):
    NONE = 0x00000000
    IN1 = 0x00010000
    IN2 = 0x00020000
    VCOS = 0x01000000

    def __str__(self):
        name = self.name
        if name is not None:
            return name
        parts = [m.name for m in type(self) if m.value and (m in self)]
        if parts:
            return "|".join(parts)
        return hex(self.value)


def read(device, address):
    # Set address and read
    request = Struct("<BBBL").pack(0, Command.NONE, address, 0x00000000)
    device.send_feature_report(request)
    data = device.get_feature_report(0, 7)
    _, _, _, value = Struct("<BBBL").unpack(data)
    return value


def write(device, address, value):
    data = Struct("<BBBL").pack(0, Command.WRITESTROBE, address, value)
    device.send_feature_report(data)


def cmd(device, cmd):
    data = Struct("<BBBL").pack(0, cmd, 0x00, 0x00000000)
    device.send_feature_report(data)


def dump(device):
    for r in Register:
        print(f"Reg. {r.name}: {read(device, r.value):08x}")


def parse_args():
    parser = argparse.ArgumentParser(
        description="AIOS utility for configuring AIOC hardware settings.",
        epilog="Example: aioc-util.py --ptt1 VPTT --store",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--defaults", action="store_true", help="Load hardware defaults"
    )
    parser.add_argument("--dump", action="store_true", help="Dump all known registers")
    parser.add_argument(
        "--swap-ptt", action="store_true", help="Swap PTT1/PTT2 sources"
    )
    parser.add_argument("--auto-ptt1", action="store_true", help="Set AutoPTT on PTT1")
    parser.add_argument(
        "--ptt1",
        metavar="SOURCE",
        help='Set arbitrary PTT1 source (e.g. "CM108GPIO1|SERIALDTR")',
    )
    parser.add_argument(
        "--ptt2",
        metavar="SOURCE",
        help='Set arbitrary PTT2 source (e.g. "CM108GPIO2|VPTT")',
    )
    parser.add_argument(
        "--list-ptt-sources",
        action="store_true",
        help="List all possible PTT sources",
    )
    parser.add_argument(
        "--usb",
        nargs=2,
        metavar=("VID", "PID"),
        type=lambda x: int(x, 0),
        help="Set USB VID and PID (hex or decimal)",
    )
    parser.add_argument(
        "--vol-up", metavar="SOURCE", help="Set Volume Up button source"
    )
    parser.add_argument(
        "--vol-dn", metavar="SOURCE", help="Set Volume Down button source"
    )
    parser.add_argument(
        "--vptt-lvlctrl",
        metavar="VALUE",
        type=lambda x: int(x, 0),
        help="Set VPTT_LVLCTRL register (hex or decimal)",
    )
    parser.add_argument(
        "--vptt-timctrl",
        metavar="VALUE",
        type=lambda x: int(x, 0),
        help="Set VPTT_TIMCTRL register (hex or decimal)",
    )
    parser.add_argument(
        "--vcos-lvlctrl",
        metavar="VALUE",
        type=lambda x: int(x, 0),
        help="Set VCOS_LVLCTRL register (hex or decimal)",
    )
    parser.add_argument(
        "--vcos-timctrl",
        metavar="VALUE",
        type=lambda x: int(x, 0),
        help="Set VCOS_TIMCTRL register (hex or decimal)",
    )
    parser.add_argument(
        "--store", action="store_true", help="Store settings into flash"
    )
    return parser.parse_args()


def parse_ptt_source(val):
    parts = val.split("|")
    return sum(PTTSource[p] for p in parts)


def parse_btn_source(val):
    parts = val.split("|")
    return sum(CM108ButtonSource[p] for p in parts)


def main():
    args = parse_args()

    if args.list_ptt_sources:
        for src in PTTSource:
            print(f"{src.name} (0x{src.value:08x})")
        sys.exit(0)

    aioc = hid.Device(vid=0x1209, pid=0x7388)

    magic = Struct("<L").pack(read(aioc, Register.MAGIC))
    if magic != b"AIOC":
        print(f"Unexpected magic: {magic}")
        sys.exit(-1)

    print(f"Manufacturer: {aioc.manufacturer}")
    print(f"Product: {aioc.product}")
    print(f"Serial No: {aioc.serial}")
    print(f"Magic: {magic}")

    if args.defaults:
        print("Loading Defaults...")
        cmd(aioc, Command.DEFAULTS)

    if args.dump:
        dump(aioc)

    ptt1_source = PTTSource(read(aioc, Register.AIOC_IOMUX0))
    ptt2_source = PTTSource(read(aioc, Register.AIOC_IOMUX1))

    print(f"Current PTT1 Source: {ptt1_source}")
    print(f"Current PTT2 Source: {ptt2_source}")

    btn1_source = CM108ButtonSource(read(aioc, Register.CM108_IOMUX0))
    btn2_source = CM108ButtonSource(read(aioc, Register.CM108_IOMUX1))
    btn3_source = CM108ButtonSource(read(aioc, Register.CM108_IOMUX2))
    btn4_source = CM108ButtonSource(read(aioc, Register.CM108_IOMUX3))

    print(f"Current CM108 Button 1 (VolUP) Source: {btn1_source}")
    print(f"Current CM108 Button 2 (VolDN) Source: {btn2_source}")
    print(f"Current CM108 Button 3 (PlbMute) Source: {btn3_source}")
    print(f"Current CM108 Button 4 (RecMute) Source: {btn4_source}")

    if args.swap_ptt:
        p1, p2 = ptt2_source, ptt1_source
        print(f"Setting PTT1 Source to {p1}")
        write(aioc, Register.AIOC_IOMUX0, p1)
        print(f"Setting PTT2 Source to {p2}")
        write(aioc, Register.AIOC_IOMUX1, p2)
        print(f"Now PTT1 Source: {PTTSource(read(aioc, Register.AIOC_IOMUX0))}")
        print(f"Now PTT2 Source: {PTTSource(read(aioc, Register.AIOC_IOMUX1))}")

    if args.auto_ptt1:
        print(f"Setting PTT1 Source to {PTTSource.VPTT}")
        write(aioc, Register.AIOC_IOMUX0, PTTSource.VPTT)
        print(f"Now PTT1 Source: {PTTSource(read(aioc, Register.AIOC_IOMUX0))}")
        print(f"Now PTT2 Source: {PTTSource(read(aioc, Register.AIOC_IOMUX1))}")

    if args.ptt1 or args.ptt2:
        if args.ptt1:
            val1 = parse_ptt_source(args.ptt1)
            print(f"Setting PTT1 Source to {PTTSource(val1)}")
            write(aioc, Register.AIOC_IOMUX0, PTTSource(val1))
        if args.ptt2:
            val2 = parse_ptt_source(args.ptt2)
            print(f"Setting PTT2 Source to {PTTSource(val2)}")
            write(aioc, Register.AIOC_IOMUX1, PTTSource(val2))
        print(f"Now PTT1 Source: {PTTSource(read(aioc, Register.AIOC_IOMUX0))}")
        print(f"Now PTT2 Source: {PTTSource(read(aioc, Register.AIOC_IOMUX1))}")

    if args.usb:
        vid, pid = args.usb
        value = (pid << 16) | (vid << 0)
        write(aioc, Register.USBID, value)
        print(f"Now USBID: {read(aioc, Register.USBID):08x}")

    if args.vol_up or args.vol_dn:
        if args.vol_up:
            su = parse_btn_source(args.vol_up)
            print(f"Setting VolUP button source to {CM108ButtonSource(su)}")
            write(aioc, Register.CM108_IOMUX0, CM108ButtonSource(su))
        if args.vol_dn:
            sd = parse_btn_source(args.vol_dn)
            print(f"Setting VolDN button source to {CM108ButtonSource(sd)}")
            write(aioc, Register.CM108_IOMUX1, CM108ButtonSource(sd))
        print(
            f"Now VolUP button source: {CM108ButtonSource(read(aioc, Register.CM108_IOMUX0))}"
        )
        print(
            f"Now VolDN button source: {CM108ButtonSource(read(aioc, Register.CM108_IOMUX1))}"
        )

    if args.vptt_lvlctrl is not None:
        print(f"Setting VPTT_LVLCTRL to {args.vptt_lvlctrl:#x}")
        write(aioc, Register.VPTT_LVLCTRL, args.vptt_lvlctrl)
        print(f"Now VPTT_LVLCTRL: {read(aioc, Register.VPTT_LVLCTRL):08x}")

    if args.vptt_timctrl is not None:
        print(f"Setting VPTT_TIMCTRL to {args.vptt_timctrl:#x}")
        write(aioc, Register.VPTT_TIMCTRL, args.vptt_timctrl)
        print(f"Now VPTT_TIMCTRL: {read(aioc, Register.VPTT_TIMCTRL):08x}")

    if args.vcos_lvlctrl is not None:
        print(f"Setting VCOS_LVLCTRL to {args.vcos_lvlctrl:#x}")
        write(aioc, Register.VCOS_LVLCTRL, args.vcos_lvlctrl)
        print(f"Now VCOS_LVLCTRL: {read(aioc, Register.VCOS_LVLCTRL):08x}")

    if args.vcos_timctrl is not None:
        print(f"Setting VCOS_TIMCTRL to {args.vcos_timctrl:#x}")
        write(aioc, Register.VCOS_TIMCTRL, args.vcos_timctrl)
        print(f"Now VCOS_TIMCTRL: {read(aioc, Register.VCOS_TIMCTRL):08x}")

    if args.store:
        print("Storing...")
        cmd(aioc, Command.STORE)


if __name__ == "__main__":
    main()

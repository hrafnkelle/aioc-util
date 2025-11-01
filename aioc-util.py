#!/usr/bin/env python3

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

AIOC_VID = 0x1209
AIOC_PID = 0x7388


class StrIntFlag(IntFlag):
    def __str__(self):
        name = self.name
        if name is not None:
            return name
        parts = [m.name for m in type(self) if m.value and (m in self)]
        if parts:
            return "|".join(parts)
        return hex(self.value)


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
    AUDIO_RX = 0x72
    AUDIO_TX = 0x78
    VPTT_LVLCTRL = 0x82
    VPTT_TIMCTRL = 0x84
    VCOS_LVLCTRL = 0x92
    VCOS_TIMCTRL = 0x94
    FOXHUNT_CTRL = 0xA0
    FOXHUNT_MSG0 = 0xA2
    FOXHUNT_MSG1 = 0xA3
    FOXHUNT_MSG2 = 0xA4
    FOXHUNT_MSG3 = 0xA5


class Command(IntFlag):
    NONE = 0x00
    WRITESTROBE = 0x01
    DEFAULTS = 0x10
    REBOOT = 0x20
    RECALL = 0x40
    STORE = 0x80


class PTTSource(StrIntFlag):
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

class PTTChannel(IntEnum):
    PTT1 = 3
    PTT2 = 4


class CM108ButtonSource(StrIntFlag):
    NONE = 0x00000000
    IN1 = 0x00010000
    IN2 = 0x00020000
    VCOS = 0x01000000

class TXBoost(IntEnum):
   TXBOOSTOFF = 0x00000000
   TXBOOSTON = 0x00000100


class RXGain(IntEnum):
    RXGAIN1X = 0x00000000
    RXGAIN2X = 0x00000001
    RXGAIN4X = 0x00000002
    RXGAIN8X = 0x00000003
    RXGAIN16X = 0x00000004


def read(device, address):
    # Set address and read
    request = Struct("<BBBL").pack(0, Command.NONE, address, 0x00000000)
    device.send_feature_report(request)
    data = device.get_feature_report(0, 7)
    _, _, _, value = Struct("<BBBL").unpack(data)
    return value


def write_feat_report(device, address, value):
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
        description="Utility for viewining configuring AIOC hardware settings.",
        epilog="Example: aioc-util.py --ptt1 VPTT --store",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--defaults", action="store_true", help="Load hardware defaults"
    )
    parser.add_argument("--reboot", action="store_true", help="Reboot the device")
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
        "--set-usb",
        nargs=2,
        metavar=("VID", "PID"),
        type=lambda x: int(x, 0),
        help="Set USB VID and PID (hex or decimal)",
    )
    parser.add_argument(
        "--open-usb",
        nargs=2,
        metavar=("VID", "PID"),
        type=lambda x: int(x, 0),
        help="USB VID and PID to use when opening the device (hex or decimal)",
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
    parser.add_argument(
        "--set-ptt1-state",
        metavar="STATE",
        choices=["on", "off"],
        help="Set PTT1 state via raw HID write: 'on' or 'off'",
    )
    parser.add_argument(
        "--set-ptt2-state",
        metavar="STATE",
        choices=["on", "off"],
        help="Set PTT2 state via raw HID write: 'on' or 'off'",
    )
    parser.add_argument(
        "--enable-hwcos",
        action="store_true",
        help="Enable hardware COS (needs an AIOC that supports it)",
    )
    parser.add_argument(
        "--enable-vcos",
        action="store_true",
        help="Enable virtual COS (default behavior)",
    )
    parser.add_argument(
        "--foxhunt-volume",
        metavar="VOLUME",
        type=lambda x: int(x, 0),
        help="Set foxhunt volume (0-65535)",
    )
    parser.add_argument(
        "--foxhunt-wpm",
        metavar="WPM",
        type=lambda x: int(x, 0),
        help="Set foxhunt words per minute (0-255)",
    )
    parser.add_argument(
        "--foxhunt-interval",
        metavar="INTERVAL",
        type=lambda x: int(x, 0),
        help="Set foxhunt interval in seconds (0-255)",
    )
    parser.add_argument(
        "--foxhunt-get-settings",
        action="store_true",
        help="Read and display current foxhunt control settings",
    )
    parser.add_argument(
        "--foxhunt-message",
        metavar="MESSAGE",
        help="Set foxhunt message (up to 16 characters, will be padded with nulls)",
    )
    parser.add_argument(
        "--foxhunt-get-message",
        action="store_true",
        help="Read and display current foxhunt message",
    )
    parser.add_argument(
        "--audio-rx-gain",
        metavar="GAIN",
        choices=["1x", "2x", "4x", "8x", "16x"],
        help="Set audio RX gain: 1x, 2x, 4x, 8x, or 16x",
    )
    parser.add_argument(
        "--audio-tx-boost",
        metavar="BOOST",
        choices=["off", "on"],
        help="Set audio TX boost: off or on",
    )
    parser.add_argument(
        "--audio-get-settings",
        action="store_true",
        help="Read and display current audio RX gain and TX boost settings",
    )

    args = parser.parse_args()
    if len(sys.argv) == 1:
        parser.print_help(sys.stderr)
        sys.exit(1)
    return args


def parse_ptt_source(val):
    parts = val.split("|")
    return sum(PTTSource[p] for p in parts)


def parse_btn_source(val):
    parts = val.split("|")
    return sum(CM108ButtonSource[p] for p in parts)


def set_ptt_state_raw(device, pin_num, state_on):
    state = 1 if state_on else 0
    iomask = 1 << (pin_num - 1)
    iodata = state << (pin_num - 1)
    data = Struct("<BBBBB").pack(0, 0, iodata, iomask, 0)
    device.write(bytes(data))


def main():
    args = parse_args()

    if args.list_ptt_sources:
        for src in PTTSource:
            print(f"{src.name} (0x{src.value:08x})")
        sys.exit(0)

    if args.open_usb:
        vid_open, pid_open = args.open_usb
    else:
        vid_open, pid_open = AIOC_VID, AIOC_PID
    try:
        aioc = hid.Device(vid=vid_open, pid=pid_open)
    except (OSError, hid.HIDException) as e:
        print(
            f"Could not open AIOC device (VID: {vid_open:#06x}, PID: {pid_open:#06x}):",
            e,
        )
        sys.exit(1)

    magic = Struct("<L").pack(read(aioc, Register.MAGIC))
    if magic != b"AIOC":
        print(f"Unexpected magic: {magic}")
        sys.exit(-1)

    if args.defaults:
        print("Loading Defaults...")
        cmd(aioc, Command.DEFAULTS)

    if args.dump:
        print(f"Manufacturer: {aioc.manufacturer}")
        print(f"Product: {aioc.product}")
        print(f"Serial No: {aioc.serial}")
        print(f"Magic: {magic}")

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

        dump(aioc)


    if args.swap_ptt:
        p1, p2 = ptt2_source, ptt1_source
        print(f"Setting PTT1 Source to {p1}")
        write_feat_report(aioc, Register.AIOC_IOMUX0, p1)
        print(f"Setting PTT2 Source to {p2}")
        write_feat_report(aioc, Register.AIOC_IOMUX1, p2)
        print(f"Now PTT1 Source: {PTTSource(read(aioc, Register.AIOC_IOMUX0))}")
        print(f"Now PTT2 Source: {PTTSource(read(aioc, Register.AIOC_IOMUX1))}")

    if args.auto_ptt1:
        print(f"Setting PTT1 Source to {PTTSource.VPTT}")
        write_feat_report(aioc, Register.AIOC_IOMUX0, PTTSource.VPTT)
        print(f"Now PTT1 Source: {PTTSource(read(aioc, Register.AIOC_IOMUX0))}")
        print(f"Now PTT2 Source: {PTTSource(read(aioc, Register.AIOC_IOMUX1))}")

    if args.ptt1 or args.ptt2:
        if args.ptt1:
            val1 = parse_ptt_source(args.ptt1)
            print(f"Setting PTT1 Source to {PTTSource(val1)}")
            write_feat_report(aioc, Register.AIOC_IOMUX0, PTTSource(val1))
        if args.ptt2:
            val2 = parse_ptt_source(args.ptt2)
            print(f"Setting PTT2 Source to {PTTSource(val2)}")
            write_feat_report(aioc, Register.AIOC_IOMUX1, PTTSource(val2))
        print(f"Now PTT1 Source: {PTTSource(read(aioc, Register.AIOC_IOMUX0))}")
        print(f"Now PTT2 Source: {PTTSource(read(aioc, Register.AIOC_IOMUX1))}")

    if args.set_usb:
        vid, pid = args.set_usb
        value = (pid << 16) | (vid << 0)
        write_feat_report(aioc, Register.USBID, value)
        print(f"Now USBID: {read(aioc, Register.USBID):08x}")

    if args.vol_up or args.vol_dn:
        if args.vol_up:
            su = parse_btn_source(args.vol_up)
            print(f"Setting VolUP button source to {CM108ButtonSource(su)}")
            write_feat_report(aioc, Register.CM108_IOMUX0, CM108ButtonSource(su))
        if args.vol_dn:
            sd = parse_btn_source(args.vol_dn)
            print(f"Setting VolDN button source to {CM108ButtonSource(sd)}")
            write_feat_report(aioc, Register.CM108_IOMUX1, CM108ButtonSource(sd))
        print(
            f"Now VolUP button source: {CM108ButtonSource(read(aioc, Register.CM108_IOMUX0))}"
        )
        print(
            f"Now VolDN button source: {CM108ButtonSource(read(aioc, Register.CM108_IOMUX1))}"
        )

    if args.vptt_lvlctrl is not None:
        print(f"Setting VPTT_LVLCTRL to {args.vptt_lvlctrl:#x}")
        write_feat_report(aioc, Register.VPTT_LVLCTRL, args.vptt_lvlctrl)
        print(f"Now VPTT_LVLCTRL: {read(aioc, Register.VPTT_LVLCTRL):08x}")

    if args.vptt_timctrl is not None:
        print(f"Setting VPTT_TIMCTRL to {args.vptt_timctrl:#x}")
        write_feat_report(aioc, Register.VPTT_TIMCTRL, args.vptt_timctrl)
        print(f"Now VPTT_TIMCTRL: {read(aioc, Register.VPTT_TIMCTRL):08x}")

    if args.vcos_lvlctrl is not None:
        print(f"Setting VCOS_LVLCTRL to {args.vcos_lvlctrl:#x}")
        write_feat_report(aioc, Register.VCOS_LVLCTRL, args.vcos_lvlctrl)
        print(f"Now VCOS_LVLCTRL: {read(aioc, Register.VCOS_LVLCTRL):08x}")

    if args.vcos_timctrl is not None:
        print(f"Setting VCOS_TIMCTRL to {args.vcos_timctrl:#x}")
        write_feat_report(aioc, Register.VCOS_TIMCTRL, args.vcos_timctrl)
        print(f"Now VCOS_TIMCTRL: {read(aioc, Register.VCOS_TIMCTRL):08x}")

    if args.enable_hwcos:
        print("Enabling hardware COS (if your aioc supports it)...")
        write_feat_report(aioc, Register.CM108_IOMUX0, CM108ButtonSource.NONE)
        write_feat_report(aioc, Register.CM108_IOMUX1, CM108ButtonSource.IN2)
        print(f"Now CM108_IOMUX0: {CM108ButtonSource(read(aioc, Register.CM108_IOMUX0))}")
        print(f"Now CM108_IOMUX1: {CM108ButtonSource(read(aioc, Register.CM108_IOMUX1))}")

    if args.enable_vcos:
        print("Enabling virtual COS...")
        write_feat_report(aioc, Register.CM108_IOMUX0, CM108ButtonSource.IN2)
        write_feat_report(aioc, Register.CM108_IOMUX1, CM108ButtonSource.VCOS)
        print(f"Now CM108_IOMUX0: {CM108ButtonSource(read(aioc, Register.CM108_IOMUX0))}")
        print(f"Now CM108_IOMUX1: {CM108ButtonSource(read(aioc, Register.CM108_IOMUX1))}")

    # Read and display foxhunt settings
    if args.foxhunt_get_settings:
        current_foxhunt = read(aioc, Register.FOXHUNT_CTRL)
        current_volume = (current_foxhunt >> 16) & 0xFFFF
        current_wpm = (current_foxhunt >> 8) & 0xFF
        current_interval = (current_foxhunt >> 0) & 0xFF
        print(f"Current foxhunt settings:")
        print(f"  Volume: {current_volume}")
        print(f"  WPM: {current_wpm}")
        print(f"  Interval: {current_interval} seconds")
        print(f"  Raw register: {current_foxhunt:08x}")

    # Read and display foxhunt message
    if args.foxhunt_get_message:
        msg_registers = [
            Register.FOXHUNT_MSG0,
            Register.FOXHUNT_MSG1,
            Register.FOXHUNT_MSG2,
            Register.FOXHUNT_MSG3
        ]
        
        # Read all 4 message registers and convert to bytes
        message_bytes = bytearray()
        print(f"Current foxhunt message registers:")
        for i, reg in enumerate(msg_registers):
            uint32_val = read(aioc, reg)
            # Convert uint32 to 4 bytes (little-endian)
            reg_bytes = uint32_val.to_bytes(4, byteorder='little')
            message_bytes.extend(reg_bytes)
            print(f"  MSG{i}: {uint32_val:08x} ('{reg_bytes.decode('ascii', errors='replace')}')")
        
        # Convert bytes to string, stopping at first null byte
        try:
            null_index = message_bytes.index(0)
            message_str = message_bytes[:null_index].decode('ascii', errors='replace')
        except ValueError:
            # No null byte found, use entire 16 bytes
            message_str = message_bytes.decode('ascii', errors='replace')
        
        print(f"Current foxhunt message: '{message_str}'")

    # Handle foxhunt control register
    if args.foxhunt_volume is not None or args.foxhunt_wpm is not None or args.foxhunt_interval is not None:
        # Read current values
        current_foxhunt = read(aioc, Register.FOXHUNT_CTRL)
        current_volume = (current_foxhunt >> 16) & 0xFFFF
        current_wpm = (current_foxhunt >> 8) & 0xFF
        current_interval = (current_foxhunt >> 0) & 0xFF
        
        # Use new values if provided, otherwise keep current values
        new_volume = args.foxhunt_volume if args.foxhunt_volume is not None else current_volume
        new_wpm = args.foxhunt_wpm if args.foxhunt_wpm is not None else current_wpm
        new_interval = args.foxhunt_interval if args.foxhunt_interval is not None else current_interval
        
        # Pack new values and write
        new_foxhunt = (new_volume << 16) | (new_wpm << 8) | (new_interval << 0)
        print(f"Setting FOXHUNT_CTRL: volume={new_volume}, wpm={new_wpm}, interval={new_interval}")
        write_feat_report(aioc, Register.FOXHUNT_CTRL, new_foxhunt)
        print(f"Now FOXHUNT_CTRL: {read(aioc, Register.FOXHUNT_CTRL):08x}")

    # Handle foxhunt message
    if args.foxhunt_message is not None:
        # Convert string to bytes and pad/truncate to 16 bytes
        message_bytes = args.foxhunt_message.encode('ascii', errors='replace')[:16]
        message_bytes = message_bytes.ljust(16, b'\x00')  # Pad with nulls to 16 bytes
        
        # Convert 16 bytes to 4 uint32 values (little-endian)
        msg_registers = [
            Register.FOXHUNT_MSG0,
            Register.FOXHUNT_MSG1, 
            Register.FOXHUNT_MSG2,
            Register.FOXHUNT_MSG3
        ]
        
        print(f"Setting foxhunt message: '{args.foxhunt_message}'")
        for i in range(4):
            # Extract 4 bytes and convert to uint32 (little-endian)
            byte_offset = i * 4
            uint32_val = int.from_bytes(message_bytes[byte_offset:byte_offset+4], byteorder='little')
            write_feat_report(aioc, msg_registers[i], uint32_val)
            print(f"  MSG{i}: {uint32_val:08x} ('{message_bytes[byte_offset:byte_offset+4].decode('ascii', errors='replace')}')")

    # Read and display audio settings
    if args.audio_get_settings:
        current_rx = read(aioc, Register.AUDIO_RX)
        current_tx = read(aioc, Register.AUDIO_TX)
        
        # Map RX gain values back to readable names
        rx_gain_names = {
            RXGain.RXGAIN1X: "1x",
            RXGain.RXGAIN2X: "2x", 
            RXGain.RXGAIN4X: "4x",
            RXGain.RXGAIN8X: "8x",
            RXGain.RXGAIN16X: "16x"
        }
        
        # Map TX boost values back to readable names
        tx_boost_names = {
            TXBoost.TXBOOSTOFF: "off",
            TXBoost.TXBOOSTON: "on"
        }
        
        rx_gain_name = rx_gain_names.get(RXGain(current_rx), f"unknown ({current_rx:08x})")
        tx_boost_name = tx_boost_names.get(TXBoost(current_tx), f"unknown ({current_tx:08x})")
        
        print(f"Current audio settings:")
        print(f"  RX Gain: {rx_gain_name}")
        print(f"  TX Boost: {tx_boost_name}")
        print(f"  Raw AUDIO_RX: {current_rx:08x}")
        print(f"  Raw AUDIO_TX: {current_tx:08x}")

    # Handle audio RX gain
    if args.audio_rx_gain is not None:
        gain_map = {
            "1x": RXGain.RXGAIN1X,
            "2x": RXGain.RXGAIN2X,
            "4x": RXGain.RXGAIN4X,
            "8x": RXGain.RXGAIN8X,
            "16x": RXGain.RXGAIN16X
        }
        rxgain = gain_map[args.audio_rx_gain]
        print(f"Setting Audio RX gain to {rxgain.name}")
        write_feat_report(aioc, Register.AUDIO_RX, rxgain)
        print(f"Now AUDIO_RX: {read(aioc, Register.AUDIO_RX):08x}")

    # Handle audio TX boost
    if args.audio_tx_boost is not None:
        boost_map = {
            "off": TXBoost.TXBOOSTOFF,
            "on": TXBoost.TXBOOSTON
        }
        txboost = boost_map[args.audio_tx_boost]
        print(f"Setting Audio TX boost to {txboost.name}")
        write_feat_report(aioc, Register.AUDIO_TX, txboost)
        print(f"Now AUDIO_TX: {read(aioc, Register.AUDIO_TX):08x}")

    if args.store:
        print("Storing...")
        cmd(aioc, Command.STORE)

    if args.set_ptt1_state:
        set_ptt_state_raw(aioc, PTTChannel.PTT1, args.set_ptt1_state == "on")

    if args.set_ptt2_state:
        set_ptt_state_raw(aioc, PTTChannel.PTT2, args.set_ptt2_state == "on")

    if args.reboot:
        print("Rebooting device...")
        cmd(aioc, Command.REBOOT)


if __name__ == "__main__":
    main()

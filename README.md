# joycontrol

Emulate Nintendo Switch Controllers over Bluetooth.

Tested on Ubuntu 19.10, and with Raspberry Pi 3B+ and 4B Raspbian GNU/Linux 10 (buster)

## Features

Emulation of JOYCON_R, JOYCON_L and PRO_CONTROLLER. Able to send:

- button commands
- stick state
- ~~nfc data~~ (removed, see [#80](https://github.com/mart1nro/joycontrol/issues/80))

## Installation

- Install dependencies

Ubuntu: Install the `dbus-python` and `libhidapi-hidraw0` packages

```bash
sudo apt install python3-dbus libhidapi-hidraw0
```

Arch Linux Derivatives: Install the `hidapi` and `bluez-utils-compat`(AUR) packages

- Clone the repository and install the joycontrol package to get missing dependencies (Note: Controller script needs super user rights, so python packages must be installed as root). In the joycontrol folder run:

```bash
sudo pip3 install .
```

- Consider to disable the bluez "input" plugin, see [#8](https://github.com/mart1nro/joycontrol/issues/8)

## Command line interface example

- Run the script

```bash
sudo python3 run_controller_cli.py PRO_CONTROLLER
```

This will create a `PRO_CONTROLLER` instance waiting for the Switch to connect. Alternative options are `JOYCON_R` and `JOYCON_L`.

- Open the "Change Grip/Order" menu of the Switch

The Switch only pairs with new controllers in the "Change Grip/Order" menu.

Note: If you already connected an emulated controller once, you can use the reconnect option, where `AA:BB:CC:DD:EE:FF` is your Switch's Bluetooth MAC address:

```bash
sudo python3 run_controller_cli.py -r AA:BB:CC:DD:EE:FF PRO_CONTROLLER
```

This does not require the "Change Grip/Order" menu to be opened. You can find out a paired MAC address using the `bluetoothctl` system command.

- After connecting, a command line interface is opened. Note: Press <kbd>Enter</kbd> if you don't see a prompt (`cmd >>`).

Call `help` to see a list of available commands.

- If you call `test_buttons`, the emulated controller automatically navigates to the "Test Controller Buttons" menu.

## Syntax

The following syntax is written in [EBNF](https://en.wikipedia.org/wiki/Extended_Backus%E2%80%93Naur_form):

```ebnf
command = [ wp ] , ( special_command | button_command | stick_command | mash_command | hold_or_release_command | nfc_command ) , [ wp ] , { "&&" , command } ;

special_command = "help" | "test_buttons" ;
button_command = button ;
stick_command = "stick" , wp , stick_side , wp , ( stick_direction | stick_finetune ) ;
mash_command = "mash" , wp , button , wp , interval ;
hold_or_release_command = ( "hold" | "release" ) , wp , button , { wp , button } ;
nfc_command = "nfc" , wp , ( file_name | "remove" ) ; (* No-op. See #80 *)

stick_side = "l" | "left" | "r" | "right" ; (* No difference between l and left, and r and right *)
stick_direction = "center" | "up" | "down" | "left" | "right" ;
stick_finetune = ( "h" | "v" ) , wp , stick_value ;

button = "a" | "b" | "x" | "y" | "up" | "down" | "left" | "right" | "l_stick" | "r_stick" | "l" | "r" | "zl" | "zr" | "minus" | "plus" | "home" | "capture" ;
interval = number ;
wp = wp_char , { wp_char }
```

Some notes:

- `wp_char` means "a space or a tab character" and `wp` means any sequence of these characters. Furthermore, `[ wp ]` means "optional whitespace".
- Commands can be "chained together" using `&&`. `cmd1 && cmd2` will send `cmd1` first and then `cmd2`.
- `file_name` is a valid path to an existing file (e.g., `Amiibo.bin`, `/home/user/Desktop/Some\ file\ with\ spaces.bin`, or `../../Downloads/Not_bin.txt`).
- `number` is any valid number written in decimal notation. That is, `3`, `0.5`, and `-3.14` are valid `number`s, while `0x0F` isn't.
- `stick_value` is an integer in the range `[0, 4096)`. That is, it is between `0` and `4095`.
  A stick's position is in the form `(h, v)`, where `h` represents its position in the horizontal axis, and `v` its position in the vertical axis.
  For example, `(0, 0)`, `(4095, 4095)`, and `(2048, 2048)` represent the stick at the extreme down-left, extreme up-right, and at rest.
- `stick_direction`'s `"center"`, `"up"`, `"down"`, `"left"`, and `"right"` signal that the stick is at position `(2048, 2048)`, `(2048, 3840)`, `(2048, 256)`, `(256, 2048)`, and `(3840, 2048)` respectively.
- Setting `interval` to zero or negative will cause `mash_command` to mash the button as fast as it can. Note that the interval here refers to seconds.
  Note as well that it is possible to have a "delay" when it comes to mashing a button, as the controller communicates with the Switch every time it presses a button.
- Mashing a button is different from holding a button.
  The former is essentially a `button_command` repeated after every `interval`. The latter tells the Switch that a button is being continuously *held*.
- Holding a button that has been previously held down is a no-op. Similarly, releasing a button that wasn't held beforehand is a no-op.

## Issues

- Some bluetooth adapters seem to cause disconnects for reasons unknown. Try to use a USB adapter instead.
- Incompatibility with Bluetooth "input" plugin requires a bluetooth restart. See [#8](https://github.com/mart1nro/joycontrol/issues/8)
- It seems like the Switch is slower processing incoming messages while in the "Change Grip/Order" menu.
  This causes flooding of packets and makes pairing somewhat inconsistent.
  Not sure yet what exactly a real controller does to prevent that.
  A workaround is to use the reconnect option after a controller was paired once, so that
  opening of the "Change Grip/Order" menu is not required.
- ...

## Thanks

- Special thanks to <https://github.com/dekuNukem/Nintendo_Switch_Reverse_Engineering> for reverse engineering of the joycon protocol
- Thanks to the growing number of contributers and users

## Resources

- [Nintendo_Switch_Reverse_Engineering](https://github.com/dekuNukem/Nintendo_Switch_Reverse_Engineering)
- [console_pairing_session](https://github.com/timmeh87/switchnotes/blob/master/console_pairing_session)

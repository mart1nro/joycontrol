# joycontrol
Emulate Nintendo Switch Controllers over Bluetooth.

Work in progress.

Pairing works, emulated controller shows up in the "Change Grip/Order" menu of the Switch.

Tested on Ubuntu 19.10 and with Raspberry Pi 4B Raspbian GNU/Linux 10 (buster)

## Installation
- Install dbus-python package
```bash
sudo apt install python3-dbus
```
- Clone the repository and install the joycontrol package to get missing dependencies (Note: Controller script needs super user rights, so python packages must be installed as root). In the joycontrol folder run:
```bash
sudo pip3 install .
```

## "Test Controller Buttons" example
- Run the script
```bash
sudo python3 run_test_controller_buttons.py
```
- Open the "Change Grip/Order" menu of the Switch
- The emulated controller should pair with the Switch and automatically navigate to the "Test Controller Buttons" menu

## Issues
- When using a Raspberry Pi 4B the connection drops after some time. Might be a hardware issue, since it works fine on my laptop. Using a different bluetooth adapter may help, but haven't tested it yet.
- Incompatibility with Bluetooth "input" plugin, see [#8](https://github.com/mart1nro/joycontrol/issues/8)
- ...


## Resources

[Nintendo_Switch_Reverse_Engineering](https://github.com/dekuNukem/Nintendo_Switch_Reverse_Engineering)

[console_pairing_session](https://github.com/timmeh87/switchnotes/blob/master/console_pairing_session)

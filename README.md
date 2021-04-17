# joycontrol

Branch: master->amiibo_edits->amiibo_writing->V12_fixes

Emulate Nintendo Switch Controllers over Bluetooth.

Tested on Raspberry 4B Raspbian, should work on 3B+ too and anything that can do the setup.

## Features
Emulation of JOYCON_R, JOYCON_L and PRO_CONTROLLER. Able to send:
- button commands
- stick state
- nfc data read

## Installation
- Install dependencies

Raspbian:
```bash
sudo apt install python3-dbus libhidapi-hidraw0 libbluetooth-dev
```

Python: (a setup.py is present but not yet up to date)
```bash
sudo pip3 install aioconsole hid crc8
```

- setup bluetooth
	- change MAC to be in Nintendos range (starts with 94:58:CB)  
	for raspi 3B+ and 4B you can use `sudo ./scrips/change_btaddr.sh`  
	rerun after every reboot
	- disable SPD  
	change the `ExecStart` paramters in `/lib/systemd/system/bluetooth.service` to `ExecStart=/usr/lib/bluetooth/bluetoothd -C -P sap,input,avrcp`
	- change alias  
	`sudo bluetoothctl system-alias 'Pro Controller'`  
	Joycons are untested yet, might work might not....

## Command line interface example
- Run the script
```bash
sudo python3 run_controller_cli.py PRO_CONTROLLER
```
This will create a PRO_CONTROLLER instance waiting for the Switch to connect.

- Open the "Change Grip/Order" menu of the Switch

The Switch only pairs with new controllers in the "Change Grip/Order" menu.

After pairing the switch will most certanly just disconnect for some reason.
Use the reconnect option to avoid this afterwards.

Note: If you already connected an emulated controller once, you can use the reconnect option of the script (-r "\<Switch Bluetooth Mac address>").
This does not require the "Change Grip/Order" menu to be opened. You can find out a paired mac address using the "bluetoothctl" system command.

- After connecting, a command line interface is opened. Note: Press \<enter> if you don't see a prompt.

Call "help" to see a list of available commands.

- If you call "test_buttons", the emulated controller automatically navigates to the "Test Controller Buttons" menu. 


## Issues
- Some bluetooth adapters seem to cause disconnects for reasons unknown, try to use an usb adapter instead 
- Incompatibility with Bluetooth "input" plugin requires a bluetooth restart, see [#8](https://github.com/mart1nro/joycontrol/issues/8)
- It seems like the Switch is slower processing incoming messages while in the "Change Grip/Order" menu.
  This causes flooding of packets and makes input after initial pairing somewhat inconsistent.
  Not sure yet what exactly a real controller does to prevent that.
  A workaround is to use the reconnect option after a controller was paired once, so that
  opening of the "Change Grip/Order" menu is not required.
- ...

## Thanks
- Special thanks to https://github.com/dekuNukem/Nintendo_Switch_Reverse_Engineering for reverse engineering of the joycon protocol
- Thanks to the growing number of contributers and users

## Resources

[Nintendo_Switch_Reverse_Engineering](https://github.com/dekuNukem/Nintendo_Switch_Reverse_Engineering)

[console_pairing_session](https://github.com/timmeh87/switchnotes/blob/master/console_pairing_session)

[V12 Issues thread](https://github.com/Poohl/joycontrol/issues/3)

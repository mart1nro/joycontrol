# joycontrol
Emulate Nintendo Switch Controllers over Bluetooth.

Work in progress.

Pairing works, emulated controller shows up in the "Change Grip/Order" menu of the Switch.

Tested with Raspberry Pi 4B Raspbian GNU/Linux 10 (buster)

- Start the program
```bash
sudo python3 run_test_controller_buttons.py
```
- Open the "Change Grip/Order" menu of the Switch
- The emulated controller pairs with the Switch and automatically navigates to the "Test Controller Buttons" menu




# Resources

[Nintendo_Switch_Reverse_Engineering](https://github.com/dekuNukem/Nintendo_Switch_Reverse_Engineering)

[console_pairing_session](https://github.com/timmeh87/switchnotes/blob/master/console_pairing_session)

[bluez-ns-controller](https://github.com/mumumusuc/bluez-ns-controller)

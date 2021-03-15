# realod systemd config changed by reconfigure
systemctl daemon-reload

# restart bluez with the new settings
systemctl restart bluetooth.service

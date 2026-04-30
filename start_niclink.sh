#!/bin/bash
sudo systemctl stop ModemManager
cd ~/NicLink
source venv/bin/activate
python -m nicsoft.play_menu

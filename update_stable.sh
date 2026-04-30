#!/bin/bash
rsync -a --exclude=venv ~/NicLink/ ~/NicLink_stable/
echo "NicLink_stable mis à jour."

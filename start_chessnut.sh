#!/bin/bash

cd ~/NicLink || exit

source venv/bin/activate

python -m nicsoft.play_stockfish

#!/bin/bash

if [ -f db/db.json ]; then
    pysondb create db/db.json
    pysondb create db/channels.json
fi

python main.py

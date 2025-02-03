#!/bin/bash

if [ -f db/db.json ]; then
    pysondb create db/db.json
fi

python main.py

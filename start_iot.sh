#!/bin/bash
cd /home/iot/ws/iot-azure

# Activate virtual environment
source /home/iot/ws/iot-azure/venv/bin/activate

# Run your Python app
python3 azure-iot-thread-simple.py

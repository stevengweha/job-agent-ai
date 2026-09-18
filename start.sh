#!/bin/bash

# Lance le script principal en arrière-plan
python src/main.py &

# Lance LangGraph Studio au premier plan (garde le conteneur vivant)
exec langgraph dev --host 0.0.0.0 --port 2024
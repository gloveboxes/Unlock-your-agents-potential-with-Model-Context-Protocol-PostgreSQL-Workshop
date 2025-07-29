#!/usr/bin/env bash

echo "Searching for processes using ports 6277 and 6274..."

# Function to find and kill processes on a specific port
kill_process_on_port() {
    local port=$1
    echo "Looking for processes on port $port..."
    
    # Find PIDs of processes using the port
    pids=$(lsof -ti :$port)
    
    if [ -z "$pids" ]; then
        echo "No processes found using port $port"
    else
        echo "Found processes with PIDs: $pids using port $port"
        echo "Killing processes..."
        
        # Kill each process
        for pid in $pids; do
            echo "Killing process $pid..."
            kill -9 $pid
            if [ $? -eq 0 ]; then
                echo "Process $pid successfully terminated"
            else
                echo "Failed to kill process $pid"
            fi
        done
    fi
}

# Kill processes on both ports
kill_process_on_port 6277
kill_process_on_port 6274

echo "Done."

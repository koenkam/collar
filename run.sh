git pull
while true; do
    python3 run.py
    # if there is an error, exit the while loop
    if [ $? -ne 0 ]; then
        break
    fi
    sleep 1
done

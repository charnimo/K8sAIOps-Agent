import requests
import json

url = "http://127.0.0.1:8000/api/v1/resources/pods/default/my-pod/metrics/history?metric=cpu&duration_mins=5&step=15s"
try:
    print("Testing metrics API...")
    # Get a real pod name first
    pods_res = requests.get("http://127.0.0.1:8000/api/v1/resources/pods?namespace=default")
    if pods_res.status_code == 200 and pods_res.json():
        pods = pods_res.json()
        running_pods = [p["name"] for p in pods if p.get("phase") == "Running"]
        if running_pods:
            pod = running_pods[0]
            url = f"http://127.0.0.1:8000/api/v1/resources/pods/default/{pod}/metrics/history?metric=cpu&duration_mins=5&step=15s"
            # we need a token though!
            print("Need JWT token to test correctly.")

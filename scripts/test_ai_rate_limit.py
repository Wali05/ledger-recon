import requests
import time
import os
import sys

base_url = 'http://localhost:8000/reconcile'

# Get an existing break ID to test with
breaks_res = requests.get('http://localhost:8000/breaks?source=synthetic&page_size=1')
breaks = breaks_res.json().get('items', [])
if not breaks:
    print("No breaks found to test with.")
    sys.exit(1)

break_id = breaks[0]['break_id']
print(f"Testing with break ID: {break_id}")

success_count = 0
for i in range(1, 18):
    print(f"Request {i}...", end=" ")
    res = requests.post(f"http://localhost:8000/breaks/{break_id}/ai-explain")
    if res.status_code == 200:
        print("Success! (cached)")
        success_count += 1
    elif res.status_code == 429:
        print("Rate Limited! (429)")
    else:
        print(f"Failed: {res.status_code} - {res.text}")
    time.sleep(0.1)

print(f"Total successful requests: {success_count}")

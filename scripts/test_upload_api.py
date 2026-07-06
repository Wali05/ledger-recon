import requests, time

base_url = 'http://localhost:8000/reconcile'

print("Uploading ledger...")
with open('sample_ledger.csv', 'rb') as f:
    res = requests.post(f'{base_url}/upload/ledger', files={'file': f})
    print('Ledger Upload:', res.json())

print("Uploading statement...")
with open('sample_statement.csv', 'rb') as f:
    res = requests.post(f'{base_url}/upload/statement', files={'file': f})
    print('Statement Upload:', res.json())

print("Triggering reconcile...")
res = requests.post(f'{base_url}/run?source=uploaded')
job_id = res.json()['job_id']
print('Job Queued:', job_id)

for i in range(10):
    res = requests.get(f'{base_url}/status/{job_id}')
    status = res.json()['status']
    print('Status:', status)
    if status in ['complete', 'failed']:
        print('Result:', res.json())
        break
    time.sleep(1)

res = requests.get('http://localhost:8000/breaks?source=uploaded')
breaks = res.json()['items']
print(f"Found {len(breaks)} uploaded breaks.")
for b in breaks:
    print(f"Break: {b['transaction_id']} - {b['break_type']} (Delta: {b['delta_amount']})")

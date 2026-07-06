import csv
from datetime import datetime, timezone

# 1. Generate test_ledger.csv
with open('test_ledger.csv', 'w', newline='') as f:
    writer = csv.writer(f)
    writer.writerow(['transaction_id', 'account_id', 'amount', 'currency', 'timestamp', 'description', 'status'])
    
    # Normal matching rows
    writer.writerow(['TXN-UPL-101', 'ACC-1', '150.00', 'USD', '2026-07-06T10:00:00Z', 'Client payment', 'COMPLETED'])
    writer.writerow(['TXN-UPL-102', 'ACC-1', '2500.50', 'USD', '2026-07-06T11:30:00Z', 'Invoice #442', 'COMPLETED'])
    writer.writerow(['TXN-UPL-103', 'ACC-1', '75.25', 'USD', '2026-07-06T12:15:00Z', 'Software sub', 'COMPLETED'])
    
    # Missing from statement (break)
    writer.writerow(['TXN-UPL-104', 'ACC-1', '500.00', 'USD', '2026-07-06T14:00:00Z', 'Uncleared check', 'COMPLETED'])
    
    # Amount mismatch (break)
    writer.writerow(['TXN-UPL-105', 'ACC-1', '99.99', 'USD', '2026-07-06T15:00:00Z', 'Monthly fee', 'COMPLETED'])

# 2. Generate test_statement.csv
with open('test_statement.csv', 'w', newline='') as f:
    writer = csv.writer(f)
    writer.writerow(['transaction_id', 'amount', 'timestamp', 'description'])
    
    # Normal matching rows
    writer.writerow(['TXN-UPL-101', '150.00', '2026-07-06T10:05:00Z', 'Incoming Wire: Client payment'])
    writer.writerow(['TXN-UPL-102', '2500.50', '2026-07-06T11:45:00Z', 'Deposit: Invoice #442'])
    writer.writerow(['TXN-UPL-103', '75.25', '2026-07-06T12:18:00Z', 'ACH Debit: Software sub'])
    
    # Missing from ledger (break)
    writer.writerow(['TXN-UPL-106', '12.00', '2026-07-06T16:00:00Z', 'Bank Maintenance Fee'])
    
    # Amount mismatch (break) (ledger says 99.99, bank says 100.00)
    writer.writerow(['TXN-UPL-105', '100.00', '2026-07-06T15:05:00Z', 'ACH Debit: Monthly fee'])

print("Successfully generated test_ledger.csv and test_statement.csv")

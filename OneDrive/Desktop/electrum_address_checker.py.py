import subprocess

# 🧱 Define the addresses you want to check
addresses_to_check = [
    "bc1qwzrryqr3ja8w7hnja2spmkgfdcgvqwp5swz4af4ngsjecfz0w0pqud7k38",
    "bc1q3nwelxcc4lgx62rjdjydnkv4e0vjnvge0dev77",
    "32BfKjhBrDSxx3BM5vJkiQ3MQqz9cszRxm6"
]

# 🧱 Optional: Define wallet path if not using default
wallet_path = None  # or "C:/Users/Onyxc/AppData/Roaming/Electrum/wallets/default_wallet"

# 🧱 Command base
base_cmd = ["electrum"]

if wallet_path:
    base_cmd += ["-w", wallet_path]

log_file = "electrum_address_check_log.txt"
with open(log_file, "w") as log:
    for addr in addresses_to_check:
        print(f"\n🔎 Checking: {addr}")
        log.write(f"\n🔎 Checking: {addr}\n")

        try:
            # Check balance
            cmd = base_cmd + ["getaddressbalance", addr]
            balance = subprocess.check_output(cmd).decode()
            print(f"💰 Balance info: {balance}")
            log.write(f"💰 Balance info: {balance}\n")

            # Check UTXOs
            cmd = base_cmd + ["listunspent", addr]
            utxos = subprocess.check_output(cmd).decode()
            print(f"📦 UTXOs: {utxos}")
            log.write(f"📦 UTXOs: {utxos}\n")

        except Exception as e:
            print(f"⚠️ Error checking {addr}: {e}")
            log.write(f"⚠️ Error checking {addr}: {e}\n")

print(f"\n✅ Scan complete. Results saved to {log_file}")

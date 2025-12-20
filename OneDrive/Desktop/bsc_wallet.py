import requests
import json

address = "0xa2b4c0af19cc16a6cfacce81f192b024d625817d"
api_key = "YourApiKeyToken"

print(f"🔍 Analyzing BSC wallet: {address}")
print("-" * 60)

# BNB Balance
url = f"https://api.bscscan.com/api?module=account&action=balance&address={address}&tag=latest&apikey={api_key}"
response = requests.get(url)
balance = json.loads(response.text)['result']
print(f"💰 BNB Balance: {int(balance)/10**18:.6f} BNB")

print("✅ Done - check https://bscscan.com/address/" + address)


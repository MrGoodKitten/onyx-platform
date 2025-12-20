import os, shutil
import py7zr  # Install via: pip install py7zr

# Set up secure vault
vault_dir = "C:\\SECURE_WALLETS"
os.makedirs(vault_dir, exist_ok=True)

# Files to secure
files = [
    r"C:\Users\Onyxc\AppData\Local\Perplexity\Comet\User Data\Default\Sync Data\LevelDB\000269.log",
    r"C:\Users\Onyxc\AppData\Roaming\Microsoft\Windows\PowerShell\PSReadLine\ConsoleHost_history.txt",
    r"C:\Users\Onyxc\OneDrive\Desktop\off line vailt\FILE 2 BITCOIN_WALLETS.txt.txt",
    r"C:\Users\Onyxc\OneDrive\Desktop\TITANS PAYLOAD\titankey.txt"
]

# Move files to vault
for file_path in files:
    if os.path.exists(file_path):
        shutil.copy2(file_path, vault_dir)

# Encrypt to .7z with password
archive_name = "wallets_encrypted.7z"
password = "ZEUS-VAULT-2025"  # You can change this
with py7zr.SevenZipFile(archive_name, 'w', password=password) as archive:
    archive.writeall(vault_dir, arcname="wallets")

print(f"\n🔐 Encrypted archive created: {archive_name}")
print(f"📁 Password: {password}")
from imapclient import IMAPClient
import pyzmail36
import json
import getpass
from datetime import datetime

EMAIL_HOST = 'imap.gmail.com'
EMAIL_USER = 'your_email@example.com'
EMAIL_PASS = getpass.getpass("Enter your email password or app password: ")
KEYWORDS = ['ethereum', 'opensea', 'nft', 'transaction', 'wallet', 'ETH', 'crypto']

def parse_email_body(body):
    eth_value = None
    wallet = None
    asset = None
    for line in body.split("\n"):
        if 'ETH' in line:
            eth_value = ''.join([c for c in line if c.isdigit() or c == '.'])
        if '0x' in line:
            wallet = line.strip()
        if 'Bored Ape' in line:
            asset = line.strip()
    return eth_value, wallet, asset

with IMAPClient(EMAIL_HOST) as server:
    server.login(EMAIL_USER, EMAIL_PASS)
    server.select_folder('INBOX', readonly=True)

    messages = server.search(['FROM', 'opensea.io'])
    print(f"📨 Found {len(messages)} OpenSea emails.")
    activity_log = []

    for msgid, data in server.fetch(messages, ['RFC822']).items():
        message = pyzmail36.PyzMessage.factory(data[b'RFC822'])
        subject = message.get_subject()
        sender = message.get_addresses('from')[0][1]
        if message.text_part:
            body = message.text_part.get_payload().decode(message.text_part.charset)
        elif message.html_part:
            body = message.html_part.get_payload().decode(message.html_part.charset)
        else:
            body = ""
        if any(keyword.lower() in body.lower() for keyword in KEYWORDS):
            eth, wallet, asset = parse_email_body(body)
            log_entry = {
                'subject': subject,
                'from': sender,
                'eth_value': eth or 'N/A',
                'asset': asset or 'N/A',
                'wallet': wallet or 'N/A',
                'timestamp': datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')
            }
            activity_log.append(log_entry)
            print(json.dumps(log_entry, indent=2))

    if activity_log:
        with open('eth_nft_activity.json', 'w') as f:
            json.dump(activity_log, f, indent=2)
        print("✅ Activity log saved to eth_nft_activity.json.")

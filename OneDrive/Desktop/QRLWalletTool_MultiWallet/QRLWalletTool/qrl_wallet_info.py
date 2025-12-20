import grpc
from qrl.generated import qrl_pb2, qrl_pb2_grpc

# === CONFIGURATION ===
NODE_ADDRESS = '127.0.0.1:19009'  # Use your QRL node IP if it's remote

# === LIST OF WALLET ADDRESSES (Replace with real hex addresses) ===
QRL_ADDRESSES_HEX = [
    '010500e0c44f219e000000000000000000000000000000000000000000000001',
    '010500e0c44f219e000000000000000000000000000000000000000000000002',
    '010500e0c44f219e000000000000000000000000000000000000000000000003'
    # Add the rest of your 459 wallet hex addresses here...
]

# === CONNECT TO QRL NODE ===
channel = grpc.insecure_channel(NODE_ADDRESS)
stub = qrl_pb2_grpc.PublicAPIStub(channel)

# === FUNCTION: Get Wallet Info ===
def get_wallet_info(wallet_address_hex):
    wallet_address = bytes.fromhex(wallet_address_hex)
    try:
        address_request = qrl_pb2.GetAddressStateReq(address=wallet_address)
        address_response = stub.GetAddressState(address_request)

        print("\n🔍 WALLET INFO")
        print(f"Address: Q{wallet_address.hex()}")
        print(f"Balance: {address_response.state.balance / 10**9:.9f} QRL")
        print(f"Nonce: {address_response.state.nonce}")
        print(f"OTS Keys Used: {sum(address_response.state.ots_bitfield)}")

        print("\n🔸 TOKENS:")
        if not address_response.state.tokens:
            print("  None")
        else:
            for token in address_response.state.tokens:
                print(f"  Token ID: {token.token_txhash.hex()} | Symbol: {token.symbol} | Balance: {token.balance}")

        tx_request = qrl_pb2.GetTransactionsByAddressReq(address=wallet_address, item_limit=5)
        tx_response = stub.GetTransactionsByAddress(tx_request)

        print("\n🔁 RECENT TRANSACTIONS:")
        if not tx_response.transactions_detail:
            print("  No transactions found.")
        else:
            for tx_detail in tx_response.transactions_detail:
                tx = tx_detail.tx
                amount = tx.amount / 10**9
                to = tx.transfer.pubhashes[0].hex() if tx.transfer.pubhashes else "N/A"
                print(f"  - TX Hash: {tx.tx_hash.hex()} | Amount: {amount:.9f} QRL | To: {to}")

    except Exception as e:
        print(f"❌ Error for address Q{wallet_address.hex()}: {e}")

# === MAIN LOOP ===
if __name__ == '__main__':
    for addr in QRL_ADDRESSES_HEX:
        get_wallet_info(addr)
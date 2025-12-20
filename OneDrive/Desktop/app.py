from flask import Flask, render_template, request, jsonify
from onyx_core import ONYXCore
import os

app = Flask(__name__)
onyx = ONYXCore()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/chat', methods=['POST'])
def chat():
    message = request.json.get('message')
    # Process with Onyx AI
    response = onyx.process(message)
    return jsonify({'response': response})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))

import os
import sys
import traceback

# Add the plugin directory to sys.path
plugin_directory = os.path.dirname(__file__).replace("\\", "/")
if plugin_directory not in sys.path:
    sys.path.append(plugin_directory)

import fabplugins
from version import version as plugin_version

# Ensure we load and instantiate QTimer correctly from Pyside for all versions
try:
    from PySide6.QtCore import QTimer
except:
    try:
        from PySide2.QtCore import QTimer
    except:
        print("Error importing Pyside, this should not happen")

LISTENING_PORT = 23292
listener = fabplugins.Listener(port=LISTENING_PORT, plugin_version=plugin_version)

def import_data_if_needed():
    if listener and (data := listener.payload()):
        try:
            for payload_data in data:
                payload = fabplugins.Payload(payload_data, print_debug=True)
                import importer
                importer = importer.Importer(payload)
                importer.import_payload(payload)
        except Exception as e:
            print("Fab error while importing textures/geometry or setting up material")
            print(traceback.format_exc())

# The file named builtins calls entrypoint from 3ds Max startup - afterwards entrypoint is the __main__ file that is run directly with bridge exports
if (__name__ == "builtins") or (__name__ == "__builtin__") or (__name__ == "__main__"):
    listener.start()
    timer = QTimer()
    timer.timeout.connect(import_data_if_needed)
    timer.start(250)

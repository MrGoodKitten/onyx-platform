import time
import shutil
import os

CYAN = "\033[96m"
BLUE = "\033[94m"
MAGENTA = "\033[95m"
RESET = "\033[0m"

class CommandCenter:
    def __init__(self, deployment_engine, onyx_engine):
        self.deployment = deployment_engine
        self.onyx = onyx_engine

    def clear(self):
        os.system("cls" if os.name == "nt" else "clear")

    def center(self, text):
        cols = shutil.get_terminal_size().columns
        return text.center(cols)

    def holo_title(self):
        print(CYAN + self.center("MAXIMUS COMMAND CENTER") + RESET)
        print(BLUE + self.center("Holographic Simulation Environment") + RESET)
        print(MAGENTA + ("=" * shutil.get_terminal_size().columns) + RESET)

    def simulate_command(self, command):
        print(MAGENTA + f"\n[SIMULATION] Executing: {command}" + RESET)
        time.sleep(0.7)
        print(BLUE + "░▒▓ Processing holographic instruction…" + RESET)
        time.sleep(0.7)
        print(CYAN + f"[RESULT] '{command}' executed in simulated mode.\n" + RESET)

    def menu(self):
        print(CYAN + """
Choose an operation:
1 — Simulate command
2 — Run Deployment Simulation
3 — Activate Godform Mode
4 — Sync ONYX.AI ↔ Maximus
5 — System Status
6 — Exit
""" + RESET)

    def run(self):
        while True:
            self.clear()
            self.holo_title()
            self.menu()
            choice = input(CYAN + "Select option: " + RESET)

            if choice == "1":
                cmd = input("Enter command to simulate: ")
                self.simulate_command(cmd)

            elif choice == "2":
                result = self.deployment.simulate_deployment()
                print(CYAN + f"Deployment Simulation Result: {result}\n" + RESET)

            elif choice == "3":
                print(MAGENTA + "\nActivating ONYX.AI Godform…" + RESET)
                self.onyx.activate_godform()

            elif choice == "4":
                print(BLUE + "Synchronizing systems…" + RESET)
                status = self.deployment.sync()
                print(CYAN + f"SYSTEM SYNC: {status}\n" + RESET)

            elif choice == "5":
                print(CYAN + "STATUS:" + RESET)
                print(f"ONYX.AI: {self.onyx.status}")
                print(f"Maximus: ONLINE")
                print(f"Engine: {self.deployment.status_sync.shared_status}\n")

            elif choice == "6":
                print(MAGENTA + "Exiting Command Center…" + RESET)
                break

            else:
                print("Invalid choice.")

            input("\nPress ENTER to continue…")

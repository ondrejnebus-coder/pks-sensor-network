import socket
import json
import threading
import secrets
import zlib
import time
from datetime import datetime, timezone

log_lock = threading.Lock()
console_logging = True
server_seq = 1
server_seq_lock = threading.Lock()

VALID_TYPES = ["ThermoNode", "WindSense", "RainDetect", "AirQuality"]


def log_event(log_type, level, source, message):
    timestamp = datetime.now(timezone.utc).isoformat(
        timespec="milliseconds"
    ).replace("+00:00", "Z")

    log_line = f"{timestamp} | {log_type} | {level} | {source} | {message}"

    with log_lock:
        with open("server.log", "a", encoding="utf-8") as file:
            file.write(log_line + "\n")

        if console_logging:
            print(log_line)


def compute_crc(message):
    message_copy = message.copy()
    message_copy.pop("crc", None)

    encoded = json.dumps(
        message_copy,
        sort_keys=True,
        separators=(",", ":")
    ).encode("utf-8")

    return f"{zlib.crc32(encoded):08x}"


def get_next_server_seq():
    global server_seq

    with server_seq_lock:
        seq = server_seq
        server_seq += 1
        return seq


def send_message(server_socket, address, message):
    server_socket.sendto(json.dumps(message).encode("utf-8"), address)

    log_event(
        "MESSAGE", "INFO", "SERVER",
        f"Sent to {address}: {json.dumps(message)}"
    )


def reset_keepalive(sensor_info):
    sensor_info["last_keepalive_time"] = None
    sensor_info["missed_keepalives"] = 0
    sensor_info["waiting_keepalive"] = False
    sensor_info["pending_keepalive_seq"] = None


def receive_messages(server_socket, sensors):
    while True:
        try:
            data, address = server_socket.recvfrom(4096)
            message = json.loads(data.decode("utf-8"))

            if not isinstance(message, dict):
                raise ValueError("Message must be a JSON object")

            log_event(
                "MESSAGE", "INFO", "SERVER",
                f"Received from {address}: {json.dumps(message)}"
            )

            message_type = message.get("type")

            if message_type == "REGISTER":
                sensor_type = message.get("sensor_type")
                sensor_id = message.get("sensor_id")
                seq = message.get("seq")
                response_seq = get_next_server_seq()

                if (
                    sensor_type not in VALID_TYPES
                    or not isinstance(sensor_id, str)
                    or not sensor_id.strip()
                ):
                    response = {
                        "type": "REJECT",
                        "seq": response_seq,
                        "ack_for": seq,
                        "reason": "INVALID_SENSOR"
                    }

                elif (
                    (sensor_type, sensor_id) in sensors
                    and sensors[(sensor_type, sensor_id)]["status"] != "DISCONNECTED"
                ):
                    response = {
                        "type": "REJECT",
                        "seq": response_seq,
                        "ack_for": seq,
                        "reason": "DUPLICATE_SENSOR"
                    }

                else:
                    token = secrets.token_hex(8)

                    sensors[(sensor_type, sensor_id)] = {
                        "token": token,
                        "address": address,
                        "last_data_time": time.monotonic(),
                        "status": "ACTIVE",
                        "last_keepalive_time": None,
                        "missed_keepalives": 0,
                        "waiting_keepalive": False,
                        "pending_keepalive_seq": None,
                        "suppress_ack_count": 0,
                    }

                    response = {
                        "type": "ACK",
                        "seq": response_seq,
                        "ack_for": seq,
                        "token": token
                    }

                    log_event(
                        "SYSTEM", "INFO", "SERVER",
                        f"Sensor registered: {sensor_type}:{sensor_id}"
                    )

                send_message(server_socket, address, response)

            elif message_type == "KEEPALIVE_ACK":
                sensor_type = message.get("sensor_type")
                sensor_id = message.get("sensor_id")
                token = message.get("token")
                sensor_key = (sensor_type, sensor_id)

                if sensor_key not in sensors:
                    log_event(
                        "SYSTEM", "WARNING", "SERVER",
                        f"KEEPALIVE_ACK from unknown sensor: {sensor_type}:{sensor_id}"
                    )

                elif (
                    sensors[sensor_key]["status"] == "DISCONNECTED"
                    or not isinstance(token, str)
                    or not token
                    or sensors[sensor_key]["token"] != token
                ):
                    log_event(
                        "SYSTEM", "WARNING", "SERVER",
                        f"Invalid KEEPALIVE_ACK token or session: {sensor_type}:{sensor_id}"
                    )

                else:
                    sensor_info = sensors[sensor_key]

                    if (
                        sensor_info["status"] == "IDLE"
                        and sensor_info["waiting_keepalive"]
                        and message.get("ack_for") == sensor_info["pending_keepalive_seq"]
                    ):
                        sensor_info["waiting_keepalive"] = False
                        sensor_info["missed_keepalives"] = 0
                        sensor_info["pending_keepalive_seq"] = None

                        log_event(
                            "SYSTEM", "INFO", "SERVER",
                            f"KEEPALIVE_ACK received from {sensor_type}:{sensor_id}"
                        )

            elif message_type == "DATA":
                sensor_type = message.get("sensor_type")
                sensor_id = message.get("sensor_id")
                token = message.get("token")
                received_crc = message.get("crc")
                seq = message.get("seq")

                if not isinstance(seq, int) or isinstance(seq, bool) or seq < 1:
                    log_event(
                        "SYSTEM", "WARNING", "SERVER",
                        f"DATA rejected - invalid or missing seq from {sensor_type}:{sensor_id}"
                    )
                    continue

                sensor_key = (sensor_type, sensor_id)

                if sensor_key not in sensors:
                    log_event(
                        "SYSTEM", "WARNING", "SERVER",
                        f"DATA from unknown sensor: {sensor_type}:{sensor_id}"
                    )

                elif sensors[sensor_key]["status"] == "DISCONNECTED":
                    log_event(
                        "SYSTEM", "WARNING", "SERVER",
                        f"DATA rejected - disconnected sensor: {sensor_type}:{sensor_id}"
                    )

                elif (
                    not isinstance(token, str)
                    or not token
                    or sensors[sensor_key]["token"] != token
                ):
                    log_event(
                        "SYSTEM", "WARNING", "SERVER",
                        f"DATA rejected - invalid token: {sensor_type}:{sensor_id}"
                    )

                elif received_crc != compute_crc(message):
                    log_event(
                        "SYSTEM", "WARNING", "SERVER",
                        f"CRC error from {sensor_type}:{sensor_id}, seq={seq}"
                    )

                    send_message(server_socket, address, {
                        "type": "RETRANSMIT_REQUEST",
                        "seq": get_next_server_seq(),
                        "ack_for": seq
                    })

                else:
                    sensor_info = sensors[sensor_key]
                    sensor_info["last_data_time"] = time.monotonic()

                    if sensor_info["status"] == "IDLE":
                        sensor_info["status"] = "ACTIVE"
                        reset_keepalive(sensor_info)

                        log_event(
                            "SYSTEM", "INFO", "SERVER",
                            f"SENSOR ACTIVE: {sensor_type}:{sensor_id}"
                        )

                    if sensor_info["suppress_ack_count"] > 0:
                        sensor_info["suppress_ack_count"] -= 1

                        log_event(
                            "SYSTEM", "WARNING", "SERVER",
                            f"ACK suppressed for {sensor_type}:{sensor_id}, "
                            f"DATA seq={seq}, remaining={sensor_info['suppress_ack_count']}"
                        )
                    else:
                        send_message(server_socket, address, {
                            "type": "ACK",
                            "seq": get_next_server_seq(),
                            "ack_for": seq
                        })

        except (json.JSONDecodeError, UnicodeDecodeError):
            log_event("SYSTEM", "WARNING", "SERVER", "Invalid JSON message received")

        except (AttributeError, TypeError, ValueError):
            log_event("SYSTEM", "WARNING", "SERVER", "Invalid message format")


        except ConnectionResetError as error:
            log_event(
                "SYSTEM",
                "WARNING",
                "SERVER",
                f"UDP connection reset - continuing to listen: {error}"
            )
            continue

        except OSError as error:
            log_event(
                "SYSTEM",
                "ERROR",
                "SERVER",
                f"UDP receive error: {error}"
            )
            if server_socket.fileno() == -1:
                break

            continue


def check_idle_sensors(server_socket, sensors):
    while True:
        current_time = time.monotonic()

        for (sensor_type, sensor_id), sensor_info in list(sensors.items()):
            if sensor_info["status"] == "DISCONNECTED":
                continue

            elapsed = current_time - sensor_info["last_data_time"]

            # Po 15 sekundach bez DATA prejdeme do IDLE
            if elapsed >= 15 and sensor_info["status"] == "ACTIVE":
                sensor_info["status"] = "IDLE"
                reset_keepalive(sensor_info)

                log_event(
                    "SYSTEM", "WARNING", "SERVER",
                    f"SENSOR IDLE: {sensor_type}:{sensor_id}"
                )

            if sensor_info["status"] != "IDLE":
                continue

            last_keepalive = sensor_info["last_keepalive_time"]

            # KEEPALIVE posielame kazdych 5 sekund
            if last_keepalive is not None and current_time - last_keepalive < 5:
                continue

            # Predchadzajuci KEEPALIVE zostal bez odpovede
            if sensor_info["waiting_keepalive"]:
                sensor_info["missed_keepalives"] += 1
                sensor_info["waiting_keepalive"] = False
                sensor_info["pending_keepalive_seq"] = None

                log_event(
                    "SYSTEM", "WARNING", "SERVER",
                    f"KEEPALIVE unanswered ({sensor_info['missed_keepalives']}/3): "
                    f"{sensor_type}:{sensor_id}"
                )

            # Po 3 nezodpovedanych KEEPALIVE zrusime relaciu
            if sensor_info["missed_keepalives"] >= 3:
                sensor_info["status"] = "DISCONNECTED"
                sensor_info["token"] = None
                sensor_info["pending_keepalive_seq"] = None

                log_event(
                    "SYSTEM", "WARNING", "SERVER",
                    f"SENSOR DISCONNECTED: {sensor_type}:{sensor_id}"
                )
                continue

            message = {
                "type": "KEEPALIVE",
                "seq": get_next_server_seq(),
                "sensor_type": sensor_type,
                "sensor_id": sensor_id,
                "token": sensor_info["token"]
            }

            sensor_info["last_keepalive_time"] = current_time
            sensor_info["waiting_keepalive"] = True
            sensor_info["pending_keepalive_seq"] = message["seq"]

            try:
                send_message(server_socket, sensor_info["address"], message)

            except OSError as error:
                log_event(
                    "SYSTEM", "ERROR", "SERVER",
                    f"KEEPALIVE sending failed: {error}"
                )

        time.sleep(1)

def configure_ack_suppression(sensors):
    if not sensors:
        print("No registered sensors.")
        return

    sensor_list = [
        (key, info) for key, info in sensors.items()
        if info["status"] != "DISCONNECTED"
    ]

    if not sensor_list:
        print("No active sensor sessions.")
        return

    print("\n===== SUPPRESS DATA ACK =====")

    for index, ((sensor_type, sensor_id), info) in enumerate(sensor_list, 1):
        print(f"{index}. {sensor_type}:{sensor_id}")

    try:
        choice = int(input("Choose sensor: "))
        if not 1 <= choice <= len(sensor_list):
            print("Invalid selection.")
            return

        count = int(input("Number of ACKs to suppress: "))
        if count < 0:
            print("Count must be 0 or greater.")
            return

        (sensor_type, sensor_id), info = sensor_list[choice - 1]
        info["suppress_ack_count"] = count

        print(f"Suppressing {count} DATA ACKs for {sensor_type}:{sensor_id}")

    except ValueError:
        print("Invalid number.")
def main():
    sensors = {}
    server_ip = "0.0.0.0"
    server_port = 5055
    server_socket = None

    while True:
        print("\n FIITMeteo SERVER ")
        print("1. Set server IP and port")
        print("2. Start listening")
        print("3. Suppress DATA ACK")
        print("0. Exit")

        choice = input("Choose an option: ")

        if choice == "1":
            print("\nPress ENTER to use the default value.")

            ip_input = input("Server IP [0.0.0.0]: ").strip()
            port_input = input("Server port [5055]: ").strip()

            new_ip = ip_input if ip_input else "0.0.0.0"

            try:
                new_port = int(port_input) if port_input else 5055

                socket.inet_aton(new_ip)

                if not 1 <= new_port <= 65535:
                    raise ValueError("Port must be between 1 and 65535")

                server_ip = new_ip
                server_port = new_port

                print(f"Server configured: {server_ip}:{server_port}")

            except (ValueError, OSError) as error:
                print(f"Invalid configuration: {error}")

        elif choice == "2":
            if server_socket is not None:
                print("Server is already running.")
                continue

            try:
                server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                server_socket.bind((server_ip, server_port))

                log_event(
                    "SYSTEM", "INFO", "SERVER",
                    f"Server listening on {server_ip}:{server_port}"
                )

                threading.Thread(
                    target=receive_messages,
                    args=(server_socket, sensors),
                    daemon=True
                ).start()

                threading.Thread(
                    target=check_idle_sensors,
                    args=(server_socket, sensors),
                    daemon=True
                ).start()

            except OSError as error:
                print(f"Error starting server: {error}")

                if server_socket is not None:
                    server_socket.close()
                    server_socket = None
        elif choice == "3":
            configure_ack_suppression(sensors)

        elif choice == "0":
            if server_socket is not None:
                server_socket.close()

            print("Exiting server...")
            break

        else:
            print("Invalid option.")


if __name__ == "__main__":
    main()
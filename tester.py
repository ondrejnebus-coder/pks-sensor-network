import random
import socket
import json
import zlib
import threading
import time
from datetime import datetime, timezone

log_lock = threading.Lock()
console_logging = True


def log_event(log_type, level, source, message):
    timestamp = datetime.now(timezone.utc).isoformat(
        timespec="milliseconds"
    ).replace("+00:00", "Z")

    log_line = f"{timestamp} | {log_type} | {level} | {source} | {message}"

    with log_lock:
        with open("tester.log", "a", encoding="utf-8") as file:
            file.write(log_line + "\n")

        if console_logging:
            print(log_line)


# Definicie senzorov: (minimum, maximum, pocet desatinnych miest)
SENSOR_SPEC = {
    "ThermoNode": {
        "temperature": (-50.0, 60.0, 1),
        "humidity": (0.0, 100.0, 1),
        "dew_point": (-50.0, 60.0, 1),
        "pressure": (800.0, 1100.0, 2)
    },
    "WindSense": {
        "wind_speed": (0.0, 50.0, 1),
        "wind_gust": (0.0, 70.0, 1),
        "wind_direction": (0, 359, 0),
        "turbulence": (0.0, 1.0, 1)
    },
    "RainDetect": {
        "rainfall": (0.0, 500.0, 1),
        "soil_moisture": (0.0, 100.0, 1),
        "flood_risk": (0, 4, 0),
        "rain_duration": (0, 60, 0)
    },
    "AirQuality": {
        "co2": (300, 5000, 0),
        "ozone": (0.0, 500.0, 1),
        "air_quality_index": (0, 500, 0)
    }
}


def generate_sensor_data(sensor_type):
    data = {}

    for parameter, (minimum, maximum, decimals) in SENSOR_SPEC[sensor_type].items():
        if decimals == 0:
            data[parameter] = random.randint(minimum, maximum)
        else:
            data[parameter] = round(random.uniform(minimum, maximum), decimals)

    return data


def compute_crc(message):
    message_copy = message.copy()
    message_copy.pop("crc", None)

    encoded = json.dumps(
        message_copy,
        sort_keys=True,
        separators=(",", ":")
    ).encode("utf-8")

    return f"{zlib.crc32(encoded):08x}"


def validate_sensor_data(sensor_type, data):
    if sensor_type not in SENSOR_SPEC:
        return False

    for parameter, (minimum, maximum, decimals) in SENSOR_SPEC[sensor_type].items():
        if parameter not in data:
            return False

        value = data[parameter]

        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return False

        if not minimum <= value <= maximum:
            return False

        if decimals == 0:
            if not isinstance(value, int):
                return False
        elif round(value, decimals) != value:
            return False

    return True


def next_seq(sensor_info):
    with sensor_info["lock"]:
        seq = sensor_info["seq"]
        sensor_info["seq"] += 1
        return seq


def send_json(sock, address, message, source, prefix="Sent"):
    sock.sendto(json.dumps(message).encode("utf-8"), address)

    log_event("MESSAGE", "INFO", source, f"{prefix} {json.dumps(message)}")


def choose_sensor(sensors, title):
    if not sensors:
        print("No registered sensors.")
        return None

    sensor_list = list(sensors.items())

    print(f"\n===== {title} =====")

    for index, ((sensor_type, sensor_id), _) in enumerate(sensor_list, 1):
        print(f"{index}. {sensor_type}:{sensor_id}")

    try:
        selection = int(input("Choose sensor: "))
    except ValueError:
        print("Invalid sensor selection.")
        return None

    if not 1 <= selection <= len(sensor_list):
        print("Invalid sensor selection.")
        return None

    return sensor_list[selection - 1]



def send_sensor_data(server_ip, server_port, sensor_type, sensor_id, sensor_info):
    source = f"TESTER:{sensor_type}:{sensor_id}"
    values = generate_sensor_data(sensor_type)
    seq = next_seq(sensor_info)

    with sensor_info["lock"]:
        corrupt = sensor_info["corrupt_next"]
        sensor_info["corrupt_next"] = False

    # Povodna DATA sprava
    message = {
        "type": "DATA",
        "seq": seq,
        "sensor_type": sensor_type,
        "sensor_id": sensor_id,
        "token": sensor_info["token"],
        **values
    }

    # CRC vypocitame pred pripadnym poskodenim
    message["crc"] = compute_crc(message)

    # Vytvorime kopiu na odoslanie
    outgoing_message = message.copy()

    if corrupt:
        parameter = next(iter(SENSOR_SPEC[sensor_type]))
        outgoing_message[parameter] += 1

        log_event(
            "SYSTEM", "WARNING", source,
            f"Intentionally corrupted DATA seq={seq}, parameter={parameter}"
        )

    # Ulozime povodnu aj odosielanu spravu pre UAT 3 a UAT 5
    with sensor_info["lock"]:
        sensor_info["pending_messages"][seq] = {
            "message": message.copy(),
            "outgoing": outgoing_message.copy(),
            "attempts": 1,
            "last_sent": time.monotonic()
        }

    try:
        send_json(
            sensor_info["socket"],
            (server_ip, server_port),
            outgoing_message,
            source
        )

    except OSError as error:
        log_event(
            "SYSTEM", "ERROR", source,
            f"DATA sending failed: {error}"
        )

def receive_sensor_messages(sensor_type, sensor_id, sensor_info):
    sock = sensor_info["socket"]
    source = f"TESTER:{sensor_type}:{sensor_id}"

    while sensor_info["active"]:
        try:
            data, address = sock.recvfrom(4096)
            message = json.loads(data.decode("utf-8"))

            if not isinstance(message, dict):
                continue

            log_event("MESSAGE", "INFO", source, f"Received {json.dumps(message)}")

            message_type = message.get("type")

            if message_type == "ACK":
                with sensor_info["lock"]:
                    sensor_info["pending_messages"].pop(message.get("ack_for"), None)

            elif message_type == "RETRANSMIT_REQUEST":
                ack_for = message.get("ack_for")

                with sensor_info["lock"]:
                    pending = sensor_info["pending_messages"].get(ack_for)
                    original_message = pending["message"].copy() if pending else None

                    if pending:
                        pending["outgoing"] = original_message.copy()
                        pending["last_sent"] = time.monotonic()

                if original_message is None:
                    log_event(
                        "SYSTEM", "WARNING", source,
                        f"No original DATA found for seq={ack_for}"
                    )
                    continue

                try:
                    send_json(
                        sock, address, original_message, source,
                        prefix=f"Retransmitted original DATA seq={ack_for}:"
                    )

                except OSError as error:
                    log_event(
                        "SYSTEM", "ERROR", source,
                        f"Retransmission failed for seq={ack_for}: {error}"
                    )

            elif message_type == "KEEPALIVE":
                if sensor_info["disconnected"]:
                    log_event(
                        "SYSTEM", "WARNING", source,
                        "KEEPALIVE ignored - sensor disconnected"
                    )
                    continue

                with sensor_info["lock"]:
                    sensor_info["last_keepalive_received"] = time.monotonic()

                response = {
                    "type": "KEEPALIVE_ACK",
                    "seq": next_seq(sensor_info),
                    "ack_for": message.get("seq"),
                    "sensor_type": sensor_type,
                    "sensor_id": sensor_id,
                    "token": sensor_info["token"]
                }

                try:
                    send_json(sock, address, response, source)

                except OSError as error:
                    log_event(
                        "SYSTEM", "ERROR", source,
                        f"KEEPALIVE_ACK sending failed: {error}"
                    )

        except socket.timeout:
            continue

        except (json.JSONDecodeError, UnicodeDecodeError):
            log_event("SYSTEM", "WARNING", source, "Invalid JSON received")

        except OSError:
            break

def retry_pending_messages(server_ip, server_port, sensor_type, sensor_id, sensor_info):
    source = f"TESTER:{sensor_type}:{sensor_id}"
    now = time.monotonic()

    with sensor_info["lock"]:
        for seq, pending in list(sensor_info["pending_messages"].items()):
            if now - pending["last_sent"] < 3:
                continue

            if pending["attempts"] >= 3:
                del sensor_info["pending_messages"][seq]
                log_event(
                    "SYSTEM", "WARNING", source,
                    f"DATA seq={seq} discarded after 3 attempts"
                )
                continue

            pending["attempts"] += 1
            pending["last_sent"] = now
            message = pending["outgoing"].copy()

            try:
                send_json(
                    sensor_info["socket"],
                    (server_ip, server_port),
                    message,
                    source
                )
            except OSError as error:
                log_event(
                    "SYSTEM", "ERROR", source,
                    f"DATA retry failed: {error}"
                )
def auto_send_sensor(server_ip, server_port, sensor_type, sensor_id, sensor_info):
    next_send = time.monotonic()

    while sensor_info["active"]:
        if sensor_info["sending_enabled"]:
            if time.monotonic() >= next_send:
                send_sensor_data(
                    server_ip, server_port, sensor_type, sensor_id, sensor_info
                )

                next_send += 10

                if next_send < time.monotonic():
                    next_send = time.monotonic() + 10
        else:
            next_send = time.monotonic()

        retry_pending_messages(
            server_ip, server_port, sensor_type, sensor_id, sensor_info
        )
        time.sleep(0.1)


def check_server_keepalive(sensor_type, sensor_id, sensor_info):
    source = f"TESTER:{sensor_type}:{sensor_id}"

    while sensor_info["active"]:
        with sensor_info["lock"]:
            last_keepalive = sensor_info["last_keepalive_received"]
            sending_enabled = sensor_info["sending_enabled"]
            disconnected = sensor_info["disconnected"]

        if (
            not disconnected
            and not sending_enabled
            and last_keepalive is not None
            and time.monotonic() - last_keepalive >= 30
        ):
            with sensor_info["lock"]:
                sensor_info["disconnected"] = True
                sensor_info["sending_enabled"] = False
                sensor_info["active"] = False

            log_event(
                "SYSTEM", "WARNING", source,
                "Sensor session expired - no KEEPALIVE for 30 seconds"
            )

            sensor_info["socket"].close()
            break

        time.sleep(0.5)


def register_all_sensors(server_ip, server_port, sensors):
    sensor_list = [
        ("ThermoNode", "td1"),
        ("WindSense", "ws1"),
        ("RainDetect", "rd1"),
        ("AirQuality", "aq1")
    ]

    for sensor_type, sensor_id in sensor_list:
        register_sensor(server_ip, server_port, sensors, sensor_type, sensor_id)


def register_sensor(server_ip, server_port, sensors, sensor_type=None, sensor_id=None):
    sensor_types = {
        "1": "ThermoNode",
        "2": "WindSense",
        "3": "RainDetect",
        "4": "AirQuality"
    }

    if sensor_type is None:
        print("\nAvailable sensor types:")
        print("1. ThermoNode")
        print("2. WindSense")
        print("3. RainDetect")
        print("4. AirQuality")
        print("5. Register ALL sensors")

        choice = input("Choose sensor type: ")

        if choice == "5":
            register_all_sensors(server_ip, server_port, sensors)
            return

        if choice not in sensor_types:
            print("Invalid sensor type.")
            return

        sensor_type = sensor_types[choice]
        sensor_id = input("Enter sensor ID: ").strip()

    if not sensor_id:
        print("Sensor ID cannot be empty.")
        return

    if (sensor_type, sensor_id) in sensors:
        old_sensor = sensors[(sensor_type, sensor_id)]

        if not old_sensor["disconnected"]:
            print(f"{sensor_type}:{sensor_id} is already registered.")
            return

        # Opatovna registracia odpojeneho senzora
        old_sensor["active"] = False
        old_sensor["socket"].close()
        del sensors[(sensor_type, sensor_id)]

    source = f"TESTER:{sensor_type}:{sensor_id}"

    message = {
        "type": "REGISTER",
        "seq": 1,
        "sensor_type": sensor_type,
        "sensor_id": sensor_id
    }

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(3)

    try:
        send_json(sock, (server_ip, server_port), message, source)

        response_data, _ = sock.recvfrom(4096)
        response = json.loads(response_data.decode("utf-8"))

        log_event("MESSAGE", "INFO", source, f"Received {json.dumps(response)}")

        if response.get("type") != "ACK" or response.get("ack_for") != 1:
            print(f"Registration failed: {response}")
            sock.close()
            return

        token = response.get("token")

        if not isinstance(token, str) or not token:
            print("Invalid token received.")
            sock.close()
            return

        sensor_info = {
            "token": token,
            "seq": 2,
            "active": True,
            "sending_enabled": True,
            "socket": sock,
            "lock": threading.Lock(),
            "corrupt_next": False,
            "pending_messages": {},
            "disconnected": False,
            "last_keepalive_received": None,
        }

        sensors[(sensor_type, sensor_id)] = sensor_info

        sock.settimeout(0.5)

        threads = [
            (receive_sensor_messages, (sensor_type, sensor_id, sensor_info)),
            (auto_send_sensor, (server_ip, server_port, sensor_type, sensor_id, sensor_info)),
            (check_server_keepalive, (sensor_type, sensor_id, sensor_info)),
        ]

        for target, args in threads:
            threading.Thread(target=target, args=args, daemon=True).start()

        print(f"Sensor registered: {sensor_type}:{sensor_id}")
        print(f"Token: {token}")

    except (socket.timeout, OSError, ValueError, UnicodeDecodeError) as error:
        print(f"Registration error: {error}")
        sock.close()


def send_custom_data(server_ip, server_port, sensors):
    selected = choose_sensor(sensors, "CUSTOM SENSOR DATA")

    if selected is None:
        return

    (sensor_type, sensor_id), sensor_info = selected

    if sensor_info["disconnected"] or not sensor_info["active"]:
        print("Cannot send DATA - sensor is disconnected.")
        return

    values = {}

    print(f"\nEnter values for {sensor_type}:{sensor_id}")

    for parameter, (minimum, maximum, decimals) in SENSOR_SPEC[sensor_type].items():
        while True:
            try:
                user_input = input(f"{parameter} ({minimum} to {maximum}): ")
                value = int(user_input) if decimals == 0 else float(user_input)

                if not minimum <= value <= maximum:
                    print("Value out of range. Try again.")
                    continue

                if decimals > 0 and round(value, decimals) != value:
                    print(f"Maximum {decimals} decimal places.")
                    continue

                values[parameter] = value
                break

            except ValueError:
                print("Invalid number. Try again.")

    if not validate_sensor_data(sensor_type, values):
        print("Invalid sensor data.")
        return

    message = {
        "type": "DATA",
        "seq": next_seq(sensor_info),
        "sensor_type": sensor_type,
        "sensor_id": sensor_id,
        "token": sensor_info["token"],
        **values
    }

    message["crc"] = compute_crc(message)
    with sensor_info["lock"]:
        sensor_info["pending_messages"][message["seq"]] = {
            "message": message.copy(),
            "outgoing": message.copy(),
            "attempts": 1,
            "last_sent": time.monotonic()
        }
    try:
        send_json(
            sensor_info["socket"],
            (server_ip, server_port),
            message,
            f"TESTER:{sensor_type}:{sensor_id}"
        )

        print(f"Custom DATA sent: {sensor_type}:{sensor_id}")

    except OSError as error:
        print(f"Error sending custom DATA: {error}")


def corrupt_next_data(sensors):
    selected = choose_sensor(sensors, "CORRUPT NEXT DATA")

    if selected is None:
        return

    (sensor_type, sensor_id), sensor_info = selected

    with sensor_info["lock"]:
        sensor_info["corrupt_next"] = True

    print(f"Next DATA will be corrupted for {sensor_type}:{sensor_id}")


def disconnect_sensor(sensors):
    selected = choose_sensor(sensors, "DISCONNECT SENSOR")

    if selected is None:
        return

    (sensor_type, sensor_id), sensor_info = selected

    with sensor_info["lock"]:
        sensor_info["disconnected"] = True
        sensor_info["sending_enabled"] = False
        sensor_info["active"] = False
        sensor_info["pending_messages"].clear()

    sensor_info["socket"].close()

    log_event(
        "SYSTEM", "WARNING",
        f"TESTER:{sensor_type}:{sensor_id}",
        "Sensor manually disconnected"
    )

    print(f"Sensor disconnected: {sensor_type}:{sensor_id}")


def toggle_sending(sensors):
    if not sensors:
        print("No registered sensors.")
        return

    sensor_list = list(sensors.items())

    print("\n===== SENSOR CONTROL =====")
    print("0. ALL sensors")

    for index, ((sensor_type, sensor_id), info) in enumerate(sensor_list, 1):
        status = "ON" if info["sending_enabled"] else "OFF"
        print(f"{index}. {sensor_type}:{sensor_id} - {status}")

    selection = input("Choose sensor (0 = ALL): ").strip()

    if selection == "0":
        selected_sensors = [info for _, info in sensor_list]

    elif selection.isdigit() and 1 <= int(selection) <= len(sensor_list):
        selected_sensors = [sensor_list[int(selection) - 1][1]]

    else:
        print("Invalid sensor selection.")
        return

    print("\n1. Start sending")
    print("2. Stop sending")

    action = input("Choose action: ").strip()

    if action not in ("1", "2"):
        print("Invalid action.")
        return

    enabled = action == "1"

    for info in selected_sensors:
        with info["lock"]:
            if info["disconnected"] or not info["active"]:
                print("Cannot change sending - sensor is disconnected.")
                continue

            info["sending_enabled"] = enabled

    print(f"Sending set to {'ON' if enabled else 'OFF'}.")


def main():
    sensors = {}
    server_ip = "127.0.0.1"
    server_port = 5055

    while True:
        print("\n FIITMeteo TESTER ")
        print("1. Set server IP and port")
        print("2. Register sensor")
        print("3. Start/stop sensor data")
        print("4. Send custom data")
        print("5. Corrupt next data message")
        print("6. Disconnect sensor")
        print("0. Exit")

        choice = input("Choose an option: ")

        if choice == "0":
            print("Exiting tester...")
            break

        elif choice == "1":
            active_sensors = [
                info for info in sensors.values()
                if info["active"] and not info["disconnected"]
            ]

            if active_sensors:
                print("Cannot change server IP/port while sensors are active.")
                print("Disconnect all sensors first.")
                continue

            print("\nPress ENTER to use the default value.")

            ip_input = input("Server IP [127.0.0.1]: ").strip()
            port_input = input("Server port [5055]: ").strip()

            new_ip = ip_input if ip_input else "127.0.0.1"

            try:
                new_port = int(port_input) if port_input else 5055

                socket.inet_aton(new_ip)

                if not 1 <= new_port <= 65535:
                    raise ValueError("Invalid port")

                server_ip = new_ip
                server_port = new_port

                print(f"Server configured: {server_ip}:{server_port}")

            except (ValueError, OSError):
                print("Invalid IP address or port.")

        elif choice == "2":
            register_sensor(server_ip, server_port, sensors)

        elif choice == "3":
            toggle_sending(sensors)

        elif choice == "4":
            send_custom_data(server_ip, server_port, sensors)

        elif choice == "5":
            corrupt_next_data(sensors)

        elif choice == "6":
            disconnect_sensor(sensors)

        else:
            print("Invalid option.")


if __name__ == "__main__":
    main()
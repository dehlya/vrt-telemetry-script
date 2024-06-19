import socket
import json
import threading
import matplotlib.pyplot as plt
import matplotlib.animation as animation
import csv
import os
from datetime import datetime
import time

# Define the address and port to listen on
UDP_IP = "0.0.0.0" #let's maybe change that one tho
UDP_PORT = 7070

# Mode selection: 'realtime' for live data, 'replay' for CSV replay
#TODO: create a selection for user input 
mode = 'realtime'  # Change to 'realtime' for live data

# File to replay from
replay_folder = '../data'
if not os.path.exists(replay_folder):
    os.makedirs(replay_folder)

# Only check for replay files if in replay mode
if mode == 'replay':
    csv_files = [f for f in os.listdir(replay_folder) if f.endswith('.csv')]
    if not csv_files:
        print(f"No CSV files found in the {replay_folder} folder. Please ensure the folder contains replay files.")
        exit(1)
    # Display available files for selection
    print("Available replay files:")
    for idx, file in enumerate(csv_files):
        print(f"{idx + 1}. {file}")
    file_idx = int(input("Select a file by entering the corresponding number: ")) - 1
    replay_filename = os.path.join(replay_folder, csv_files[file_idx])

# Initialize data storage
data_storage = {
    "temperatures": {
        "Left_Engine_Temp": [],
        "Right_Engine_Temp": [],
        "Left_Inverter_Temperature": [],
        "Right_Inverter_Temperature": [],
        "Right_Gearbox_Temp": [],
        "Right_Radiator_Temp": [],
        "Left_Gearbox_Temp": [],
        "Left_Radiator_Temp": []
    },
    "speeds": {
        "Car_Speed": [],
        "GSPSpeed": []
    },
    "suspensions": {
        "Suspension_Back_Left": [],
        "Suspension_Back_Right": [],
        "Suspension_Front_Left": [],
        "Suspension_Front_Right": []
    },
    "pedals": {
        "Brake_Pedal": [],
        "Accelerator_Pedal": []
    },
    "direction": {
        "Raw_Direction": []
    },
    "gps": {
        "lat": [],
        "lon": []
    },
    "flag": {
        "Flag": []
    },
    "timestamp": []
}

# Create a lock for thread-safe data access
data_lock = threading.Lock()

# CSV logging setup (only for 'realtime' mode)
if mode == 'realtime':
    start_time = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_filename = os.path.join(replay_folder, f"telemetry_data_{start_time}.csv")
    csv_columns = ["timestamp"] + [key for category in data_storage.values() if isinstance(category, dict) for key in category.keys()] + ["Raw_Direction", "GPSCoords", "Flag"]

    # Ensure the CSV file exists and create it with headers if not
    if not os.path.isfile(csv_filename):
        with open(csv_filename, mode='w', newline='') as file:
            writer = csv.writer(file)
            writer.writerow(csv_columns)


def _map(x, in_min, in_max, out_min, out_max):
    return float((x - in_min) * (out_max - out_min) / (in_max - in_min) + out_min)

def udp_listener():
    while mode == 'realtime':
        data, _ = sock.recvfrom(1024)
        message = data.decode('utf-8')
        try:
            json_data = json.loads(message)
        except json.JSONDecodeError:
            print("Received a corrupted JSON package, skipping...")
            continue
        
        process_data(json_data)
        
        # Log data to CSV
        log_to_csv(json_data)

def replay_listener():
    with open(replay_filename, mode='r') as file:
        reader = csv.DictReader(file)
        for row in reader:
            json_data = {
                key: float(row[key]) if key in ["lat", "lon", "Car_Speed", "GSPSpeed", "Brake_Pedal", "Accelerator_Pedal"] else row[key]
                for key in row.keys()
                # if key not in ["timestamp"]
            }
            if "GPSCoords" in json_data: #TODO: GPS replay fix
                lat_lon = json_data["GPSCoords"].split(' ')
                if len(lat_lon) == 2:
                    json_data["lat"] = float(lat_lon[0])
                    json_data["lon"] = float(lat_lon[1])
                del json_data["GPSCoords"]
            # if "timestamp" not in json_data:
            #     json_data["timestamp"] = datetime.now().isoformat()
            process_data(json_data)
            time.sleep(1)  # Simulate delay between readings

def process_data(json_data):
    with data_lock:
        for category, values in data_storage.items():
            if isinstance(values, dict):
                for key in values.keys():
                    if key in json_data:
                        if key == "Raw_Direction":  # Process direction data
                            direction = int(json_data[key])  # Ensure conversion to int
                            if direction < 2500:
                                direction += 200
                            else:
                                direction -= 3000
                            direction = _map(direction, 2600, 122, -140, 140)
                            values[key].append(direction)
                        else:
                            try:
                                values[key].append(float(json_data[key]))  # Ensure all data is numerical
                            except ValueError:
                                continue
                        if len(values[key]) > 100:
                            values[key].pop(0)
            if category == "gps":
                gps_coords = json_data.get("GPSCoords", "0 0").split(' ')
                if len(gps_coords) == 2:
                    try:
                        lat, lon = float(gps_coords[0]), float(gps_coords[1])
                        values["lat"].append(lat)
                        values["lon"].append(lon)
                        if len(values["lat"]) > 100:
                            values["lat"].pop(0)
                            values["lon"].pop(0)
                        print(f"Parsed GPS Coordinates: {lat}, {lon}")  # Debug print
                    except (ValueError, IndexError):
                        print("Received malformed GPS coordinates, skipping...")
            if "timestamp" in json_data:
                data_storage["timestamp"].append(json_data["timestamp"])

def log_to_csv(json_data):
    if mode == 'realtime':
        with open(csv_filename, mode='a', newline='') as file:
            writer = csv.writer(file)
            timestamp = datetime.now().isoformat()
            row = [timestamp] + [json_data.get(key, 0) for category in data_storage.values() if isinstance(category, dict) for key in category.keys()] + [json_data.get("Raw_Direction", 0), json_data.get("GPSCoords", "0 0"), json_data.get("Flag", 0)]
            writer.writerow(row)
            data_storage["timestamp"].append(timestamp)

# Start the appropriate listener thread
if mode == 'realtime':
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((UDP_IP, UDP_PORT))

    print(f"Listening for UDP packets on {UDP_IP}:{UDP_PORT}")

    listener_thread = threading.Thread(target=udp_listener)
else:
    listener_thread = threading.Thread(target=replay_listener)

listener_thread.daemon = True
listener_thread.start()

# Set up the plots
fig, axs = plt.subplots(4, 2, figsize=(15, 20))

# gps_lat_bounds = (46.210, 46.203)
# gps_lon_bounds = (7.550, 7.625)

# Configure each subplot
ax_titles = ['Temperatures', 'Speeds', 'Suspensions', 'Pedals', 'Direction', 'GPS Coordinates', 'Flags']
y_limits = [(0, 100), (0, 100), (0, 5000), (1000, 2500), (-150, 150), (None, None), (0, 10)] #TODO: change limits to fit only the possible values
live_data_texts = []

# Define GPS map boundaries
gps_lat_bounds = (46.200, 46.700)
gps_lon_bounds = (7.200, 7.365)

for i, ax in enumerate(axs.flatten()):
    if i < len(ax_titles):
        ax.set_title(ax_titles[i])
        if i != 5:  # All plots except GPS
            ax.set_xlim(0, 100) #TODO: change this to put timestamps (hh:mm:ss i think)
            if y_limits[i]:
                ax.set_ylim(y_limits[i])
        else:  # GPS plot
            ax.set_xlim(gps_lon_bounds)
            ax.set_ylim(gps_lat_bounds)
            ax.set_xlabel('Longitude')
            ax.set_ylabel('Latitude')
        ax.grid(True)
        live_data_texts.append(ax.text(0.05, 0.95, '', transform=ax.transAxes, fontsize=9, verticalalignment='top'))
    else:
        fig.delaxes(ax)

# Lines for each graph
lines = {
    "temperatures": [axs[0, 0].plot([], [], label=key)[0] for key in data_storage["temperatures"].keys()],
    "speeds": [axs[0, 1].plot([], [], label=key)[0] for key in data_storage["speeds"].keys()],
    "suspensions": [axs[1, 0].plot([], [], label=key)[0] for key in data_storage["suspensions"].keys()],
    "pedals": [axs[1, 1].plot([], [], label=key)[0] for key in data_storage["pedals"].keys()],
    "direction": axs[2, 0].plot([], [], label='Raw_Direction')[0],
    "gps": axs[2, 1].plot([], [], 'o', label='GPS Coordinates')[0],
    "flag": axs[3, 0].plot([], [], label='Flag')[0]
}

# Adding legends
for ax in axs.flatten():
    handles, labels = ax.get_legend_handles_labels()
    if handles:
        ax.legend()

flag_lines = []

def add_flag_lines(axs, flag_x): #TODO: check this because it doesn't work ahahaha 
    for ax in axs.flatten():
        flag_line = ax.axvline(x=flag_x, color='red', linestyle='--')
        flag_lines.append(flag_line)
        if len(flag_lines) > 10:
            flag_lines.pop(0).remove()

def init():
    artists = []
    for line_list in lines.values():
        if isinstance(line_list, list):
            for line in line_list:
                line.set_data([], [])
                artists.append(line)
        else:
            line.set_data([], [])
            artists.append(line)
    return artists + live_data_texts

def update(frame):
    artists = []
    with data_lock:
        for i, (category, line_list) in enumerate(lines.items()):
            current_values = []
            if isinstance(line_list, list):
                for line, key in zip(line_list, data_storage[category].keys()):
                    xdata = list(range(len(data_storage[category][key])))
                    ydata = data_storage[category][key]
                    line.set_data(xdata, ydata)
                    if ydata:
                        current_values.append(f"{key}: {ydata[-1]}")
                    ax = line.axes
                    if xdata:
                        ax.set_xlim(max(0, len(xdata) - 100), len(xdata))  # Set the x-axis to scroll
                    artists.append(line)
            else:
                if category == "direction":
                    key = "Raw_Direction"
                    xdata = list(range(len(data_storage["direction"]["Raw_Direction"])))
                    ydata = data_storage["direction"]["Raw_Direction"]
                elif category == "flag":
                    key = "Flag"
                    xdata = list(range(len(data_storage["flag"]["Flag"])))
                    ydata = data_storage["flag"]["Flag"]
                elif category == "gps":
                    lat_data = data_storage["gps"]["lat"]
                    lon_data = data_storage["gps"]["lon"]
                    line_list.set_data(lon_data, lat_data)
                    if lat_data and lon_data:
                        current_values.append(f"GPS: {lat_data[-1]}, {lon_data[-1]}")
                    artists.append(line_list)
                    continue
                else:
                    key = category
                    xdata = list(range(len(data_storage[key])))
                    ydata = data_storage[key]

                line_list.set_data(xdata, ydata)
                if ydata:
                    current_values.append(f"{key}: {ydata[-1]}")
                ax = line_list.axes
                if xdata:
                    ax.set_xlim(max(0, len(xdata) - 100), len(xdata))  # Set the x-axis to scroll
                artists.append(line_list)
            live_data_texts[i].set_text("\n".join(current_values))
    return artists + live_data_texts + flag_lines

# Create the animation
ani = animation.FuncAnimation(fig, update, init_func=init, blit=True, interval=1000, cache_frame_data=False)

# Display the plot
plt.tight_layout()
plt.show()

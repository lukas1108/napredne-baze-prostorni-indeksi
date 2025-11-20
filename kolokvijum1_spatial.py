import time
from auto_simulator import AutoSimulator
from drive_simulator import DriveSimulator, get_route_coordinates, get_route_coords, load_serbian_roads, show_route_distances
import pandas
from rtree import index

# ------------------------------
# Učitati podatke o nezgodama
# ------------------------------
def load_accidents_data():
    file_path = 'dataset/nez-opendata-2020-20210125.xlsx'

    try:
        df = pandas.read_excel(file_path, header=None)
    except FileNotFoundError:
        print(f"❌ Fajl nije pronađen: {file_path}")
        return None

    # 0=id, 1=grad, 2=opstina, 3=datumvreme, 4=lon, 5=lat, 6=steta, 7=opis1, 8=opis2
    df[5] = pandas.to_numeric(df[5], errors='coerce')
    df[4] = pandas.to_numeric(df[4], errors='coerce')
    df[3] = pandas.to_datetime(
        df[3].astype(str),
        format="%d.%m.%Y,%H:%M",
        errors='coerce'
    )

    df['day_of_year'] = df[3].dt.dayofyear
    df['hour_of_day'] = df[3].dt.hour

    spatial_idx = index.Index()
    temporal_day_idx = index.Index()
    temporal_year_idx = index.Index()

    accidents_list = []
    for row_index, row in df.iterrows():
        lat = row[5]
        lon = row[4]
        dt = row[3]

        if pandas.isna(lat) or pandas.isna(lon) or pandas.isna(dt):
            continue

        radius = 0.0001
        bbox = (lon - radius, lat - radius, lon + radius, lat + radius)

        spatial_idx.insert(row_index, bbox)

        #DAN
        hour_val = row['hour_of_day']
        temporal_day_idx.insert(row_index, bbox, obj=(hour_val - 1, hour_val + 1))

        #GODINA
        day_val = row['day_of_year']
        temporal_year_idx.insert(row_index, bbox, obj=(day_val - 30, day_val + 30))

        accidents_list.append({
            'id': row_index,
            'lat': lat,
            'lon': lon,
            'datetime': dt,
            'type': row[6],
            'bbox': bbox
        })

    print(f"Ucitano {len(accidents_list)} nesreća iz 2025. godine.")

    return {
        'df': df,
        'accidents': accidents_list,
        'spatial_idx': spatial_idx,
        'temporal_day_idx': temporal_day_idx,
        'temporal_year_idx': temporal_year_idx
    }


# OVDE UNETI KOD KOJI ĆE PROVERAVATI OKOLINU AUTOMOBILA
# Globalna promenljiva za podatke o nesrećama (inicijalizovana u main-u)
ACCIDENT_DATA = None

def check_accident_zone(lat, lon):
    global ACCIDENT_DATA
    if not ACCIDENT_DATA:
        print("⚠️ Podaci o nesrećama nisu učitani!")
        return

    search_radius = 0.0045
    bbox = (lon - search_radius, lat - search_radius, lon + search_radius, lat + search_radius)

    # 1. prostorne nesrece
    spatial_hits = list(ACCIDENT_DATA['spatial_idx'].intersection(bbox))
    spatial_count = len(spatial_hits)
    # 2. dnevne nesrece
    now = pandas.Timestamp.now()
    current_hour = now.hour

    # vraca tuple
    temporal_day_hits = list(ACCIDENT_DATA['temporal_day_idx'].intersection(bbox, objects='raw'))

    filtered_day_hits = []
    for hit in temporal_day_hits:
        hour_min, hour_max = hit
        if hour_min <= current_hour <= hour_max:
            filtered_day_hits.append(hit)

    day_count = len(filtered_day_hits)

    current_day_of_year = now.dayofyear

    temporal_year_hits = list(ACCIDENT_DATA['temporal_year_idx'].intersection(bbox, objects='raw'))

    filtered_year_hits = []
    for hit in temporal_year_hits:
        day_min, day_max = hit            # ← ispravka: hit JE tuple
        if day_min <= current_day_of_year <= day_max:
            filtered_year_hits.append(hit)

    year_count = len(filtered_year_hits)

    # ukupno
    total_accidents = spatial_count + day_count + year_count

    if total_accidents > 5:
        risk_level = "VEOMA OPASNO"
    elif total_accidents >= 2:
        risk_level = "OPASNO"
    elif total_accidents >= 1:
        risk_level = "UMERENO OPASNO"
    else:
        risk_level = "BEZBEDNO"

    print(f"\n OPASNOST ({lat:.4f}, {lon:.4f})")
    print(f"Prostorne nezgode {spatial_count}")
    print(f"Nezgode u istom satu (+ ili - 1h): {day_count}")
    print(f"Nezgode u istom mesecu (+ ili - 30 dana): {year_count}")
    print(f"Ukupno {total_accidents} - {risk_level}")

if __name__ == "__main__":
    # ------------------------------
    # Učitaj podatke o nezgodama
    # ------------------------------
    ACCIDENT_DATA = load_accidents_data()
    # -------------------------------
    # -------------------------------

    start_city = "Jagodina"
    end_city = "Subotica"

    # 1. Učitaj mrežu puteva Srbije
    G = load_serbian_roads()

    print(f"Ucitana mreža puteva Srbije! {len(G.nodes)} čvorova, {len(G.edges)} ivica.")

    # 2. Odredjivanje koordinata pocetka i kraja rute
    orig, dest = get_route_coordinates(start_city, end_city)

    # 3. Odredjivanje rute
    route_coords, route = get_route_coords(G, orig, dest)

    #show_route_distances(route_coords)

    # 4. Inicijalizacija grafičke mape za voznju rutom
    drive_simulator = DriveSimulator(G, edge_color='lightgray', edge_linewidth=0.5)

    # 5. Prikaz mape sa rutom
    drive_simulator.prikazi_mapu(route_coords, route_color='blue', auto_marker_color='ro', auto_marker_size=8)

    # 6. Inicijalizuj simulator kretanja automobila sa brzinom 250 km/h i intervalom od 1 sekunde
    automobil = AutoSimulator(route_coords, speed_kmh=300, interval=60.0)
    automobil.running = True

    print("\n=== Simulacija pokrenuta ===")
    print("Kontrole: Auto se pomera automatski svakih", automobil.interval, "sekundi")
    print("Za zaustavljanje pritisnite Ctrl+C\n")

    interval_simulacije = 1.0  # sekunde
    # 7. Glavna petlja simulacije
    try:
        step_count = 0
        while automobil.running:
            # Pomeri automobil
            auto_current_pos = automobil.move()
            lat, lon = auto_current_pos

            drive_simulator.move_auto_marker(lat, lon, automobil.get_progress_info(), plot_pause=0.01)


            # Pozovi check_neighbourhood samo na svakih 5 koraka (da ne zatrpava konzolu)
            step_count += 1
            if step_count % 5 == 0:
                # -------------------------------
                # -------------------------------
                check_accident_zone(lat, lon)
                # -------------------------------
                # -------------------------------

            # Proveri da li je stigao na kraj
            if automobil.is_finished():
                print("\n=== Automobil je stigao na destinaciju! ===")
                break

            # Čekaj interval pre sledećeg pomeraja
            time.sleep(interval_simulacije)

    except KeyboardInterrupt:
        print("\n\n=== Simulacija prekinuta ===")


    drive_simulator.finish_drive()





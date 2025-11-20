import time
from auto_simulator import AutoSimulator
from drive_simulator import DriveSimulator, get_route_coordinates, get_route_coords, load_serbian_roads, show_route_distances
import pandas
import h3
from rtree import index

class H3TimeIndex:
    """H3 indeks"""
    def __init__(self, accidents_list, res=9, time_bucket_hours=1):
        self.res = res
        self.time_bucket_hours = time_bucket_hours
        self.index = {}

        for acc in accidents_list:
            lat = acc['lat']
            lon = acc['lon']
            dt = acc['datetime']
            acc_id = acc['id']

            cell = h3.latlng_to_cell(lat, lon, res)
            bucket = int(dt.hour // self.time_bucket_hours) + dt.dayofyear * (24 // self.time_bucket_hours)
            key = (cell, bucket)
            if key not in self.index:
                self.index[key] = []
            self.index[key].append(acc_id)

    def query(self, lat, lon, dt, radius_rings=1):
        """Vraca listu ID-jeva nesreca"""
        cell = h3.latlng_to_cell(lat, lon, self.res)
        bucket = int(dt.hour // self.time_bucket_hours) + dt.dayofyear * (24 // self.time_bucket_hours)

        cells = set()
        for r in range(radius_rings + 1):
            cells.update(h3.grid_disk(cell, r))

        results = []
        for c in cells:
            key = (c, bucket)
            if key in self.index:
                results.extend(self.index[key])
        return results


# ------------------------------
# Učitati podatke o nezgodama
# ------------------------------
def load_accidents_data():
    file_path = 'dataset/nez-opendata-2020-20210125.xlsx'

    try:
        df = pandas.read_excel(file_path, header=None)
    except FileNotFoundError:
        print(f"Fajl nije pronađen: {file_path}")
        return None

    df[5] = pandas.to_numeric(df[5], errors='coerce')  # lat
    df[4] = pandas.to_numeric(df[4], errors='coerce')  # lon
    df[3] = pandas.to_datetime(df[3].astype(str), format="%d.%m.%Y,%H:%M", errors='coerce')  # datum i vreme

    df['day_of_year'] = df[3].dt.dayofyear
    df['hour_of_day'] = df[3].dt.hour

    p = index.Property()
    p.dimension = 2 #samo longitude i latitude sa rtree
    spatial_idx = index.Index(properties=p)

    accidents_list = []
    for idx, row in df.iterrows():
        lat = row[5]
        lon = row[4]
        dt = row[3]
        if pandas.isna(lat) or pandas.isna(lon) or pandas.isna(dt):
            continue

        spatial_idx.insert(idx, (lon, lat, lon, lat)) #ubacivanje

        accidents_list.append({
            'id': idx,
            'lat': lat,
            'lon': lon,
            'datetime': dt,
            'hour_of_day': row['hour_of_day'],
            'day_of_year': row['day_of_year'],
            'type': row[6]
        })

    # H3 indeks za vreme
    h3_idx = H3TimeIndex(accidents_list, res=9, time_bucket_hours=1)

    print(f"Ucitano {len(accidents_list)} nesreca iz 2025. godine.")
    return {
        'df': df,
        'accidents': accidents_list,
        'spatial_idx': spatial_idx,
        'h3_idx': h3_idx
    }

ACCIDENT_DATA = None    # globalna promenljiva za ucitane podatke o nesrecama

def check_accident_zone(lat, lon, current_time=None):

    global ACCIDENT_DATA

    if not ACCIDENT_DATA:
        print("Podaci o nesrecama nisu ucitani!")
        return

    now = current_time or pandas.Timestamp.now()
    search_radius = 0.0045  # 500m

    bbox = (lon - search_radius, lat - search_radius, lon + search_radius, lat + search_radius)
    spatial_hits = list(ACCIDENT_DATA['spatial_idx'].intersection(bbox))

    spatial_count = 0
    same_hour = 0
    same_30d = 0

    for idx in spatial_hits:
        acc = ACCIDENT_DATA['accidents'][idx]
        spatial_count += 1

        dt = acc['datetime']

        if abs((dt - now).total_seconds()) <= 3600:
            same_hour += 1

        if abs(dt.dayofyear - now.dayofyear) <= 30:
            same_30d += 1

    total_accidents = spatial_count + same_hour + same_30d

    if total_accidents > 5:
        risk_level = "Veoma opasno"
    elif total_accidents >= 3:
        risk_level = "Opasno"
    elif total_accidents >= 1:
        risk_level = "Umereno opasno"
    else:
        risk_level = "Bezbedno"

    print(f"\nPROVERA OPASNOSTI ({lat:.4f}, {lon:.4f})")
    print(f"     - Prostorne nezgode: {spatial_count}")
    print(f"     - Nezgode u okviru istog sata: {same_hour}")
    print(f"     - Nezgode u okviru istog meseca: {same_30d}")
    print(f"UKUPNO: {total_accidents} - {risk_level}")

# -------------------------------
# Glavni deo simulacije
# -------------------------------
if __name__ == "__main__":

    ACCIDENT_DATA = load_accidents_data()

    #CUSTOM VREME I GRADOVI
    date_time = pandas.Timestamp("2025-08-11 15:42:34") #custom vreme
    #date_time = None
    start_city = "Jagodina"
    end_city = "Subotica"

    # 1. Učitaj mrežu puteva Srbije
    G = load_serbian_roads()

    print(f"Ucitana mreža puteva Srbije! {len(G.nodes)} čvorova, {len(G.edges)} ivica.")

    # 2. Odredjivanje koordinata pocetka i kraja rute
    orig, dest = get_route_coordinates(start_city, end_city)

    # 3. Odredjivanje rute
    route_coords, route = get_route_coords(G, orig, dest)

    # show_route_distances(route_coords)

    # 4. Inicijalizacija grafičke mape za voznju rutom
    drive_simulator = DriveSimulator(G, edge_color='lightgray', edge_linewidth=0.5)

    # 5. Prikaz mape sa rutom
    drive_simulator.prikazi_mapu(route_coords, route_color='blue', auto_marker_color='ro', auto_marker_size=8)

    # 6. Inicijalizuj simulator kretanja automobila sa brzinom 250 km/h i intervalom od 60 sekundi
    automobil = AutoSimulator(route_coords, speed_kmh=250, interval=60.0)
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


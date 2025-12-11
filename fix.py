import streamlit as st
import requests
import pandas as pd
import json
import os
import time
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from datetime import datetime

# --- 1. KONFIGURASI USER ---
MY_NIM = "2213030014"       
MY_PASSWORD = "2213030014" 
BASE_URL = 'https://siakad2.unpkediri.ac.id/'
CONFIG_FILE = 'auto_absen_config.json'

# --- 2. CONFIG HALAMAN ---
st.set_page_config(
    page_title="SIAKAD Auto Pilot",
    page_icon="🤖",
    layout="wide"
)

# --- 3. MANAJEMEN PENYIMPANAN (Supaya Settingan Tidak Hilang) ---
def load_config():
    """Memuat daftar matkul yang di-whitelist untuk auto absen."""
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    return []

def save_config(selected_matkuls):
    """Menyimpan daftar matkul yang dipilih ke file."""
    with open(CONFIG_FILE, 'w') as f:
        json.dump(selected_matkuls, f)

# --- 4. ENGINE UTAMA (LOGIN & ABSEN) ---

def init_browser():
    """Inisialisasi browser dengan Header sesuai Burp Suite agar tidak terdeteksi bot."""
    if 'browser' not in st.session_state:
        st.session_state['browser'] = requests.Session()
        # Headers sesuai screenshot Burp Suite Anda
        st.session_state['browser'].headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36',
            'Referer': BASE_URL + 'template/login/login.php',
            'Origin': BASE_URL
        })

def login_otomatis():
    """Melakukan login otomatis jika belum login."""
    session = st.session_state['browser']
    
    # Cek dulu apakah session masih hidup (akses home)
    try:
        cek = session.get(BASE_URL + 'home.php')
        if "Selamat datang" in cek.text or "Logout" in cek.text:
            return True, "Session Aktif"
    except:
        pass

    # Jika mati, lakukan Login Ulang
    login_url = BASE_URL + 'template/login/login.php'
    payload = {'username': MY_NIM, 'password': MY_PASSWORD}
    
    try:
        res = session.post(login_url, data=payload)
        # Cek cookie PHPSESSID dari respon
        if "home" in res.url or "logout" in res.text.lower():
            return True, "Login Baru Berhasil"
        return False, "Gagal Login (Cek Password)"
    except Exception as e:
        return False, f"Error: {e}"

def get_data_lengkap():
    """Mengambil Biodata DAN Daftar Matkul sekaligus."""
    session = st.session_state['browser']
    biodata = {}
    matkul_list = []
    
    try:
        # 1. AMBIL BIODATA (dari Home)
        res_home = session.get(BASE_URL + 'home.php')
        soup_home = BeautifulSoup(res_home.text, 'html.parser')
        
        # Cari Tabel Biodata
        tables = soup_home.find_all('table')
        for table in tables:
            if "NPM" in table.get_text():
                rows = table.find_all('tr')
                for row in rows:
                    cols = row.find_all('td')
                    if len(cols) == 3:
                        biodata[cols[0].get_text(strip=True)] = cols[2].get_text(" ", strip=True)
                break
        
        # 2. AMBIL MATKUL (dari Presensi)
        res_presensi = session.get(BASE_URL + 'appl/siakad/presensi_mhs/presensi_mhs.php')
        soup_presensi = BeautifulSoup(res_presensi.text, 'html.parser')
        
        rows = soup_presensi.find_all('tr')
        for row in rows:
            cols = row.find_all('td')
            if len(cols) >= 8:
                try:
                    int(cols[0].get_text(strip=True)) # Validasi kolom no
                    nama = cols[4].get_text(strip=True)
                    dosen = cols[6].get_text(strip=True)
                    link = cols[7].find('a', href=True)
                    url_absen = urljoin(BASE_URL, link['href']) if link else ""
                    
                    if url_absen:
                        matkul_list.append({
                            "Mata Kuliah": nama,
                            "Dosen": dosen,
                            "URL": url_absen
                        })
                except:
                    continue
                    
        return biodata, matkul_list
    except Exception as e:
        return {}, []

def auto_execute(matkul_list):
    """
    Inti Otomatisasi:
    Cek config user -> Cek Matkul -> Eksekusi jika cocok.
    """
    session = st.session_state['browser']
    # Load config matkul mana saja yang boleh di-absenkan
    allowed_matkuls = load_config()
    logs = []
    
    for mk in matkul_list:
        nama = mk['Mata Kuliah']
        
        # Hanya jalankan jika matkul ini ada di daftar "WHITELIST" user
        if nama in allowed_matkuls:
            try:
                # Buka halaman absen matkul
                res = session.get(mk['URL'])
                soup = BeautifulSoup(res.text, 'html.parser')
                
                # Cari tombol/form
                btn_hadir = soup.find('a', class_='btn-success', string=lambda t: t and "Hadir" in t)
                form = soup.find('form')
                
                timestamp = datetime.now().strftime("%H:%M:%S")
                
                if btn_hadir:
                    session.get(urljoin(BASE_URL, btn_hadir['href']))
                    logs.append(f"✅ [{timestamp}] {nama}: SUKSES KLIK HADIR")
                elif form:
                    radios = form.find_all('input', type='radio')
                    if radios:
                        radio_name = radios[0].get('name')
                        payload = {radio_name: 'H', 'simpan': 'Simpan'}
                        session.post(urljoin(BASE_URL, form.get('action', '')), data=payload)
                        logs.append(f"✅ [{timestamp}] {nama}: SUKSES SUBMIT FORM")
                    else:
                        logs.append(f"ℹ️ [{timestamp}] {nama}: Form ada tapi radio button tidak ketemu.")
                else:
                    logs.append(f"⏳ [{timestamp}] {nama}: Belum dibuka.")
            except Exception as e:
                logs.append(f"❌ {nama}: Error {e}")
        else:
            # Matkul tidak dicentang user, skip
            pass
            
    return logs

# --- 5. TAMPILAN UI (MAIN) ---

init_browser()

# Header Dashboard
st.title("🚀 SIAKAD Auto-Pilot")
st.markdown("Bot ini otomatis login dan mengecek absensi matkul yang Anda aktifkan setiap kali dibuka.")

# CONTAINER STATUS (Paling Atas)
status_container = st.container()

# LOGIC RUN-ON-LOAD
# Kode ini jalan otomatis tiap script direfresh/dibuka
with st.spinner("🔄 Auto-Pilot sedang bekerja (Login & Cek Absen)..."):
    is_login, msg_login = login_otomatis()
    
    if is_login:
        biodata, list_matkul = get_data_lengkap()
        
        # JALANKAN AUTO ABSENSI DI BACKGROUND
        if list_matkul:
            log_hasil = auto_execute(list_matkul)
        else:
            log_hasil = ["Tidak ada jadwal kuliah ditemukan."]
            
        # TAMPILAN DASHBOARD
        tab1, tab2 = st.tabs(["📊 Biodata & Log", "⚙️ Pengaturan Auto-Absen"])
        
        # --- TAB 1: HASIL KERJA BOT ---
        with tab1:
            col_bio, col_log = st.columns([1, 2])
            
            with col_bio:
                st.subheader("👤 Profil")
                if biodata:
                    st.success(f"Status: {biodata.get('Status', 'Aktif')}")
                    st.text_input("Nama", biodata.get("Nama", "-"), disabled=True)
                    st.text_input("NIM", biodata.get("NPM", "-"), disabled=True)
                    st.text_input("Prodi", biodata.get("Prodi", "-"), disabled=True)
                else:
                    st.warning("Gagal ambil biodata.")
            
            with col_log:
                st.subheader("📝 Live Log Aktivitas")
                if log_hasil:
                    for log in log_hasil:
                        if "✅" in log:
                            st.success(log)
                        elif "⏳" in log:
                            st.info(log)
                        else:
                            st.write(log)
                else:
                    st.write("Belum ada mata kuliah yang diaktifkan untuk auto-absen.")
                    st.info("Pergi ke Tab 'Pengaturan' untuk memilih matkul.")

        # --- TAB 2: PENGATURAN (TOGGLE) ---
        with tab2:
            st.subheader("⚙️ Pilih Matkul untuk Di-Otomatisasi")
            st.write("Centang mata kuliah yang ingin diabsenkan otomatis oleh bot. Pengaturan ini tersimpan permanen.")
            
            # Load config lama
            saved_config = load_config()
            
            # Siapkan Dataframe untuk Editor
            df_prep = []
            for m in list_matkul:
                df_prep.append({
                    "Aktifkan": m['Mata Kuliah'] in saved_config,
                    "Mata Kuliah": m['Mata Kuliah'],
                    "Dosen": m['Dosen']
                })
            
            df_matkul = pd.DataFrame(df_prep)
            
            # Tampilkan Editor
            if not df_matkul.empty:
                edited_df = st.data_editor(
                    df_matkul,
                    column_config={
                        "Aktifkan": st.column_config.CheckboxColumn(
                            "Auto Absen?",
                            help="Jika dicentang, bot akan otomatis absen di matkul ini saat dibuka.",
                            default=False
                        )
                    },
                    disabled=["Mata Kuliah", "Dosen"],
                    hide_index=True,
                    use_container_width=True
                )
                
                # Logic Penyimpanan Otomatis
                # Kita cek apakah ada perubahan, jika ada kita simpan ke JSON
                current_selected = edited_df[edited_df["Aktifkan"] == True]["Mata Kuliah"].tolist()
                
                # Tombol Simpan Manual (untuk memastikan)
                if st.button("💾 Simpan Pengaturan"):
                    save_config(current_selected)
                    st.success("Pengaturan tersimpan! Bot akan mengingat pilihan ini.")
                    time.sleep(1)
                    st.rerun()
            else:
                st.warning("Tidak ada data mata kuliah.")

    else:
        st.error(f"Gagal Login: {msg_login}")
        st.button("Coba Lagi")
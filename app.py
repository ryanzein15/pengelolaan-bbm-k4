from contextlib import closing
from datetime import date, datetime
from html import escape
from pathlib import Path
import sqlite3

import pandas as pd
import streamlit as st

DB_PATH = Path(__file__).with_name("penjualan_bbm.db")
SEED_PRODUCTS = [
    ("Pertamax", "Bahan Bakar Premium", 16000),
    ("Pertalite", "Bahan Bakar Subsidi", 10000),
    ("Dexlite", "Bahan Bakar Premium", 24000),
    ("Bio Solar", "Bahan Bakar Subsidi", 7000),
    ("Pertamina Dex", "Bahan Bakar Premium", 26000),
]
# (tanggal, nama produk, harga per liter saat transaksi, jumlah liter)
SEED_SALES = [
    ("2026-08-03", "Pertamax", 16000, 3),
    ("2026-08-03", "Pertalite", 10000, 2),
    ("2026-08-05", "Dexlite", 24000, 2),
    ("2026-08-07", "Bio Solar", 7000, 4),
    ("2026-08-10", "Pertamina Dex", 26000, 5),
    ("2026-08-14", "Pertamax", 16000, 5),
    ("2026-08-17", "Pertalite", 10000, 6),
    ("2026-08-17", "Dexlite", 24000, 6),
    ("2026-08-19", "Bio Solar", 7000, 3),
    ("2026-08-21", "Pertamina Dex", 26000, 3),
    ("2026-08-26", "Pertamax", 16000, 3),
    ("2026-08-28", "Pertalite", 10000, 4),
    ("2026-08-31", "Dexlite", 24000, 1),
    ("2026-09-01", "Bio Solar", 7000, 4),
    ("2026-09-02", "Pertamina Dex", 26000, 4),
    ("2026-09-07", "Pertamax", 16000, 5),
    ("2026-09-09", "Pertalite", 10000, 4),
    ("2026-09-11", "Dexlite", 24000, 3),
    ("2026-09-14", "Bio Solar", 7000, 6),
    ("2026-09-16", "Pertamina Dex", 26000, 2),
    ("2026-09-21", "Pertamax", 16000, 5),
    ("2026-09-23", "Pertalite", 10000, 3),
    ("2026-09-25", "Dexlite", 24000, 5),
    ("2026-09-28", "Bio Solar", 7000, 2),
    ("2026-09-30", "Pertamina Dex", 26000, 3),
]
JOIN_SQL = "FROM sales JOIN products ON products.id = sales.product_id"
ALLOWED_USERNAMES = frozenset({"ryan", "wilis", "amel", "tasya"})
REGISTRATION_CODE = "kelompok 4"


def get_connection():
    """Buka koneksi SQLite dan aktifkan pemeriksaan foreign key."""
    connection = sqlite3.connect(DB_PATH)
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize_accounts():
    """Buat tabel akun terdaftar jika belum tersedia."""
    with closing(get_connection()) as connection:
        connection.execute(
            "CREATE TABLE IF NOT EXISTS accounts (username TEXT PRIMARY KEY)"
        )
        connection.commit()


def username_is_allowed(username):
    """Periksa username bawaan dan akun yang sudah terdaftar."""
    if username in ALLOWED_USERNAMES:
        return True

    with closing(get_connection()) as connection:
        return (
            connection.execute(
                "SELECT 1 FROM accounts WHERE username = ?", (username,)
            ).fetchone()
            is not None
        )


def create_account(username):
    """Simpan akun baru; kembalikan False jika username sudah digunakan."""
    with closing(get_connection()) as connection:
        cursor = connection.execute(
            "INSERT OR IGNORE INTO accounts (username) VALUES (?)", (username,)
        )
        connection.commit()
        return cursor.rowcount == 1


def exit_login():
    """Kosongkan formulir masuk dan tampilkan konfirmasi keluar."""
    st.session_state.username_masuk = ""
    st.session_state.login_denied = False
    st.session_state.keluar_dari_masuk = True


def logout_account():
    """Akhiri sesi dashboard dan kembalikan ke halaman awal login."""
    for key in [
        "dashboard_masuk",
        "username_login",
        "username_masuk",
        "tanggal_transaksi",
        "active_page",
        "login_denied",
        "halaman_pendaftaran",
        "keluar_dari_masuk",
        "registration_success",
    ]:
        st.session_state.pop(key, None)
    st.session_state.dashboard_masuk = False
    st.session_state.username_login = ""
    st.session_state.active_page = "Dashboard"
    for key in ["logged_in", "user"]:
        if key in st.query_params:
            st.query_params.pop(key)


def sync_login_from_query_params():
    """Pulihkan sesi login dari URL agar refresh tidak otomatis logout."""
    logged_in = str(st.query_params.get("logged_in", "")).lower() == "true"
    username = str(st.query_params.get("user", "") or "")
    if logged_in and username:
        st.session_state.dashboard_masuk = True
        st.session_state.username_login = username
        return True
    return False


def sync_page_from_query_params():
    """Pulihkan halaman aktif dari URL, tanpa menutup navigasi manual."""
    page = str(st.query_params.get("page", "") or "")
    valid_pages = {
        "Dashboard",
        "Data Stok BBM",
        "Transaksi Penjualan",
        "Pengisian Ulang Stok",
        "Laporan Penjualan dan Keuntungan",
    }
    if page in valid_pages:
        st.session_state.active_page = page
    else:
        st.session_state.setdefault("active_page", "Dashboard")
    return st.session_state.get("active_page", "Dashboard")


def plate_matches_date(plate_digits, selected_date):
    """Cocokkan empat digit nomor kendaraan dengan aturan ganjil/genap tanggal."""
    if len(plate_digits) != 4 or not plate_digits.isdecimal():
        return False
    return int(plate_digits[-1]) % 2 == selected_date.day % 2


def initialize_database():
    """Buat tabel, isi katalog, dan isi transaksi simulasi jika masih kosong."""
    with closing(get_connection()) as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                category TEXT NOT NULL,
                catalog_price INTEGER NOT NULL CHECK (catalog_price > 0),
                stock INTEGER NOT NULL DEFAULT 50,
                cost_price INTEGER
            );

            CREATE TABLE IF NOT EXISTS sales (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sale_date TEXT NOT NULL,
                product_id INTEGER NOT NULL,
                unit_price INTEGER NOT NULL CHECK (unit_price > 0),
                unit_cost INTEGER,
                quantity INTEGER NOT NULL CHECK (quantity > 0),
                total INTEGER NOT NULL CHECK (total = unit_price * quantity),
                FOREIGN KEY (product_id) REFERENCES products(id)
            );

            CREATE TABLE IF NOT EXISTS stock_purchases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_name TEXT NOT NULL,
                price_per_liter INTEGER NOT NULL CHECK (price_per_liter > 0),
                quantity_liter INTEGER NOT NULL CHECK (quantity_liter > 0),
                total_price INTEGER NOT NULL CHECK (total_price > 0),
                purchased_at TEXT NOT NULL
            );
            """
        )
        product_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(products)")
        }
        if "cost_price" not in product_columns:
            connection.execute("ALTER TABLE products ADD COLUMN cost_price INTEGER")

        sales_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(sales)")
        }
        if "unit_cost" not in sales_columns:
            connection.execute("ALTER TABLE sales ADD COLUMN unit_cost INTEGER")

        connection.execute(
            "DELETE FROM sales WHERE product_id IN (SELECT id FROM products WHERE name = 'Nitrogen')"
        )
        connection.execute("DELETE FROM products WHERE name = 'Nitrogen'")

        connection.executemany(
            """
            INSERT OR IGNORE INTO products (name, category, catalog_price, cost_price)
            VALUES (?, ?, ?, ?)
            """,
            [(name, category, price, price - 4000) for name, category, price in SEED_PRODUCTS],
        )
        connection.execute(
            "UPDATE products SET cost_price = catalog_price - 4000 WHERE cost_price IS NULL OR cost_price <= 0"
        )

        stock_purchase_count = connection.execute(
            "SELECT COUNT(*) FROM stock_purchases"
        ).fetchone()[0]
        if stock_purchase_count == 0:
            connection.executemany(
                """
                INSERT INTO stock_purchases
                    (product_name, price_per_liter, quantity_liter, total_price, purchased_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                [
                    ("Pertamax", 15000, 2000, 30000000, "2026-10-10T09:00:00"),
                    ("Pertalite", 6000, 1500, 13500000, "2026-10-12T11:20:00"),
                ],
            )

        sales_count = connection.execute("SELECT COUNT(*) FROM sales").fetchone()[0]
        if sales_count == 0:
            product_ids = dict(
                connection.execute("SELECT name, id FROM products").fetchall()
            )
            product_costs = dict(
                connection.execute("SELECT id, cost_price FROM products").fetchall()
            )
            connection.executemany(
                """
                INSERT INTO sales
                    (sale_date, product_id, unit_price, unit_cost, quantity, total)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        sale_date,
                        product_ids[name],
                        price,
                        product_costs[product_ids[name]],
                        quantity,
                        price * quantity,
                    )
                    for sale_date, name, price, quantity in SEED_SALES
                ],
            )
        else:
            connection.execute(
                """
                UPDATE sales
                SET unit_cost = (
                    SELECT products.cost_price
                    FROM products
                    WHERE products.id = sales.product_id
                )
                WHERE unit_cost IS NULL
                """
            )
        connection.commit()


def run_query(sql, params=()):
    """Jalankan query SELECT dan kembalikan hasilnya sebagai tabel DataFrame."""
    with closing(get_connection()) as connection:
        return pd.read_sql_query(sql, connection, params=list(params))


def get_categories():
    """Ambil daftar kategori untuk pilihan filter."""
    result = run_query("SELECT DISTINCT category FROM products ORDER BY category")
    return result["category"].tolist()


def get_date_bounds():
    """Ambil tanggal transaksi paling awal dan paling akhir."""
    result = run_query(
        "SELECT MIN(sale_date) AS first_date, MAX(sale_date) AS last_date FROM sales"
    )
    return (
        date.fromisoformat(result.iloc[0]["first_date"]),
        date.fromisoformat(result.iloc[0]["last_date"]),
    )


def get_total_units_sold():
    """Hitung total keseluruhan unit/liter yang sudah terjual."""
    result = run_query("SELECT COALESCE(SUM(quantity), 0) AS total FROM sales")
    return result.iloc[0]["total"]


def get_product_stock(product_name):
    """Ambil sisa stok produk tertentu."""
    result = run_query("SELECT stock FROM products WHERE name = ?", (product_name,))
    if not result.empty:
        return result.iloc[0]["stock"]
    return 0
    


def build_filter(start_date, end_date, categories):
    """Susun bagian WHERE dan nilai parameternya dari pilihan filter."""
    placeholders = ", ".join("?" for _ in categories)
    where_sql = (
        "WHERE sales.sale_date BETWEEN ? AND ? "
        f"AND products.category IN ({placeholders})"
    )
    params = [start_date.isoformat(), end_date.isoformat(), *categories]
    return where_sql, params


def get_summary(where_sql, params):
    """Hitung angka ringkasan untuk semua transaksi yang lolos filter."""
    result = run_query(
        f"""
        SELECT
            COUNT(*) AS jumlah_transaksi,
            COALESCE(SUM(sales.quantity), 0) AS unit_terjual,
            COALESCE(SUM(sales.total), 0) AS omzet,
            COALESCE(AVG(sales.total), 0) AS rata_rata,
            COALESCE(MAX(sales.total), 0) AS transaksi_terbesar
        {JOIN_SQL}
        {where_sql}
        """,
        params,
    )
    return result.iloc[0]


def get_dashboard_profit(where_sql, params):
    """Hitung estimasi laba kotor dari selisih harga jual dan modal."""
    result = run_query(
        f"""
        SELECT
            COALESCE(
                SUM(
                    (sales.unit_price - COALESCE(sales.unit_cost, products.cost_price))
                    * sales.quantity
                ),
                0
            ) AS estimasi_keuntungan,
            SUM(CASE WHEN COALESCE(sales.unit_cost, products.cost_price) IS NULL THEN 1 ELSE 0 END)
                AS transaksi_tanpa_modal
        {JOIN_SQL}
        {where_sql}
        """,
        params,
    )
    return result.iloc[0]


def get_sales_chart(where_sql, params):
    """Ambil jumlah liter terjual per bulan untuk grafik dashboard."""
    return run_query(
        f"""
        SELECT
            strftime('%Y-%m', sales.sale_date) AS bulan,
            SUM(sales.quantity) AS liter_terjual
        {JOIN_SQL}
        {where_sql}
        GROUP BY bulan
        ORDER BY bulan
        """,
        params,
    )


def get_report_by_product(where_sql, params, min_revenue):
    """Laporan per produk; HAVING menyaring produk dengan omzet kecil."""
    return run_query(
        f"""
        SELECT
            products.name AS produk,
            products.category AS kategori,
            COUNT(*) AS jumlah_transaksi,
            SUM(sales.quantity) AS unit_terjual,
            SUM(sales.total) AS omzet
        {JOIN_SQL}
        {where_sql}
        GROUP BY products.id, products.name, products.category
        HAVING SUM(sales.total) >= ?
        ORDER BY omzet DESC, produk
        """,
        [*params, min_revenue],
    )


def get_report_by_category(where_sql, params):
    """Laporan per kategori produk."""
    return run_query(
        f"""
        SELECT
            products.category AS kategori,
            COUNT(*) AS jumlah_transaksi,
            SUM(sales.quantity) AS unit_terjual,
            SUM(sales.total) AS omzet
        {JOIN_SQL}
        {where_sql}
        GROUP BY products.category
        ORDER BY omzet DESC
        """,
        params,
    )


def get_report_by_month(where_sql, params):
    """Laporan per bulan; strftime mengambil tahun-bulan dari tanggal."""
    return run_query(
        f"""
        SELECT
            strftime('%Y-%m', sales.sale_date) AS bulan,
            COUNT(*) AS jumlah_transaksi,
            SUM(sales.quantity) AS unit_terjual,
            SUM(sales.total) AS omzet
        {JOIN_SQL}
        {where_sql}
        GROUP BY bulan
        ORDER BY bulan
        """,
        params,
    )


def get_sales_detail(where_sql, params):
    """Data detail (baris per transaksi) untuk menelusuri angka laporan."""
    return run_query(
        f"""
        SELECT
            sales.id AS nomor,
            sales.sale_date AS tanggal,
            products.name AS produk,
            products.category AS kategori,
            sales.unit_price AS harga_satuan,
            sales.quantity AS jumlah,
            sales.total AS total
        {JOIN_SQL}
        {where_sql}
        ORDER BY sales.sale_date, sales.id
        """,
        params,
    )


def get_stock_purchase_history(limit=10, product_name=None, month_filter=None):
    """Ambil riwayat pembelian stok dengan opsi filter produk dan bulan."""
    sql = """
        SELECT
            product_name AS jenis_bbm,
            price_per_liter AS harga_per_liter,
            quantity_liter AS jumlah_liter,
            total_price AS total_harga,
            purchased_at AS tanggal_pembelian
        FROM stock_purchases
        WHERE 1 = 1
    """
    params = []
    if product_name and product_name != "Semua":
        sql += " AND product_name = ?"
        params.append(product_name)
    if month_filter and month_filter != "Semua":
        sql += " AND strftime('%Y-%m', purchased_at) = ?"
        params.append(month_filter)
    sql += " ORDER BY id DESC"
    if limit is not None:
        sql += " LIMIT ?"
        params.append(limit)
    return run_query(sql, tuple(params))


def reset_stock_purchase_history():
    """Hapus riwayat pembelian stok dan kembalikan saldo produk ke 0."""
    with closing(get_connection()) as connection:
        connection.execute("DELETE FROM stock_purchases")
        connection.execute(
            "UPDATE products SET stock = 0, cost_price = CASE WHEN cost_price IS NULL OR cost_price <= 0 THEN catalog_price - 4000 ELSE cost_price END"
        )
        connection.commit()


def get_purchase_status(purchased_at):
    """Tentukan status pengiriman teks secara sederhana berdasarkan waktu pembelian."""
    try:
        purchased_dt = datetime.fromisoformat(str(purchased_at))
    except ValueError:
        return "Diproses"

    delta_hours = (datetime.now() - purchased_dt).total_seconds() / 3600
    if delta_hours <= 2:
        return "Diproses"
    if delta_hours <= 24:
        return "Dalam perjalanan"
    return "Tiba"


def format_rupiah(value):
    """Ubah angka menjadi teks rupiah, misalnya 1500000 -> Rp1.500.000."""
    return f"Rp{round(value):,}".replace(",", ".")


def get_stock_status(stock_value):
    """Kembalikan status stok yang mudah dibaca untuk dashboard dan tabel."""
    stock = int(stock_value)
    if stock <= 0:
        return "Habis"
    if stock <= 100:
        return "Menipis"
    return "Tersedia"


def get_stock_status_color(stock_value):
    """Warna status stok untuk tampilan visual di UI."""
    stock = int(stock_value)
    if stock <= 0:
        return "#dc2626"
    if stock <= 100:
        return "#d97706"
    return "#16a34a"


def to_csv_bytes(table):
    """Ubah DataFrame menjadi isi file CSV yang rapi saat dibuka di Excel."""
    return table.to_csv(index=False, sep=";").encode("utf-8-sig")


COLUMN_CONFIG = {
    "nomor": st.column_config.NumberColumn("No."),
    "tanggal": st.column_config.TextColumn("Tanggal"),
    "bulan": st.column_config.TextColumn("Bulan"),
    "produk": st.column_config.TextColumn("Produk"),
    "kategori": st.column_config.TextColumn("Kategori"),
    "jumlah_transaksi": st.column_config.NumberColumn("Jumlah transaksi"),
    "unit_terjual": st.column_config.NumberColumn("Unit terjual"),
    "jumlah": st.column_config.NumberColumn("Jumlah unit"),
    "harga_satuan": st.column_config.NumberColumn(
        "Harga satuan (Rp)", format="localized"
    ),
    "total": st.column_config.NumberColumn("Total (Rp)", format="localized"),
    "omzet": st.column_config.NumberColumn("Omzet (Rp)", format="localized"),
}


def show_report(table, file_stem, start_date, end_date):
    """Tampilkan tabel laporan beserta tombol unduh CSV-nya."""
    if table.empty:
        st.info("Tidak ada baris laporan untuk filter ini.")
        return False

    st.dataframe(
        table,
        column_config=COLUMN_CONFIG,
        hide_index=True,
        width="stretch",
    )
    st.download_button(
        "Unduh CSV",
        data=to_csv_bytes(table),
        file_name=f"{file_stem}_{start_date}_{end_date}.csv",
        mime="text/csv",
        key=f"download_{file_stem}",
    )
    return True


def main():
    st.set_page_config(page_title="Nusa Energy", layout="wide")
    st.session_state.setdefault("dashboard_masuk", False)
    st.session_state.setdefault("username_login", "")
    st.session_state.setdefault("active_page", "Dashboard")

    if not st.session_state.get("dashboard_masuk", False):
        sync_login_from_query_params()
    if "active_page" not in st.session_state:
        sync_page_from_query_params()

    st.markdown(
        """
        <style>
            html {
                font-size: 14px;
            }
            input, textarea {
                color: #111827 !important;
            }
            input::placeholder, textarea::placeholder {
                color: #64748b !important;
                opacity: 1;
            }
            [data-baseweb="select"] * {
                color: #111827 !important;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )

    if not st.session_state.get("dashboard_masuk", False):
        initialize_accounts()

        if st.session_state.get("halaman_pendaftaran", False):
            st.title("Daftar Akun")
            st.caption("Isi formulir berikut untuk membuat akun baru.")
            with st.form("form_pendaftaran"):
                username_baru = st.text_input(
                    "Nama username",
                    placeholder="Masukkan username yang ingin digunakan",
                )
                kode_perizinan = st.text_input(
                    "Kode perizinan",
                    type="password",
                    help="Masukkan kode perizinan yang diberikan.",
                )
                daftar_dikirim = st.form_submit_button(
                    "Daftar akun", type="primary", use_container_width=True
                )

            if daftar_dikirim:
                username_baru = username_baru.strip().lower()
                if not username_baru:
                    st.error("Username wajib diisi.")
                elif kode_perizinan.strip() != REGISTRATION_CODE:
                    st.error("Kode perizinan salah. Akun tidak dibuat.")
                elif username_is_allowed(username_baru):
                    st.error("Username sudah terdaftar. Gunakan username lain.")
                elif create_account(username_baru):
                    st.session_state.halaman_pendaftaran = False
                    st.session_state.username_masuk = username_baru
                    st.session_state.login_denied = False
                    st.session_state.registration_success = True
                    st.rerun()
                else:
                    st.error("Username sudah terdaftar. Gunakan username lain.")

            if st.button("Kembali ke halaman masuk"):
                st.session_state.halaman_pendaftaran = False
                st.rerun()
            return

        if st.session_state.get("keluar_dari_masuk", False):
            st.title("Anda telah keluar")
            st.info("Silakan tutup tab ini untuk meninggalkan aplikasi.")
            if st.button("Kembali ke halaman masuk"):
                st.session_state.keluar_dari_masuk = False
                st.rerun()
            return

        st.markdown(
            """
            <style>
                [data-testid="stSidebar"] {display: none;}
                .block-container {
                    padding-top: 16vh;
                    max-width: 1100px;
                }
                .nusa-welcome {
                    min-height: 48vh;
                    display: flex;
                    flex-direction: column;
                    align-items: center;
                    justify-content: center;
                    text-align: center;
                }
                .nusa-logo-wrap {
                    display: flex;
                    justify-content: center;
                    margin-bottom: 1.3rem;
                }
                .nusa-logo {
                    width: 94px;
                    height: 94px;
                    filter: drop-shadow(0 10px 18px rgba(19, 134, 111, 0.26));
                }
                .nusa-mark {
                    color: #13866f;
                    font-size: 1rem;
                    font-weight: 700;
                    letter-spacing: 0.45rem;
                    margin-bottom: 1.1rem;
                }
                .nusa-title {
                    color: #172b35;
                    font-size: clamp(2.2rem, 6vw, 4rem);
                    font-weight: 750;
                    letter-spacing: 0.08em;
                    line-height: 1.08;
                    margin: 0;
                }
                .nusa-subtitle {
                    color: #6b7b82;
                    font-size: 0.95rem;
                    margin-top: 1.2rem;
                }
                div.stButton > button[kind="primary"] {
                    min-height: 3.2rem;
                    border-radius: 999px;
                    font-weight: 700;
                    letter-spacing: 0.12em;
                }
            </style>
            <section class="nusa-welcome">
                <div class="nusa-logo-wrap">
                    <svg class="nusa-logo" viewBox="0 0 120 120" xmlns="http://www.w3.org/2000/svg" aria-label="Nusa Energy logo">
                        <defs>
                            <linearGradient id="nusaLogoGradient" x1="0" x2="1" y1="0" y2="1">
                                <stop offset="0%" stop-color="#0f766e" />
                                <stop offset="100%" stop-color="#083344" />
                            </linearGradient>
                        </defs>
                        <rect x="8" y="8" width="104" height="104" rx="28" fill="url(#nusaLogoGradient)" />
                        <circle cx="60" cy="60" r="32" fill="rgba(255,255,255,0.12)" />
                        <path d="M60 33 L78 55.5 C80.5 58.2 80.5 62.8 78 65.5 L60 87 L42 65.5 C39.5 62.8 39.5 58.2 42 55.5 L60 33 Z" fill="#ffffff" opacity="0.95"/>
                        <path d="M60 44 L68 56.1 C69.3 57.8 69.3 60.2 68 61.9 L60 72.5 L52 61.9 C50.7 60.2 50.7 57.8 52 56.1 L60 44 Z" fill="#0f766e" opacity="0.9"/>
                        <path d="M60 21 L74 26 L69 38 L60 34 L51 38 L46 26 Z" fill="#facc15" opacity="0.95"/>
                        <path d="M32 69 L52 69 L59 82 L42 84 Z" fill="#f8fafc" opacity="0.9"/>
                        <path d="M88 69 L68 69 L61 82 L78 84 Z" fill="#f8fafc" opacity="0.9"/>
                    </svg>
                </div>
                <div class="nusa-mark">● &nbsp; ENERGI UNTUK NEGERI</div>
                <h1 class="nusa-title">NUSA ENERGY</h1>
                <p class="nusa-subtitle">
                    Sistem informasi penjualan dan persediaan BBM
                </p>
            </section>
            """,
            unsafe_allow_html=True,
        )
        _, button_column, _ = st.columns([1, 1, 1])
        with button_column:
            username = st.text_input(
                "Masukkan username",
                placeholder="Contoh: ryan",
                key="username_masuk",
            )
            if st.session_state.pop("registration_success", False):
                st.success("Akun berhasil dibuat. Silakan masuk dengan username Anda.")
            if st.button(
                "MASUK",
                type="primary",
                use_container_width=True,
                key="tombol_masuk_dashboard",
            ):
                username_normalized = username.strip().lower()
                if username_is_allowed(username_normalized):
                    st.session_state.username_login = username_normalized
                    st.session_state.tanggal_transaksi = date.today()
                    st.session_state.dashboard_masuk = True
                    st.query_params["logged_in"] = "true"
                    st.query_params["user"] = username_normalized
                    st.rerun()
                else:
                    st.session_state.login_denied = True
                    st.error("Username tidak diizinkan. Periksa kembali username Anda.")
            if st.session_state.get("login_denied", False):
                daftar_column, keluar_column = st.columns(2)
                if daftar_column.button("Daftar akun", use_container_width=True):
                    st.session_state.halaman_pendaftaran = True
                    st.session_state.login_denied = False
                    st.rerun()
                keluar_column.button(
                    "Keluar", use_container_width=True, on_click=exit_login
                )
        return

    initialize_database()
    st.markdown(
        """
        <style>
            [data-testid="stAppViewContainer"] {
                background: #f3f6fa;
            }
            .block-container {
                max-width: 1500px;
                padding-top: 2rem;
                padding-bottom: 3rem;
            }
            [data-testid="stSidebar"] {
                background: #14283f;
            }
            [data-testid="stSidebar"] * {
                color: #e8eef5;
            }
            [data-testid="stSidebar"] button,
            [data-testid="stSidebar"] button * {
                color: #14283f !important;
                -webkit-text-fill-color: #14283f !important;
            }
            [data-testid="stSidebar"] [data-testid="stWidgetLabel"] {
                color: #ffffff !important;
            }
            [data-testid="stSidebar"] [data-testid="stDateInput"] *,
            [data-testid="stSidebar"] [data-testid="stMultiSelect"] *,
            [data-testid="stSidebar"] [data-testid="stSelectbox"] *,
            [data-testid="stSidebar"] [data-testid="stSlider"] [data-testid="stThumbValue"] {
                color: #111827 !important;
            }
            [data-testid="stSidebar"] label,
            [data-testid="stSidebar"] label *,
            [data-testid="stSidebar"] [data-testid="stWidgetLabel"],
            [data-testid="stSidebar"] [data-testid="stWidgetLabel"] * {
                color: #ffffff !important;
                -webkit-text-fill-color: #ffffff !important;
            }
            [data-testid="stSidebar"] [data-testid="stDateInput"] input {
                -webkit-text-fill-color: #111827 !important;
                opacity: 1 !important;
            }
            [data-testid="stMetric"] {
                background: #ffffff;
                border: 1px solid #e5ebf1;
                border-radius: 14px;
                padding: 1rem 1.1rem;
                box-shadow: 0 3px 12px rgba(25, 48, 74, 0.05);
            }
            [data-testid="stMetricLabel"] {
                color: #64748b;
            }
            .dashboard-eyebrow {
                color: #16816f;
                font-size: 0.75rem;
                font-weight: 750;
                letter-spacing: 0.16em;
                text-transform: uppercase;
                margin: 0 0 0.25rem;
            }
            .dashboard-heading {
                color: #14283f;
                font-size: clamp(1.45rem, 2.5vw, 1.9rem);
                font-weight: 750;
                line-height: 1.15;
                margin: 0;
            }
            .dashboard-subheading {
                color: #718096;
                margin: 0.45rem 0 0;
            }
            .stock-card {
                background: #ffffff;
                border: 1px solid #e5ebf1;
                border-radius: 12px;
                padding: 0.8rem 0.9rem;
                margin-bottom: 0.6rem;
            }
            .stock-card-title {
                color: #26384b;
                font-weight: 700;
            }
            .stock-card-meta {
                color: #64748b;
                font-size: 0.85rem;
                margin-top: 0.25rem;
            }
            div.stButton > button {
                border-radius: 9px;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )

    first_date, last_date = get_date_bounds()
    categories = get_categories()
    df_products = run_query(
        "SELECT name, category, catalog_price, stock, cost_price FROM products"
    )
    tanggal_transaksi = st.session_state.get("tanggal_transaksi", date.today())

    with st.sidebar:
        sapaan_username = escape(
            st.session_state.get("username_login", "Pengguna").title()
        )
        greeting_column, logout_column = st.columns([4, 1])
        with greeting_column:
            st.markdown(
                f"""
                <div style="padding: 0.6rem 0 1rem;">
                    <div style="
                        font-size: 1.15rem; font-weight: 750; color: #ffffff;
                        margin-bottom: 0.25rem;">
                        Hai, {sapaan_username} :)
                    </div>
                    <div style="
                        font-size: 0.88rem; color: #c2d0df; margin-bottom: 1rem;">
                        Have a nice day :)
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        logout_column.button(
            "↪",
            help="Logout akun",
            key="logout_account",
            on_click=logout_account,
        )
        st.markdown(
            """
            <div style="padding: 0 0 1rem;">
                <div style="font-size: 1.25rem; font-weight: 800;">
                    ⛽ NUSA ENERGY
                </div>
                <div style="font-size: 0.78rem; color: #a9bbce;">
                    SISTEM OPERASIONAL SPBU
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        menu_pages = [
            "Dashboard",
            "Data Stok BBM",
            "Transaksi Penjualan",
            "Pengisian Ulang Stok",
            "Laporan Penjualan dan Keuntungan",
        ]
        pending_page = st.session_state.pop("pending_page", None)
        if pending_page in menu_pages:
            st.session_state["active_page"] = pending_page
        st.session_state.setdefault("active_page", "Dashboard")
        current_page = st.session_state.get("active_page", "Dashboard")
        if current_page not in menu_pages:
            current_page = "Dashboard"
        active_page = st.radio(
            "Navigasi",
            options=menu_pages,
            index=menu_pages.index(current_page),
            key="active_page",
            label_visibility="collapsed",
        )
        st.query_params["page"] = active_page

        if active_page == "Dashboard":
            st.divider()
            st.subheader("🛒 Input Transaksi Baru")
            pilihan_produk = st.selectbox(
                "Pilih Produk", df_products["name"].tolist()
            )
            produk_info = df_products[df_products["name"] == pilihan_produk].iloc[0]
            stok_sekarang = int(produk_info["stock"])
            harga_transaksi = int(produk_info["catalog_price"])
            is_subsidized = produk_info["category"] == "Bahan Bakar Subsidi"
            st.caption(f"Tanggal transaksi: {tanggal_transaksi:%d/%m/%Y}")
            st.write(f"Harga Satuan: {format_rupiah(harga_transaksi)}")
            st.write(f"Sisa Stok: {stok_sekarang} Liter")

            if is_subsidized:
                plat_nomor = st.text_input(
                    "4 angka terakhir plat nomor",
                    max_chars=4,
                    key=f"plat_nomor_{pilihan_produk}",
                    help="BBM bersubsidi mengikuti aturan ganjil/genap tanggal transaksi.",
                )
            else:
                plat_nomor = ""

            if stok_sekarang <= 200:
                st.error(
                    f"🚨 **PERINGATAN!** Stok {pilihan_produk} sisa "
                    f"{stok_sekarang} liter. Segera Restock!"
                )

            if pd.isna(produk_info["cost_price"]):
                st.warning("Harga modal produk ini belum diatur.")
            else:
                st.write(
                    f"Harga Modal: {format_rupiah(int(produk_info['cost_price']))}"
                )

            quantity_key = f"jumlah_beli_{pilihan_produk}"
            if st.session_state.pop(f"reset_{quantity_key}", False):
                st.session_state[quantity_key] = 0
            jumlah_beli = st.number_input(
                "Jumlah Beli (Liter)",
                min_value=0,
                value=0,
                step=1,
                key=quantity_key,
            )
            total_transaksi = harga_transaksi * jumlah_beli
            sisa_stok_setelah = stok_sekarang - jumlah_beli
            st.markdown("#### Ringkasan transaksi")
            st.write(f"Produk: {pilihan_produk}")
            st.write(f"Harga satuan: {format_rupiah(harga_transaksi)}")
            st.write(f"Jumlah beli: {jumlah_beli:,} liter")
            st.write(f"Total: {format_rupiah(total_transaksi)}")
            st.write(f"Sisa stok setelah transaksi: {max(sisa_stok_setelah, 0):,} liter")
            if st.button("Proses Transaksi", disabled=jumlah_beli == 0):
                if jumlah_beli <= 0:
                    st.error("Jumlah beli harus lebih dari 0 liter.")
                    st.stop()
                if jumlah_beli > stok_sekarang:
                    st.error(
                        f"Jumlah beli melebihi stok yang tersedia "
                        f"({stok_sekarang} liter). Kurangi jumlah pembelian."
                    )
                    st.stop()
                if is_subsidized and not plate_matches_date(
                    plat_nomor.strip(), tanggal_transaksi
                ):
                    if len(plat_nomor.strip()) != 4 or not plat_nomor.strip().isdecimal():
                        st.error(
                            "Masukkan tepat 4 angka terakhir plat nomor "
                            "untuk membeli BBM bersubsidi."
                        )
                    else:
                        aturan_hari = (
                            "genap" if tanggal_transaksi.day % 2 == 0 else "ganjil"
                        )
                        st.error(
                            f"Transaksi BBM bersubsidi tidak dapat dilakukan: "
                            f"tanggal {tanggal_transaksi:%d/%m/%Y} adalah tanggal "
                            f"{aturan_hari}, sedangkan plat nomor berakhiran "
                            f"{int(plat_nomor.strip()[-1])}."
                        )
                    st.stop()

                with closing(get_connection()) as connection:
                    cursor = connection.execute(
                        """
                        UPDATE products
                        SET stock = stock - ?
                        WHERE name = ? AND stock >= ?
                        """,
                        (jumlah_beli, pilihan_produk, jumlah_beli),
                    )
                    if cursor.rowcount:
                        product_id = connection.execute(
                            "SELECT id FROM products WHERE name = ?",
                            (pilihan_produk,),
                        ).fetchone()[0]
                        connection.execute(
                            """
                            INSERT INTO sales
                                (
                                    sale_date, product_id, unit_price, unit_cost,
                                    quantity, total
                                )
                            VALUES (?, ?, ?, ?, ?, ?)
                            """,
                            (
                                tanggal_transaksi.isoformat(),
                                product_id,
                                harga_transaksi,
                                (
                                    int(produk_info["cost_price"])
                                    if not pd.isna(produk_info["cost_price"])
                                    else None
                                ),
                                jumlah_beli,
                                harga_transaksi * jumlah_beli,
                            ),
                        )
                        connection.commit()
                    else:
                        st.error("Stok tidak mencukupi!")
                        st.stop()
                st.session_state[f"reset_{quantity_key}"] = True
                st.success("Transaksi berhasil!")
                st.rerun()

            with st.expander("Atur harga modal produk"):
                produk_modal = st.selectbox(
                    "Produk untuk diatur modalnya",
                    df_products["name"].tolist(),
                    key="produk_modal",
                )
                info_modal = df_products[df_products["name"] == produk_modal].iloc[0]
                modal_sekarang = (
                    int(info_modal["cost_price"])
                    if not pd.isna(info_modal["cost_price"])
                    else 0
                )
                harga_modal_baru = st.number_input(
                    "Harga modal per liter (Rp)",
                    min_value=1,
                    value=max(1, modal_sekarang),
                    step=500,
                    key=f"harga_modal_{produk_modal}",
                )
                if st.button("Simpan harga modal"):
                    with closing(get_connection()) as connection:
                        connection.execute(
                            "UPDATE products SET cost_price = ? WHERE name = ?",
                            (harga_modal_baru, produk_modal),
                        )
                        connection.commit()
                    st.success(f"Harga modal {produk_modal} berhasil disimpan.")
                    st.rerun()

            st.divider()
            st.header("Filter laporan")
            period = st.date_input(
                "Periode",
                value=(first_date, last_date),
                format="DD/MM/YYYY",
            )
            selected_categories = st.multiselect(
                "Kategori", options=categories, default=categories
            )
            min_revenue = st.slider(
                "Omzet minimum per produk (Rp)",
                min_value=0,
                max_value=500000,
                value=0,
                step=25000,
            )

    if active_page != "Dashboard":
        st.title(active_page)
        if active_page == "Data Stok BBM":
            stock_table = df_products.copy()
            stock_table["status"] = stock_table["stock"].apply(get_stock_status)
            stock_table["status_color"] = stock_table["stock"].apply(get_stock_status_color)
            stock_table = stock_table.rename(
                columns={
                    "name": "Produk",
                    "category": "Kategori",
                    "catalog_price": "Harga jual (Rp)",
                    "stock": "Stok (liter)",
                    "cost_price": "Harga modal (Rp)",
                }
            )
            st.subheader("Filter stok")
            filter_search, filter_status = st.columns([1.5, 1])
            with filter_search:
                product_options = ["Semua"] + stock_table["Produk"].sort_values().tolist()
                search_term = st.selectbox(
                    "Cari produk",
                    options=product_options,
                    index=0,
                )
            with filter_status:
                status_filter = st.selectbox(
                    "Status stok",
                    options=["Semua", "Tersedia", "Menipis", "Habis"],
                    index=0,
                )
            filtered_stock = stock_table.copy()
            if search_term != "Semua":
                filtered_stock = filtered_stock[
                    filtered_stock["Produk"] == search_term
                ]
            if status_filter != "Semua":
                filtered_stock = filtered_stock[filtered_stock["status"] == status_filter]

            if filtered_stock.empty:
                st.info("Tidak ada data produk yang sesuai dengan filter saat ini.")
            else:
                st.dataframe(
                    filtered_stock.drop(columns=["status_color"], errors="ignore"),
                    hide_index=True,
                    width="stretch",
                    column_config={
                        "Harga jual (Rp)": st.column_config.NumberColumn(
                            "Harga jual (Rp)", format="localized"
                        ),
                        "Harga modal (Rp)": st.column_config.NumberColumn(
                            "Harga modal (Rp)", format="localized"
                        ),
                        "Stok (liter)": st.column_config.NumberColumn(
                            "Stok (liter)", format="%d"
                        ),
                    },
                )
            st.caption("Status stok otomatis dihitung berdasarkan ambang: Tersedia > 100 liter, Menipis <= 100 liter, Habis <= 0 liter.")
        elif active_page == "Pengisian Ulang Stok":
            st.subheader("Formulir Pembelian Pasokan BBM")
            st.caption("Formulir pembelian stok baru tanpa input harga per liter, karena harga modal sudah mengikuti aturan bisnis produk.")

            produk_restock = st.selectbox(
                "Jenis BBM yang dibeli",
                options=df_products["name"].tolist(),
                key="restock_product",
            )
            produk_terpilih = df_products[df_products["name"] == produk_restock].iloc[0]
            saldo_sekarang = int(produk_terpilih["stock"])
            harga_per_liter = (
                int(produk_terpilih["cost_price"])
                if not pd.isna(produk_terpilih["cost_price"])
                else max(int(produk_terpilih["catalog_price"]) - 4000, 0)
            )

            if st.session_state.pop("reset_restock_jumlah_pasokan", False):
                st.session_state["restock_jumlah_pasokan"] = 0
            jumlah_pasokan = st.number_input(
                "Jumlah pasokan masuk (liter)",
                min_value=0,
                value=0,
                step=100,
                key="restock_jumlah_pasokan",
            )
            total_harga = harga_per_liter * jumlah_pasokan

            st.write(f"Harga per liter: {format_rupiah(harga_per_liter)}")
            st.write(f"Saldo stok yang dimiliki: {saldo_sekarang:,} liter")
            st.metric("Total harga", format_rupiah(total_harga))

            if st.button(
                "Beli",
                type="primary",
                use_container_width=True,
                disabled=jumlah_pasokan == 0,
            ):
                if jumlah_pasokan <= 0:
                    st.error("Jumlah pasokan harus lebih dari 0 liter.")
                    st.stop()
                if harga_per_liter <= 0:
                    st.error("Harga modal produk belum diatur dengan benar. Silakan atur harga modal terlebih dahulu.")
                else:
                    pembelian_waktu = datetime.now()
                    with closing(get_connection()) as connection:
                        connection.execute(
                            """
                            UPDATE products
                            SET stock = stock + ?, cost_price = ?
                            WHERE name = ?
                            """,
                            (jumlah_pasokan, harga_per_liter, produk_restock),
                        )
                        connection.execute(
                            """
                            INSERT INTO stock_purchases
                                (product_name, price_per_liter, quantity_liter, total_price, purchased_at)
                            VALUES (?, ?, ?, ?, ?)
                            """,
                            (
                                produk_restock,
                                harga_per_liter,
                                jumlah_pasokan,
                                total_harga,
                                pembelian_waktu.isoformat(timespec="seconds"),
                            ),
                        )
                        connection.commit()
                    st.session_state["struk_terakhir"] = {
                        "jenis_bbm": produk_restock,
                        "harga_per_liter": harga_per_liter,
                        "jumlah_liter": jumlah_pasokan,
                        "total_harga": total_harga,
                        "datetime": pembelian_waktu,
                    }
                    st.session_state["show_struk"] = True
                    st.session_state["reset_restock_jumlah_pasokan"] = True
                    st.success(
                        f"Pembelian {produk_restock} berhasil ditambahkan sebanyak "
                        f"{jumlah_pasokan:,} liter."
                    )
                    st.rerun()

            if st.session_state.get("show_struk") and "struk_terakhir" in st.session_state:
                struk = st.session_state["struk_terakhir"]
            else:
                riwayat_terbaru = get_stock_purchase_history(1)
                if not riwayat_terbaru.empty:
                    latest = riwayat_terbaru.iloc[0]
                    struk = {
                        "jenis_bbm": latest["jenis_bbm"],
                        "harga_per_liter": int(latest["harga_per_liter"]),
                        "jumlah_liter": int(latest["jumlah_liter"]),
                        "total_harga": int(latest["total_harga"]),
                        "datetime": datetime.fromisoformat(str(latest["tanggal_pembelian"])),
                    }
                    st.session_state["struk_terakhir"] = struk
                    st.session_state["show_struk"] = True
                else:
                    struk = None

            if struk is not None:
                st.divider()
                st.subheader("Struk Pembelian")
                st.markdown(
                    f"""
                    <div style="
                        background:#ffffff; border:1px solid #e5ebf1; border-radius:12px;
                        padding:1.2rem; max-width: 480px;">
                        <h4 style="margin:0 0 0.8rem; color:#14283f;">NUSA ENERGY</h4>
                        <div style="margin-bottom:0.6rem;"><strong>Jenis BBM:</strong> {escape(struk['jenis_bbm'])}</div>
                        <div style="margin-bottom:0.6rem;"><strong>Harga per liter:</strong> {format_rupiah(struk['harga_per_liter'])}</div>
                        <div style="margin-bottom:0.6rem;"><strong>Jumlah liter:</strong> {struk['jumlah_liter']:,} liter</div>
                        <div style="margin-bottom:0.6rem;"><strong>Subtotal:</strong> {format_rupiah(struk['jumlah_liter'] * struk['harga_per_liter'])}</div>
                        <div style="margin-bottom:0.6rem;"><strong>Total harga:</strong> {format_rupiah(struk['total_harga'])}</div>
                        <div style="margin-top:1rem; color:#64748b; font-size:0.9rem;">
                            <strong>Datetime pembelian:</strong> {struk['datetime'].strftime('%d/%m/%Y %H:%M:%S')}
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

                st.divider()
                st.subheader("Riwayat Pembelian")

                with st.container():
                    reset_confirm = st.checkbox("Saya ingin menghapus riwayat pembelian stok dan mulai dari awal.", value=False, key="reset_stock_history_confirm")
                    if reset_confirm:
                        if st.button("Reset riwayat pembelian stok", type="secondary", use_container_width=True):
                            reset_stock_purchase_history()
                            st.session_state.pop("show_struk", None)
                            st.session_state.pop("struk_terakhir", None)
                            st.success("Riwayat pembelian stok berhasil dihapus. Stok produk direset ke awal.")
                            st.rerun()

                history_df = get_stock_purchase_history(limit=None).copy()
                if not history_df.empty:
                    history_df["status_pengiriman"] = history_df["tanggal_pembelian"].apply(
                        get_purchase_status
                    )
                    history_df["harga_per_liter"] = history_df["harga_per_liter"].astype(int)
                    history_df["jumlah_liter"] = history_df["jumlah_liter"].astype(int)
                    history_df["total_harga"] = history_df["total_harga"].astype(int)

                    product_options = ["Semua"] + sorted(history_df["jenis_bbm"].unique().tolist())
                    selected_product = st.selectbox(
                        "Filter produk",
                        options=product_options,
                        index=0,
                        key="purchase_history_product_filter",
                    )
                    month_options = ["Semua"] + sorted(
                        history_df["tanggal_pembelian"].map(
                            lambda val: datetime.fromisoformat(str(val)).strftime("%Y-%m")
                        ).unique().tolist()
                    )
                    selected_month = st.selectbox(
                        "Filter bulan",
                        options=month_options,
                        index=0,
                        key="purchase_history_month_filter",
                    )

                    if selected_product != "Semua":
                        history_df = history_df[history_df["jenis_bbm"] == selected_product]
                    if selected_month != "Semua":
                        history_df = history_df[
                            history_df["tanggal_pembelian"].map(
                                lambda val: datetime.fromisoformat(str(val)).strftime("%Y-%m")
                            )
                            == selected_month
                        ]

                    if not history_df.empty:
                        total_pembelian = int(history_df["total_harga"].sum())
                        total_liter = int(history_df["jumlah_liter"].sum())
                        summary_col1, summary_col2, summary_col3 = st.columns(3)
                        summary_col1.metric("Total pembelian", format_rupiah(total_pembelian))
                        summary_col2.metric("Total liter masuk", f"{total_liter:,} liter")
                        summary_col3.metric(
                            "Status terkini",
                            get_purchase_status(history_df["tanggal_pembelian"].iloc[0]),
                        )

                        display_df = history_df.rename(
                            columns={
                                "jenis_bbm": "Jenis BBM",
                                "harga_per_liter": "Harga/Liter",
                                "jumlah_liter": "Jumlah Liter",
                                "total_harga": "Total Harga",
                                "tanggal_pembelian": "Tanggal Pembelian",
                                "status_pengiriman": "Status Pengiriman",
                            }
                        )
                        st.dataframe(
                            display_df[
                                [
                                    "Jenis BBM",
                                    "Harga/Liter",
                                    "Jumlah Liter",
                                    "Total Harga",
                                    "Tanggal Pembelian",
                                    "Status Pengiriman",
                                ]
                            ],
                            hide_index=True,
                            width="stretch",
                        )
                        st.download_button(
                            "Unduh riwayat pembelian",
                            data=to_csv_bytes(display_df),
                            file_name="riwayat-pembelian-stok.csv",
                            mime="text/csv",
                            key="download_riwayat_pembelian_stok",
                        )
                    else:
                        st.info("Tidak ada riwayat yang sesuai dengan filter yang dipilih.")
                else:
                    st.info("Belum ada riwayat pembelian stok.")
        elif active_page == "Transaksi Penjualan":
            st.subheader("Formulir Transaksi Penjualan")
            pilihan_produk = st.selectbox(
                "Pilih Produk",
                options=df_products["name"].tolist(),
                key="transaksi_page_produk",
            )
            produk_info = df_products[df_products["name"] == pilihan_produk].iloc[0]
            stok_sekarang = int(produk_info["stock"])
            harga_transaksi = int(produk_info["catalog_price"])
            is_subsidized = produk_info["category"] == "Bahan Bakar Subsidi"

            col_form_1, col_form_2 = st.columns(2)
            with col_form_1:
                st.write(f"Tanggal transaksi: {tanggal_transaksi:%d/%m/%Y}")
                st.write(f"Harga satuan: {format_rupiah(harga_transaksi)}")
                st.write(f"Stok tersedia: {stok_sekarang:,} liter")
                if pd.isna(produk_info["cost_price"]):
                    st.warning("Harga modal produk belum diatur.")
                else:
                    st.write(f"Harga modal: {format_rupiah(int(produk_info['cost_price']))}")

            with col_form_2:
                quantity_key = "transaksi_page_jumlah"
                if st.session_state.pop(f"reset_{quantity_key}", False):
                    st.session_state[quantity_key] = 0
                jumlah_beli = st.number_input(
                    "Jumlah Beli (Liter)",
                    min_value=0,
                    value=0,
                    step=1,
                    key=quantity_key,
                )
                total_harga = harga_transaksi * jumlah_beli
                sisa_stok_setelah = stok_sekarang - jumlah_beli
                st.metric("Total harga", format_rupiah(total_harga))
                st.write(f"Sisa stok setelah transaksi: {max(sisa_stok_setelah, 0):,} liter")

                if is_subsidized:
                    plat_nomor = st.text_input(
                        "4 angka terakhir plat nomor",
                        max_chars=4,
                        key="transaksi_page_plat",
                    )
                else:
                    plat_nomor = ""

            if st.button(
                "Proses Transaksi",
                type="primary",
                use_container_width=True,
                disabled=jumlah_beli == 0,
            ):
                if jumlah_beli <= 0:
                    st.error("Jumlah beli harus lebih dari 0 liter.")
                    st.stop()
                if jumlah_beli > stok_sekarang:
                    st.error(
                        f"Jumlah beli melebihi stok yang tersedia ({stok_sekarang} liter)."
                    )
                    st.stop()
                if is_subsidized and not plate_matches_date(
                    plat_nomor.strip(), tanggal_transaksi
                ):
                    if len(plat_nomor.strip()) != 4 or not plat_nomor.strip().isdecimal():
                        st.error("Masukkan tepat 4 angka terakhir plat nomor.")
                    else:
                        aturan_hari = (
                            "genap" if tanggal_transaksi.day % 2 == 0 else "ganjil"
                        )
                        st.error(
                            f"Transaksi BBM bersubsidi tidak dapat dilakukan pada tanggal "
                            f"{tanggal_transaksi:%d/%m/%Y}; aturan tanggal {aturan_hari}."
                        )
                    st.stop()

                with closing(get_connection()) as connection:
                    cursor = connection.execute(
                        """
                        UPDATE products
                        SET stock = stock - ?
                        WHERE name = ? AND stock >= ?
                        """,
                        (jumlah_beli, pilihan_produk, jumlah_beli),
                    )
                    if cursor.rowcount:
                        product_id = connection.execute(
                            "SELECT id FROM products WHERE name = ?",
                            (pilihan_produk,),
                        ).fetchone()[0]
                        connection.execute(
                            """
                            INSERT INTO sales
                                (sale_date, product_id, unit_price, unit_cost, quantity, total)
                            VALUES (?, ?, ?, ?, ?, ?)
                            """,
                            (
                                tanggal_transaksi.isoformat(),
                                product_id,
                                harga_transaksi,
                                (
                                    int(produk_info["cost_price"])
                                    if not pd.isna(produk_info["cost_price"])
                                    else None
                                ),
                                jumlah_beli,
                                jumlah_beli * harga_transaksi,
                            ),
                        )
                        connection.commit()
                        st.session_state[f"reset_{quantity_key}"] = True
                        st.success("Transaksi berhasil diproses.")
                        st.rerun()
                    else:
                        st.error("Stok tidak mencukupi untuk transaksi ini.")
                        st.stop()

            st.divider()
            st.subheader("Riwayat transaksi terakhir")
            if st.button("Reset riwayat penjualan", key="reset_riwayat_penjualan", type="secondary"):
                st.session_state["confirm_reset_penjualan"] = True

            if st.session_state.get("confirm_reset_penjualan"):
                st.warning("Yakin ingin menghapus semua riwayat penjualan? Stok produk akan kembali ke kondisi awal.")
                col_reset_yes, col_reset_no = st.columns(2)
                with col_reset_yes:
                    if st.button("Ya, reset", key="confirm_reset_penjualan_yes", type="primary"):
                        with closing(get_connection()) as connection:
                            connection.execute("DELETE FROM sales")
                            connection.execute("UPDATE products SET stock = 50")
                            connection.commit()
                        st.session_state.pop("confirm_reset_penjualan", None)
                        st.success("Riwayat penjualan berhasil dihapus.")
                        st.rerun()
                with col_reset_no:
                    if st.button("Batal", key="confirm_reset_penjualan_no", type="secondary"):
                        st.session_state.pop("confirm_reset_penjualan", None)
                        st.rerun()

            recent_transactions = run_query(
                """
                SELECT
                    sales.sale_date AS tanggal,
                    products.name AS produk,
                    sales.quantity AS jumlah_liter,
                    sales.total AS total
                FROM sales
                JOIN products ON products.id = sales.product_id
                ORDER BY sales.id DESC
                LIMIT 10
                """
            )
            if recent_transactions.empty:
                st.info("Belum ada transaksi penjualan yang tercatat.")
            else:
                st.dataframe(
                    recent_transactions.rename(
                        columns={
                            "tanggal": "Tanggal",
                            "produk": "Produk",
                            "jumlah_liter": "Jumlah Liter",
                            "total": "Total",
                        }
                    ),
                    hide_index=True,
                    width="stretch",
                    column_config={
                        "Total": st.column_config.NumberColumn("Total", format="localized"),
                        "Jumlah Liter": st.column_config.NumberColumn("Jumlah Liter", format="%d"),
                    },
                )
        elif active_page == "Laporan Penjualan dan Keuntungan":
            st.subheader("Laporan Penjualan dan Keuntungan")
            st.caption("Pantau omzet, transaksi, dan estimasi keuntungan berdasarkan periode yang dipilih.")
            period = st.date_input(
                "Periode",
                value=(first_date, last_date),
                format="DD/MM/YYYY",
            )
            selected_categories = st.multiselect(
                "Kategori", options=categories, default=categories
            )
            min_revenue = st.slider(
                "Omzet minimum per produk (Rp)",
                min_value=0,
                max_value=500000,
                value=0,
                step=25000,
            )

            if not isinstance(period, tuple) or len(period) != 2 or None in period:
                st.info("Pilih tanggal awal dan tanggal akhir periode di sidebar.")
                st.stop()
            if not selected_categories:
                st.warning("Pilih minimal satu kategori di sidebar.")
                st.stop()

            start_date, end_date = period
            where_sql, params = build_filter(start_date, end_date, selected_categories)
            summary = get_summary(where_sql, params)

            st.subheader(f"Ringkasan {start_date:%d/%m/%Y} – {end_date:%d/%m/%Y}")
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Omzet", format_rupiah(summary["omzet"]))
            col2.metric("Jumlah transaksi", int(summary["jumlah_transaksi"]))
            col3.metric("Rata-rata per transaksi", format_rupiah(summary["rata_rata"]))
            col4.metric("Transaksi terbesar", format_rupiah(summary["transaksi_terbesar"]))

            if summary["jumlah_transaksi"] == 0:
                st.info("Tidak ada transaksi pada periode dan kategori ini.")
                st.stop()

            by_product = get_report_by_product(where_sql, params, min_revenue)
            by_category = get_report_by_category(where_sql, params)
            by_month = get_report_by_month(where_sql, params)
            detail = get_sales_detail(where_sql, params)
            tab_product, tab_category, tab_month_tab, tab_detail = st.tabs(
                ["Per Produk", "Per Kategori", "Per Bulan", "Detail Transaksi"]
            )

            with tab_product:
                st.caption(f"Produk dengan omzet minimal {format_rupiah(min_revenue)}.")
                if show_report(by_product, "laporan-produk", start_date, end_date):
                    st.bar_chart(
                        by_product,
                        x="produk",
                        y="omzet",
                        x_label="Produk",
                        y_label="Omzet (Rp)",
                        sort="-omzet",
                        horizontal=True,
                    )

            with tab_category:
                if show_report(by_category, "laporan-kategori", start_date, end_date):
                    st.bar_chart(
                        by_category,
                        x="kategori",
                        y="omzet",
                        x_label="Kategori",
                        y_label="Omzet (Rp)",
                        sort="-omzet",
                        horizontal=True,
                    )

            with tab_month_tab:
                if show_report(by_month, "laporan-bulanan", start_date, end_date):
                    st.line_chart(
                        by_month, x="bulan", y="omzet", x_label="Bulan", y_label="Omzet (Rp)"
                    )

            with tab_detail:
                show_report(detail, "detail-transaksi", start_date, end_date)

            with st.expander("Cek kecocokan angka"):
                checks = {
                    "Kartu Omzet": summary["omzet"],
                    "Total tab Per Kategori": by_category["omzet"].sum(),
                    "Total tab Per Bulan": by_month["omzet"].sum(),
                    "Total tab Detail": detail["total"].sum(),
                }
                for label, value in checks.items():
                    st.write(f"{label}: {format_rupiah(value)}")
                if len(set(checks.values())) == 1:
                    st.success("Semua total cocok. Laporan dapat ditelusuri ke data detail.")
                else:
                    st.error("Ada total yang berbeda. Periksa query laporan.")

        return

    st.markdown(
        f"""
        <div style="
            display:flex; justify-content:space-between; align-items:flex-end;
            gap:1rem; margin-bottom:1.2rem;">
            <div>
                <p class="dashboard-eyebrow">Ringkasan operasional</p>
                <h1 class="dashboard-heading">Dashboard Penjualan BBM</h1>
                <p class="dashboard-subheading">
                    Pantau penjualan, persediaan, dan kondisi operasional.
                </p>
            </div>
            <div style="
                color:#64748b; background:#fff; border:1px solid #e5ebf1;
                border-radius:10px; padding:0.65rem 0.9rem; white-space:nowrap;">
                📅 &nbsp; {date.today():%d %B %Y}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    dashboard_where = "WHERE 1 = 1"
    sales_chart = get_report_by_month(dashboard_where, [])
    dashboard_col1, dashboard_col2, dashboard_col3, dashboard_col4 = st.columns(4)
    stok_bbm = df_products[df_products["category"] != "Add on"]
    total_stok = int(stok_bbm["stock"].sum())

    current_month = date.today().strftime("%Y-%m")
    month_where = "WHERE strftime('%Y-%m', sales.sale_date) = ?"
    month_summary = get_summary(month_where, [current_month])
    month_profit = get_dashboard_profit(month_where, [current_month])
    omzet_bulan_ini = int(month_summary["omzet"] or 0)

    today_str = date.today().isoformat()
    today_summary = run_query(
        """
        SELECT
            COALESCE(SUM(sales.total), 0) AS omzet_hari_ini,
            COALESCE(SUM(sales.quantity), 0) AS liter_hari_ini,
            COUNT(*) AS transaksi_hari_ini
        FROM sales
        WHERE sales.sale_date = ?
        """,
        (today_str,),
    )
    omzet_hari_ini = int(today_summary.iloc[0]["omzet_hari_ini"] or 0)

    dashboard_col1.metric("Total stok tersedia", f"{total_stok:,} liter")
    dashboard_col2.metric(
        "Total transaksi penjualan bulan ini",
        int(month_summary["jumlah_transaksi"]),
    )
    dashboard_col3.metric(
        "Total pendapatan bulan ini",
        format_rupiah(month_summary["omzet"]),
    )
    if int(month_profit["transaksi_tanpa_modal"] or 0) == 0:
        dashboard_col4.metric(
            "Estimasi keuntungan bulan ini",
            format_rupiah(month_profit["estimasi_keuntungan"]),
        )
    else:
        dashboard_col4.metric("Estimasi keuntungan bulan ini", "Belum lengkap")
        st.info(
            f"{int(month_profit['transaksi_tanpa_modal'])} transaksi "
            "belum memiliki data modal, sehingga estimasi keuntungan bulan ini belum lengkap. "
            "Atur harga modal produk di sidebar."
        )

    st.subheader("Kinerja hari ini")
    kpi_col1, kpi_col2 = st.columns(2)
    kpi_col1.metric(
        "Penjualan hari ini",
        f"{int(today_summary.iloc[0]['liter_hari_ini'] or 0):,} liter",
    )
    kpi_col2.metric("Omzet hari ini", format_rupiah(omzet_hari_ini))

    stok_menipis = stok_bbm[stok_bbm["stock"] <= 100].sort_values("stock")
    if not stok_menipis.empty:
        st.warning(
            "Stok menipis: "
            + ", ".join(
                f"{produk['name']} ({int(produk['stock'])} liter)"
                for _, produk in stok_menipis.iterrows()
            )
            + ". Segera lakukan pengisian ulang stok."
        )
        if st.button("Lanjut ke Pengisian Ulang Stok", type="primary"):
            st.session_state["pending_page"] = "Pengisian Ulang Stok"
            st.query_params["page"] = "Pengisian Ulang Stok"
            st.rerun()
    chart_column, status_column = st.columns([1.65, 1])
    with chart_column:
        with st.container(border=True):
            st.subheader("Ringkasan Penjualan Bulanan")
            st.caption("Omzet berdasarkan seluruh transaksi yang tersimpan.")
            if sales_chart.empty:
                st.info("Belum ada data penjualan untuk ditampilkan pada grafik.")
            else:
                st.bar_chart(
                    sales_chart,
                    x="bulan",
                    y="omzet",
                    x_label="Bulan",
                    y_label="Omzet (Rp)",
                    color="#16816f",
                )

    with status_column:
        with st.container(border=True):
            st.subheader("Status Persediaan BBM")
            st.caption("Status dihitung dari stok produk saat ini.")
            if stok_bbm.empty:
                st.info("Belum ada data produk BBM.")
            else:
                stock_columns = st.columns(2)
                for index, (_, produk) in enumerate(stok_bbm.iterrows()):
                    stok_produk = int(produk["stock"])
                    nama_produk = escape(str(produk["name"]))
                    status = "Menipis" if stok_produk <= 100 else "Tersedia"
                    status_color = "#c2413b" if stok_produk <= 100 else "#16816f"
                    with stock_columns[index % 2]:
                        st.markdown(
                            f"""
                            <div class="stock-card">
                                <div class="stock-card-title">
                                    {nama_produk}
                                </div>
                                <div class="stock-card-meta">
                                    {stok_produk:,} liter ·
                                    <span style="color:{status_color};font-weight:700;">
                                        {status}
                                    </span>
                                </div>
                            </div>
                            """,
                            unsafe_allow_html=True,
                        )

    product_top = run_query(
        """
        SELECT
            products.name AS produk,
            SUM(sales.quantity) AS total_liter,
            SUM(sales.total) AS omzet
        FROM sales
        JOIN products ON products.id = sales.product_id
        GROUP BY products.id, products.name
        ORDER BY total_liter DESC, omzet DESC
        LIMIT 5
        """
    )
    recent_transactions = run_query(
        """
        SELECT
            sales.sale_date AS tanggal,
            products.name AS produk,
            sales.quantity AS liter,
            sales.total AS total
        FROM sales
        JOIN products ON products.id = sales.product_id
        ORDER BY sales.id DESC
        LIMIT 5
        """
    )

    st.subheader("Produk paling laku & transaksi terbaru")
    product_col, recent_col = st.columns([1.2, 1])
    with product_col:
        with st.container(border=True):
            st.markdown("#### Produk paling laku")
            if product_top.empty:
                st.info("Belum ada data produk yang terjual.")
            else:
                st.dataframe(
                    product_top.rename(
                        columns={
                            "produk": "Produk",
                            "total_liter": "Liter terjual",
                            "omzet": "Omzet",
                        }
                    ),
                    hide_index=True,
                    width="stretch",
                    column_config={
                        "Omzet": st.column_config.NumberColumn("Omzet", format="localized"),
                        "Liter terjual": st.column_config.NumberColumn("Liter terjual", format="%d"),
                    },
                )
    with recent_col:
        with st.container(border=True):
            st.markdown("#### Transaksi terakhir")
            if recent_transactions.empty:
                st.info("Belum ada transaksi terbaru.")
            else:
                st.dataframe(
                    recent_transactions.rename(
                        columns={
                            "tanggal": "Tanggal",
                            "produk": "Produk",
                            "liter": "Liter",
                            "total": "Total",
                        }
                    ),
                    hide_index=True,
                    width="stretch",
                    column_config={
                        "Total": st.column_config.NumberColumn("Total", format="localized"),
                        "Liter": st.column_config.NumberColumn("Liter", format="%d"),
                    },
                )

    st.subheader("Persediaan & Komposisi Penjualan")
    inventory_column, mix_column = st.columns([1.55, 1])
    with inventory_column:
        with st.container(border=True):
            st.markdown("#### Persediaan Produk")
            inventory = df_products.copy()
            inventory["status"] = inventory["stock"].apply(
                lambda stock: "Menipis" if stock <= 100 else "Tersedia"
            )
            inventory = inventory.rename(
                columns={
                    "name": "Produk",
                    "category": "Kategori",
                    "catalog_price": "Harga jual (Rp)",
                    "stock": "Stok (liter)",
                    "cost_price": "Harga modal (Rp)",
                    "status": "Status",
                }
            )
            st.dataframe(
                inventory,
                hide_index=True,
                width="stretch",
                column_config={
                    "Harga jual (Rp)": st.column_config.NumberColumn(
                        "Harga jual (Rp)", format="localized"
                    ),
                    "Harga modal (Rp)": st.column_config.NumberColumn(
                        "Harga modal (Rp)", format="localized"
                    ),
                    "Stok (liter)": st.column_config.NumberColumn(
                        "Stok (liter)", format="%d"
                    ),
                },
            )

    with mix_column:
        with st.container(border=True):
            st.markdown("#### Penjualan per Kategori")
            sales_mix = run_query(
                f"""
                SELECT
                    products.category AS kategori,
                    COALESCE(SUM(sales.quantity), 0) AS unit_terjual
                {JOIN_SQL}
                GROUP BY products.category
                ORDER BY unit_terjual DESC
                """
            )
            if sales_mix.empty or sales_mix["unit_terjual"].sum() == 0:
                st.info("Belum ada penjualan untuk ditampilkan.")
            else:
                st.vega_lite_chart(
                    sales_mix,
                    {
                        "mark": {
                            "type": "arc",
                            "innerRadius": 55,
                            "outerRadius": 95,
                        },
                        "encoding": {
                            "theta": {
                                "field": "unit_terjual",
                                "type": "quantitative",
                            },
                            "color": {
                                "field": "kategori",
                                "type": "nominal",
                                "scale": {
                                    "range": ["#16816f", "#f4a340", "#264766"]
                                },
                            },
                            "tooltip": [
                                {"field": "kategori", "type": "nominal"},
                                {"field": "unit_terjual", "type": "quantitative"},
                            ],
                        },
                    },
                    width="stretch",
                )
            st.markdown("#### Aksi Cepat")
            action_download, action_refresh = st.columns(2)
            action_download.download_button(
                "Unduh stok",
                data=to_csv_bytes(inventory),
                file_name="persediaan-produk.csv",
                mime="text/csv",
                width="stretch",
                key="download_persediaan_dashboard",
            )
            if action_refresh.button(
                "Muat ulang", width="stretch", key="refresh_dashboard"
            ):
                st.rerun()

    if not stok_menipis.empty:
        st.warning(
            "Stok menipis: "
            + ", ".join(
                f"{produk['name']} ({int(produk['stock'])} liter)"
                for _, produk in stok_menipis.iterrows()
            )
        )

    st.caption(
        "Estimasi keuntungan adalah laba kotor dari harga jual dikurangi harga modal; "
        "transaksi tanpa data modal belum dapat dihitung."
    )

    if not isinstance(period, tuple) or len(period) != 2 or None in period:
        st.info("Pilih tanggal awal dan tanggal akhir periode di sidebar.")
        st.stop()
    if not selected_categories:
        st.warning("Pilih minimal satu kategori di sidebar.")
        st.stop()

    start_date, end_date = period
    where_sql, params = build_filter(start_date, end_date, selected_categories)
    summary = get_summary(where_sql, params)

    st.subheader(f"Ringkasan {start_date:%d/%m/%Y} – {end_date:%d/%m/%Y}")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Omzet", format_rupiah(summary["omzet"]))
    col2.metric("Jumlah transaksi", int(summary["jumlah_transaksi"]))
    col3.metric("Rata-rata per transaksi", format_rupiah(summary["rata_rata"]))
    col4.metric("Transaksi terbesar", format_rupiah(summary["transaksi_terbesar"]))

    if summary["jumlah_transaksi"] == 0:
        st.info("Tidak ada transaksi pada periode dan kategori ini.")
        st.stop()

    by_product = get_report_by_product(where_sql, params, min_revenue)
    by_category = get_report_by_category(where_sql, params)
    by_month = get_report_by_month(where_sql, params)
    detail = get_sales_detail(where_sql, params)

    tab_product, tab_category, tab_month, tab_detail = st.tabs(
        ["Per Produk", "Per Kategori", "Per Bulan", "Detail Transaksi"]
    )

    with tab_product:
        st.caption(f"Produk dengan omzet minimal {format_rupiah(min_revenue)}.")
        if show_report(by_product, "laporan-produk", start_date, end_date):
            st.bar_chart(
                by_product,
                x="produk",
                y="omzet",
                x_label="Produk",
                y_label="Omzet (Rp)",
                sort="-omzet",
                horizontal=True,
            )

    with tab_category:
        if show_report(by_category, "laporan-kategori", start_date, end_date):
            st.bar_chart(
                by_category,
                x="kategori",
                y="omzet",
                x_label="Kategori",
                y_label="Omzet (Rp)",
                sort="-omzet",
                horizontal=True,
            )

    with tab_month:
        if show_report(by_month, "laporan-bulanan", start_date, end_date):
            st.line_chart(
                by_month, x="bulan", y="omzet", x_label="Bulan", y_label="Omzet (Rp)"
            )

    with tab_detail:
        show_report(detail, "detail-transaksi", start_date, end_date)

    with st.expander("Cek kecocokan angka"):
        checks = {
            "Kartu Omzet": summary["omzet"],
            "Total tab Per Kategori": by_category["omzet"].sum(),
            "Total tab Per Bulan": by_month["omzet"].sum(),
            "Total tab Detail": detail["total"].sum(),
        }
        for label, value in checks.items():
            st.write(f"{label}: {format_rupiah(value)}")
        if len(set(checks.values())) == 1:
            st.success("Semua total cocok. Laporan dapat ditelusuri ke data detail.")
        else:
            st.error("Ada total yang berbeda. Periksa query laporan.")
        st.caption(
            "Total tab Per Produk bisa lebih kecil jika omzet minimum di atas 0, "
            f"karena HAVING menyaring produk. Saat ini: "
            f"{format_rupiah(by_product['omzet'].sum())}."
        )


if __name__ == "__main__":
    main()

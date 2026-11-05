# Pengelolaan BBM

Aplikasi manajemen stok dan penjualan BBM berbasis Streamlit. Aplikasi ini membantu pengguna untuk:

- memantau stok BBM
- mencatat transaksi penjualan
- mengelola pembelian stok baru
- melihat laporan penjualan dan keuntungan
- memantau produk yang stoknya menipis

## Fitur utama

- Dashboard operasional
- Data stok BBM
- Transaksi penjualan
- Pengisian ulang stok
- Laporan penjualan dan keuntungan
- Filter produk dan kategori
- Riwayat pembelian stok

## Teknologi

- Python
- Streamlit
- Pandas
- SQLite

## Cara menjalankan

1. Pastikan Python sudah terinstall.
2. Buat virtual environment (opsional tetapi disarankan).
3. Install dependency:

   ```bash
   pip install -r requirements.txt
   ```

4. Jalankan aplikasi:

   ```bash
   streamlit run app.py
   ```

## Struktur utama

- `app.py` = aplikasi utama
- `penjualan_bbm.db` = database SQLite
- `requirements.txt` = dependency aplikasi

## Catatan

Aplikasi ini dibuat untuk kebutuhan manajemen operasional SPBU dengan data stok dan penjualan yang sederhana dan mudah dipantau.

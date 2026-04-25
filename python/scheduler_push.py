"""
scheduler_push.py
Jalankan push_to_dashboard.py otomatis setiap hari kerja.
Jadwal: coba jam 17:00 → kalau data belum ada, retry jam 18:00 → 19:00.

Usage:
    uv run scheduler_push.py          # jalan terus (loop harian)
"""
import time, subprocess, sys, os
from datetime import datetime, timedelta

RETRY_HOURS = [17, 18, 19]   # jam percobaan (WIB = UTC+7, sesuaikan jika server UTC)
CHECK_DAYS  = [0, 1, 2, 3, 4]  # Senin–Jumat


def is_weekday() -> bool:
    return datetime.now().weekday() in CHECK_DAYS


def run_push(date: str) -> bool:
    """Jalankan push_to_dashboard.py, return True kalau data berhasil dipush."""
    script = os.path.join(os.path.dirname(__file__), "push_to_dashboard.py")
    result = subprocess.run(
        ["uv", "run", script, date],
        capture_output=False,
        text=True,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    return result.returncode == 0


def seconds_until(hour: int) -> float:
    now  = datetime.now()
    target = now.replace(hour=hour, minute=0, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds()


def main():
    print(f"Scheduler aktif. Akan push setiap hari kerja jam {RETRY_HOURS} WIB.")
    print("Tekan Ctrl+C untuk berhenti.\n")

    pushed_today = None  # tanggal yang sudah berhasil dipush

    while True:
        now  = datetime.now()
        today = now.strftime("%Y-%m-%d")
        hour  = now.hour

        # Reset pushed_today kalau sudah hari baru
        if pushed_today != today:
            pushed_today = None

        if is_weekday() and pushed_today != today and hour in RETRY_HOURS:
            print(f"\n[{now.strftime('%H:%M:%S')}] Mencoba push data {today}...")
            ok = run_push(today)
            if ok:
                pushed_today = today
                print(f"[{now.strftime('%H:%M:%S')}] Berhasil push {today}. Menunggu hari berikutnya.")
            else:
                # Tentukan jam retry berikutnya
                next_retries = [h for h in RETRY_HOURS if h > hour]
                if next_retries:
                    print(f"[{now.strftime('%H:%M:%S')}] Gagal/data belum ada. Retry jam {next_retries[0]:02d}:00.")
                else:
                    print(f"[{now.strftime('%H:%M:%S')}] Semua retry habis untuk hari ini.")

            # Tidur 61 menit supaya tidak trigger ulang di jam yang sama
            time.sleep(61 * 60)
        else:
            # Cari jam push berikutnya
            future = [h for h in RETRY_HOURS if h > hour] if is_weekday() and pushed_today != today else []
            if future:
                wait = seconds_until(future[0])
                next_str = datetime.now().replace(hour=future[0], minute=0, second=0).strftime("%H:%M")
                print(f"[{now.strftime('%H:%M:%S')}] Menunggu hingga {next_str} ({wait/3600:.1f} jam lagi)...")
            else:
                # Tunggu sampai jam 17:00 hari kerja berikutnya
                wait = seconds_until(RETRY_HOURS[0])
                print(f"[{now.strftime('%H:%M:%S')}] Menunggu run berikutnya ({wait/3600:.1f} jam lagi)...")

            # Tidur 5 menit lalu cek lagi
            time.sleep(5 * 60)


if __name__ == "__main__":
    main()

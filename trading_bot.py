from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, ConversationHandler, filters, JobQueue
import json, os, requests
from datetime import datetime

JOURNAL_FILE = "jurnal.json"
CHAT_ID = 5056350311  # Chat ID penerima auto sinyal

# Simpan harga sebelumnya untuk deteksi pergerakan signifikan
harga_sebelumnya = {"eurusd": None, "gbpusd": None, "usdjpy": None, "xauusd": None}

def baca_jurnal():
    if os.path.exists(JOURNAL_FILE):
        with open(JOURNAL_FILE, "r") as f:
            return json.load(f)
    return []

def simpan_jurnal(data):
    with open(JOURNAL_FILE, "w") as f:
        json.dump(data, f)

def ambil_harga():
    try:
        url = "https://api.frankfurter.app/latest?base=USD"
        r = requests.get(url, timeout=5)
        rates = r.json()["rates"]
        eurusd = round(1 / rates["EUR"], 5)
        gbpusd = round(1 / rates["GBP"], 5)
        usdjpy = round(rates["JPY"], 3)
    except:
        eurusd = gbpusd = usdjpy = None

    try:
        url2 = "https://query1.finance.yahoo.com/v8/finance/chart/GC=F"
        headers = {"User-Agent": "Mozilla/5.0"}
        r2 = requests.get(url2, timeout=5, headers=headers)
        data2 = r2.json()
        xauusd = round(data2["chart"]["result"][0]["meta"]["regularMarketPrice"], 2)
    except:
        xauusd = None

    return eurusd, gbpusd, usdjpy, xauusd

def buat_pesan_sinyal(eurusd, gbpusd, usdjpy, xauusd, judul="📊 *HARGA LIVE*"):
    xau_teks = (
        f"🔴 *XAU/USD* : `{xauusd}`\n"
        f"   SL : `{round(xauusd+10,2)}` | TP : `{round(xauusd-15,2)}`\n\n"
    ) if xauusd else "⚠️ *XAU/USD* : Gagal ambil harga\n\n"

    return (
        f"{judul}\n"
        f"_{datetime.now().strftime('%d/%m/%Y %H:%M')}_\n\n"
        f"🔴 *EUR/USD* : `{eurusd}`\n"
        f"   SL : `{round(eurusd+0.0020,5)}` | TP : `{round(eurusd-0.0030,5)}`\n\n"
        f"🔴 *GBP/USD* : `{gbpusd}`\n"
        f"   SL : `{round(gbpusd+0.0020,5)}` | TP : `{round(gbpusd-0.0030,5)}`\n\n"
        f"🔴 *USD/JPY* : `{usdjpy}`\n"
        f"   SL : `{round(usdjpy+0.30,3)}` | TP : `{round(usdjpy-0.40,3)}`\n\n"
        + xau_teks +
        f"⚠️ _Selalu pasang SL sebelum entry!_"
    )

# ── AUTO SINYAL TERJADWAL (setiap 60 menit) ───────────────

async def auto_sinyal_terjadwal(context):
    eurusd, gbpusd, usdjpy, xauusd = ambil_harga()
    pesan = buat_pesan_sinyal(eurusd, gbpusd, usdjpy, xauusd, judul="🕐 *AUTO SINYAL TERJADWAL*")
    await context.bot.send_message(
        chat_id=CHAT_ID,
        text=pesan,
        parse_mode="Markdown")

# ── AUTO ALERT PERGERAKAN SIGNIFIKAN (cek setiap 5 menit) ─

async def auto_alert_pergerakan(context):
    global harga_sebelumnya
    eurusd, gbpusd, usdjpy, xauusd = ambil_harga()

    alerts = []

    # Threshold pergerakan signifikan
    if harga_sebelumnya["eurusd"] and eurusd:
        selisih = abs(eurusd - harga_sebelumnya["eurusd"])
        if selisih >= 0.0020:  # 20 pips
            arah = "⬆️ NAIK" if eurusd > harga_sebelumnya["eurusd"] else "⬇️ TURUN"
            alerts.append(f"🚨 *EUR/USD* {arah}\n   `{harga_sebelumnya['eurusd']}` → `{eurusd}` ({round(selisih*10000,1)} pips)")

    if harga_sebelumnya["gbpusd"] and gbpusd:
        selisih = abs(gbpusd - harga_sebelumnya["gbpusd"])
        if selisih >= 0.0020:  # 20 pips
            arah = "⬆️ NAIK" if gbpusd > harga_sebelumnya["gbpusd"] else "⬇️ TURUN"
            alerts.append(f"🚨 *GBP/USD* {arah}\n   `{harga_sebelumnya['gbpusd']}` → `{gbpusd}` ({round(selisih*10000,1)} pips)")

    if harga_sebelumnya["usdjpy"] and usdjpy:
        selisih = abs(usdjpy - harga_sebelumnya["usdjpy"])
        if selisih >= 0.20:  # 20 pips JPY
            arah = "⬆️ NAIK" if usdjpy > harga_sebelumnya["usdjpy"] else "⬇️ TURUN"
            alerts.append(f"🚨 *USD/JPY* {arah}\n   `{harga_sebelumnya['usdjpy']}` → `{usdjpy}` ({round(selisih*100,1)} pips)")

    if harga_sebelumnya["xauusd"] and xauusd:
        selisih = abs(xauusd - harga_sebelumnya["xauusd"])
        if selisih >= 5.0:  # $5 pergerakan emas
            arah = "⬆️ NAIK" if xauusd > harga_sebelumnya["xauusd"] else "⬇️ TURUN"
            alerts.append(f"🚨 *XAU/USD* {arah}\n   `{harga_sebelumnya['xauusd']}` → `{xauusd}` (${round(selisih,2)})")

    # Kirim alert kalau ada pergerakan signifikan
    if alerts:
        pesan = (
            f"⚡ *ALERT PERGERAKAN SIGNIFIKAN*\n"
            f"_{datetime.now().strftime('%d/%m/%Y %H:%M')}_\n\n"
            + "\n\n".join(alerts) +
            "\n\n⚠️ _Pantau chart sebelum entry!_"
        )
        await context.bot.send_message(
            chat_id=CHAT_ID,
            text=pesan,
            parse_mode="Markdown")

    # Update harga sebelumnya
    if eurusd: harga_sebelumnya["eurusd"] = eurusd
    if gbpusd: harga_sebelumnya["gbpusd"] = gbpusd
    if usdjpy: harga_sebelumnya["usdjpy"] = usdjpy
    if xauusd: harga_sebelumnya["xauusd"] = xauusd

# ── KEYBOARD ──────────────────────────────────────────────

MENU_KB = ReplyKeyboardMarkup([
    [KeyboardButton("📊 Sinyal"), KeyboardButton("📐 Lot Size")],
    [KeyboardButton("🗒 Catat Trade"), KeyboardButton("📋 Jurnal")],
    [KeyboardButton("📈 Statistik"), KeyboardButton("ℹ Bantuan")],
], resize_keyboard=True)

PAIR_KB = ReplyKeyboardMarkup([
    ["EUR/USD", "GBP/USD"],
    ["USD/JPY", "XAU/USD"],
    ["❌ Batal"]
], resize_keyboard=True)

ARAH_KB = ReplyKeyboardMarkup([
    ["BUY 🟢", "SELL 🔴"],
    ["❌ Batal"]
], resize_keyboard=True)

(LOT_MODAL, LOT_RISK, LOT_SL) = range(3)
(CATAT_PAIR, CATAT_ARAH, CATAT_ENTRY, CATAT_SL,
 CATAT_TP, CATAT_EXIT, CATAT_CATATAN) = range(3, 10)

# ── HANDLER ───────────────────────────────────────────────

async def start(update, context):
    await update.message.reply_text(
        "Halo! 👋 Selamat datang di *Bot Trading Forex Scalping* 🤖\n\nPilih menu di bawah:",
        parse_mode="Markdown",
        reply_markup=MENU_KB)

async def bantuan(update, context):
    await update.message.reply_text(
        "ℹ *PANDUAN BOT*\n\n"
        "📊 *Sinyal* — Harga live + level trading\n"
        "📐 *Lot Size* — Kalkulator lot\n"
        "🗒 *Catat Trade* — Simpan hasil trade\n"
        "📋 *Jurnal* — Lihat trade terakhir\n"
        "📈 *Statistik* — Win rate & total pips\n\n"
        "🕐 *Auto Sinyal* — Kirim otomatis setiap 1 jam\n"
        "⚡ *Auto Alert* — Notif kalau harga bergerak signifikan\n\n"
        "⚠️ _Bukan saran investasi._",
        parse_mode="Markdown",
        reply_markup=MENU_KB)

async def sinyal(update, context):
    await update.message.reply_text("⏳ Mengambil harga live...")
    eurusd, gbpusd, usdjpy, xauusd = ambil_harga()
    pesan = buat_pesan_sinyal(eurusd, gbpusd, usdjpy, xauusd)
    await update.message.reply_text(pesan, parse_mode="Markdown", reply_markup=MENU_KB)

# ── LOT SIZE ──────────────────────────────────────────────

async def lot_start(update, context):
    await update.message.reply_text(
        "📐 *KALKULATOR LOT SIZE*\n\nMasukkan *modal* kamu (USD):\n_Contoh: 1000_",
        parse_mode="Markdown")
    return LOT_MODAL

async def lot_modal(update, context):
    try:
        context.user_data["modal"] = float(update.message.text)
        await update.message.reply_text(
            f"✅ Modal: *${context.user_data['modal']:,.0f}*\n\nMasukkan *persentase risk*:\n_Contoh: 2_",
            parse_mode="Markdown")
        return LOT_RISK
    except:
        await update.message.reply_text("❌ Masukkan angka. Contoh: 1000")
        return LOT_MODAL

async def lot_risk(update, context):
    try:
        risk = float(update.message.text)
        if risk > 5:
            await update.message.reply_text("⚠️ Risk terlalu besar! Masukkan 1–2%:")
            return LOT_RISK
        context.user_data["risk"] = risk
        await update.message.reply_text(
            f"✅ Risk: *{risk}%*\n\nMasukkan *Stop Loss dalam pips*:\n_Contoh: 10_",
            parse_mode="Markdown")
        return LOT_SL
    except:
        await update.message.reply_text("❌ Masukkan angka. Contoh: 2")
        return LOT_RISK

async def lot_hasil(update, context):
    try:
        sl = float(update.message.text)
        modal = context.user_data["modal"]
        risk = context.user_data["risk"]
        risk_usd = modal * risk / 100
        lot = round((risk_usd / (sl * 10)) / 0.01) * 0.01
        await update.message.reply_text(
            f"📐 *HASIL KALKULASI*\n\n"
            f"Modal    : `${modal:,.0f}`\n"
            f"Risk     : `{risk}%` = `${risk_usd:.2f}`\n"
            f"SL       : `{sl} pips`\n"
            f"――――――――――――\n"
            f"Lot Size : *{lot:.2f} lot*",
            parse_mode="Markdown",
            reply_markup=MENU_KB)
        return ConversationHandler.END
    except:
        await update.message.reply_text("❌ Masukkan angka. Contoh: 10")
        return LOT_SL

# ── CATAT TRADE ───────────────────────────────────────────

async def catat_start(update, context):
    context.user_data["trade"] = {"tanggal": datetime.now().strftime("%d/%m/%Y %H:%M")}
    await update.message.reply_text(
        "🗒 *CATAT TRADE*\n\nPilih pair:",
        parse_mode="Markdown",
        reply_markup=PAIR_KB)
    return CATAT_PAIR

async def catat_pair(update, context):
    if update.message.text == "❌ Batal":
        await update.message.reply_text("❌ Dibatalkan.", reply_markup=MENU_KB)
        return ConversationHandler.END
    context.user_data["trade"]["pair"] = update.message.text
    await update.message.reply_text("Arah posisi?", reply_markup=ARAH_KB)
    return CATAT_ARAH

async def catat_arah(update, context):
    if update.message.text == "❌ Batal":
        await update.message.reply_text("❌ Dibatalkan.", reply_markup=MENU_KB)
        return ConversationHandler.END
    context.user_data["trade"]["arah"] = "BUY" if "BUY" in update.message.text else "SELL"
    await update.message.reply_text("Harga *Entry*?", parse_mode="Markdown")
    return CATAT_ENTRY

async def catat_entry(update, context):
    context.user_data["trade"]["entry"] = update.message.text
    await update.message.reply_text("Harga *Stop Loss*?", parse_mode="Markdown")
    return CATAT_SL

async def catat_sl(update, context):
    context.user_data["trade"]["sl"] = update.message.text
    await update.message.reply_text("Harga *Take Profit*?", parse_mode="Markdown")
    return CATAT_TP

async def catat_tp(update, context):
    context.user_data["trade"]["tp"] = update.message.text
    await update.message.reply_text("Harga *Exit*?", parse_mode="Markdown")
    return CATAT_EXIT

async def catat_exit(update, context):
    context.user_data["trade"]["exit"] = update.message.text
    try:
        entry = float(context.user_data["trade"]["entry"])
        exit_ = float(update.message.text)
        arah  = context.user_data["trade"]["arah"]
        pair  = context.user_data["trade"]["pair"]
        m = 100 if "JPY" in pair else (1 if "XAU" in pair else 10000)
        pips = (exit_ - entry) * m if arah == "BUY" else (entry - exit_) * m
        context.user_data["trade"]["pips"]  = round(pips, 1)
        context.user_data["trade"]["hasil"] = "WIN" if pips > 0 else ("LOSS" if pips < 0 else "BE")
    except:
        context.user_data["trade"]["pips"]  = "-"
        context.user_data["trade"]["hasil"] = "-"
    await update.message.reply_text("*Catatan*:\n_Ketik - jika tidak ada_", parse_mode="Markdown")
    return CATAT_CATATAN

async def catat_simpan(update, context):
    context.user_data["trade"]["catatan"] = update.message.text
    trade  = context.user_data["trade"]
    jurnal = baca_jurnal()
    jurnal.append(trade)
    simpan_jurnal(jurnal)
    emoji = "✅" if trade.get("hasil") == "WIN" else ("❌" if trade.get("hasil") == "LOSS" else "➖")
    await update.message.reply_text(
        f"💾 *Trade tersimpan!*\n\n"
        f"Pair  : *{trade['pair']}* | {trade['arah']}\n"
        f"Entry : `{trade['entry']}` → Exit: `{trade['exit']}`\n"
        f"Pips  : `{trade['pips']}`\n"
        f"Hasil : {emoji} *{trade['hasil']}*",
        parse_mode="Markdown",
        reply_markup=MENU_KB)
    return ConversationHandler.END

# ── JURNAL ────────────────────────────────────────────────

async def lihat_jurnal(update, context):
    data = baca_jurnal()
    if not data:
        await update.message.reply_text("📋 Jurnal masih kosong!", reply_markup=MENU_KB)
        return
    teks = "📋 *10 TRADE TERAKHIR*\n\n"
    for t in data[-10:][::-1]:
        e = "✅" if t.get("hasil") == "WIN" else ("❌" if t.get("hasil") == "LOSS" else "➖")
        teks += f"{e} *{t.get('pair','-')}* {t.get('arah','-')} | {t.get('pips','-')} pips | {t.get('tanggal','-')}\n"
    await update.message.reply_text(teks, parse_mode="Markdown", reply_markup=MENU_KB)

# ── STATISTIK ─────────────────────────────────────────────

async def statistik(update, context):
    data = baca_jurnal()
    if not data:
        await update.message.reply_text("📈 Belum ada data.", reply_markup=MENU_KB)
        return
    total  = len(data)
    wins   = sum(1 for t in data if t.get("hasil") == "WIN")
    losses = sum(1 for t in data if t.get("hasil") == "LOSS")
    wr     = wins / total * 100 if total > 0 else 0
    pips   = sum(t.get("pips", 0) for t in data if isinstance(t.get("pips"), (int, float)))
    await update.message.reply_text(
        f"📈 *STATISTIK TRADING*\n\n"
        f"Total Trade : *{total}*\n"
        f"WIN         : *{wins}* ✅\n"
        f"LOSS        : *{losses}* ❌\n"
        f"Win Rate    : *{wr:.1f}%*\n"
        f"Total Pips  : *{pips:.1f}*\n\n"
        f"{'🟢 Performa bagus!' if wr >= 50 else '⚠️ Perlu evaluasi!'}",
        parse_mode="Markdown",
        reply_markup=MENU_KB)

# ── MENU HANDLER ──────────────────────────────────────────

async def menu_handler(update, context):
    t = update.message.text
    if t == "📊 Sinyal":      await sinyal(update, context)
    elif t == "📋 Jurnal":    await lihat_jurnal(update, context)
    elif t == "📈 Statistik": await statistik(update, context)
    elif t == "ℹ Bantuan":   await bantuan(update, context)

# ── MAIN ──────────────────────────────────────────────────

def main():
    TOKEN = os.environ.get("TOKEN", "8811389403:AAFFCGMS13UFOokIkKrH29tr1KKGNZAE_AM")
    app = ApplicationBuilder().token(TOKEN).build()

    # Job auto sinyal terjadwal setiap 60 menit
    app.job_queue.run_repeating(
        auto_sinyal_terjadwal,
        interval=3600,   # 3600 detik = 1 jam
        first=10)        # mulai 10 detik setelah bot aktif

    # Job cek pergerakan signifikan setiap 5 menit
    app.job_queue.run_repeating(
        auto_alert_pergerakan,
        interval=300,    # 300 detik = 5 menit
        first=15)        # mulai 15 detik setelah bot aktif

    conv_lot = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^📐 Lot Size$"), lot_start)],
        states={
            LOT_MODAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, lot_modal)],
            LOT_RISK:  [MessageHandler(filters.TEXT & ~filters.COMMAND, lot_risk)],
            LOT_SL:    [MessageHandler(filters.TEXT & ~filters.COMMAND, lot_hasil)],
        }, fallbacks=[])

    conv_catat = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^🗒 Catat Trade$"), catat_start)],
        states={
            CATAT_PAIR:    [MessageHandler(filters.TEXT & ~filters.COMMAND, catat_pair)],
            CATAT_ARAH:    [MessageHandler(filters.TEXT & ~filters.COMMAND, catat_arah)],
            CATAT_ENTRY:   [MessageHandler(filters.TEXT & ~filters.COMMAND, catat_entry)],
            CATAT_SL:      [MessageHandler(filters.TEXT & ~filters.COMMAND, catat_sl)],
            CATAT_TP:      [MessageHandler(filters.TEXT & ~filters.COMMAND, catat_tp)],
            CATAT_EXIT:    [MessageHandler(filters.TEXT & ~filters.COMMAND, catat_exit)],
            CATAT_CATATAN: [MessageHandler(filters.TEXT & ~filters.COMMAND, catat_simpan)],
        }, fallbacks=[])

    app.add_handler(CommandHandler("start",     start))
    app.add_handler(CommandHandler("sinyal",    sinyal))
    app.add_handler(CommandHandler("jurnal",    lihat_jurnal))
    app.add_handler(CommandHandler("statistik", statistik))
    app.add_handler(conv_lot)
    app.add_handler(conv_catat)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, menu_handler))

    print("🤖 Bot Trading aktif! ✅")
    app.run_polling()

if __name__ == "__main__":
    main()

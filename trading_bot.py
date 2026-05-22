import os
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, ConversationHandler, filters, JobQueue
import json, requests
from datetime import datetime

JOURNAL_FILE  = "jurnal.json"
CHAT_ID       = 5056350311
TWELVE_KEY    = os.environ.get("TWELVE_KEY", "c3e4f0511f6245e693d49a9303d6ee8c")

harga_sebelumnya = {"eurusd": None, "gbpusd": None, "usdjpy": None, "xauusd": None, "btcusd": None}

def baca_jurnal():
    if os.path.exists(JOURNAL_FILE):
        with open(JOURNAL_FILE, "r") as f:
            return json.load(f)
    return []

def simpan_jurnal(data):
    with open(JOURNAL_FILE, "w") as f:
        json.dump(data, f)

# ── AMBIL HARGA REAL TIME (Twelve Data) ───────────────────

def ambil_harga_twelvedata(symbol):
    try:
        url = f"https://api.twelvedata.com/price?symbol={symbol}&apikey={TWELVE_KEY}"
        r   = requests.get(url, timeout=5)
        return float(r.json()["price"])
    except:
        return None

def ambil_historis_twelvedata(symbol, interval="1h", outputsize=50):
    try:
        url = (f"https://api.twelvedata.com/time_series"
               f"?symbol={symbol}&interval={interval}"
               f"&outputsize={outputsize}&apikey={TWELVE_KEY}")
        r    = requests.get(url, timeout=8)
        data = r.json()
        closes = [float(v["close"]) for v in reversed(data["values"])]
        return closes
    except:
        return []

def ambil_harga():
    eurusd = ambil_harga_twelvedata("EUR/USD")
    gbpusd = ambil_harga_twelvedata("GBP/USD")
    usdjpy = ambil_harga_twelvedata("USD/JPY")
    xauusd = ambil_harga_twelvedata("XAU/USD")
    btcusd = ambil_harga_twelvedata("BTC/USD")

    # Fallback BTC ke Binance kalau Twelve Data gagal
    if not btcusd:
        try:
            r      = requests.get("https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT", timeout=5)
            btcusd = round(float(r.json()["price"]), 2)
        except:
            pass

    if eurusd: eurusd = round(eurusd, 5)
    if gbpusd: gbpusd = round(gbpusd, 5)
    if usdjpy: usdjpy = round(usdjpy, 3)
    if xauusd: xauusd = round(xauusd, 2)
    if btcusd: btcusd = round(btcusd, 2)

    return eurusd, gbpusd, usdjpy, xauusd, btcusd

# ── INDIKATOR ─────────────────────────────────────────────

def hitung_rsi(harga_list, period=14):
    if len(harga_list) < period + 1:
        return None
    gains, losses = [], []
    for i in range(1, len(harga_list)):
        diff = harga_list[i] - harga_list[i-1]
        gains.append(max(diff, 0))
        losses.append(max(-diff, 0))
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    if avg_loss == 0:
        return 100
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 2)

def hitung_ma(harga_list, period):
    if len(harga_list) < period:
        return None
    return round(sum(harga_list[-period:]) / period, 5)

def hitung_bollinger(harga_list, period=20):
    if len(harga_list) < period:
        return None, None, None
    data  = harga_list[-period:]
    ma    = sum(data) / period
    std   = (sum((x - ma) ** 2 for x in data) / period) ** 0.5
    return round(ma, 5), round(ma + 2*std, 5), round(ma - 2*std, 5)

def hitung_macd(harga_list):
    if len(harga_list) < 26:
        return None, None, None
    def ema(data, period):
        k = 2 / (period + 1)
        e = data[0]
        for p in data[1:]:
            e = p * k + e * (1 - k)
        return e
    ema12  = ema(harga_list[-26:], 12)
    ema26  = ema(harga_list[-26:], 26)
    macd   = round(ema12 - ema26, 5)
    signal = round(ema(harga_list[-9:], 9), 5) if len(harga_list) >= 9 else None
    hist   = round(macd - signal, 5) if signal else None
    return macd, signal, hist

def hitung_support_resistance(harga_list):
    if len(harga_list) < 10:
        return None, None
    return round(min(harga_list[-20:]), 5), round(max(harga_list[-20:]), 5)

def analisa_sinyal(harga_list, harga_kini):
    rsi              = hitung_rsi(harga_list)
    ma5              = hitung_ma(harga_list, 5)
    ma20             = hitung_ma(harga_list, 20)
    bb_mid, bb_up, bb_low = hitung_bollinger(harga_list)
    macd, signal, hist_macd = hitung_macd(harga_list)
    sup, res         = hitung_support_resistance(harga_list)
    skor, alasan     = 0, []

    if rsi:
        if rsi < 35:   skor += 2; alasan.append(f"RSI oversold ({rsi})")
        elif rsi > 65: skor -= 2; alasan.append(f"RSI overbought ({rsi})")

    if ma5 and ma20:
        if ma5 > ma20: skor += 1; alasan.append("MA5 > MA20 bullish")
        else:          skor -= 1; alasan.append("MA5 < MA20 bearish")

    if bb_low and bb_up:
        if harga_kini <= bb_low: skor += 2; alasan.append("Harga sentuh BB bawah")
        elif harga_kini >= bb_up: skor -= 2; alasan.append("Harga sentuh BB atas")

    if macd and signal:
        if macd > signal:   skor += 1; alasan.append("MACD bullish")
        elif macd < signal: skor -= 1; alasan.append("MACD bearish")

    if   skor >= 3:  sinyal = "BUY 🟢"
    elif skor <= -3: sinyal = "SELL 🔴"
    elif skor > 0:   sinyal = "BUY LEMAH 🟡"
    elif skor < 0:   sinyal = "SELL LEMAH 🟡"
    else:            sinyal = "WAIT ⏳"; alasan.append("Sinyal belum jelas")

    return sinyal, rsi, ma5, ma20, bb_up, bb_low, macd, signal, sup, res, " | ".join(alasan)

# ── BUAT PESAN SINYAL ─────────────────────────────────────

def buat_pesan_sinyal(eurusd, gbpusd, usdjpy, xauusd, btcusd, judul="📊 *HARGA LIVE + ANALISA*"):
    hist_eur = ambil_historis_twelvedata("EUR/USD")
    hist_gbp = ambil_historis_twelvedata("GBP/USD")
    hist_jpy = ambil_historis_twelvedata("USD/JPY")
    hist_xau = ambil_historis_twelvedata("XAU/USD")
    hist_btc = ambil_historis_twelvedata("BTC/USD")

    def blok_pair(nama, harga, hist, sl_jarak, tp_jarak, desimal=5):
        if not harga:
            return f"⚠️ *{nama}* : Gagal ambil harga\n\n"
        if hist:
            sny, rsi, ma5, ma20, bb_up, bb_low, macd, sig, sup, res, alasan = analisa_sinyal(hist, harga)
        else:
            sny, rsi, ma5, ma20, bb_up, bb_low, macd, sig, sup, res, alasan = "WAIT ⏳", "-", "-", "-", "-", "-", "-", "-", "-", "-", "Data tidak tersedia"

        if "BUY" in str(sny):
            sl = round(harga - sl_jarak, desimal)
            tp = round(harga + tp_jarak, desimal)
        elif "SELL" in str(sny):
            sl = round(harga + sl_jarak, desimal)
            tp = round(harga - tp_jarak, desimal)
        else:
            sl = round(harga - sl_jarak, desimal)
            tp = round(harga + tp_jarak, desimal)

        emoji = "🟢" if "BUY" in str(sny) else ("🔴" if "SELL" in str(sny) else "🟡")
        return (
            f"{emoji} *{nama}* : `{harga}`\n"
            f"   SL : `{sl}` | TP : `{tp}`\n"
            f"   Sinyal : *{sny}*\n"
            f"   RSI : `{rsi}` | MA5 : `{ma5}` | MA20 : `{ma20}`\n"
            f"   BB Atas : `{bb_up}` | BB Bawah : `{bb_low}`\n"
            f"   MACD : `{macd}` | Signal : `{sig}`\n"
            f"   Support : `{sup}` | Resistance : `{res}`\n"
            f"   📝 _{alasan}_\n\n"
        )

    return (
        f"{judul}\n"
        f"_{datetime.now().strftime('%d/%m/%Y %H:%M')}_\n\n"
        + blok_pair("EUR/USD", eurusd, hist_eur, 0.0020, 0.0030, 5)
        + blok_pair("GBP/USD", gbpusd, hist_gbp, 0.0020, 0.0030, 5)
        + blok_pair("USD/JPY", usdjpy, hist_jpy, 0.30,   0.40,   3)
        + blok_pair("XAU/USD", xauusd, hist_xau, 10,     15,     2)
        + blok_pair("BTC/USD", btcusd, hist_btc, 500,    800,    2)
        + f"⚠️ _Selalu pasang SL sebelum entry!_"
    )

# ── AUTO JOBS ─────────────────────────────────────────────

async def auto_sinyal_terjadwal(context):
    eurusd, gbpusd, usdjpy, xauusd, btcusd = ambil_harga()
    pesan = buat_pesan_sinyal(eurusd, gbpusd, usdjpy, xauusd, btcusd, judul="🕐 *AUTO SINYAL TERJADWAL*")
    await context.bot.send_message(chat_id=CHAT_ID, text=pesan, parse_mode="Markdown")

async def ringkasan_harian(context):
    data     = baca_jurnal()
    hari_ini = datetime.now().strftime("%d/%m/%Y")
    trade_hari = [t for t in data if t.get("tanggal", "").startswith(hari_ini)]
    if not trade_hari:
        pesan = f"🌅 *SELAMAT PAGI!*\n_{hari_ini}_\n\nBelum ada trade hari ini.\nSemangat trading! 💪"
    else:
        wins   = sum(1 for t in trade_hari if t.get("hasil") == "WIN")
        losses = sum(1 for t in trade_hari if t.get("hasil") == "LOSS")
        pips   = sum(t.get("pips", 0) for t in trade_hari if isinstance(t.get("pips"), (int, float)))
        pesan  = (
            f"🌅 *RINGKASAN HARIAN*\n_{hari_ini}_\n\n"
            f"Total Trade : *{len(trade_hari)}*\n"
            f"WIN         : *{wins}* ✅\n"
            f"LOSS        : *{losses}* ❌\n"
            f"Total Pips  : *{pips:.1f}*\n\n"
            f"{'🟢 Hari yang bagus!' if pips > 0 else '⚠️ Evaluasi strategi!'}"
        )
    eurusd, gbpusd, usdjpy, xauusd, btcusd = ambil_harga()
    sinyal_pagi = buat_pesan_sinyal(eurusd, gbpusd, usdjpy, xauusd, btcusd, judul="📊 *SINYAL PAGI*")
    await context.bot.send_message(chat_id=CHAT_ID, text=pesan, parse_mode="Markdown")
    await context.bot.send_message(chat_id=CHAT_ID, text=sinyal_pagi, parse_mode="Markdown")

async def auto_alert_pergerakan(context):
    global harga_sebelumnya
    eurusd, gbpusd, usdjpy, xauusd, btcusd = ambil_harga()
    hist_eur = ambil_historis_twelvedata("EUR/USD")
    hist_gbp = ambil_historis_twelvedata("GBP/USD")
    hist_jpy = ambil_historis_twelvedata("USD/JPY")
    hist_xau = ambil_historis_twelvedata("XAU/USD")
    hist_btc = ambil_historis_twelvedata("BTC/USD")
    alerts   = []

    def cek_alert(nama, harga, harga_lama, hist, threshold, mult, satuan="pips"):
        if not harga or not harga_lama: return
        s = abs(harga - harga_lama)
        if s >= threshold:
            arah = "⬆️ NAIK" if harga > harga_lama else "⬇️ TURUN"
            alerts.append(f"🚨 *{nama}* {arah}\n   `{harga_lama}` → `{harga}` ({round(s*mult,1)} {satuan})")
        if hist:
            rsi = hitung_rsi(hist)
            if rsi and rsi < 20:  alerts.append(f"⚡ *{nama}* RSI sangat oversold `{rsi}` — Potensi BUY kuat!")
            elif rsi and rsi > 80: alerts.append(f"⚡ *{nama}* RSI sangat overbought `{rsi}` — Potensi SELL kuat!")
            sup, res = hitung_support_resistance(hist)
            if sup and res:
                tol = (res - sup) * 0.02
                if abs(harga - sup) <= tol:   alerts.append(f"📍 *{nama}* Mendekati Support `{sup}`")
                elif abs(harga - res) <= tol: alerts.append(f"📍 *{nama}* Mendekati Resistance `{res}`")

    cek_alert("EUR/USD", eurusd, harga_sebelumnya["eurusd"], hist_eur, 0.0020, 10000)
    cek_alert("GBP/USD", gbpusd, harga_sebelumnya["gbpusd"], hist_gbp, 0.0020, 10000)
    cek_alert("USD/JPY", usdjpy, harga_sebelumnya["usdjpy"], hist_jpy, 0.20,   100)
    cek_alert("XAU/USD", xauusd, harga_sebelumnya["xauusd"], hist_xau, 5.0,    1, "$")
    cek_alert("BTC/USD", btcusd, harga_sebelumnya["btcusd"], hist_btc, 500,    1, "$")

    if alerts:
        pesan = (
            f"⚡ *ALERT TRADING*\n"
            f"_{datetime.now().strftime('%d/%m/%Y %H:%M')}_\n\n"
            + "\n\n".join(alerts)
            + "\n\n⚠️ _Pantau chart sebelum entry!_"
        )
        await context.bot.send_message(chat_id=CHAT_ID, text=pesan, parse_mode="Markdown")

    if eurusd: harga_sebelumnya["eurusd"] = eurusd
    if gbpusd: harga_sebelumnya["gbpusd"] = gbpusd
    if usdjpy: harga_sebelumnya["usdjpy"] = usdjpy
    if xauusd: harga_sebelumnya["xauusd"] = xauusd
    if btcusd: harga_sebelumnya["btcusd"] = btcusd

# ── KEYBOARD ──────────────────────────────────────────────

MENU_KB = ReplyKeyboardMarkup([
    [KeyboardButton("📊 Sinyal"), KeyboardButton("📐 Lot Size")],
    [KeyboardButton("🗒 Catat Trade"), KeyboardButton("📋 Jurnal")],
    [KeyboardButton("📈 Statistik"), KeyboardButton("ℹ Bantuan")],
], resize_keyboard=True)

PAIR_KB = ReplyKeyboardMarkup([
    ["EUR/USD", "GBP/USD"],
    ["USD/JPY", "XAU/USD"],
    ["BTC/USD"], ["❌ Batal"]
], resize_keyboard=True)

ARAH_KB = ReplyKeyboardMarkup([
    ["BUY 🟢", "SELL 🔴"], ["❌ Batal"]
], resize_keyboard=True)

(LOT_MODAL, LOT_RISK, LOT_SL) = range(3)
(CATAT_PAIR, CATAT_ARAH, CATAT_ENTRY, CATAT_SL,
 CATAT_TP, CATAT_EXIT, CATAT_CATATAN) = range(3, 10)

# ── HANDLER ───────────────────────────────────────────────

async def start(update, context):
    await update.message.reply_text(
        "Halo! 👋 Selamat datang di *Bot Trading Forex Scalping* 🤖\n\nPilih menu di bawah:",
        parse_mode="Markdown", reply_markup=MENU_KB)

async def bantuan(update, context):
    await update.message.reply_text(
        "ℹ *PANDUAN BOT*\n\n"
        "📊 *Sinyal* — Harga real time + RSI + MA + BB + MACD + S/R\n"
        "📐 *Lot Size* — Kalkulator lot\n"
        "🗒 *Catat Trade* — Simpan hasil trade\n"
        "📋 *Jurnal* — Lihat trade terakhir\n"
        "📈 *Statistik* — Win rate & total pips\n\n"
        "🕐 *Auto Sinyal* — Kirim otomatis setiap 1 jam\n"
        "🌅 *Ringkasan Harian* — Kirim otomatis setiap pagi jam 08.00\n"
        "⚡ *Auto Alert* — Notif pergerakan, RSI ekstrem & S/R\n\n"
        "⚠️ _Bukan saran investasi._",
        parse_mode="Markdown", reply_markup=MENU_KB)

async def sinyal(update, context):
    await update.message.reply_text("⏳ Mengambil harga & analisa...")
    eurusd, gbpusd, usdjpy, xauusd, btcusd = ambil_harga()
    pesan = buat_pesan_sinyal(eurusd, gbpusd, usdjpy, xauusd, btcusd)
    await update.message.reply_text(pesan, parse_mode="Markdown", reply_markup=MENU_KB)

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
        sl       = float(update.message.text)
        modal    = context.user_data["modal"]
        risk     = context.user_data["risk"]
        risk_usd = modal * risk / 100
        lot      = round((risk_usd / (sl * 10)) / 0.01) * 0.01
        await update.message.reply_text(
            f"📐 *HASIL KALKULASI*\n\n"
            f"Modal    : `${modal:,.0f}`\n"
            f"Risk     : `{risk}%` = `${risk_usd:.2f}`\n"
            f"SL       : `{sl} pips`\n"
            f"――――――――――――\n"
            f"Lot Size : *{lot:.2f} lot*",
            parse_mode="Markdown", reply_markup=MENU_KB)
        return ConversationHandler.END
    except:
        await update.message.reply_text("❌ Masukkan angka. Contoh: 10")
        return LOT_SL

async def catat_start(update, context):
    context.user_data["trade"] = {"tanggal": datetime.now().strftime("%d/%m/%Y %H:%M")}
    await update.message.reply_text("🗒 *CATAT TRADE*\n\nPilih pair:",
        parse_mode="Markdown", reply_markup=PAIR_KB)
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
        m     = 100 if "JPY" in pair else (1 if "XAU" in pair or "BTC" in pair else 10000)
        pips  = (exit_ - entry) * m if arah == "BUY" else (entry - exit_) * m
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
        parse_mode="Markdown", reply_markup=MENU_KB)
    return ConversationHandler.END

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
        parse_mode="Markdown", reply_markup=MENU_KB)

async def menu_handler(update, context):
    t = update.message.text
    if t == "📊 Sinyal":      await sinyal(update, context)
    elif t == "📋 Jurnal":    await lihat_jurnal(update, context)
    elif t == "📈 Statistik": await statistik(update, context)
    elif t == "ℹ Bantuan":   await bantuan(update, context)

# ── MAIN ──────────────────────────────────────────────────

def main():
    TOKEN = os.environ.get("TOKEN", "8811389403:AAFFCGMS13UFOokIkKrH29tr1KKGNZAE_AM")
    app   = ApplicationBuilder().token(TOKEN).build()

    app.job_queue.run_repeating(auto_sinyal_terjadwal, interval=3600, first=10)
    app.job_queue.run_repeating(auto_alert_pergerakan, interval=300,  first=15)
    app.job_queue.run_daily(ringkasan_harian, time=datetime.strptime("08:00", "%H:%M").time())

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
